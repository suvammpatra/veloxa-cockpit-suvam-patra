"""The ingestion pipeline: Register, Parse, Extract, Resolve (ARCHITECTURE.md 5).

For each file:
  1. Register. Hash the bytes (SHA-256). A hash already in the register is a
     duplicate and nothing is written. Templates and unsupported types are
     skipped and logged.
  2. Parse into citable units (app.ingestion.parsers).
  3. Date. released_on is 10:00 IST on the release day given to the command
     (DECISIONS.md 2). exported_on comes from the file itself where it says so;
     otherwise from the --exported-on value or a README in the folder that
     states an export date; otherwise it stays empty and a warning is logged.
     Transcripts never get one (ARCHITECTURE.md 4).
  4. Store one Evidence row per unit, then typed facts by rule (app.ingestion.typed).
  5. Commit the file on its own. A failure rolls back that file only and is
     recorded as a failed SourceRecord with its error.
After all files, name forms are linked to people (app.ingestion.identity_links).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ingestion import parsers, profiles, typed
from app.ingestion.dates import find_export_date, first_full_date, parse_instant
from app.ingestion.identity_links import link_identities
from app.models import Evidence, IngestionError, SourceRecord
from app.privacy.payroll import PayrollStore
from app.temporal import release_timestamp

log = logging.getLogger(__name__)


@dataclass
class FileResult:
    relative_path: str
    status: str                     # ingested | partial | failed | duplicate | skipped
    source_key: str | None = None
    units: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    errors: int = 0
    warnings: int = 0
    message: str | None = None


@dataclass
class IngestReport:
    files: list[FileResult] = field(default_factory=list)
    identities: dict[str, int] = field(default_factory=dict)

    def by_status(self, status: str) -> list[FileResult]:
        return [f for f in self.files if f.status == status]

    @property
    def ok(self) -> bool:
        return not self.by_status("failed")


@dataclass
class _Candidate:
    path: Path
    relative: str
    readme_export: tuple[date, str] | None


class Ingestor:
    def __init__(self, session_factory: sessionmaker[Session], *, release_day: date,
                 payroll_store: PayrollStore | None = None, default_exported_on: date | None = None):
        self.session_factory = session_factory
        self.released = release_timestamp(release_day)
        self.payroll_store = payroll_store
        self.default_exported_on = default_exported_on

    # ------------------------------------------------------------ public

    def ingest(self, paths: list[Path]) -> IngestReport:
        report = IngestReport()
        for cand in self._collect(paths):
            result = self._ingest_one(cand)
            log.info("%s: %s %s", cand.relative, result.status, result.source_key or "")
            report.files.append(result)
        with self.session_factory() as s:
            report.identities = link_identities(s)
            s.commit()
        return report

    # ------------------------------------------------------------ discovery

    def _collect(self, paths: list[Path]) -> list[_Candidate]:
        out = []
        for root in paths:
            if root.is_dir():
                files = sorted(p for p in root.rglob("*") if p.is_file())
                readmes = {p.parent: find_export_date(p.read_text(encoding="utf-8", errors="replace"))
                           for p in files if p.name.lower() == "readme.txt"}
                for f in files:
                    out.append(_Candidate(f, f.relative_to(root).as_posix(), _readme_for(f, root, readmes)))
            elif root.is_file():
                out.append(_Candidate(root, root.name, None))
            else:
                out.append(_Candidate(root, root.name, None))
        return out

    # ------------------------------------------------------------ one file

    def _ingest_one(self, cand: _Candidate) -> FileResult:
        rel = cand.relative
        name = cand.path.name
        if not cand.path.exists():
            return FileResult(rel, "failed", message="File not found.")
        if name.startswith((".", "~$")):
            return FileResult(rel, "skipped", message="Hidden or temporary file.")
        profile = profiles.match(rel)
        if profile.role == "template":
            self._log_only(name, rel, profile.note)
            return FileResult(rel, "skipped", message=profile.note)
        if cand.path.suffix.lower() not in parsers.SUPPORTED:
            msg = f"Unsupported file type {cand.path.suffix or '(none)'}; not ingested."
            self._log_only(name, rel, msg)
            return FileResult(rel, "skipped", message=msg)

        data = cand.path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        with self.session_factory() as s:
            dup = s.scalar(select(SourceRecord).where(SourceRecord.sha256 == sha))
            if dup is not None:
                return FileResult(rel, "duplicate", source_key=dup.source_key,
                                  message=f"Same content as {dup.source_key} ({dup.filename}); nothing written.")
            try:
                parsed = parsers.parse(cand.path, data)
            except parsers.ParseFailure as exc:
                return self._record_failure(s, cand, profile, sha, len(data), str(exc))
            try:
                return self._store(s, cand, profile, sha, len(data), parsed)
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
                log.exception("Ingestion of %s failed", rel)
                s.rollback()
                return self._record_failure(s, cand, profile, sha, len(data),
                                            f"Extraction failed: {type(exc).__name__}: {exc}")

    def _store(self, s: Session, cand, profile, sha, size, parsed: parsers.ParsedFile) -> FileResult:
        exported, basis, date_text = self._exported_on(cand, profile, parsed)
        src = SourceRecord(
            source_key=_next_source_key(s), filename=cand.path.name, relative_path=cand.relative,
            file_type=cand.path.suffix.lower().lstrip("."), system=profile.system, trust_rung=profile.trust_rung,
            role=profile.role, access="restricted" if profile.restricted_columns else "open",
            sha256=sha, size_bytes=size, released_on=self.released, exported_on=exported,
            exported_basis=basis, note=_note(profile, parsed), status="ingested")
        s.add(src)
        s.flush()

        problems = list(parsed.problems)
        if profile.name == "unknown":
            problems.append((None, "warning", profile.note))
        if exported is None:
            problems.append((None, "warning", basis))
        earlier = s.scalars(select(SourceRecord).where(SourceRecord.filename == src.filename,
                                                       SourceRecord.id != src.id)).all()
        if earlier:
            problems.append((None, "warning", "A different file with this name was ingested before as "
                             + ", ".join(e.source_key for e in earlier) + "; both are kept."))

        conf = profiles.confidence_for(profile.trust_rung)
        next_ev = _next_evidence_number(s)
        evidence: dict[str, Evidence] = {}
        for unit in parsed.units:
            fields, content = unit.fields, unit.content
            if fields is not None and profile.restricted_columns:
                fields = {k: v for k, v in fields.items() if not profiles.is_restricted(profile, k)}
                content = parsers.row_content(fields)
            ev = Evidence(evidence_key=f"E{next_ev:03d}", source_record_id=src.id, locator=unit.locator,
                          content=content, confidence=conf, released_on=self.released, exported_on=exported,
                          date_as_written=(date_text if unit is parsed.units[0] else None),
                          fields_json=json.dumps(fields, ensure_ascii=False, default=str) if fields else None)
            next_ev += 1
            s.add(ev)
            evidence[unit.locator] = ev
        s.flush()

        ctx = typed.ExtractContext(session=s, source=src, released=self.released, file_exported=exported,
                                   evidence=evidence, titles=parsed.titles)
        extractor = typed.EXTRACTORS.get(profile.kind)
        if extractor is not None and profile.role == "evidence":
            extractor(ctx, parsed.units)
            s.flush()
        problems.extend(ctx.problems)

        for loc, severity, msg in problems:
            s.add(IngestionError(source_record_id=src.id, filename=src.filename, locator=loc,
                                 severity=severity, message=msg))
        n_err = sum(1 for p in problems if p[1] == "error")
        src.status = "partial" if n_err else "ingested"
        s.commit()

        if ctx.payroll_entries:
            if self.payroll_store is None:
                self._mark_failed(s, src, "Payroll rows found but no payroll store is configured; amounts not stored.")
                n_err += 1
            else:
                self.payroll_store.add_entries(ctx.payroll_entries)

        return FileResult(cand.relative, src.status, source_key=src.source_key, units=len(evidence),
                          counts=ctx.counts, errors=n_err, warnings=len(problems) - n_err)

    # ------------------------------------------------------------ dates

    def _exported_on(self, cand, profile, parsed) -> tuple[datetime | None, str, str | None]:
        """(exported_on, basis, date as written). Specific file evidence wins over defaults."""
        if profile.kind == "transcript":
            return None, "Unknown: transcripts carry no recording date (ARCHITECTURE.md 4).", None
        if profile.kind == "email":
            raw = parsed.headers.get("Date")
            when = _email_date(raw)
            if when is None:
                return None, f"No readable Date header ({raw!r}); exported_on left empty.", raw
            return when, "Email Date header.", raw
        for sheet, title in parsed.titles.items():
            found = find_export_date(title)
            if found:
                return _midnight(found[0]), f"Title line of sheet {sheet}: '{found[1]}'.", None
        if profile.kind == "document" and profile.role == "evidence" and parsed.units:
            found = first_full_date(parsed.units[0].content)
            if found:
                return _midnight(found[0]), f"First full date on {parsed.units[0].locator}: '{found[1]}'.", found[1]
        if self.default_exported_on is not None:
            return _midnight(self.default_exported_on), "Given to the ingestion command (--exported-on).", None
        if cand.readme_export is not None:
            d, words = cand.readme_export
            return _midnight(d), f"README.txt in the ingested folder: '{words}'.", None
        return None, "No export date found in the file or given; exported_on left empty.", None

    # ------------------------------------------------------------ failures

    def _record_failure(self, s: Session, cand, profile, sha, size, message) -> FileResult:
        src = SourceRecord(source_key=_next_source_key(s), filename=cand.path.name, relative_path=cand.relative,
                           file_type=cand.path.suffix.lower().lstrip("."), system=profile.system,
                           trust_rung=profile.trust_rung, role=profile.role if profile.role != "template" else "reference",
                           access="restricted" if profile.restricted_columns else "open",
                           sha256=sha, size_bytes=size, released_on=self.released, status="failed")
        s.add(src)
        s.flush()
        s.add(IngestionError(source_record_id=src.id, filename=src.filename, severity="error", message=message))
        s.commit()
        return FileResult(cand.relative, "failed", source_key=src.source_key, errors=1, message=message)

    def _mark_failed(self, s: Session, src: SourceRecord, message: str) -> None:
        src.status = "failed"
        s.add(IngestionError(source_record_id=src.id, filename=src.filename, severity="error", message=message))
        s.commit()

    def _log_only(self, filename: str, rel: str, message: str) -> None:
        with self.session_factory() as s:
            s.add(IngestionError(source_record_id=None, filename=filename, locator=rel,
                                 severity="warning", message=message))
            s.commit()


# ---------------------------------------------------------------- helpers

def _readme_for(f: Path, root: Path, readmes: dict) -> tuple[date, str] | None:
    """The nearest README.txt at or above the file's folder, within the ingested root."""
    d = f.parent
    while True:
        if readmes.get(d):
            return readmes[d]
        if d == root or root not in d.parents:
            return None
        d = d.parent


def _email_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parse_instant(parsedate_to_datetime(raw))
    except (TypeError, ValueError):
        return None


def _midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def _note(profile, parsed) -> str | None:
    parts = [profile.note] if profile.note else []
    parts += [f"{sheet}: {title}" for sheet, title in parsed.titles.items()]
    return " | ".join(parts) or None


def _next_source_key(s: Session) -> str:
    keys = s.scalars(select(SourceRecord.source_key)).all()
    n = max((int(m.group(1)) for k in keys if (m := re.fullmatch(r"SRC-(\d+)", k))), default=0)
    return f"SRC-{n + 1:03d}"


def _next_evidence_number(s: Session) -> int:
    keys = s.scalars(select(Evidence.evidence_key)).all()
    return max((int(m.group(1)) for k in keys if (m := re.fullmatch(r"E(\d+)", k))), default=0) + 1
