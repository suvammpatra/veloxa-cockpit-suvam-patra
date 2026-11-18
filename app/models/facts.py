"""Typed facts from structured exports. Each row points back to its evidence."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TemporalMixin
from app.models.sources import Evidence


class FinancialTxn(TemporalMixin, Base):
    """A GL line. Amounts in paise to avoid float error. Never payroll detail."""

    __tablename__ = "financial_txn"

    id: Mapped[int] = mapped_column(primary_key=True)
    voucher: Mapped[str] = mapped_column(String(32))
    ref: Mapped[str] = mapped_column(String(64))
    txn_date: Mapped[date] = mapped_column(Date, index=True)
    vendor: Mapped[str] = mapped_column(String(128))
    cost_centre: Mapped[str] = mapped_column(String(32), index=True)
    amount_paise: Mapped[int] = mapped_column(Integer)
    narration: Mapped[str | None] = mapped_column(Text)
    entered_by: Mapped[str | None] = mapped_column(String(32))
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"))

    evidence: Mapped[Evidence] = relationship()

    __table_args__ = (UniqueConstraint("voucher", "ref", name="uq_voucher_ref"),)


class Ticket(TemporalMixin, Base):
    """A Jira ticket. Status is as of the export snapshot; there is no history."""

    __tablename__ = "ticket"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True)
    project_key: Mapped[str] = mapped_column(String(16), index=True)
    issue_type: Mapped[str | None] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    epic_key: Mapped[str | None] = mapped_column(String(32), index=True)
    assignee_alias: Mapped[str | None] = mapped_column(String(32))  # initials as exported
    assignee_person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"))
    story_points: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    created: Mapped[date | None] = mapped_column(Date)
    resolved: Mapped[date | None] = mapped_column(Date)
    fix_version: Mapped[str | None] = mapped_column(String(64))
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"))

    evidence: Mapped[Evidence] = relationship()


class Incident(TemporalMixin, Base):
    """A PagerDuty incident. Times converted from UTC to IST on ingestion."""

    __tablename__ = "incident"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True)
    severity: Mapped[str] = mapped_column(String(8), index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    service: Mapped[str | None] = mapped_column(String(64))
    responder_alias: Mapped[str | None] = mapped_column(String(64))
    responder_person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"))
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"))

    evidence: Mapped[Evidence] = relationship()


class Commit(TemporalMixin, Base):
    """A git commit. Commit times are never turned into a per-person signal (DECISIONS.md 23)."""

    __tablename__ = "commit"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha: Mapped[str] = mapped_column(String(64), unique=True)
    author_email: Mapped[str] = mapped_column(String(128), index=True)
    author_person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"))
    committed_at: Mapped[datetime] = mapped_column(DateTime)
    repo: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str | None] = mapped_column(Text)
    files_changed: Mapped[int | None] = mapped_column(Integer)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"))
