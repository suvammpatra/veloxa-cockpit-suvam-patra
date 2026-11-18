"""Reading a question: dates, periods, and the people, departments and projects it names.

Rules, all deterministic:
  * "as of <date>" in the question sets the time frame when the caller gave none.
  * A day ("on 22 Aug 2026"), a month ("in August 2026") or a range
    ("between 1 Aug and 15 Aug 2026") becomes a period in IST.
  * A month or day written without a year is read as the latest one not after
    the as-of date, and the answer says so.
  * Names resolve only through app.services.identity (exact rules and reviewed
    aliases), at the time frame's release cutoff. Nothing is fuzzy-matched.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alias, Department, Person, Project
from app.services.identity import Resolution, normalize, resolve_person
from app.temporal import TimeContext

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_name) if m})
_MONTHS["sept"] = 9
_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|" \
       r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_ORD = r"(?:st|nd|rd|th)?"
_DAY = (rf"(?:(?P<iso>\d{{4}}-\d{{2}}-\d{{2}})"
        rf"|(?<!\d)(?P<d1>\d{{1,2}}){_ORD}\s+(?P<m1>{_MON})\b\.?(?:,?\s+(?P<y1>\d{{4}}))?"
        rf"|\b(?P<m2>{_MON})\.?\s+(?P<d2>\d{{1,2}})(?!\d){_ORD}(?:,?\s+(?P<y2>\d{{4}}))?)")
_MONTH = rf"(?:(?P<ym>\d{{4}}-\d{{2}})(?!-\d)|(?P<m3>{_MON})(?:\s+(?P<y3>\d{{4}}))?)"


@dataclass(frozen=True)
class Period:
    start: datetime
    end: datetime
    label: str
    assumed_year: bool = False

    def contains(self, when: datetime) -> bool:
        return self.start <= when <= self.end


def _resolve_year(month: int, day: int, year: str | None, ref: datetime) -> tuple[date | None, bool]:
    if year:
        try:
            return date(int(year), month, day), False
        except ValueError:
            return None, False
    for y in (ref.year, ref.year - 1):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if d <= ref.date():
            return d, True
    return None, True


def _day_from(m: re.Match, ref: datetime) -> tuple[date | None, bool]:
    if m.group("iso"):
        try:
            return date.fromisoformat(m.group("iso")), False
        except ValueError:
            return None, False
    mon, day, year = ((m.group("m1"), m.group("d1"), m.group("y1")) if m.group("m1")
                      else (m.group("m2"), m.group("d2"), m.group("y2")))
    return _resolve_year(_MONTHS[mon.lower().rstrip(".")], int(day), year, ref)


def _month_from(m: re.Match, ref: datetime) -> tuple[tuple[int, int] | None, bool]:
    if m.group("ym"):
        y, mo = map(int, m.group("ym").split("-"))
        return ((y, mo) if 1 <= mo <= 12 else None), False
    mo = _MONTHS[m.group("m3").lower()]
    if m.group("y3"):
        return (int(m.group("y3")), mo), False
    y = ref.year if mo <= ref.month else ref.year - 1
    return (y, mo), True


def _day_period(d: date, assumed: bool) -> Period:
    return Period(datetime.combine(d, time.min), datetime.combine(d, time(23, 59, 59)),
                  f"{d.day} {d:%b %Y}", assumed)


def _month_period(y: int, mo: int, assumed: bool) -> Period:
    last = calendar.monthrange(y, mo)[1]
    return Period(datetime(y, mo, 1), datetime(y, mo, last, 23, 59, 59), f"{calendar.month_name[mo]} {y}", assumed)


def split_as_of(question: str) -> tuple[str, datetime | None]:
    """Remove an "as of <date>" phrase. Returns (rest of question, end of that day or None)."""
    m = re.search(rf"\bas\s+(?:of|at|on)\s+{_DAY}", question, flags=re.I)
    if not m:
        return question, None
    d, _ = _day_from(m, datetime.now())
    if d is None:
        return question, None
    return (question[:m.start()] + question[m.end():]).strip(), datetime.combine(d, time(23, 59, 59))


def find_period(question: str, ref: datetime) -> Period | None:
    q = question
    rng = re.search(rf"\b(?:between|from)\s+(?P<a>.+?)\s+(?:and|to|until|till)\s+(?P<b>.+?)(?:[?.!,]|$)", q, re.I)
    if rng:
        a, b = find_period(rng.group("a"), ref), find_period(rng.group("b"), ref)
        if a and b:
            # A year written on one end of a range applies to the other end too.
            if a.assumed_year and not b.assumed_year:
                a = find_period(rng.group("a"), b.end)
                a = Period(a.start, a.end, a.label, False)
            elif b.assumed_year and not a.assumed_year:
                b = find_period(rng.group("b"), datetime(a.start.year, 12, 31, 23, 59, 59))
                if b.end < a.start:  # e.g. November to February: February of the next year
                    b = find_period(rng.group("b"), datetime(a.start.year + 1, 12, 31, 23, 59, 59))
                b = Period(b.start, b.end, b.label, False)
            return Period(a.start, b.end, f"{a.label} to {b.label}", a.assumed_year or b.assumed_year)
    m = re.search(_DAY, q, flags=re.I)
    if m:
        d, assumed = _day_from(m, ref)
        if d:
            return _day_period(d, assumed)
    for m in re.finditer(rf"\b{_MONTH}\b", q, flags=re.I):
        if m.group("m3") and m.group("m3").lower() == "may" and not m.group("y3"):
            continue  # "may" is usually the verb
        ym, assumed = _month_from(m, ref)
        if ym:
            return _month_period(*ym, assumed)
    return None


def find_day(question: str, ref: datetime) -> tuple[date | None, bool]:
    m = re.search(_DAY, question, flags=re.I)
    return _day_from(m, ref) if m else (None, False)


# ---------------------------------------------------------------- names

_STOP = set("""
a about above after again against all am an and any are as at be because been before being below between both
but by can could did do does doing down during each few for from further had has have having he her here hers
herself him himself his how i if in into is it its itself just me more most my myself no nor not now of off on
once only or other our ours out over own same she should so some such than that the their theirs them then there
these they this those through to too under until up very was we were what when where which while who whom why
will with would you your yours tell show give list many much ok please whose
yes report reports reported reporting manager managers manages managed boss team teams company companies
headcount employees employee people staff person persons number total payroll salary salaries pay paid earn
earns gross month months year years date dates today yesterday incident incidents outage outages sev sev1 sev2
sev3 sev4 ga release released launch launched kit ready readiness marketing owner owners own owns ownership lead
leads atlas jira git github pagerduty keka board email emails ceo cro cfo cto vp head department departments
sources source records record disagree disagreement conflict conflicts contradict happened happen status
mon tue wed thu fri sat sun monday tuesday wednesday thursday friday saturday sunday
""".split())
_STOP |= set(_MONTHS)


@dataclass
class PersonMention:
    text: str
    status: str                     # resolved | ambiguous | unresolved (a known name form with no link)
    resolution: Resolution

    @property
    def person(self) -> Person | None:
        return self.resolution.person


@dataclass
class Entities:
    persons: list[PersonMention] = field(default_factory=list)
    unknown_names: list[str] = field(default_factory=list)
    departments: list[Department] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)   # project words named, e.g. "atlas"

    def first_person(self) -> PersonMention | None:
        return self.persons[0] if self.persons else None


def _tokens(question: str) -> list[tuple[str, bool]]:
    out = []
    for m in re.finditer(r"[A-Za-z0-9][A-Za-z0-9.@+_-]*", question):
        t = re.sub(r"(?:'s|’s|')$", "", m.group(0)).rstrip(".")
        if t:
            out.append((t, t[0].isupper() or any(c.isdigit() for c in t) or "@" in t))
    return out


def find_entities(session: Session, question: str, ctx: TimeContext) -> Entities:
    ents = Entities()
    q = question
    for d in session.scalars(select(Department).order_by(Department.name)):
        if re.search(rf"\b{re.escape(d.name)}\b", q, re.I) or re.search(rf"\b{re.escape(d.code)}\b", q):
            ents.departments.append(d)
            q = re.sub(rf"\b{re.escape(d.name)}\b", " ", q, flags=re.I)
    words = {w.lower() for w in re.findall(r"[A-Za-z]+", q)}
    project_words = {"atlas"} | {p.key.lower() for p in session.scalars(select(Project))} | \
                    {p.name.lower() for p in session.scalars(select(Project))}
    ents.projects = sorted(w for w in project_words if w in words)

    toks = _tokens(q)
    lower_only = not any(c for t, c in toks if c)
    known_forms = {a.normalized for a in session.scalars(select(Alias).where(
        Alias.released_on <= ctx.release_cutoff))}
    usable = [(t, cap) for t, cap in toks]
    i = 0
    while i < len(usable):
        matched = False
        for n in (3, 2, 1):
            gram = usable[i:i + n]
            if len(gram) < n:
                continue
            if any(t.lower() in _STOP or t.lower() in ents.projects for t, _ in gram):
                continue
            if not lower_only and not all(cap for _, cap in gram):
                continue
            text = " ".join(t for t, _ in gram)
            r = resolve_person(session, text, ctx)
            if r.status in ("resolved", "ambiguous"):
                ents.persons.append(PersonMention(text, r.status, r))
                i += n
                matched = True
                break
            if n == 1 and normalize(text) in known_forms:
                ents.persons.append(PersonMention(text, "unresolved", r))
                i += 1
                matched = True
                break
            if n == 1 and not lower_only and not text.isdigit():
                ents.unknown_names.append(text)
        if not matched:
            i += 1
    return ents


def released_people(session: Session, ctx: TimeContext) -> list[Person]:
    return list(session.scalars(select(Person).where(Person.released_on <= ctx.release_cutoff)))
