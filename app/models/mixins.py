from datetime import datetime

from sqlalchemy import Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column


class TemporalMixin:
    """The three dates every fact carries (ARCHITECTURE.md section 4).

    released_on  when I was allowed to know it (10:00 IST on release day); required
    exported_on  when the source produced it; None when unknown (transcripts)
    as_of_start / as_of_end  the period the record describes; None when unknown
    """

    released_on: Mapped[datetime] = mapped_column(DateTime, index=True)
    exported_on: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    as_of_start: Mapped[datetime | None] = mapped_column(DateTime)
    as_of_end: Mapped[datetime | None] = mapped_column(DateTime)


class ValidityMixin:
    """An effective-dated row (DECISIONS.md 17-18).

    valid_from   first moment the row is known to hold. None only for an
                 announced change whose effective date is unknown.
    start_exact  False when valid_from is just the earliest record of it
                 (e.g. a Keka snapshot date): before valid_from the answer is
                 "unknown", not "something else".
    valid_to     None means still current.
    status       confirmed | announced | withdrawn. Only confirmed rows count
                 as the org (DECISIONS.md 18).
    released_on  when the record behind the row reached me (point-in-time).
    """

    valid_from: Mapped[datetime | None] = mapped_column(DateTime)
    start_exact: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(default="confirmed")
    released_on: Mapped[datetime] = mapped_column(DateTime)
