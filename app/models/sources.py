"""Where every fact comes from: source files, evidence excerpts, claims, conflicts."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TemporalMixin

CONFIDENCE = ("H", "M", "L")


class SourceRecord(Base):
    """One ingested file (ARCHITECTURE.md section 5, Register)."""

    __tablename__ = "source_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(16), unique=True)  # SRC-001
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(16))   # xlsx, pdf, docx, eml, csv, txt
    system: Mapped[str | None] = mapped_column(String(64))  # Zoho Books, Keka, Jira, MeetNotes AI...
    trust_rung: Mapped[int | None] = mapped_column(Integer)  # 1 (best) .. 5 (transcripts)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    released_on: Mapped[datetime] = mapped_column(DateTime, index=True)
    exported_on: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="ingested")  # ingested | partial | failed
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # Provenance (Phase 3). relative_path is relative to the folder given to the
    # ingestion command, never an absolute path on the machine that ran it.
    relative_path: Mapped[str | None] = mapped_column(String(512))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16), default="evidence")  # evidence | copy | reference
    access: Mapped[str] = mapped_column(String(16), default="open")  # open | restricted (payroll)
    exported_basis: Mapped[str | None] = mapped_column(String(128))  # where exported_on came from
    note: Mapped[str | None] = mapped_column(Text)

    evidence: Mapped[list[Evidence]] = relationship(back_populates="source")
    errors: Mapped[list[IngestionError]] = relationship(back_populates="source")

    __table_args__ = (
        CheckConstraint("trust_rung IS NULL OR trust_rung BETWEEN 1 AND 5", name="ck_rung"),
        CheckConstraint("status IN ('ingested','partial','failed')", name="ck_source_status"),
        CheckConstraint("role IN ('evidence','copy','reference')", name="ck_source_role"),
        CheckConstraint("access IN ('open','restricted')", name="ck_source_access"),
    )


class IngestionError(Base):
    """Nothing is silently discarded: every failed file, row or page is logged."""

    __tablename__ = "ingestion_error"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_record_id: Mapped[int | None] = mapped_column(ForeignKey("source_record.id"))
    filename: Mapped[str] = mapped_column(String(255))
    locator: Mapped[str | None] = mapped_column(String(128))
    severity: Mapped[str] = mapped_column(String(8), default="error")  # error | warning
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    source: Mapped[SourceRecord | None] = relationship(back_populates="errors")


class Evidence(TemporalMixin, Base):
    """One citable excerpt: a row, page, paragraph or email (ARCHITECTURE.md section 6)."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_key: Mapped[str] = mapped_column(String(16), unique=True)  # E001, never reused
    source_record_id: Mapped[int] = mapped_column(ForeignKey("source_record.id"), index=True)
    locator: Mapped[str] = mapped_column(String(128))   # e.g. "Issues!row 14", "page 1", "body"
    content: Mapped[str] = mapped_column(Text)
    date_as_written: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[str] = mapped_column(String(1), default="M")
    fields_json: Mapped[str | None] = mapped_column(Text)  # a table row's cells, by header

    source: Mapped[SourceRecord] = relationship(back_populates="evidence")

    __table_args__ = (
        UniqueConstraint("source_record_id", "locator", name="uq_evidence_locator"),
        CheckConstraint("confidence IN ('H','M','L')", name="ck_evidence_conf"),
    )


class Claim(TemporalMixin, Base):
    """A structured statement taken from evidence: subject, attribute, value."""

    __tablename__ = "claim"

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), index=True)
    subject_type: Mapped[str] = mapped_column(String(32))   # person, project, department, company
    subject_key: Mapped[str] = mapped_column(String(64), index=True)  # VX007, ATLAS, ENG, VELOXA
    attribute: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(32))
    extractor: Mapped[str] = mapped_column(String(8), default="rule")  # rule | llm
    confidence: Mapped[str] = mapped_column(String(1), default="M")

    evidence: Mapped[Evidence] = relationship()

    __table_args__ = (
        CheckConstraint("extractor IN ('rule','llm')", name="ck_extractor"),
        CheckConstraint("confidence IN ('H','M','L')", name="ck_claim_conf"),
    )


class Conflict(Base):
    """Two or more records that disagree. Stored, never silently resolved (DECISIONS.md 1)."""

    __tablename__ = "conflict"

    id: Mapped[int] = mapped_column(primary_key=True)
    conflict_key: Mapped[str] = mapped_column(String(32), unique=True)  # C-ATLAS-DONE
    title: Mapped[str] = mapped_column(String(255))
    resolution: Mapped[str | None] = mapped_column(Text)
    rule: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(1), default="M")
    would_overturn: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | resolved
    # Phase 5 follow-up: where the conflict came from and when it was noted (point-in-time).
    origin: Mapped[str] = mapped_column(String(16), default="rule")   # rule (ingestion) | reviewed (file)
    released_on: Mapped[datetime | None] = mapped_column(DateTime)  # when it was noted; None = when its sides were
    documented_in: Mapped[str | None] = mapped_column(Text)           # e.g. "ARCHITECTURE.md 15.5"

    sides: Mapped[list[ConflictSide]] = relationship(back_populates="conflict", cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint("status IN ('open','resolved')", name="ck_conflict_status"),
                      CheckConstraint("origin IN ('rule','reviewed')", name="ck_conflict_origin"))


class ConflictSide(Base):
    __tablename__ = "conflict_side"

    id: Mapped[int] = mapped_column(primary_key=True)
    conflict_id: Mapped[int] = mapped_column(ForeignKey("conflict.id"), index=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"))
    side: Mapped[str] = mapped_column(String(1))  # A or B
    summary: Mapped[str] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(Text)  # reviewed sides: the words that located the record (JSON)

    conflict: Mapped[Conflict] = relationship(back_populates="sides")
    evidence: Mapped[Evidence] = relationship()

