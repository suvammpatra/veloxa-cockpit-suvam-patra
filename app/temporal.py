"""Time rules (ARCHITECTURE.md sections 4 and 11; DECISIONS.md 2).

Convention: every datetime stored in the database is a naive IST wall-clock
time. Sources in UTC (PagerDuty, git) are converted on the way in, so grouping
by day or month is always in IST (ARCHITECTURE.md 15.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum

IST = timezone(timedelta(hours=5, minutes=30), name="IST")
RELEASE_TIME = time(10, 0)  # each pack counts as released at 10:00 IST
END_OF_DAY = time(23, 59, 59)


def to_ist_naive(value: datetime) -> datetime:
    """Aware datetimes are converted to IST; naive ones are taken as IST already."""
    if value.tzinfo is None:
        return value
    return value.astimezone(IST).replace(tzinfo=None)


def release_timestamp(day: date) -> datetime:
    """When a pack released on `day` becomes known: 10:00 IST that day."""
    return datetime.combine(day, RELEASE_TIME)


def resolve_as_of(value: date | datetime | str | None, *, now: datetime | None = None) -> datetime:
    """Turn a user's as-of input into one IST instant.

    A date with no time means the end of that day (23:59:59 IST).
    A datetime is compared exactly. None means now.
    """
    if value is None:
        return to_ist_naive(now) if now else datetime.now(IST).replace(tzinfo=None)
    if isinstance(value, str):
        value = _parse(value)
    if isinstance(value, datetime):
        return to_ist_naive(value)
    return datetime.combine(value, END_OF_DAY)


def _parse(text: str) -> date | datetime:
    text = text.strip()
    if len(text) == 10:
        return date.fromisoformat(text)
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class Mode(str, Enum):
    KNOWN = "known"        # what could I know at X?          uses released_on
    RECORDED = "recorded"  # what had the company recorded by X? uses exported_on


@dataclass(frozen=True)
class TimeContext:
    """The time frame of one question.

    In KNOWN mode, only records released by `as_of` count.
    In RECORDED mode, records count if the company had them by `as_of`
    (exported_on), but only among records already released to me by
    `knowledge_cutoff` (defaults to now), so nothing unreleased can leak.
    """

    as_of: datetime
    mode: Mode = Mode.KNOWN
    knowledge_cutoff: datetime | None = None

    @classmethod
    def known_at(cls, value, **kw) -> "TimeContext":
        return cls(as_of=resolve_as_of(value, **kw), mode=Mode.KNOWN)

    @classmethod
    def recorded_by(cls, value, knowledge_cutoff=None) -> "TimeContext":
        return cls(
            as_of=resolve_as_of(value),
            mode=Mode.RECORDED,
            knowledge_cutoff=resolve_as_of(knowledge_cutoff),
        )

    @property
    def release_cutoff(self) -> datetime:
        return self.as_of if self.mode is Mode.KNOWN else self.knowledge_cutoff
