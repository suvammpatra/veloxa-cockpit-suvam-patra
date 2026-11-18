"""Evidence search (ARCHITECTURE.md 6, 7, 9 and 11).

search() returns only stored Evidence rows, each with a citation built from
its row and source. In order:

  1. Validate the request; bad input raises SearchError, never a crash.
  2. Full-text match with FTS5 (bm25), or no text match if only filters are given.
  3. Filter in SQL: point-in-time (repositories.temporal.visible), policy
     (retrieval.policy), source, system, file type, trust rung, date range.
  4. Person and department filters, resolved at the as-of date. An ambiguous or
     unknown person returns no evidence and says why.
  5. Rank: bm25, then trust rung (1 first), then evidence key. Deterministic.
  6. Collapse duplicates: rows with the same text keep one representative
     (best rung, earliest release) and list the others.
  7. Attach conflicts: any stored Conflict with a side among the hits is
     returned with all sides visible at the time frame. A conflict whose other
     side was not yet visible is not shown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.models import Conflict, ConflictSide, Evidence, SourceRecord
from app.repositories.temporal import visible
from app.retrieval import fts, policy
from app.retrieval.citations import Citation, cite
from app.retrieval.subjects import UnknownDepartment, department_evidence_ids, person_evidence_ids
from app.services.identity import resolve_person
from app.temporal import TimeContext

MAX_QUERY_CHARS = 500
MAX_LIMIT = 100


class SearchError(ValueError):
    """The request cannot be run as given. The message is safe to show."""


@dataclass
class Filters:
    person: str | None = None
    department: str | None = None
    source_keys: tuple[str, ...] = ()
    systems: tuple[str, ...] = ()
    file_types: tuple[str, ...] = ()
    max_trust_rung: int | None = None     # 3 keeps rungs 1-3
    date_from: date | None = None          # on what the evidence describes
    date_to: date | None = None
    roles: tuple[str, ...] = policy.DEFAULT_ROLES
    include_restricted: bool = False
    purpose: str | None = None


@dataclass
class Hit:
    citation: Citation
    content: str
    snippet: str | None
    score: float | None
    duplicates: list[str] = field(default_factory=list)  # evidence keys with the same text
    via_conflict: bool = False                            # returned because it is a side of a hit's conflict


@dataclass
class ConflictRef:
    conflict_key: str
    title: str
    status: str
    resolution: str | None
    rule: str | None
    sides: list[tuple[str, str, str]]  # (side, evidence key, summary)
    origin: str = "rule"               # rule (ingestion) | reviewed (conflict file)
    confidence: str | None = None
    would_overturn: str | None = None
    documented_in: str | None = None
    noted_on: datetime | None = None
    quotes: dict[str, str] = field(default_factory=dict)  # evidence key -> exact words that locate the side


@dataclass
class SearchResult:
    status: str                 # ok | no_evidence | ambiguous_person | unknown_person
    hits: list[Hit] = field(default_factory=list)
    conflicts: list[ConflictRef] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)  # names, for an ambiguous person
    total_matches: int = 0
    as_of: datetime | None = None
    mode: str | None = None


def search(session: Session, query: str | None, ctx: TimeContext, filters: Filters | None = None, *,
           limit: int = 10, all_terms: bool = False) -> SearchResult:
    f = filters or Filters()
    _validate(query, f, limit)
    result = SearchResult(status="ok", as_of=ctx.as_of, mode=ctx.mode.value)

    # 2. text match
    scores: dict[int, float] | None = None
    snippets: dict[int, str] = {}
    if query and query.strip():
        result.terms = fts.terms(query)
        if not result.terms:
            raise SearchError("The question has no searchable words.")
        rows = session.execute(text(
            "SELECT rowid, bm25(evidence_fts, 1.0, 0.2) AS score, "
            "snippet(evidence_fts, 0, '[', ']', ' ... ', 16) AS snip "
            "FROM evidence_fts WHERE evidence_fts MATCH :q"),
            {"q": fts.match_expression(result.terms, all_terms=all_terms)}).all()
        scores = {r.rowid: r.score for r in rows}
        snippets = {r.rowid: r.snip for r in rows}

    # 4. subject filters, as sets of evidence ids
    subject_ids: set[int] | None = None
    if f.person:
        r = resolve_person(session, f.person, ctx)
        if r.status == "ambiguous":
            result.status = "ambiguous_person"
            result.candidates = sorted(p.full_name for p in r.candidates)
            result.warnings.append(f"{f.person!r} could be more than one person; no evidence returned. {r.note or ''}".strip())
            return result
        if r.status != "resolved":
            result.status = "unknown_person"
            result.warnings.append(f"{f.person!r} does not match a known person at this date. {r.note or ''}".strip())
            return result
        if r.confidence != "H":
            result.warnings.append(f"{f.person!r} was matched to {r.person.full_name} at confidence "
                                   f"{r.confidence}: {r.note}")
        subject_ids = person_evidence_ids(session, r.person, ctx)
    if f.department:
        try:
            dept_ids, warning = department_evidence_ids(session, f.department, ctx)
        except UnknownDepartment as exc:
            raise SearchError(str(exc)) from exc
        if warning:
            result.warnings.append(warning)
        subject_ids = dept_ids if subject_ids is None else subject_ids & dept_ids

    # 3. SQL filters
    stmt = select(Evidence).join(SourceRecord, Evidence.source_record_id == SourceRecord.id)
    stmt = visible(stmt, Evidence, ctx)
    stmt = policy.apply(stmt, include_restricted=f.include_restricted, purpose=f.purpose, roles=f.roles)
    if scores is not None:
        stmt = stmt.where(Evidence.id.in_(scores))
    if subject_ids is not None:
        stmt = stmt.where(Evidence.id.in_(subject_ids))
    if f.source_keys:
        stmt = stmt.where(SourceRecord.source_key.in_(f.source_keys))
    if f.systems:
        stmt = stmt.where(SourceRecord.system.in_(f.systems))
    if f.file_types:
        stmt = stmt.where(SourceRecord.file_type.in_([t.lower().lstrip(".") for t in f.file_types]))
    if f.max_trust_rung is not None:
        stmt = stmt.where(SourceRecord.trust_rung.is_not(None), SourceRecord.trust_rung <= f.max_trust_rung)
    if f.date_from or f.date_to:
        start = func.coalesce(Evidence.as_of_start, Evidence.exported_on)
        end = func.coalesce(Evidence.as_of_end, Evidence.as_of_start, Evidence.exported_on)
        undated = session.scalar(select(func.count()).select_from(
            stmt.where(start.is_(None)).subquery()))
        if undated:
            result.warnings.append(f"{undated} matching record(s) have no date and were left out of the date range.")
        stmt = stmt.where(start.is_not(None))
        if f.date_to:
            stmt = stmt.where(start <= datetime.combine(f.date_to, time(23, 59, 59)))
        if f.date_from:
            stmt = stmt.where(end >= datetime.combine(f.date_from, time.min))
    rows = session.scalars(stmt).all()

    # 5. rank
    def rank(ev: Evidence):
        return (scores.get(ev.id, 0.0) if scores else 0.0, ev.source.trust_rung or 6,
                int(ev.evidence_key[1:]))
    rows.sort(key=rank)

    # 6. collapse duplicates
    groups: dict[str, list[Evidence]] = {}
    for ev in rows:
        groups.setdefault(_dedup_key(ev.content), []).append(ev)
    ordered = []
    for group in groups.values():
        best = min(group, key=lambda e: (e.source.trust_rung or 6, e.released_on, e.id))
        hit = Hit(citation=cite(best), content=best.content, snippet=snippets.get(best.id),
                  score=scores.get(best.id) if scores else None,
                  duplicates=[e.evidence_key for e in group if e is not best])
        ordered.append((rank(group[0]), hit, best.id))
    ordered.sort(key=lambda t: t[0])
    result.total_matches = len(ordered)
    result.hits = [h for _, h, _ in ordered[:limit]]
    hit_ids = {i for _, _, i in ordered[:limit]}

    # 7. conflicts
    _attach_conflicts(session, ctx, f, result, hit_ids)

    if not result.hits:
        result.status = "no_evidence"
        result.warnings.append("No ingested evidence matches this search at this date.")
    return result


def get_evidence(session: Session, key: str, ctx: TimeContext, *, purpose: str | None = None,
                 include_restricted: bool = False) -> Hit | None:
    """One evidence row by key, if it exists and may be used at this time frame."""
    if not re.fullmatch(r"E\d{3,}", key or ""):
        raise SearchError("An evidence key looks like E001.")
    stmt = select(Evidence).join(SourceRecord, Evidence.source_record_id == SourceRecord.id) \
        .where(Evidence.evidence_key == key)
    stmt = policy.apply(visible(stmt, Evidence, ctx), include_restricted=include_restricted, purpose=purpose,
                        roles=("evidence", "copy", "reference"))
    ev = session.scalar(stmt)
    return None if ev is None else Hit(citation=cite(ev), content=ev.content, snippet=None, score=None)


# ---------------------------------------------------------------- helpers

def _validate(query: str | None, f: Filters, limit: int) -> None:
    if query is not None and len(query) > MAX_QUERY_CHARS:
        raise SearchError(f"The search is longer than {MAX_QUERY_CHARS} characters.")
    if not (1 <= limit <= MAX_LIMIT):
        raise SearchError(f"limit must be between 1 and {MAX_LIMIT}.")
    if not (query and query.strip()) and not any((f.person, f.department, f.source_keys, f.systems,
                                                   f.file_types, f.date_from, f.date_to)):
        raise SearchError("Give search words or at least one filter.")
    if f.date_from and f.date_to and f.date_from > f.date_to:
        raise SearchError("date_from is after date_to.")
    if f.max_trust_rung is not None and not (1 <= f.max_trust_rung <= 5):
        raise SearchError("max_trust_rung must be between 1 and 5.")
    unknown_roles = set(f.roles) - {"evidence", "copy", "reference"}
    if unknown_roles or not f.roles:
        raise SearchError("roles must be some of: evidence, copy, reference.")


def _dedup_key(content: str) -> str:
    return re.sub(r"\s+", " ", content).strip().casefold()


def conflicts_for(session: Session, ctx: TimeContext, evidence_ids, *, include_restricted: bool = False,
                  purpose: str | None = None) -> list[tuple[ConflictRef, dict[int, Evidence]]]:
    """Stored conflicts with a side among `evidence_ids`, each with its side rows.

    A conflict is returned only when it was noted by the release cutoff, and every
    side is visible at the time frame and allowed by policy; otherwise it did not
    exist yet (or cannot be shown) at that time."""
    ids = set(evidence_ids or ())
    if not ids:
        return []
    conflict_ids = set(session.scalars(select(ConflictSide.conflict_id).where(ConflictSide.evidence_id.in_(ids))))
    out = []
    stmt = select(Conflict).where(Conflict.id.in_(conflict_ids),
                                  or_(Conflict.released_on.is_(None), Conflict.released_on <= ctx.release_cutoff))
    for c in session.scalars(stmt.order_by(Conflict.conflict_key)):
        side_ids = [s.evidence_id for s in c.sides]
        stmt = select(Evidence).join(SourceRecord, Evidence.source_record_id == SourceRecord.id) \
            .where(Evidence.id.in_(side_ids))
        stmt = policy.apply(visible(stmt, Evidence, ctx), include_restricted=include_restricted,
                            purpose=purpose, roles=("evidence", "copy", "reference"))
        usable = {e.id: e for e in session.scalars(stmt)}
        if len(usable) < len(side_ids):
            continue  # not every side was known (or usable) at this time frame
        ref = ConflictRef(conflict_key=c.conflict_key, title=c.title, status=c.status, resolution=c.resolution,
                          rule=c.rule, sides=[(s.side, usable[s.evidence_id].evidence_key, s.summary)
                                              for s in sorted(c.sides, key=lambda s: (s.side, s.id))],
                          origin=c.origin, confidence=c.confidence, would_overturn=c.would_overturn,
                          documented_in=c.documented_in, noted_on=c.released_on,
                          quotes={usable[s.evidence_id].evidence_key: q for s in c.sides
                                  if (q := _side_quote(s, usable[s.evidence_id]))})
        out.append((ref, {s.evidence_id: usable[s.evidence_id] for s in c.sides}))
    return out


def _side_quote(side: ConflictSide, ev: Evidence) -> str | None:
    """For a reviewed side: the sentence (or table cell) of the record that holds the first
    match term, as an exact substring of the record. None for ingestion conflicts."""
    if not side.reference:
        return None
    import json
    terms = json.loads(side.reference).get("match")
    term = (terms[0] if isinstance(terms, list) else terms) or ""
    for m in re.finditer(r"[^.!?\n;]+[.!?]?", ev.content):
        piece = m.group(0).strip()
        if re.search(re.escape(term).replace(r"\ ", r"\s+"), piece, re.I):
            return piece[:240].strip()
    return None


def _attach_conflicts(session: Session, ctx: TimeContext, f: Filters, result: SearchResult,
                      hit_ids: set[int]) -> None:
    shown = {h.citation.evidence_key for h in result.hits}
    for ref, sides in conflicts_for(session, ctx, hit_ids, include_restricted=f.include_restricted,
                                    purpose=f.purpose):
        result.conflicts.append(ref)
        for ev in sides.values():
            if ev.evidence_key not in shown:
                result.hits.append(Hit(citation=cite(ev), content=ev.content, snippet=None, score=None,
                                       via_conflict=True))
                shown.add(ev.evidence_key)


__all__ = ["Filters", "Hit", "ConflictRef", "SearchResult", "SearchError", "search", "get_evidence",
           "conflicts_for"]
