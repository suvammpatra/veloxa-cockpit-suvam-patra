"""The restricted payroll store (DECISIONS.md 3, 20; ARCHITECTURE.md section 10).

Payroll rows live in their own SQLite file, not in the cockpit database. The
only way out is PayrollAggregator.total(), which:

  * refuses any group whose membership on the date cannot be established;
  * refuses groups smaller than FLOOR (five);
  * refuses a total whose members differ by 1-4 people from any total already
    released, whatever its label or period, so two answers cannot be
    subtracted to reveal one or a few salaries;
  * never returns an individual's pay.

Exception flags (e.g. a full month paid for a partial month) carry no amounts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

FLOOR = 5


class _PayrollBase(DeclarativeBase):
    pass


class PayrollEntry(_PayrollBase):
    __tablename__ = "payroll_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_id: Mapped[str] = mapped_column(String(16), index=True)
    month: Mapped[str] = mapped_column(String(7), index=True)  # YYYY-MM
    days_in_month: Mapped[int] = mapped_column(Integer)
    days_payable: Mapped[int] = mapped_column(Integer)
    gross_paise: Mapped[int] = mapped_column(Integer)
    released_on: Mapped[datetime] = mapped_column(DateTime)


class ReleasedAggregate(_PayrollBase):
    """Every total ever answered, kept for the differencing check."""

    __tablename__ = "released_aggregate"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(64))
    month: Mapped[str] = mapped_column(String(7))
    members: Mapped[str] = mapped_column(Text)  # sorted emp_ids, comma-separated
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


@dataclass(frozen=True)
class AggregateResult:
    ok: bool
    total_paise: int | None = None
    member_count: int | None = None
    refusal: str | None = None   # membership_unknown | below_floor | differencing | no_data | individual_pay
    message: str | None = None


@dataclass(frozen=True)
class ExceptionFlag:
    emp_id: str
    month: str
    kind: str
    detail: str  # never contains an amount


REFUSALS = {
    "individual_pay": "I cannot provide individual salary information.",
    "membership_unknown": "Who was in that group on that date cannot be established, so no total is given.",
    "below_floor": f"That group has fewer than {FLOOR} people, so its total would expose individual pay.",
    "differencing": ("A total already given differs from this one by fewer than "
                     f"{FLOOR} people; together they would expose individual pay."),
    "no_data": "No payroll records cover that period.",
}


class PayrollStore:
    def __init__(self, path: Path | str):
        url = "sqlite:///:memory:" if str(path) == ":memory:" else f"sqlite:///{Path(path).as_posix()}"
        self._engine = create_engine(url, future=True)
        _PayrollBase.metadata.create_all(self._engine)

    def add_entries(self, rows: list[dict]) -> int:
        with Session(self._engine) as s:
            s.add_all(PayrollEntry(**r) for r in rows)
            s.commit()
        return len(rows)

    def aggregator(self) -> "PayrollAggregator":
        return PayrollAggregator(self._engine)

    def dispose(self) -> None:
        self._engine.dispose()


# Resolves a group label and month to the emp_ids in it on that date, or None if unknown.
MembershipFn = Callable[[str, str], "set[str] | None"]


class PayrollAggregator:
    def __init__(self, engine):
        self._engine = engine

    @staticmethod
    def individual(_emp_id: str) -> AggregateResult:
        return AggregateResult(ok=False, refusal="individual_pay", message=REFUSALS["individual_pay"])

    def total(self, label: str, month: str, membership: MembershipFn,
              *, released_cutoff: datetime) -> AggregateResult:
        members = membership(label, month)
        if members is None:
            return self._refuse("membership_unknown")
        with Session(self._engine) as s:
            rows = s.scalars(select(PayrollEntry).where(
                PayrollEntry.month == month,
                PayrollEntry.emp_id.in_(members),
                PayrollEntry.released_on <= released_cutoff,
            )).all()
            if not rows:
                return self._refuse("no_data")
            paid = {r.emp_id for r in rows}
            if len(paid) < FLOOR:
                return self._refuse("below_floor")
            for prior in s.scalars(select(ReleasedAggregate)).all():
                diff = len(paid.symmetric_difference(prior.members.split(",")))
                if 0 < diff < FLOOR:
                    return self._refuse("differencing")
            s.add(ReleasedAggregate(label=label, month=month, members=",".join(sorted(paid))))
            s.commit()
            return AggregateResult(ok=True, total_paise=sum(r.gross_paise for r in rows),
                                   member_count=len(paid))

    def exception_flags(self, *, released_cutoff: datetime,
                        join_dates: dict[str, "datetime.date"]) -> list[ExceptionFlag]:
        """Days paid against days eligible, with no money values (DECISIONS.md 4)."""
        flags = []
        with Session(self._engine) as s:
            for r in s.scalars(select(PayrollEntry).where(PayrollEntry.released_on <= released_cutoff)):
                joined = join_dates.get(r.emp_id)
                if joined is None or joined.strftime("%Y-%m") != r.month:
                    continue
                eligible = r.days_in_month - joined.day + 1
                if r.days_payable > eligible:
                    flags.append(ExceptionFlag(
                        emp_id=r.emp_id, month=r.month, kind="days_paid_exceed_eligible",
                        detail=(f"{r.days_payable} days payable out of {r.days_in_month}, "
                                f"but joined on day {joined.day} ({eligible} days eligible)."),
                    ))
        return flags

    @staticmethod
    def _refuse(reason: str) -> AggregateResult:
        return AggregateResult(ok=False, refusal=reason, message=REFUSALS[reason])
