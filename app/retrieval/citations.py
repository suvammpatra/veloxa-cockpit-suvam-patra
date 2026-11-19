"""Citations: stable evidence keys, and checks that a cited key is real and usable.

An evidence key (E001 ...) is assigned once at ingestion and never reused. A
citation is built only from a stored Evidence row and its SourceRecord, so a
citation cannot point at anything that was not ingested.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Evidence
from app.retrieval import policy
from app.temporal import Mode, TimeContext

KEY_PATTERN = re.compile(r"\bE\d{3,}\b")


@dataclass(frozen=True)
class Citation:
    evidence_key: str
    source_key: str
    filename: str
    relative_path: str | None
    locator: str
    system: str | None
    trust_rung: int | None
    confidence: str
    released_on: datetime
    exported_on: datetime | None
    date_as_written: str | None
    source_sha256: str

    @property
    def label(self) -> str:
        """Short form for an answer: E012 (Employee_Master.xlsx, Employees!row 9)."""
        return f"{self.evidence_key} ({self.filename}, {self.locator})"


def cite(ev: Evidence) -> Citation:
    src = ev.source
    return Citation(evidence_key=ev.evidence_key, source_key=src.source_key, filename=src.filename,
                    relative_path=src.relative_path, locator=ev.locator, system=src.system,
                    trust_rung=src.trust_rung, confidence=ev.confidence, released_on=ev.released_on,
                    exported_on=ev.exported_on, date_as_written=ev.date_as_written,
                    source_sha256=src.sha256)


@dataclass(frozen=True)
class CitationCheck:
    evidence_key: str
    ok: bool
    reason: str | None = None   # unknown_key | not_released_yet | not_recorded_yet | restricted |
                                # purpose_limited | source_failed | role_copy | role_reference | quote_not_found |
                                # withheld (disclosure rules, decisions 28 and 29)
    citation: Citation | None = None


def extract_keys(text: str) -> list[str]:
    """Evidence keys mentioned in a piece of text, in order, without repeats."""
    seen: list[str] = []
    for k in KEY_PATTERN.findall(text):
        if k not in seen:
            seen.append(k)
    return seen


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def validate(session: Session, keys: list[str], ctx: TimeContext, *, purpose: str | None = None,
             include_restricted: bool = False, roles: tuple[str, ...] = policy.DEFAULT_ROLES,
             quotes: dict[str, str] | None = None) -> list[CitationCheck]:
    """Check each cited key: it exists, it could be known at the time frame, the
    policy allows it, and any quoted words really appear in it."""
    quotes = quotes or {}
    rows = {e.evidence_key: e for e in session.scalars(select(Evidence).where(Evidence.evidence_key.in_(keys)))}
    checks = []
    for key in keys:
        ev = rows.get(key)
        if ev is None:
            checks.append(CitationCheck(key, False, "unknown_key"))
            continue
        reason = None
        if ev.released_on > ctx.release_cutoff:
            reason = "not_released_yet"
        elif ctx.mode is Mode.RECORDED and (ev.exported_on is None or ev.exported_on > ctx.as_of):
            reason = "not_recorded_yet"
        else:
            reason = policy.allowed(ev.source, include_restricted=include_restricted, purpose=purpose, roles=roles)
        if reason is None:
            # Disclosure rules (decisions 28, 29): a record with nothing disclosable cannot be cited,
            # and a quote may come only from text that is not withheld.
            from app.retrieval import disclosure
            r = disclosure.redact(session, ev.content, ctx)
            if r.fully_withheld:
                reason = "withheld"
            elif key in quotes:
                if _norm(quotes[key]) in _norm(r.text):
                    pass
                elif _norm(quotes[key]) in _norm(ev.content):
                    reason = "withheld"
                else:
                    reason = "quote_not_found"
        checks.append(CitationCheck(key, reason is None, reason, cite(ev) if reason is None else None))
    return checks
