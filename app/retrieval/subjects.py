"""Which evidence is about a person or a department, at a point in time.

A person's evidence is:
  * rows that created their record, memberships and reporting lines;
  * tickets, incidents and commits whose name form resolves to them through an
    Alias row released by the cutoff (so a link made by a later file is not
    used for an earlier date);
  * text that mentions their full name, Emp ID, work email, a name form that
    resolves to them, or their first name when exactly one known person has
    it and no reviewed row marks that name as ambiguous or unresolved.
Matching is by whole FTS5 tokens, so "Sneha" never matches "Snehal".
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import (Alias, Commit, Department, DepartmentMembership, Incident, Person, ReportingLine,
                        Ticket)
from app.repositories.temporal import released_by
from app.retrieval.fts import quote
from app.services.identity import normalize, resolve_person
from app.services.org import department_members
from app.temporal import TimeContext


def fts_ids(session: Session, phrase: str) -> set[int]:
    return set(session.scalars(text("SELECT rowid FROM evidence_fts WHERE evidence_fts MATCH :q"),
                               {"q": quote(phrase)}).all())


def person_evidence_ids(session: Session, person: Person, ctx: TimeContext) -> set[int]:
    cutoff = ctx.release_cutoff
    ids: set[int] = set()
    if person.source_evidence_id:
        ids.add(person.source_evidence_id)
    for model in (DepartmentMembership, ReportingLine):
        ids |= {i for i in session.scalars(select(model.source_evidence_id).where(model.person_id == person.id)) if i}

    for model, alias_col in ((Ticket, Ticket.assignee_alias), (Incident, Incident.responder_alias),
                             (Commit, Commit.author_email)):
        for name_form in set(session.scalars(select(alias_col).where(alias_col.is_not(None)))):
            r = resolve_person(session, name_form, ctx)
            if r.status == "resolved" and r.person.id == person.id:
                ids |= set(session.scalars(select(model.evidence_id).where(alias_col == name_form)))

    phrases = {person.full_name}
    phrases |= {v for v in (person.emp_id, person.work_email) if v}
    aliases = session.scalars(released_by(select(Alias), Alias, cutoff)).all()
    phrases |= {a.alias_text for a in aliases if a.status == "resolved" and a.target_person_id == person.id}
    first = normalize(person.full_name).split(" ")[0]
    people = session.scalars(released_by(select(Person), Person, cutoff)).all()
    blocked = {a.normalized for a in aliases if a.status != "resolved"}
    if sum(normalize(p.full_name).split(" ")[0] == first for p in people) == 1 and first not in blocked:
        phrases.add(first)
    for phrase in phrases:
        ids |= fts_ids(session, phrase)
    return ids


class UnknownDepartment(ValueError):
    pass


def department_evidence_ids(session: Session, code_or_name: str, ctx: TimeContext) -> tuple[set[int], str | None]:
    """(evidence ids, warning). Members are taken on the as-of date (DECISIONS.md 20). When
    membership on that date is unknown, only text naming the department is used, and a
    warning says so."""
    key = code_or_name.strip()
    dept = session.scalar(select(Department).where((Department.code == key.upper()) | (Department.name == key)))
    if dept is None:
        raise UnknownDepartment(f"No department {code_or_name!r} is known.")
    ids = fts_ids(session, dept.name)
    members = department_members(session, dept.code, ctx)
    if members is None:
        return ids, (f"Who was in {dept.name} on {ctx.as_of:%d %b %Y} cannot be established; "
                     "only records naming the department are used.")
    for pid in members:
        ids |= person_evidence_ids(session, session.get(Person, pid), ctx)
    return ids, None
