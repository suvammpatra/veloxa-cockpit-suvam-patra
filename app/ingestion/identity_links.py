"""Linking name forms in exports to people (ARCHITECTURE.md 5, Resolve stage; DECISIONS.md 21).

A Jira initial, a git author email or a PagerDuty first name becomes a link to a
person only through an Alias row that names the rule and the record behind it.
The rules are exact; there is no fuzzy matching:

  git_email       equals one employee's Keka work email                      -> H
  jira_initials   first and last initials match exactly one known person     -> M
  pagerduty_name  equals one person's full name (H) or exact first name (M)

Two or more candidates give an ambiguous row; none gives an unresolved row.
Ambiguous and unresolved rows carry no target, so nothing is merged. Rows are
never edited: when a later file makes a name resolvable, a new row is added,
released when the later record was, so earlier points in time still see
"unresolved". Reviewed mappings (e.g. a GitHub no-reply address) are loaded
as curated rows from a file the user supplies (see load_curated).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alias, Commit, Evidence, Incident, Person, Ticket
from app.services.identity import normalize


@dataclass
class Derived:
    status: str
    person: Person | None
    confidence: str
    note: str


def _cite(session: Session, person: Person) -> str:
    if person.source_evidence_id:
        ev = session.get(Evidence, person.source_evidence_id)
        if ev is not None:
            return f"{ev.evidence_key} ({ev.source.filename}, {ev.locator})"
    return f"person record {person.emp_id or person.full_name}"


def _initials(name: str) -> str:
    parts = [p for p in normalize(name).replace(".", " ").split(" ") if p]
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else ""


def derive(session: Session, text: str, kind: str) -> Derived:
    people = session.scalars(select(Person)).all()
    key = normalize(text)
    if kind == "git_email":
        hits = [p for p in people if p.work_email and normalize(p.work_email) == key]
        rule, conf = "author email equals the Keka work email of", "H"
    elif kind == "jira_initials":
        hits = [p for p in people if _initials(p.full_name) == text.strip().upper()]
        rule, conf = "initials match exactly one known person,", "M"
    else:
        hits = [p for p in people if normalize(p.full_name) == key]
        rule, conf = "equals the full name of", "H"
        if not hits and " " not in key:
            hits = [p for p in people if normalize(p.full_name).split(" ")[0] == key]
            rule, conf = "exact first name; only one known person has it:", "M"
    if len(hits) == 1:
        p = hits[0]
        return Derived("resolved", p, conf, f"Rule: {rule} {p.full_name} ({p.emp_id or p.worker_type}), "
                                            f"{_cite(session, p)}.")
    if len(hits) > 1:
        names = ", ".join(sorted(p.full_name for p in hits))
        return Derived("ambiguous", None, "L", f"Rule found {len(hits)} candidates ({names}); not linked.")
    return Derived("unresolved", None, "L", "No known person matches this name form; not linked.")


def _ensure_alias(session: Session, text: str, kind: str, d: Derived, released: datetime) -> Alias:
    key = normalize(text)
    target_id = d.person.id if d.person else None
    existing = session.scalar(select(Alias).where(
        Alias.normalized == key, Alias.kind == kind, Alias.status == d.status,
        (Alias.target_person_id == target_id) if target_id else Alias.target_person_id.is_(None)))
    if existing is not None:
        return existing
    rel = released if d.person is None else max(released, d.person.released_on)
    alias = Alias(alias_text=text.strip(), normalized=key, kind=kind,
                  target_type="person" if d.person else None, target_person_id=target_id,
                  status=d.status, confidence=d.confidence, evidence_note=d.note, origin="rule",
                  released_on=rel)
    session.add(alias)
    session.flush()
    return alias


def _has_rule_row(session: Session, text: str, kind: str, d: Derived) -> bool:
    target_id = d.person.id if d.person else None
    return session.scalar(select(Alias.id).where(
        Alias.normalized == normalize(text), Alias.kind == kind, Alias.origin == "rule",
        Alias.status == d.status,
        (Alias.target_person_id == target_id) if target_id else Alias.target_person_id.is_(None))) is not None


def _current(session: Session, text: str, kind: str) -> Alias | None:
    """Curated rows outrank rule rows; a resolved row outranks an unresolved one."""
    rows = session.scalars(select(Alias).where(Alias.normalized == normalize(text), Alias.kind == kind)).all()
    for origin in ("curated", "rule"):
        mine = [a for a in rows if a.origin == origin]
        if any(a.status == "ambiguous" for a in mine):
            return next(a for a in mine if a.status == "ambiguous")
        resolved = [a for a in mine if a.status == "resolved"]
        if resolved:
            return max(resolved, key=lambda a: a.released_on)
        if mine:
            return mine[0]  # unresolved
    return None


_TARGETS = (
    (Ticket, "assignee_alias", "assignee_person_id", "jira_initials"),
    (Incident, "responder_alias", "responder_person_id", "pagerduty_name"),
    (Commit, "author_email", "author_person_id", "git_email"),
)


def link_identities(session: Session) -> dict[str, int]:
    """Derive alias rows for every name form in the typed facts and set each fact's link
    to the best current alias (curated before rule; ambiguous or unresolved means no link).

    Idempotent. The stored person link is a convenience for the current state;
    point-in-time questions resolve names through Alias rows and their released_on.
    """
    stats = {"linked": 0, "ambiguous": 0, "unresolved": 0}
    for model, alias_col, person_col, kind in _TARGETS:
        rows = session.scalars(select(model).where(getattr(model, alias_col).is_not(None))).all()
        by_text: dict[str, list] = {}
        for r in rows:
            by_text.setdefault(getattr(r, alias_col), []).append(r)
        for text, facts in by_text.items():
            released = min(f.released_on for f in facts)
            d = derive(session, text, kind)
            if not _has_rule_row(session, text, kind, d):
                _ensure_alias(session, text, kind, d, released)
            best = _current(session, text, kind)
            target = best.target_person_id if best is not None and best.status == "resolved" else None
            for f in facts:
                setattr(f, person_col, target)
            if target:
                stats["linked"] += len(facts)
            else:
                state = "ambiguous" if best is not None and best.status == "ambiguous" else "unresolved"
                stats[state] += len(facts)
    session.flush()
    return stats


def _release(value: str, line: int) -> datetime:
    """A date means 10:00 IST that day, the release time (DECISIONS.md 2)."""
    from datetime import date

    from app.temporal import release_timestamp, resolve_as_of
    try:
        return release_timestamp(date.fromisoformat(value)) if len(value) == 10 else resolve_as_of(value)
    except ValueError as exc:
        raise ValueError(f"Line {line}: released_on {value!r} is not a date.") from exc


CURATED_COLUMNS = ("alias_text", "kind", "status", "target_emp_id", "confidence", "evidence_note", "released_on")


def load_curated(session: Session, path: Path) -> int:
    """Load reviewed alias rows from a CSV the user supplies. Every row needs an
    evidence note; a resolved row needs a target Emp ID that exists."""
    added = 0
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in CURATED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Alias file is missing columns: {', '.join(missing)}")
        for line, row in enumerate(reader, start=2):
            status = row["status"].strip()
            note = row["evidence_note"].strip()
            if not note:
                raise ValueError(f"Line {line}: evidence_note is required.")
            target = None
            if status == "resolved":
                target = session.scalar(select(Person).where(Person.emp_id == row["target_emp_id"].strip()))
                if target is None:
                    raise ValueError(f"Line {line}: Emp ID {row['target_emp_id']!r} is not a known person.")
            elif status not in ("ambiguous", "unresolved"):
                raise ValueError(f"Line {line}: status must be resolved, ambiguous or unresolved.")
            elif row["target_emp_id"].strip():
                raise ValueError(f"Line {line}: only a resolved row may name a target.")
            released = _release(row["released_on"].strip(), line)
            key, kind = normalize(row["alias_text"]), row["kind"].strip()
            same = session.scalar(select(Alias.id).where(
                Alias.origin == "curated", Alias.normalized == key, Alias.kind == kind, Alias.status == status,
                Alias.released_on == released,
                (Alias.target_person_id == target.id) if target else Alias.target_person_id.is_(None)))
            if same is not None:
                continue  # loading the same file twice adds nothing
            session.add(Alias(alias_text=row["alias_text"].strip(), normalized=key,
                              kind=kind, target_type="person" if target else None,
                              target_person_id=target.id if target else None, status=status,
                              confidence=row["confidence"].strip() or "M", evidence_note=note,
                              origin="curated", released_on=released))
            added += 1
    session.flush()
    return added
