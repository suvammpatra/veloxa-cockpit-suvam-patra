"""Name resolution by evidence, never by similarity (DECISIONS.md 21).

Matching is exact after normalising case and spaces. "Sneha" and "Snehal" are
different strings, so they can never meet. A first name alone resolves only
when exactly one known person has that exact first name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alias, Person
from app.repositories.temporal import released_by
from app.temporal import TimeContext


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


@dataclass
class Resolution:
    status: str                     # resolved | ambiguous | unresolved
    person: Person | None = None
    confidence: str | None = None   # H, M or L when resolved
    method: str | None = None       # alias | exact_name | email | emp_id | first_name
    note: str | None = None
    candidates: list[Person] = field(default_factory=list)


def resolve_person(session: Session, text: str, ctx: TimeContext) -> Resolution:
    key = normalize(text)
    cutoff = ctx.release_cutoff

    aliases = session.scalars(
        released_by(select(Alias).where(Alias.normalized == key), Alias, cutoff)
    ).all()
    if any(a.status == "ambiguous" for a in aliases):
        note = next(a.evidence_note for a in aliases if a.status == "ambiguous")
        return Resolution(status="ambiguous", note=note)
    targets = {a.target_person_id: a for a in aliases if a.status == "resolved" and a.target_person_id}
    if len(targets) > 1:
        return Resolution(status="ambiguous", note="Several records map this name to different people.",
                          candidates=[a.target_person for a in targets.values()])
    if len(targets) == 1:
        a = next(iter(targets.values()))
        return Resolution(status="resolved", person=a.target_person, confidence=a.confidence,
                          method="alias", note=a.evidence_note)
    if any(a.status == "unresolved" for a in aliases):
        return Resolution(status="unresolved", note=aliases[0].evidence_note)

    people = session.scalars(released_by(select(Person), Person, cutoff)).all()
    for attr, method in (("emp_id", "emp_id"), ("work_email", "email"), ("full_name", "exact_name")):
        hits = [p for p in people if getattr(p, attr) and normalize(getattr(p, attr)) == key]
        if len(hits) == 1:
            return Resolution(status="resolved", person=hits[0], confidence="H", method=method)

    if " " not in key:
        hits = [p for p in people if normalize(p.full_name).split(" ")[0] == key]
        if len(hits) == 1:
            return Resolution(status="resolved", person=hits[0], confidence="M", method="first_name",
                              note="Matched on an exact first name; only one known person has it.")
        if len(hits) > 1:
            return Resolution(status="ambiguous", candidates=hits,
                              note="More than one known person has this first name.")

    return Resolution(status="unresolved", note="No record links this name to a known person.")
