"""The reviewed conflict registry (ARCHITECTURE.md 7 and 15.5; DECISIONS.md 1).

Conflicts documented in ARCHITECTURE.md are loaded from a reviewed JSON file
the user supplies. Each side names a source file and the words that locate its
record. Rules, all strict:

  * Every side must match exactly one ingested evidence row: the file was
    ingested, the row holds every match term (whole words, case and spacing
    ignored), and the row's date equals the date given (or both are undated).
    A row from a failed, copied, reference or restricted source is never used.
  * A conflict loads whole or not at all. A missing, ambiguous or misdated
    reference rejects that conflict, says why, and writes nothing for it.
  * Nothing is fabricated: no evidence row is ever created here.
  * Nothing is resolved automatically. Status comes only from the file, and a
    resolved status needs a resolution text. Loading never changes a stored
    conflict: the same content is skipped, different content is rejected.
  * A conflict is visible from 10:00 IST on its noted_on date, and only when
    every side is visible at the time frame (app.retrieval.search.conflicts_for).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conflict, ConflictSide, Evidence, SourceRecord
from app.temporal import release_timestamp

REQUIRED = ("conflict_key", "title", "status", "noted_on", "documented_in", "confidence", "sides")
SIDE_REQUIRED = ("side", "file", "match", "summary")


@dataclass
class LoadResult:
    loaded: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    rejected: dict[str, list[str]] = field(default_factory=dict)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def contains(content: str, term: str) -> bool:
    """`term` appears in `content` as whole words, ignoring case and spacing."""
    return re.search(rf"(?<!\w){re.escape(_norm(term))}(?!\w)", _norm(content)) is not None


def _check_shape(data) -> list[dict]:
    if not isinstance(data, dict) or not isinstance(data.get("conflicts"), list):
        raise ValueError('The file must hold {"conflicts": [...]}.')
    seen = set()
    for i, c in enumerate(data["conflicts"], 1):
        where = f"Conflict {i}"
        if not isinstance(c, dict):
            raise ValueError(f"{where}: not an object.")
        missing = [k for k in REQUIRED if c.get(k) in (None, "", [])]
        if missing:
            raise ValueError(f"{where}: missing {', '.join(missing)}.")
        key = c["conflict_key"]
        where = f"Conflict {key}"
        if not re.fullmatch(r"C-[A-Z0-9][A-Z0-9-]*", key) or key.startswith("C-RX-"):
            raise ValueError(f"{where}: keys look like C-ATLAS-DONE; C-RX- keys belong to ingestion.")
        if key in seen:
            raise ValueError(f"{where}: the key appears twice in the file.")
        seen.add(key)
        if c["status"] not in ("open", "resolved"):
            raise ValueError(f"{where}: status must be open or resolved.")
        if c["status"] == "resolved" and not (c.get("resolution") or "").strip():
            raise ValueError(f"{where}: a resolved conflict needs its resolution text.")
        if c["confidence"] not in ("H", "M", "L"):
            raise ValueError(f"{where}: confidence must be H, M or L.")
        try:
            date.fromisoformat(c["noted_on"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{where}: noted_on must be a date (YYYY-MM-DD).") from exc
        sides = c["sides"]
        if not isinstance(sides, list) or len({s.get("side") for s in sides if isinstance(s, dict)}) < 2:
            raise ValueError(f"{where}: needs records on at least two sides.")
        for s in sides:
            missing = [k for k in SIDE_REQUIRED if s.get(k) in (None, "", [])]
            if missing:
                raise ValueError(f"{where}: a side is missing {', '.join(missing)}.")
            if not re.fullmatch(r"[A-Z]", s["side"]):
                raise ValueError(f"{where}: side must be one capital letter.")
            terms = s["match"] if isinstance(s["match"], list) else [s["match"]]
            if not all(isinstance(t, str) and t.strip() for t in terms):
                raise ValueError(f"{where}: match terms must be non-empty text.")
            if s.get("date") is not None:
                try:
                    date.fromisoformat(s["date"])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{where}: a side date must be YYYY-MM-DD or null.") from exc
    return data["conflicts"]


def find_side(session: Session, side: dict) -> tuple[Evidence | None, str | None]:
    """The one evidence row a side refers to, or (None, why not)."""
    terms = side["match"] if isinstance(side["match"], list) else [side["match"]]
    label = f"side {side['side']} ({side['file']}, {terms})"
    sources = session.scalars(select(SourceRecord).where(SourceRecord.filename == side["file"])).all()
    if not sources:
        return None, f"{label}: the file has not been ingested."
    usable = [s for s in sources if s.status != "failed" and s.role == "evidence" and s.access == "open"]
    if not usable:
        return None, f"{label}: the file is a failed, copied, reference or restricted source."
    rows = session.scalars(select(Evidence).where(Evidence.source_record_id.in_([s.id for s in usable]))
                           .order_by(Evidence.id)).all()
    if side.get("locator"):
        rows = [e for e in rows if e.locator.startswith(side["locator"])]
    hits = [e for e in rows if all(contains(e.content, t) for t in terms)]
    if not hits:
        return None, f"{label}: no ingested record holds these words."
    if len(hits) > 1:
        return None, (f"{label}: {len(hits)} records hold these words "
                      f"({', '.join(e.evidence_key for e in hits[:6])}); make the match more specific.")
    ev = hits[0]
    want = side.get("date")
    have = ev.exported_on.date().isoformat() if ev.exported_on else None
    if want != have:
        return None, f"{label}: the record is dated {have or 'unknown'}, the file says {want or 'undated'}."
    return ev, None


def _signature(c: Conflict) -> tuple:
    return (c.title, c.status, c.resolution, c.rule, c.confidence, c.would_overturn, c.released_on,
            c.documented_in, sorted((s.side, s.evidence_id, s.summary) for s in c.sides))


def load_reviewed_conflicts(session: Session, path: Path) -> LoadResult:
    entries = _check_shape(json.loads(Path(path).read_text(encoding="utf-8")))
    result = LoadResult()
    for c in entries:
        key = c["conflict_key"]
        found, problems = [], []
        for s in c["sides"]:
            ev, why = find_side(session, s)
            if why:
                problems.append(why)
            else:
                found.append((s, ev))
        if problems:
            result.rejected[key] = problems
            continue
        if len({ev.id for _, ev in found}) < len(found):
            result.rejected[key] = ["Two sides point at the same record."]
            continue
        new = Conflict(conflict_key=key, title=c["title"], status=c["status"], resolution=c.get("resolution"),
                       rule=c.get("rule") or "Not resolved automatically (DECISIONS.md 1). Status changes only "
                                             "in the reviewed conflict file.",
                       confidence=c["confidence"], would_overturn=c.get("would_overturn"), origin="reviewed",
                       released_on=release_timestamp(date.fromisoformat(c["noted_on"])),
                       documented_in=c["documented_in"])
        new.sides = [ConflictSide(evidence_id=ev.id, side=s["side"], summary=s["summary"],
                                  reference=json.dumps({"file": s["file"], "match": s["match"],
                                                        "locator": s.get("locator"), "date": s.get("date")}))
                     for s, ev in found]
        existing = session.scalar(select(Conflict).where(Conflict.conflict_key == key))
        if existing is not None:
            if _signature(existing) == _signature(new):
                result.unchanged.append(key)
            else:
                result.rejected[key] = ["A conflict with this key is already stored with different content. "
                                        "Stored conflicts are not overwritten (ARCHITECTURE.md 7)."]
            continue
        session.add(new)
        session.flush()
        result.loaded.append(key)
    return result
