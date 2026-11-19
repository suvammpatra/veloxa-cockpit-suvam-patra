"""Date parsing for source files. Nothing is guessed: a value that does not
parse returns None and the caller logs it (ARCHITECTURE.md 5: dates are never imputed)."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

from app.temporal import to_ist_naive

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_name) if m})

_DMY = r"(\d{1,2})[ -]([A-Za-z]{3,9})[ ,-]*(\d{4})"


def _dmy(day: str, month: str, year: str) -> date | None:
    m = _MONTHS.get(month.lower())
    if m is None:
        return None
    try:
        return date(int(year), m, int(day))
    except ValueError:
        return None


def parse_date(value) -> date | None:
    """A calendar date from a cell or string: 2026-04-08, 31-Oct-2026, 6 Oct 2026."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    m = re.fullmatch(_DMY, text)
    return _dmy(*m.groups()) if m else None


def parse_instant(value) -> datetime | None:
    """A timestamp, converted to naive IST. 'Z' and offsets are honoured;
    a value with no zone is taken as IST already."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return to_ist_naive(value)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return to_ist_naive(datetime.fromisoformat(text))
    except ValueError:
        return None


def month_range(value) -> tuple[datetime, datetime] | None:
    """'Jan-2026' or 'January 2026' -> first and last instant of that month."""
    m = re.fullmatch(r"([A-Za-z]{3,9})[ -](\d{4})", str(value).strip())
    if not m:
        return None
    month = _MONTHS.get(m.group(1).lower())
    if month is None:
        return None
    year = int(m.group(2))
    last = calendar.monthrange(year, month)[1]
    return datetime(year, month, 1), datetime(year, month, last, 23, 59, 59)


def previous_month_range(day: date) -> tuple[datetime, datetime]:
    end = day.replace(day=1) - timedelta(days=1)
    return datetime(end.year, end.month, 1), datetime(end.year, end.month, end.day, 23, 59, 59)


def find_export_date(text: str) -> tuple[date, str] | None:
    """'Exported 31-Oct-2026' or 'Exported by IT on 31 Oct 2026' -> (date, words as written)."""
    m = re.search(r"Exported(?: by [^.]*?)?(?: on)? " + _DMY, text)
    if not m:
        return None
    d = _dmy(*m.groups()[-3:])
    return (d, m.group(0)) if d else None


def first_full_date(text: str) -> tuple[date, str] | None:
    """The first complete day-month-year date in a text, as written."""
    for m in re.finditer(_DMY, text):
        d = _dmy(*m.groups())
        if d:
            return d, m.group(0).strip()
    return None


def first_numeric_dmy(text: str) -> tuple[date, str] | None:
    """The first DD/MM/YYYY date in a text, as written. Used only where the day-first
    reading was approved (Indian vendor invoices, ARCHITECTURE.md 16.10); "01/10/2026" is
    1 October 2026. A value that is not a real date returns nothing."""
    for m in re.finditer(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4})(?![\d/])", text):
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))), m.group(0)
        except ValueError:
            continue
    return None
