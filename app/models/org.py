"""People, departments, roles and effective-dated reporting (DECISIONS.md 17-22)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import ValidityMixin

STATUS_CHECK = "status IN ('confirmed','announced','withdrawn')"


class Department(Base):
    __tablename__ = "department"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)  # stable key, e.g. MKT
    name: Mapped[str] = mapped_column(String(64), unique=True)  # as in Keka, e.g. Marketing


class Person(Base):
    """Employees carry an Emp ID; contractors do not (DECISIONS.md 22)."""

    __tablename__ = "person"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_id: Mapped[str | None] = mapped_column(String(16), unique=True)  # VX007; None for contractors
    full_name: Mapped[str] = mapped_column(String(128))
    worker_type: Mapped[str] = mapped_column(String(16), default="employee")
    work_email: Mapped[str | None] = mapped_column(String(128), unique=True)
    title: Mapped[str | None] = mapped_column(String(128))
    location: Mapped[str | None] = mapped_column(String(64))
    join_date: Mapped[date | None] = mapped_column(Date)
    exit_date: Mapped[date | None] = mapped_column(Date)
    employment_status: Mapped[str | None] = mapped_column(String(32))  # as written in Keka
    note: Mapped[str | None] = mapped_column(Text)  # e.g. "identity inferred, M"
    source_evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id"))
    released_on: Mapped[datetime] = mapped_column(DateTime)  # when I first learned of them

    memberships: Mapped[list[DepartmentMembership]] = relationship(back_populates="person")

    __table_args__ = (
        CheckConstraint("worker_type IN ('employee','contractor')", name="ck_worker_type"),
        CheckConstraint(
            "(worker_type = 'employee' AND emp_id IS NOT NULL) OR "
            "(worker_type = 'contractor' AND emp_id IS NULL)",
            name="ck_emp_id_matches_worker_type",
        ),
    )


class DepartmentMembership(ValidityMixin, Base):
    __tablename__ = "department_membership"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"), index=True)
    source_evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id"))

    person: Mapped[Person] = relationship(back_populates="memberships")
    department: Mapped[Department] = relationship()

    __table_args__ = (CheckConstraint(STATUS_CHECK, name="ck_membership_status"),)


class Position(Base):
    """A role that exists apart from its holder, e.g. CRO (vacant) (DECISIONS.md 19)."""

    __tablename__ = "position"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)  # CEO, CRO
    title: Mapped[str] = mapped_column(String(128))


class PositionHolder(ValidityMixin, Base):
    __tablename__ = "position_holder"

    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("position.id"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"))
    source_evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id"))

    position: Mapped[Position] = relationship()
    person: Mapped[Person] = relationship()

    __table_args__ = (CheckConstraint(STATUS_CHECK, name="ck_holder_status"),)


class ReportingLine(ValidityMixin, Base):
    """Person -> manager (a person or a position). Never overwritten; closed and replaced."""

    __tablename__ = "reporting_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"), index=True)
    manager_person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"))
    manager_position_id: Mapped[int | None] = mapped_column(ForeignKey("position.id"))
    source_evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id"))

    person: Mapped[Person] = relationship(foreign_keys=[person_id])
    manager_person: Mapped[Person | None] = relationship(foreign_keys=[manager_person_id])
    manager_position: Mapped[Position | None] = relationship()

    __table_args__ = (
        CheckConstraint(STATUS_CHECK, name="ck_line_status"),
        CheckConstraint(
            "(manager_person_id IS NULL) + (manager_position_id IS NULL) = 1",
            name="ck_one_manager",
        ),
    )


class DepartmentLine(ValidityMixin, Base):
    """Which leader a department sits under, e.g. Marketing -> CRO (announced)."""

    __tablename__ = "department_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"), index=True)
    reports_to_position_id: Mapped[int] = mapped_column(ForeignKey("position.id"))
    source_evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id"))
    note: Mapped[str | None] = mapped_column(Text)

    department: Mapped[Department] = relationship()
    reports_to: Mapped[Position] = relationship()

    __table_args__ = (CheckConstraint(STATUS_CHECK, name="ck_deptline_status"),)


class Alias(Base):
    """A name form found in a source, mapped to an entity only with evidence (DECISIONS.md 21).

    status: resolved | ambiguous | unresolved. Ambiguous and unresolved rows carry
    no target, so nothing can silently merge two people.
    """

    __tablename__ = "alias"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias_text: Mapped[str] = mapped_column(String(128), index=True)
    normalized: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # transcript_name, git_email, jira_initials, vendor, tool
    target_type: Mapped[str | None] = mapped_column(String(16))  # person, vendor, tool, project
    target_person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"))
    target_label: Mapped[str | None] = mapped_column(String(128))  # for non-person targets
    status: Mapped[str] = mapped_column(String(16), default="resolved")
    confidence: Mapped[str] = mapped_column(String(1), default="M")
    evidence_note: Mapped[str] = mapped_column(Text)  # the record that supports the mapping
    origin: Mapped[str] = mapped_column(String(8), default="curated")  # rule | curated
    released_on: Mapped[datetime] = mapped_column(DateTime)

    target_person: Mapped[Person | None] = relationship()

    __table_args__ = (
        CheckConstraint("status IN ('resolved','ambiguous','unresolved')", name="ck_alias_status"),
        CheckConstraint("confidence IN ('H','M','L')", name="ck_alias_conf"),
        CheckConstraint(
            "status = 'resolved' OR (target_person_id IS NULL AND target_label IS NULL)",
            name="ck_unresolved_has_no_target",
        ),
    )


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(16), unique=True)  # ATLAS
    name: Mapped[str] = mapped_column(String(128))
    note: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
