"""Org questions answered as of a date (DECISIONS.md 17-22)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Department, DepartmentLine, DepartmentMembership, Person, Position, PositionHolder, ReportingLine
from app.repositories.temporal import pending, released_by, valid_at
from app.temporal import TimeContext


@dataclass
class ManagerAnswer:
    status: str                      # known | unknown
    manager: str | None = None       # a person's name or a position title
    note: str | None = None
    pending_changes: list[str] = field(default_factory=list)
    source_evidence_id: int | None = None     # the record behind the line (or the earliest one, if unknown)
    pending_evidence_ids: list[int] = field(default_factory=list)


def _employed_at(person: Person, at: datetime) -> bool:
    d = at.date()
    if person.join_date and person.join_date > d:
        return False
    return not (person.exit_date and person.exit_date < d)


def position_holder(session: Session, code: str, ctx: TimeContext) -> Person | None:
    """The confirmed holder of a role at the as-of date, or None if vacant."""
    stmt = valid_at(
        select(PositionHolder).join(Position).where(Position.code == code),
        PositionHolder, ctx.as_of, release_cutoff=ctx.release_cutoff,
    )
    row = session.scalars(stmt).first()
    return row.person if row else None


def manager_as_of(session: Session, person: Person, ctx: TimeContext) -> ManagerAnswer:
    lines = session.scalars(
        valid_at(select(ReportingLine).where(ReportingLine.person_id == person.id),
                 ReportingLine, ctx.as_of, release_cutoff=ctx.release_cutoff)
    ).all()
    pend = session.scalars(
        pending(select(ReportingLine).where(ReportingLine.person_id == person.id),
                ReportingLine, release_cutoff=ctx.release_cutoff)
    ).all()
    pending_changes = [_describe_pending(line) for line in pend]

    if not lines:
        earliest = session.scalars(
            released_by(select(ReportingLine).where(ReportingLine.person_id == person.id,
                                                    ReportingLine.status == "confirmed"),
                        ReportingLine, ctx.release_cutoff)
            .order_by(ReportingLine.valid_from)
        ).first()
        note = "No record shows this person's manager on that date."
        if earliest is not None and earliest.valid_from and not earliest.start_exact:
            note = (f"The earliest record of this reporting line is "
                    f"{earliest.valid_from:%d %b %Y}; before that it is unknown.")
        return ManagerAnswer(status="unknown", note=note, pending_changes=pending_changes,
                             source_evidence_id=earliest.source_evidence_id if earliest else None,
                             pending_evidence_ids=[p.source_evidence_id for p in pend if p.source_evidence_id])

    line = lines[0]
    if line.manager_person is not None:
        label = line.manager_person.full_name
    else:
        holder = position_holder(session, line.manager_position.code, ctx)
        label = f"{line.manager_position.title} ({holder.full_name if holder else 'vacant'})"
    return ManagerAnswer(status="known", manager=label, pending_changes=pending_changes,
                         source_evidence_id=line.source_evidence_id,
                         pending_evidence_ids=[p.source_evidence_id for p in pend if p.source_evidence_id])


def department_reports_to(session: Session, dept_code: str, ctx: TimeContext) -> tuple[str | None, list[str]]:
    base = select(DepartmentLine).join(Department).where(Department.code == dept_code)
    current = session.scalars(valid_at(base, DepartmentLine, ctx.as_of, release_cutoff=ctx.release_cutoff)).first()
    pend = session.scalars(pending(base, DepartmentLine, release_cutoff=ctx.release_cutoff)).all()
    label = current.reports_to.title if current else None
    return label, [_describe_pending(p) for p in pend]


def _describe_pending(row) -> str:
    target = getattr(row, "reports_to", None) or getattr(row, "manager_position", None)
    who = target.title if target is not None else (row.manager_person.full_name if row.manager_person else "?")
    when = f"from {row.valid_from:%d %b %Y}" if row.valid_from else "effective date not confirmed"
    return f"Announced: reports to {who}, {when}"


def department_members(session: Session, dept_code: str, ctx: TimeContext,
                       *, employees_only: bool = True) -> set[int] | None:
    """Person ids in the department at the as-of date.

    Returns None when membership cannot be established: someone employed at
    that date has no confirmed membership row covering it (DECISIONS.md 17, 20).
    """
    at = ctx.as_of
    people = session.scalars(
        released_by(select(Person), Person, ctx.release_cutoff)
    ).all()
    if employees_only:
        people = [p for p in people if p.worker_type == "employee"]
    employed = [p for p in people if _employed_at(p, at)]

    rows = session.scalars(
        valid_at(select(DepartmentMembership), DepartmentMembership, at,
                 release_cutoff=ctx.release_cutoff)
    ).all()
    dept_of = {r.person_id: r.department.code for r in rows}
    if any(p.id not in dept_of for p in employed):
        return None
    return {p.id for p in employed if dept_of[p.id] == dept_code}


@dataclass
class Headcount:
    employees: int
    contractors: list[str]
    note: str = "Employees from Keka; contractors are listed separately and not counted (DECISIONS.md 22)."


def headcount(session: Session, ctx: TimeContext) -> Headcount:
    people = session.scalars(released_by(select(Person), Person, ctx.release_cutoff)).all()
    employees = [p for p in people if p.worker_type == "employee" and _employed_at(p, ctx.as_of)]
    contractors = sorted(p.full_name for p in people if p.worker_type == "contractor")
    return Headcount(employees=len(employees), contractors=contractors)
