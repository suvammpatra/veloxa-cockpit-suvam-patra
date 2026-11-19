"""Typed question handlers (ARCHITECTURE.md 9, step 6).

Each handler reads typed records and evidence through the existing time rules
(app.repositories.temporal, app.services.org, app.retrieval) and returns a
draft Answer. A handler states only what a record shows, and it cites that
record. It never fills a missing value; where a value is missing it says so.

The engine (app.answering.engine) then adds conflicts, validates every
citation and computes confidence. A handler only reports the factors.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.answering import classify as C
from app.answering.classify import Intent
from app.answering.model import Answer, ChainLink, Factors
from app.answering.parse import Entities, PersonMention, find_day, find_period, released_people
from app.models import (Alias, Claim, ConflictSide, Department, DepartmentLine, DepartmentMembership, Evidence, Incident,
                        Person, SourceRecord, Ticket)
from app.privacy.payroll import REFUSALS, PayrollAggregator
from app.repositories.temporal import pending, released_by, valid_at, visible
from app.retrieval import fts, policy
from app.retrieval.search import Filters, Hit, SearchError, conflicts_for, search
from app.services.identity import normalize, resolve_person
from app.services.org import department_members, department_reports_to, manager_as_of, position_holder
from app.temporal import Mode, TimeContext


@dataclass
class Ask:
    session: Session
    question: str
    ctx: TimeContext
    ents: Entities
    intent: Intent
    payroll: PayrollAggregator | None = None

    def new(self, short: str, *, status: str = "answered", **kw) -> Answer:
        return Answer(question=self.question, short_answer=short, status=status, kind=self.intent.kind,
                      purpose=self.intent.purpose, **kw)


# ---------------------------------------------------------------- small helpers

def d(day) -> str:
    if day is None:
        return "unknown date"
    if isinstance(day, datetime):
        day = day.date()
    return f"{day.day} {day:%b %Y}"


def inr(paise: int) -> str:
    """Indian digit grouping: Rs.1,23,45,678.90"""
    rupees, p = divmod(abs(paise), 100)
    s = str(rupees)
    head, tail = s[:-3], s[-3:]
    while len(head) > 2:
        tail = head[-2:] + "," + tail
        head = head[:-2]
    s = (head + "," + tail) if head else tail
    return f"{'-' if paise < 0 else ''}Rs.{s}" + (f".{p:02d}" if p else "")


def end_of(day: date) -> datetime:
    return datetime.combine(day, time(23, 59, 59))


def org_context(ctx: TimeContext, at: datetime) -> TimeContext:
    """The org on date `at`, using every record released by the question's cutoff."""
    return TimeContext(as_of=at, mode=Mode.RECORDED, knowledge_cutoff=ctx.release_cutoff)


def usable(session: Session, ctx: TimeContext, ids, purpose: str | None = None) -> dict[int, Evidence]:
    """Evidence rows that may be cited at this time frame under the default policy."""
    ids = {i for i in ids if i}
    if not ids:
        return {}
    stmt = select(Evidence).join(SourceRecord, Evidence.source_record_id == SourceRecord.id).where(Evidence.id.in_(ids))
    return {e.id: e for e in session.scalars(policy.apply(visible(stmt, Evidence, ctx), purpose=purpose))}


def _keysort(evs) -> list[str]:
    return sorted({e.evidence_key for e in evs}, key=lambda k: int(k[1:]))


def quote_from(content: str, words, *, limit: int = 220) -> str | None:
    """The sentence (or table cell) of `content` that contains the most of `words`, as an exact
    substring. Ties go to the longer matched words (more specific), then the earliest sentence."""
    best, best_n, best_hit = None, (0, 0), None
    for m in re.finditer(r"[^.!?\n;]+[.!?]?", content):
        s = m.group(0).strip()
        if _META.match(s) or "[text withheld" in s:
            continue  # email headers, document labels and withheld text are not statements
        hits = [h for w in words if (h := re.search(_word(w), s, re.I))]
        score = (len(hits), sum(len(h.group(0)) for h in hits))
        if hits and score > best_n:
            best, best_n, best_hit = s, score, hits[0]
    if best is None or len(best) <= limit:
        return best
    start = max(0, best_hit.start() - limit // 3)
    return best[start:start + limit].strip()


_META = re.compile(r"(From|To|Cc|Subject|Date|Owner|Dated|Sent)\s*:", re.I)


def first_line(content: str, limit: int = 160) -> str:
    line = next((ln.strip() for ln in content.splitlines() if ln.strip()), content.strip())
    return line[:limit].strip()


def employed_at(p: Person, at: datetime) -> bool:
    if p.join_date and p.join_date > at.date():
        return False
    return not (p.exit_date and p.exit_date < at.date())


def question_day(a: Ask) -> tuple[datetime, str | None]:
    """The date an org question is about: a date in the question, else the as-of date."""
    day, assumed = find_day(a.question, a.ctx.as_of)
    if day is None:
        return a.ctx.as_of, None
    note = f"Read the date as {d(day)} (no year was given)." if assumed else None
    return end_of(day), note


def _word(w: str) -> str:
    """Short words and acronyms ("GA") match as whole words; longer words also match their
    word forms ("delay" finds "delayed")."""
    return rf"\b{re.escape(w)}\b" if len(w) <= 3 else rf"\b{re.escape(w)}"


def hours_remark(session: Session, content: str, ctx: TimeContext) -> bool:
    """True when the record holds a sentence pairing a working-hours phrase with a name
    (decisions 23 and 28). The rule itself lives in app.retrieval.disclosure."""
    from app.retrieval import disclosure
    return "working_hours" in disclosure.redact(session, content, ctx).reasons


def statements(a: Ask, query: str, words, *, purpose: str | None = None, exclude_systems=("Jira",),
               limit: int = 6, require: tuple[str, ...] = ()) -> list[Hit]:
    """Text records that mention the topic, oldest first, each with a quotable sentence.

    Excluded systems are left out in SQL, before the result limit. When `require` is given,
    the record must also name one of those words (e.g. the project), so a generic word
    such as "lead" does not pull in unrelated rows."""
    exclude_systems = tuple(exclude_systems) + _no_commits(a)
    try:
        r = search(a.session, query, a.ctx, Filters(purpose=purpose, exclude_systems=exclude_systems),
                   limit=100)
    except SearchError:
        return []
    hits = [h for h in r.hits if not h.via_conflict and quote_from(h.content, words)
            and (not require or any(re.search(_word(w), h.content, re.I) for w in require))]
    hits.sort(key=lambda h: (h.citation.exported_on is None, h.citation.exported_on or datetime.max,
                             int(h.citation.evidence_key[1:])))
    return hits[:limit]


def _no_commits(a: Ask) -> tuple[str, ...]:
    """Git commit records are left out, in SQL, for any question about a person, on-call, hours or
    activity (DECISIONS.md 30). The engine checks the finished answer again."""
    return (C.COMMIT_SYSTEM,) if C.commit_records_barred(a.question, a.ents) else ()


def statement_link(h: Hit, words, role: str = "context") -> ChainLink:
    c = h.citation
    when = d(c.exported_on) if c.exported_on else "undated"
    kind = "transcript, " if c.trust_rung == 5 else ""
    return ChainLink(f"{c.filename} ({kind}{when}) says", [c.evidence_key], quote_from(h.content, words), role)


# ---------------------------------------------------------------- shared answers

def ambiguous(a: Ask, m: PersonMention) -> Answer:
    names = sorted(p.full_name for p in m.resolution.candidates)
    who = " or ".join(names) if names else f"more than one person ({m.resolution.note or 'no single match'})"
    ans = a.new(f"'{m.text}' could be {who}. I won't pick one; ask again with the full name.", status="ambiguous",
                weakest_link=m.resolution.note or "The name matches more than one person.",
                would_change_mind="A reviewed alias row, or the full name in the question.")
    ans.factors = Factors(identity="L", completeness="insufficient")
    return ans


def unlinked(a: Ask, m: PersonMention) -> Answer:
    ans = a.new(f"'{m.text}' appears in the records but is not linked to any known person, so I can't answer "
                "this about a person.", status="uncertain",
                weakest_link=m.resolution.note or "No record links this name to a person.",
                would_change_mind="A record that gives the full name, reviewed and added to the alias file.")
    ans.factors = Factors(identity="L", completeness="insufficient")
    return ans


def unknown_person(a: Ask, name: str) -> Answer:
    ans = a.new(f"'{name}' does not match anyone in the records known at this date.", status="no_evidence",
                weakest_link="Names match exactly or through reviewed aliases; there is no fuzzy matching.",
                would_change_mind="A record naming this person, or the name as Keka spells it.")
    ans.factors = Factors(identity="L", completeness="insufficient")
    return ans


# ---------------------------------------------------------------- refusals

REFUSAL_TEXT = {
    "performance_assessment": (
        "I won't describe or judge a person's working hours, commit times or performance. Commit times and "
        "remarks about late nights are not records of hours worked, output or how someone feels "
        "(DECISIONS.md 23).",
        "Ask about the work instead: ticket status, or who holds Atlas tickets."),
    "speculation": (
        "The records don't show anyone's intentions or feelings, and I won't infer them (DECISIONS.md 11, 23). "
        "I can say what the records show: role, dates and assigned work.",
        "Only a record in which the person states it themselves."),
    "not_computable": (
        "That can't be computed from these records. No export contains revenue, so profit, margin and net burn "
        "are not available (ARCHITECTURE.md 9).",
        "A revenue export or an invoice register."),
    "individual_pay": (
        REFUSALS["individual_pay"] + " Payroll is answered only as totals over five or more people "
        "(DECISIONS.md 3).",
        "Only the CFO relaxing the rule. Ask for a company total for a month instead."),
}


_CONTINUITY_OFFER = ("Ask instead: \"What is our workforce continuity?\" It lists confirmed departures, open and "
                     "paused roles, contractors and work that rests on one person, from the records, with no one "
                     "scored.")
REFUSAL_TEXT["retention_ranking"] = (
    "I won't rank or score people by how likely they are to leave. The records don't show anyone's intentions, and a "
    "ranking built from emails, calls, leave, commit activity, hours or sentiment would be a guess about each person "
    "(DECISIONS.md 11, 23, 34). Private messages, such as Slack or WhatsApp, are not in the records and are not read.",
    _CONTINUITY_OFFER)
REFUSAL_TEXT["private_messages"] = (
    "I can't show private messages. Slack, WhatsApp and other private messages are not in the records, and the "
    "cockpit does not read people's private communications (DECISIONS.md 34).",
    _CONTINUITY_OFFER)


def refusal(a: Ask, reason: str | None = None) -> Answer:
    reason = reason or a.intent.refusal
    text, change = REFUSAL_TEXT[reason]
    if re.search(C.CONSENT, a.question, re.I):
        text += (" One person's approval doesn't change this: it is not consent from the people concerned, and the "
                 "rule does not depend on who asks.")
    ans = a.new(text, status="refused", refusal=reason, weakest_link="None: this is a fixed rule, not a "
                "reading of the records.", would_change_mind=change)
    ans.kind = "refusal"
    ans.factors = Factors(policy=True)
    return ans


# ---------------------------------------------------------------- headcount

def _snapshot_date(evs) -> datetime | None:
    dates = [e.exported_on for e in evs if e.exported_on]
    return min(dates) if dates else None


def company_headcount(a: Ask) -> Answer:
    at, note = question_day(a)
    people = released_people(a.session, a.ctx)
    employees = [p for p in people if p.worker_type == "employee" and employed_at(p, at)]
    contractor_rows = [p for p in people if p.worker_type == "contractor"]
    contractor_ev = usable(a.session, a.ctx, [p.source_evidence_id for p in contractor_rows])
    # A contractor is listed only when the record behind it is visible here, and never counted.
    contractors = sorted(p.full_name for p in contractor_rows
                         if p.source_evidence_id is None or p.source_evidence_id in contractor_ev)
    if not employees:
        return _none(a, "No employee records are known at this date.",
                     "Employee records arrive with the Keka export.")
    evs = usable(a.session, a.ctx, [p.source_evidence_id for p in employees])
    counted = [p for p in employees if p.source_evidence_id in evs]
    if not counted:
        return _none(a, f"The employee records known were not recorded by {d(a.ctx.as_of)}.",
                     "A record of the staff list made by that date.")
    snap = _snapshot_date(evs.values())
    short = f"{len(counted)} employees on {d(at)}"
    if contractors:
        short += f". {len(contractors)} contractor(s) are known and not counted: {', '.join(contractors)}"
    short += " (DECISIONS.md 22)." if contractors else "."
    f = Factors()
    weak = f"One Keka snapshot (exported {d(snap)}). Keka lists employees only, not contractors."
    if snap and at < snap:
        f.completeness = "partial"
        weak += f" For {d(at)}, anyone who left before the export is not in it, so the count may be low."
    if any(p.join_date is None for p in counted):
        f.temporal = "approximate"
        f.notes.append("Some employees have no join date")
    if len(counted) < len(employees):
        f.completeness = "partial"
    chain = _by_source(evs.values(), lambda n, fn: f"{n} employee rows in {fn} employed on {d(at)} "
                                                   "(join and exit dates)")
    chain += _by_source(contractor_ev.values(), lambda n, fn: f"Contractor record ({fn}); listed, not counted",
                        role="context")
    ans = a.new(short, evidence_chain=chain, weakest_link=weak,
                would_change_mind="A dated Keka history, or a later export that lists different people.")
    ans.factors = f
    if note:
        ans.warnings.append(note)
    return ans


def _by_source(evs, statement, role="support") -> list[ChainLink]:
    groups: dict[str, list[Evidence]] = {}
    for e in evs:
        groups.setdefault(e.source.filename, []).append(e)
    return [ChainLink(statement(len(rows), fn), _keysort(rows), role=role) for fn, rows in sorted(groups.items())]


def _none(a: Ask, short: str, change: str, weak: str = "There is no record to weigh.") -> Answer:
    ans = a.new(short, status="no_evidence", weakest_link=weak, would_change_mind=change)
    ans.factors = Factors(completeness="insufficient")
    return ans


def department_headcount(a: Ask) -> Answer:
    dept = a.ents.departments[0]
    at, note = question_day(a)
    members = department_members(a.session, dept.code, org_context(a.ctx, at))
    rows = a.session.scalars(released_by(select(DepartmentMembership).where(
        DepartmentMembership.department_id == dept.id), DepartmentMembership, a.ctx.release_cutoff)).all()
    if not rows:
        return _none(a, f"No membership records for {dept.name} are known at this date.",
                     "A Keka export that lists the department.")
    if members is None:
        earliest = min((r.valid_from for r in rows if r.valid_from), default=None)
        evs = usable(a.session, a.ctx, [r.source_evidence_id for r in rows if r.valid_from == earliest])
        ans = a.new(f"Who was in {dept.name} on {d(at)} cannot be established. Department membership is "
                    f"recorded from {d(earliest)} (a Keka snapshot); before that it is unknown, and it is not "
                    "assumed back to join dates (DECISIONS.md 17, 20).", status="uncertain",
                    evidence_chain=_by_source(evs.values(), lambda n, fn: f"Membership records for {dept.name} "
                                              f"in {fn} start on {d(earliest)}", role="context"),
                    weakest_link="Keka has no history: one snapshot cannot show earlier membership.",
                    would_change_mind="A dated Keka history, or another record of the team on that date.")
        ans.factors = Factors(completeness="insufficient")
        return ans
    valid = a.session.scalars(valid_at(select(DepartmentMembership).where(
        DepartmentMembership.department_id == dept.id, DepartmentMembership.person_id.in_(members or {0})),
        DepartmentMembership, at, release_cutoff=a.ctx.release_cutoff)).all()
    evs = usable(a.session, a.ctx, [r.source_evidence_id for r in valid])
    if members and not evs:
        return _none(a, f"The membership records for {dept.name} were not recorded by {d(a.ctx.as_of)}.",
                     "A record of the team made by that date.")
    snap = _snapshot_date(evs.values())
    ans = a.new(f"{len(members)} employees in {dept.name} on {d(at)}. Contractors are not counted "
                "(DECISIONS.md 22).",
                evidence_chain=_by_source(evs.values(), lambda n, fn: f"{n} {dept.name} membership rows in {fn}, "
                                          f"valid on {d(at)}"),
                weakest_link=f"Membership comes from one Keka snapshot (exported {d(snap)}); it shows the "
                             "department on that date, not when each person joined it.",
                would_change_mind="A later Keka export, or a dated move between departments.")
    if len(evs) < len(members):
        ans.factors.completeness = "partial"
    if note:
        ans.warnings.append(note)
    return ans


# ---------------------------------------------------------------- manager

def manager(a: Ask) -> Answer:
    m = a.ents.first_person()
    if m is None:
        if a.ents.departments:
            return _department_line(a, a.ents.departments[0])
        if a.ents.unknown_names:
            return unknown_person(a, a.ents.unknown_names[0])
        return _none(a, "Name the person whose manager you want.", "A question that names a person.")
    if m.status == "ambiguous":
        return ambiguous(a, m)
    if m.status != "resolved":
        return unlinked(a, m)
    p = m.person
    at, note = question_day(a)
    own = usable(a.session, a.ctx, [p.source_evidence_id])
    if p.exit_date and p.exit_date < at.date() or p.join_date and p.join_date > at.date():
        left = p.exit_date and p.exit_date < at.date()
        short = (f"{p.full_name} left on {d(p.exit_date)}, so no reporting line applies on {d(at)}." if left else
                 f"{p.full_name} had not joined on {d(at)} (join date {d(p.join_date)}).")
        ans = a.new(short, evidence_chain=[ChainLink(f"{p.full_name}'s employee record", _keysort(own.values()))],
                    weakest_link="Join and exit dates come from one Keka snapshot.",
                    would_change_mind="A later Keka export with different dates.")
        ans.factors.identity = m.resolution.confidence
        return ans

    res = manager_as_of(a.session, p, org_context(a.ctx, at))
    line_ev = usable(a.session, a.ctx, [res.source_evidence_id])
    pend_ev = usable(a.session, a.ctx, res.pending_evidence_ids)
    pending = (" Pending: " + "; ".join(res.pending_changes) + " (not applied until a source confirms the date, "
               "DECISIONS.md 18).") if res.pending_changes else ""
    member = a.session.scalars(valid_at(select(DepartmentMembership).where(DepartmentMembership.person_id == p.id),
                                        DepartmentMembership, at, release_cutoff=a.ctx.release_cutoff)).first()
    dept_pend = pending_department_lines(a, member.department) if member else []
    if dept_pend:
        pending += (" Pending for " + member.department.name + ", not in effect: "
                    + "; ".join(t for t, _ in dept_pend) + " (DECISIONS.md 18).")
        pend_ev.update({e.id: e for _, e in dept_pend})
    chain = []
    if res.status == "known":
        if not line_ev:
            return _none(a, f"The record of {p.full_name}'s reporting line was not recorded by {d(a.ctx.as_of)}.",
                         "A record of the line made by that date.")
        chain.append(ChainLink(f"Reporting line for {p.full_name}, valid on {d(at)}", _keysort(line_ev.values())))
        short = f"{p.full_name} reports to {res.manager} on {d(at)}.{pending}"
        status, f = "answered", Factors()
    else:
        if line_ev:
            chain.append(ChainLink(f"Earliest reporting-line record for {p.full_name}", _keysort(line_ev.values()),
                                   role="context"))
        short = f"{p.full_name}'s manager on {d(at)} is not known. {res.note}{pending}"
        status, f = "uncertain", Factors(completeness="insufficient")
    if pend_ev:
        chain.append(ChainLink("Announced change", _keysort(pend_ev.values()), role="context"))
    f.identity = m.resolution.confidence
    snap = _snapshot_date(line_ev.values())
    ans = a.new(short, status=status, evidence_chain=chain,
                weakest_link=(f"Reporting lines come from one Keka snapshot (exported {d(snap)}), so a line is "
                              "known only from that date. A later change shows only with a new export or a dated "
                              "announcement." if snap else "No reporting-line record covers that date."),
                would_change_mind="A later Keka export, or a dated announcement of a change (DECISIONS.md 18).")
    ans.factors = f
    if note:
        ans.warnings.append(note)
    return ans


def pending_department_lines(a: Ask, dept: Department) -> list[tuple[str, Evidence]]:
    """Announced changes for a department that may be shown at this time frame: released by
    the cutoff, and with a source record visible here (so an undated transcript is not shown
    in recorded-by mode). They are never applied (DECISIONS.md 18)."""
    rows = a.session.scalars(pending(select(DepartmentLine).where(DepartmentLine.department_id == dept.id),
                                     DepartmentLine, release_cutoff=a.ctx.release_cutoff)).all()
    evs = usable(a.session, a.ctx, [r.source_evidence_id for r in rows])
    out = []
    for r in rows:
        if r.source_evidence_id not in evs:
            continue
        holder = position_holder(a.session, r.reports_to.code, a.ctx)
        when = f"from {d(r.valid_from)}" if r.valid_from else "effective date not confirmed"
        out.append((f"announced that {dept.name} will report to {r.reports_to.title} "
                    f"({holder.full_name if holder else 'no holder on record'}), {when}", evs[r.source_evidence_id]))
    return out


def _department_line(a: Ask, dept: Department) -> Answer:
    at, note = question_day(a)
    label, _ = department_reports_to(a.session, dept.code, org_context(a.ctx, at))
    pend = pending_department_lines(a, dept)
    rows = a.session.scalars(valid_at(select(DepartmentLine).where(DepartmentLine.department_id == dept.id),
                                      DepartmentLine, at, release_cutoff=a.ctx.release_cutoff)).all()
    evs = usable(a.session, a.ctx, [r.source_evidence_id for r in rows])
    if label is None and not pend:
        return _none(a, f"No record shows which leader {dept.name} sits under. Individual reporting lines are in "
                        "Keka; ask about a person.", "A record of the department's line.")
    short = (f"{dept.name} sits under {label} on {d(at)}." if label else
             f"No confirmed line for {dept.name} on {d(at)}; the current reporting lines of its people are "
             "unchanged.")
    if pend:
        short += " Pending, not in effect: " + "; ".join(t for t, _ in pend) + " (DECISIONS.md 18)."
    chain = [ChainLink(f"Department line records for {dept.name}", _keysort(evs.values()))] if evs else []
    chain += [ChainLink(f"Announced change: {t}", [e.evidence_key], role="context") for t, e in pend]
    ans = a.new(short, status="answered" if label else "uncertain", evidence_chain=chain,
                weakest_link=("The announcement gives no effective date, so it is not applied."
                              if pend else "Department lines are stored only from records that state them."),
                would_change_mind="A dated announcement of the change, or a Keka export showing the new line.")
    if not label:
        ans.factors.completeness = "insufficient"
    if note:
        ans.warnings.append(note)
    return ans


# ---------------------------------------------------------------- payroll (restricted totals only)

INDIVIDUAL = r"\b(individual|each (employee|person)|per (employee|person|head)|who earns|highest[- ]paid|" \
             r"lowest[- ]paid|top earners?|his|her|their own)\b"
PERSONAL_PAY = r"\b(salary|salaries|earn|earns|earning|earnings|ctc|compensation|wages?|take[- ]home|paid)\b"


def payroll(a: Ask) -> Answer:
    """Totals only. A named person, an individual phrasing, or a salary word next to a name
    that is not a known person is refused as individual pay (DECISIONS.md 3)."""
    unknown_name_pay = a.ents.unknown_names and re.search(PERSONAL_PAY, a.question, re.I)
    if a.ents.persons or unknown_name_pay or re.search(INDIVIDUAL, a.question, re.I):
        ans = refusal(a, "individual_pay")
        ans.kind = "payroll"
        return ans
    period = find_period(a.question, a.ctx.as_of)
    if period is None:
        ans = a.new("Payroll totals are given per month. Name a month, for example 'company payroll total for "
                    "March 2026'.", status="uncertain", weakest_link="No month was named.",
                    would_change_mind="A question that names a month.")
        ans.factors = Factors(completeness="insufficient")
        return ans
    month = f"{period.start:%Y-%m}"
    mlabel = f"{period.start:%B %Y}"
    if a.payroll is None:
        return _none(a, "No payroll store is available, so no total can be given.",
                     "Ingesting the payroll register.")
    cutoff = a.ctx.release_cutoff
    month_end = end_of((period.start.replace(day=28) + timedelta(days=4)).replace(day=1).date() - timedelta(days=1))
    dept = a.ents.departments[0] if a.ents.departments else None
    people = {p.id: p for p in released_people(a.session, a.ctx)}
    if dept:
        label = dept.name
        mctx = org_context(a.ctx, month_end)

        def membership(_label, _month):
            ids = department_members(a.session, dept.code, mctx)
            return None if ids is None else {people[i].emp_id for i in ids if i in people and people[i].emp_id}
    else:
        label = "Company"
        members = [p for p in people.values() if p.worker_type == "employee" and p.emp_id
                   and (p.join_date is None or p.join_date <= month_end.date())
                   and (p.exit_date is None or p.exit_date >= period.start.date())]

        def membership(_label, _month):
            return {p.emp_id for p in members}

    r = a.payroll.total(label, month, membership, released_cutoff=cutoff)
    if not r.ok:
        return _payroll_refusal(a, r.refusal, r.message, dept, mlabel)

    reg = a.session.scalars(released_by(select(SourceRecord).where(SourceRecord.access == "restricted"),
                                        SourceRecord, cutoff)).all()
    rung = min((s.trust_rung for s in reg if s.trust_rung), default=None)
    system = reg[0].system if reg else "Payroll register"
    member_ids = membership(label, month) or set()
    mevs = usable(a.session, a.ctx, [p.source_evidence_id for p in people.values() if p.emp_id in member_ids])
    chain = [ChainLink(f"Total from the restricted payroll store over {r.member_count} people. Individual "
                       "amounts are never read out (DECISIONS.md 3).", [],
                       record="Restricted payroll totals function (payroll register)", record_rung=rung,
                       record_system=system)]
    chain += _by_source(mevs.values(), lambda n, fn: f"Group members: {n} rows in {fn}", role="context")
    snap = _snapshot_date(mevs.values())
    f = Factors()
    weak = "The total comes from the payroll register only; the GL payroll line is a consistency check, not a " \
           "second source (ARCHITECTURE.md 9)."
    if not dept and snap and month_end < snap:
        f.completeness = "partial"
        weak = (f"Membership comes from the Keka snapshot (exported {d(snap)}). Anyone paid in {mlabel} who left "
                "before that export is not in it, so their pay is not counted and the total may be low.")
    group = "the company" if label == "Company" else label
    ans = a.new(f"Gross payroll for {group}, {mlabel}: {inr(r.total_paise)} across {r.member_count} people.",
                evidence_chain=chain, weakest_link=weak,
                would_change_mind="A payroll export with its own department field, or a dated Keka history.")
    ans.factors = f
    if period.assumed_year:
        ans.warnings.append(f"Read the month as {mlabel} (no year was given).")
    return ans


def _payroll_refusal(a: Ask, reason: str, message: str, dept, mlabel: str) -> Answer:
    if reason == "no_data":
        return _none(a, f"No payroll records for {mlabel} are known at this date.",
                     "A payroll register that covers that month.")
    extra = ""
    if reason == "membership_unknown" and dept is not None:
        first = a.session.scalar(select(func.min(DepartmentMembership.valid_from)).where(
            DepartmentMembership.released_on <= a.ctx.release_cutoff))
        extra = (f" Department membership is recorded only from {d(first)} (a Keka snapshot); {mlabel} is before "
                 "it, and membership is not assumed back to join dates (ARCHITECTURE.md 16.2).")
    ans = a.new(message + extra, status="refused", refusal=reason,
                weakest_link="None: the privacy floor is a fixed rule (DECISIONS.md 3, 20).",
                would_change_mind=("A dated department history." if reason == "membership_unknown" else
                                   "Only the CFO relaxing the rule or approving grouped reporting."))
    ans.kind = "payroll"
    ans.factors = Factors(policy=True)
    return ans


# ---------------------------------------------------------------- incidents

def _who(a: Ask, alias: str | None) -> str:
    if not alias:
        return "no responder recorded"
    r = resolve_person(a.session, alias, a.ctx)
    if r.status == "resolved":
        return r.person.full_name
    if r.status == "ambiguous":
        return f"'{alias}' (could be more than one person)"
    return f"'{alias}' (not linked to a known person)"


def incidents(a: Ask) -> Answer:
    period = find_period(a.question, a.ctx.as_of)
    rows = a.session.scalars(visible(select(Incident), Incident, a.ctx).order_by(Incident.opened_at, Incident.key)).all()
    evs = usable(a.session, a.ctx, [i.evidence_id for i in rows])
    rows = [i for i in rows if i.evidence_id in evs]
    if not rows:
        return _none(a, "No incident records are known at this date.", "A PagerDuty export.")
    lo, hi = rows[0].opened_at, rows[-1].opened_at
    sev = re.search(r"\bsev ?([1-4])\b", a.question, re.I)
    chosen = [i for i in rows if (period is None or period.contains(i.opened_at))
              and (sev is None or re.sub(r"\s", "", i.severity).upper() == f"SEV{sev.group(1)}")]
    what = f"SEV{sev.group(1)} incidents" if sev else "incidents"
    # Coverage (ASSUMPTIONS.md, Build): see incident_coverage().
    cov = incident_coverage([i.opened_at for i in rows],
                            sorted({evs[i.evidence_id].source.filename for i in rows}))
    cover_from, cover_to = cov.start, cov.end
    weak = (f"Incident coverage is taken as {cover_from:%B %Y} to {cover_to:%B %Y}, {cov.basis}. Times are "
            "converted from UTC to IST.")
    ans_kw = dict(would_change_mind="A fuller PagerDuty export, or one that states its coverage period.")
    if not chosen:
        if period and (period.end < cover_from or period.start > cover_to):
            ans = a.new(f"Coverage unavailable: no incident record covers {period.label}. The incident records "
                        f"known cover {cover_from:%B %Y} to {cover_to:%B %Y}, so this is not a count of zero.",
                        status="uncertain", weakest_link=weak,
                        evidence_chain=[ChainLink("Earliest and latest incident records known",
                                                  _keysort([evs[rows[0].evidence_id], evs[rows[-1].evidence_id]]),
                                                  role="context")], **ans_kw)
            ans.factors = Factors(completeness="insufficient")
        else:
            ans = a.new(f"No {what} were recorded {_span(period)} (IST).", weakest_link=weak,
                        evidence_chain=[ChainLink(f"Incident records known run from {d(lo)} to {d(hi)}; none in "
                                                  "the period", _keysort([evs[rows[0].evidence_id],
                                                                          evs[rows[-1].evidence_id]]))], **ans_kw)
    else:
        by_sev = Counter(i.severity for i in chosen)
        people = Counter(_who(a, i.responder_alias) for i in chosen)
        unlinked_names = sorted({f"'{i.responder_alias}'" for i in chosen if i.responder_alias
                                 and resolve_person(a.session, i.responder_alias, a.ctx).status != "resolved"})
        short = (f"{len(chosen)} {what} opened {_span(period)} (IST): "
                 + ", ".join(f"{n} {s}" for s, n in sorted(by_sev.items())) + ". Responders: "
                 + ", ".join(f"{w} ({n})" for w, n in sorted(people.items())) + ".")
        chain = [ChainLink(f"{i.key} {i.severity}, opened {i.opened_at:%d %b %Y %H:%M} IST, {i.service or 'service ?'}, "
                           f"responder {_who(a, i.responder_alias)}", [evs[i.evidence_id].evidence_key])
                 for i in chosen[:15]]
        if len(chosen) > 15:
            chain.append(ChainLink(f"{len(chosen) - 15} more incidents", _keysort(evs[i.evidence_id]
                                                                                 for i in chosen[15:])))
        if unlinked_names:
            weak += " Some responder names are not linked to a person: " + ", ".join(unlinked_names) + "."
        ans = a.new(short, evidence_chain=chain, weakest_link=weak, **ans_kw)
    if period and period.assumed_year:
        ans.warnings.append(f"Read the period as {period.label} (no year was given).")
    if period is None:
        ans.warnings.append("No period was named, so every incident known is counted.")
    if cov.contradicted:
        ans.warnings.append(f"The file name {cov.contradicted} does not match the incidents in it; coverage is "
                            "taken from the incidents instead.")
    return ans


@dataclass(frozen=True)
class Coverage:
    start: datetime
    end: datetime
    basis: str
    contradicted: str | None = None   # a file name whose months the file's own incidents contradict


def incident_coverage(opened: list[datetime], filenames: list[str]) -> Coverage:
    """The period the incident records cover.

    1. The months a file name states (Incidents_Aug-Oct_2026.xlsx), when every incident in
       the records falls inside them.
    2. Otherwise the whole months of the first and last incident. A file name that its own
       incidents contradict is not used, and the answer says so.
    Inside the coverage, no incident means "none recorded"; outside it, "coverage unavailable".
    """
    lo, hi = min(opened), max(opened)
    observed = Coverage(_month_start(lo), _month_end(hi),
                        f"the months of the first and last incident known ({d(lo)}, {d(hi)}), since the export "
                        "does not state its coverage")
    named = [(f, c) for f in filenames if (c := coverage_from_name(f))]
    if not named:
        return observed
    start, end = min(c[0] for _, c in named), max(c[1] for _, c in named)
    if all(start <= t <= end for t in opened):
        return Coverage(start, end, "as the file name states (" + ", ".join(f for f, _ in named) + ")")
    names = ", ".join(f for f, _ in named)
    return Coverage(observed.start, observed.end,
                    f"the months of the first and last incident known ({d(lo)}, {d(hi)}). The file name "
                    f"({names}) is not used: the file holds incidents outside the months it names", names)


def _month_start(t: datetime) -> datetime:
    return datetime(t.year, t.month, 1)


def _month_end(t: datetime) -> datetime:
    nxt = (t.replace(day=28) + timedelta(days=4)).replace(day=1)
    return datetime(nxt.year, nxt.month, 1) - timedelta(seconds=1)


def coverage_from_name(filename: str) -> tuple[datetime, datetime] | None:
    """'Incidents_Aug-Oct_2026.xlsx' -> 1 Aug 2026 to the end of 31 Oct 2026. Exact pattern only."""
    from app.answering.parse import _MONTHS
    m = re.search(r"_([A-Za-z]{3,9})-([A-Za-z]{3,9})_(\d{4})\b", filename)
    if not m:
        return None
    a, b, year = _MONTHS.get(m.group(1).lower()), _MONTHS.get(m.group(2).lower()), int(m.group(3))
    if not a or not b or b < a:
        return None
    return datetime(year, a, 1), _month_end(datetime(year, b, 1))


def _span(period) -> str:
    if period is None:
        return "in all records known"
    if " to " in period.label:
        return "from " + period.label
    return ("on " if period.label[0].isdigit() else "in ") + period.label


# ---------------------------------------------------------------- release date (Atlas GA)

RELEASE_WORDS = ("GA", "general availability", "release", "ship", "go live")


@dataclass
class ReleaseView:
    version: str
    current: Claim | None
    history: list[Claim]
    original: Claim | None
    changed_by: str | None
    evidence: dict[int, Evidence]


def release_views(a: Ask) -> tuple[list[ReleaseView], list[str]]:
    """Release-date claims per version, at the time frame. Returns (views, all versions known)."""
    s, ctx = a.session, a.ctx
    stmt = select(Claim).join(Evidence, Claim.evidence_id == Evidence.id) \
        .join(SourceRecord, Evidence.source_record_id == SourceRecord.id).where(Claim.subject_type == "release")
    claims = s.scalars(policy.apply(released_by(stmt, Claim, ctx.release_cutoff)).order_by(Claim.id)).all()
    versions = sorted({c.subject_key for c in claims})
    wanted = versions
    if a.ents.projects:
        keys = {p.upper() for p in a.ents.projects}
        tickets = s.scalars(released_by(select(Ticket.fix_version).where(Ticket.project_key.in_(keys)),
                                        Ticket, ctx.release_cutoff)).all()
        wanted = [v for v in versions if any(p in v.lower() for p in a.ents.projects) or v in set(tickets)]
    evs = usable(s, ctx if ctx.mode is Mode.KNOWN else TimeContext.known_at(ctx.release_cutoff),
                 [c.evidence_id for c in claims])
    views = []
    for v in wanted:
        mine = [c for c in claims if c.subject_key == v and c.evidence_id in evs]
        cur = [c for c in mine if c.attribute == "release_date"]
        if ctx.mode is Mode.RECORDED:
            cur = [c for c in cur if c.exported_on and c.exported_on <= ctx.as_of]
        cur.sort(key=lambda c: (c.exported_on or datetime.min, c.id))
        orig = [c for c in mine if c.attribute == "original_release_date"] if ctx.mode is Mode.KNOWN else []
        by = [c for c in mine if c.attribute == "changed_by" and (ctx.mode is Mode.KNOWN or (
            c.exported_on and c.exported_on <= ctx.as_of))]
        views.append(ReleaseView(v, cur[-1] if cur else None, cur, orig[-1] if orig else None,
                                 by[-1].value if by else None, evs))
    return views, versions


def _claim_quote(ev: Evidence, value: str) -> str | None:
    for part in ev.content.split("; "):
        if value in part:
            return part.strip()
    return None


def release_date(a: Ask) -> Answer:
    views, versions = release_views(a)
    topic = " ".join(a.ents.projects) or ""
    stmts = statements(a, f"{topic} GA release".strip(), RELEASE_WORDS)
    stmt_links = [statement_link(h, RELEASE_WORDS) for h in stmts]
    weak = ("Jira shows only the current and the original date, not each change between them. Statements in "
            "emails, board updates and transcripts are quoted as written, not read as dates.")
    change = "A Jira version history, or a dated announcement of a new GA date."
    found = [v for v in views if v.current or v.original]
    if not found:
        what = f"for {topic.title()} " if topic else ""
        if not stmts:
            return _none(a, f"No release date {what}is recorded at this date.", change)
        first = stmts[0].citation
        extra = ""
        if versions and a.ents.projects and not views:
            extra = " Known release versions: " + ", ".join(versions) + "."
        if a.ctx.mode is Mode.RECORDED and views:
            extra += " Jira's original date has no recorded time, so it is not used for this date."
        ans = a.new(f"No Jira release date {what}is recorded at this date. {len(stmts)} other record(s) mention the "
                    f"release; the earliest is {first.filename} ({d(first.exported_on) if first.exported_on else 'undated'})."
                    f"{extra} Their words are quoted below, not read as a date.", status="uncertain",
                    evidence_chain=[statement_link(h, RELEASE_WORDS, role="support") for h in stmts],
                    weakest_link=weak, would_change_mind=change)
        ans.factors = Factors(completeness="partial")
        return ans

    parts, chain = [], []
    f = Factors()
    if re.search(HISTORY, a.question, re.I):
        f.completeness = "partial"
        f.notes.append("Jira holds no history of the date between its original and current values")
    for v in found:
        if v.current is None:
            parts.append(f"{v.version}: no current release date is recorded by {d(a.ctx.as_of)}")
            continue
        cur = v.current
        ev = v.evidence[cur.evidence_id]
        line = f"{v.version}: GA date {d(date.fromisoformat(cur.value))} in Jira"
        if cur.exported_on:
            line += f" (last changed {d(cur.exported_on)}" + (f" by {v.changed_by})" if v.changed_by else ")")
        earlier = [c for c in v.history[:-1] if c.value != cur.value]
        if earlier:
            line += "; earlier exports showed " + ", ".join(d(date.fromisoformat(c.value)) for c in earlier)
        chain.append(ChainLink(f"{v.version} release date in Jira", [ev.evidence_key], _claim_quote(ev, cur.value)))
        for c in earlier:
            e2 = v.evidence[c.evidence_id]
            chain.append(ChainLink(f"Earlier export of {v.version}", [e2.evidence_key], _claim_quote(e2, c.value)))
        if v.original and v.original.value != cur.value:
            line += f". The original date was {d(date.fromisoformat(v.original.value))}"
            oe = v.evidence[v.original.evidence_id]
            chain.append(ChainLink(f"{v.version} original release date in Jira", [oe.evidence_key],
                                   _claim_quote(oe, v.original.value)))
        elif v.original:
            line += " (unchanged from the original)"
        parts.append(line)
    if a.ctx.mode is Mode.RECORDED:
        f.notes.append("Jira's original date has no recorded time, so it is not used in recorded-by mode")
    # Corroboration: a statement from another system that gives the same current date.
    current = next((v.current for v in found if v.current), None)
    agreeing = []
    if current is not None:
        cur_day = date.fromisoformat(current.value)
        for h, link in zip(stmts, stmt_links):
            form = same_date_in(h.content, cur_day)
            if form:
                link.role, link.quote = "support", quote_from(h.content, [form])
                link.statement = f"{h.citation.filename} gives the same date"
                agreeing.append(h.citation.filename)
    f.corroborated = bool(agreeing)
    short = ". ".join(parts) + "."
    if agreeing:
        short += f" {', '.join(agreeing)} states the same date."
    others = len(stmts) - len(agreeing)
    if others:
        short += f" {others} other dated or transcript record(s) mention the release; see the chain."
    ans = a.new(short, evidence_chain=chain + stmt_links, weakest_link=weak, would_change_mind=change)
    ans.factors = f
    return ans


HISTORY = r"\b(change|changed|changes|history|moved?|slip|slipped|original|originally|delay|delayed|over time)\b"


def same_date_in(content: str, day: date) -> str | None:
    """The form in which `content` states `day` (e.g. '15 December'), or None. Exact forms only."""
    forms = [day.isoformat(), f"{day.day} {day:%B}", f"{day.day} {day:%b}", f"{day:%B} {day.day}",
             f"{day:%b} {day.day}"]
    for form in forms:
        if re.search(rf"(?<![\w-]){re.escape(form)}(?![\w-])", content, re.I):
            return form
    return None


# ---------------------------------------------------------------- marketing launch readiness

READY = {"ready", "done", "complete", "completed"}
_STATUS = r"ready|done|complete(?:d)?|draft|in progress|not started|pending|tbc|tbd|blocked|waiting|on hold"
_ITEM_LINE = re.compile(rf"^[ \t]*(?P<item>[A-Za-z][^:\n|]{{0,60}}?)[ \t]*[:|][ \t]*(?P<status>{_STATUS})\b(?P<rest>[^\n]*)$",
                        re.I | re.M)
_SKIP_ITEMS = {"owner", "dated", "date", "version", "sent", "from", "to", "subject"}


def kit_items(ev: Evidence) -> list[tuple[str, str, str, str]]:
    """(item, status, rest, exact quote) for each status line in a launch kit page.

    Two layouts are read: "Deck: Ready" on one line, and a two-column table whose text
    comes out as the item on one line and its status on the next. The quote is always an
    exact substring of the page."""
    out = []
    for m in _ITEM_LINE.finditer(ev.content):
        item = m.group("item").strip()
        if item.lower() in _SKIP_ITEMS:
            continue
        out.append((item, m.group("status").strip(), m.group("rest").strip(), m.group(0).strip()))
    if out:
        return out
    lines = list(re.finditer(r"[^\n]+", ev.content))
    status_re = re.compile(rf"^\s*(?P<status>{_STATUS})\b(?P<rest>.*)$", re.I)
    for prev, cur in zip(lines, lines[1:]):
        item, sm = prev.group(0).strip(), status_re.match(cur.group(0))
        if not sm or not item or status_re.match(item) or item.lower() in _SKIP_ITEMS | {"asset", "item"} \
                or ":" in item:
            continue
        out.append((item, sm.group("status").strip(), sm.group("rest").strip(),
                    ev.content[prev.start():cur.end()].strip()))
    return out


def _planned(text: str, year: int) -> tuple[date | None, str | None]:
    m = re.search(r"planned\s*(?:for\s*)?(\d{1,2})\s+([A-Za-z]{3,9})(?:\s+(\d{4}))?", text, re.I)
    if not m:
        return None, None
    from app.answering.parse import _MONTHS
    mo = _MONTHS.get(m.group(2).lower())
    if not mo:
        return None, None
    try:
        return date(int(m.group(3) or year), mo, int(m.group(1))), m.group(0)
    except ValueError:
        return None, None


def launch_readiness(a: Ask) -> Answer:
    s, ctx = a.session, a.ctx
    stmt = select(Evidence).join(SourceRecord, Evidence.source_record_id == SourceRecord.id) \
        .where(SourceRecord.filename.ilike("%launch%kit%"))
    kits = s.scalars(policy.apply(visible(stmt, Evidence, ctx)).order_by(Evidence.id)).all()
    change = "A newer launch kit, or a dated launch plan agreed with engineering."
    if not kits:
        words = ("launch", "ready", "kit")
        stmts = statements(a, "launch kit ready", words, exclude_systems=())
        if not stmts:
            return _none(a, "No launch kit or launch readiness record is known at this date.", change)
        ans = a.new(f"No launch kit document is known at this date. {len(stmts)} record(s) mention launch "
                    "readiness; their words are quoted below.", status="uncertain",
                    evidence_chain=[statement_link(h, words, role="support") for h in stmts],
                    weakest_link="Statements only; no kit with item statuses.", would_change_mind=change)
        ans.factors = Factors(completeness="partial")
        return ans
    latest_src = max({e.source for e in kits}, key=lambda src: (src.exported_on or src.released_on, src.id))
    pages = [e for e in kits if e.source_record_id == latest_src.id]
    kit_date = latest_src.exported_on
    items = [(e, *it) for e in pages for it in kit_items(e)]
    if not items:
        ans = a.new(f"A launch kit is on record ({latest_src.filename}, {d(kit_date)}), but its status lines could "
                    "not be read. Its opening words are quoted below.", status="uncertain",
                    evidence_chain=[ChainLink("Launch kit", [pages[0].evidence_key], first_line(pages[0].content))],
                    weakest_link="The kit's layout was not recognised.", would_change_mind=change)
        ans.factors = Factors(completeness="insufficient")
        return ans
    ready = [it for it in items if it[2].lower() in READY]
    not_ready = [it for it in items if it[2].lower() not in READY]
    chain = [ChainLink(f"Kit item '{it[1]}': {it[2]}", [it[0].evidence_key], it[4]) for it in items]
    parts = [f"the launch kit ({latest_src.filename}, dated {d(kit_date)}) marks {len(ready)} of {len(items)} items "
             "ready" + (": not ready are " + ", ".join(f"{it[1]} ({it[2]})" for it in not_ready) if not_ready else "")]
    year = (kit_date or ctx.as_of).year
    planned = None
    for e in pages:
        planned, _ = _planned(e.content, year)
        if planned:
            break
    f = Factors()
    late = False
    if planned:
        parts.append(f"its planned launch date was {d(planned)}" +
                     (", which has passed" if planned < ctx.as_of.date() else ""))
    views, _ = release_views(a)
    ga = next((v for v in views if v.current), None)
    if ga:
        ga_date = date.fromisoformat(ga.current.value)
        gev = ga.evidence[ga.current.evidence_id]
        chain.append(ChainLink(f"Current GA date for {ga.version} in Jira", [gev.evidence_key],
                               _claim_quote(gev, ga.current.value)))
        if planned and ga_date > planned:
            late = True
            text = f"Jira's GA date is {d(ga_date)}, after the kit's planned date"
            if kit_date and ga.current.exported_on and kit_date < ga.current.exported_on:
                text += (f", and it was set on {d(ga.current.exported_on)}, after the kit was written; no later "
                         "kit is in the records")
                f.completeness = "partial"
                f.notes.append("The kit predates the latest GA change")
            parts.append(text)
    owner_m = None
    for e in pages:
        owner_m = re.search(r"\bOwner\s*[:\-]\s*([A-Z][A-Za-z'-]*(?: [A-Z][A-Za-z'-]*)?)", e.content)
        if owner_m:
            break
    if owner_m:
        name = owner_m.group(1).rstrip(".")
        r = resolve_person(s, name, ctx)
        if r.status == "resolved":
            p = r.person
            pev = usable(s, ctx, [p.source_evidence_id])
            if p.exit_date:
                verb = "left on" if p.exit_date <= ctx.as_of.date() else "has an exit date of"
                parts.append(f"its owner, {p.full_name}, {verb} {d(p.exit_date)}")
                if pev:
                    chain.append(ChainLink(f"{p.full_name}'s employee record (exit date)", _keysort(pev.values()),
                                           role="context"))
            if r.confidence != "H":
                f.notes.append(f"Kit owner '{name}' linked to {p.full_name} at confidence {r.confidence}")
        else:
            parts.append(f"its owner is written as '{name}', not linked to a known person")
    verdict = "Not ready on the records" if (not_ready or late) else "Ready on the records"
    short = f"{verdict}: " + "; ".join(parts) + "."
    ans = a.new(short, evidence_chain=chain,
                weakest_link=f"The kit is dated {d(kit_date)} and no later version is in the records, so later "
                             "progress is not shown.", would_change_mind=change)
    ans.factors = f
    return ans


# ---------------------------------------------------------------- ownership (the only purpose-limited path)

OWN_WORDS = ("own", "owns", "owner", "ownership", "lead", "leads")
_DONE = {"done", "closed", "resolved"}


def ownership(a: Ask) -> Answer:
    s, ctx = a.session, a.ctx
    keys = {p.upper() for p in a.ents.projects}
    rows = s.scalars(visible(select(Ticket).where(Ticket.project_key.in_(keys)), Ticket, ctx).order_by(Ticket.key)).all()
    evs = usable(s, ctx, [t.evidence_id for t in rows])
    rows = [t for t in rows if t.evidence_id in evs]
    topic = " ".join(a.ents.projects)
    stmts = statements(a, f"{topic} owner owns ownership leads", OWN_WORDS, purpose=a.intent.purpose,
                       require=tuple(a.ents.projects))
    change = "A named owner in a plan or announcement, or a Jira history that shows reassignment."
    if not rows and not stmts:
        return _none(a, f"No ticket or statement about {topic.title()} ownership is known at this date.", change)
    chain, parts = [], []
    f = Factors(completeness="partial", notes=["Ticket assignment shows who holds work, not who decides"])
    if rows:
        groups: dict[str, list[Ticket]] = {}
        for t in rows:
            groups.setdefault(t.assignee_alias or "(unassigned)", []).append(t)
        open_total = sum(1 for t in rows if t.status.lower() not in _DONE)
        named = []
        for alias, ts in groups.items():
            who = _who(a, alias) if alias != "(unassigned)" else "unassigned"
            n_open = sum(1 for t in ts if t.status.lower() not in _DONE)
            named.append((len(ts), n_open, who, alias, ts))
        named.sort(key=lambda x: (-x[0], -x[1], x[2]))
        top = named[0]
        parts.append(f"In Jira, {top[2]} holds the most {topic.title()} tickets: {top[0]} of {len(rows)}, "
                     f"{top[1]} of the {open_total} open")
        if len(named) > 1:
            parts.append("others: " + ", ".join(f"{w} {n}" for n, _, w, _, _ in named[1:]))
        for n, n_open, who, alias, ts in named:
            chain.append(ChainLink(f"{who}: {n} ticket{'s' if n != 1 else ''}, {n_open} open",
                                   _keysort(evs[t.evidence_id] for t in ts)))
        r = resolve_person(s, top[3], ctx) if top[3] != "(unassigned)" else None
        f.identity = r.confidence if r and r.status == "resolved" else "L"
    if stmts:
        parts.append(f"{len(stmts)} record(s) speak to ownership; their words are quoted below")
        chain += [statement_link(h, OWN_WORDS) for h in stmts]
    snap = _snapshot_date(evs.values())
    ans = a.new("; ".join(parts) + ".", evidence_chain=chain,
                weakest_link=(f"Jira is a snapshot (exported {d(snap)}): it shows who holds tickets at export, not "
                              "who owns decisions." if snap else "Statements only; no ticket records."),
                would_change_mind=change)
    ans.factors = f
    return ans


# ---------------------------------------------------------------- source disagreement

_DISAGREE_WORDS = re.compile(C.DISAGREE + r"|\b(sources?|records?|any|there|about|on|over|between)\b", re.I)


def disagreement(a: Ask) -> Answer:
    s, ctx = a.session, a.ctx
    rest = _DISAGREE_WORDS.sub(" ", a.question)
    terms = fts.terms(rest)
    if terms:
        try:
            r = search(s, " ".join(terms), ctx, limit=30)
            found = conflicts_for(s, ctx, _ids_for(s, [h.citation.evidence_key for h in r.hits]))
        except SearchError:
            found = []
    else:
        found = conflicts_for(s, ctx, s.scalars(select(ConflictSide.evidence_id)).all())
    about = f" about {' '.join(terms)}" if terms else ""
    if not found:
        return _none(a, f"No recorded disagreement{about} is known at this date.",
                     "Two records found to differ on the same fact.",
                     weak="Conflicts are recorded where ingestion finds two records that differ on the same key, "
                          "or in the reviewed conflict file; a disagreement in prose is not detected automatically.")
    chain, lines = [], []
    for ref, sides in found[:5]:
        by_key = {e.evidence_key: e for e in sides.values()}
        for side, key, summary in ref.sides:
            chain.append(ChainLink(f"{ref.conflict_key} side {side}: {summary}", [key],
                                   ref.quotes.get(key) or first_line(by_key[key].content), role="support"))
        lines.append(f"{ref.title}. " + conflict_sentence(ref, by_key))
    overturn = [f"{ref.conflict_key}: {ref.would_overturn}" for ref, _ in found[:5] if ref.would_overturn]
    ans = a.new(f"Yes: {len(found)} recorded disagreement(s){about}. " + " ".join(lines[:3]),
                evidence_chain=chain, conflicts=[ref for ref, _ in found],
                weakest_link="For an open conflict, which side is right is not settled. A working position is "
                             "what is relied on meanwhile, not a resolution.",
                would_change_mind="; ".join(overturn) if overturn else "A record that settles which side is right.")
    return ans


def conflict_sentence(ref, by_key: dict[str, Evidence]) -> str:
    """Both (or all) sides of a conflict, grouped by side, with any resolution or working position."""
    groups: dict[str, list[tuple[str, str, str]]] = {}
    for side, key, summary in ref.sides:
        groups.setdefault(side, []).append((key, by_key[key].source.filename, summary))
    parts = []
    for side, rows in groups.items():
        files = ", ".join(sorted({f for _, f, _ in rows}))
        what = rows[0][2] if len(rows) == 1 else f"{len(rows)} records"
        parts.append(f"side {side} {', '.join(k for k, _, _ in rows)} ({files}): {what}")
    text = f"The records disagree ({ref.conflict_key}, {ref.status}): " + "; ".join(parts) + "."
    if ref.resolution:
        label = "Resolved" if ref.status == "resolved" else "Working position, not a resolution"
        text += f" {label}: {ref.resolution.rstrip('.')}."
    return text


def _ids_for(session: Session, keys: list[str]) -> list[int]:
    if not keys:
        return []
    return list(session.scalars(select(Evidence.id).where(Evidence.evidence_key.in_(keys))))


# ---------------------------------------------------------------- on-call (decision 30)

ROTA_SYSTEM = "Team wiki"   # OnCall_Rota.xlsx, the only approved source for who was on call
_ROTA_SHOWN = 8


@dataclass
class RotaWeek:
    start: date
    evidence: Evidence
    names: dict[str, str]   # column -> name exactly as the rota writes it

    @property
    def end(self) -> date:
        return self.start + timedelta(days=6)

    def line(self) -> str:
        return ", ".join(f"{k} {v}" for k, v in self.names.items()) or "no names"


def rota_weeks(a: Ask) -> list[RotaWeek]:
    """On-call rota rows known at this time frame, by week. Nothing else is read."""
    stmt = (select(Evidence).join(SourceRecord, Evidence.source_record_id == SourceRecord.id)
            .where(SourceRecord.system == ROTA_SYSTEM).order_by(Evidence.id))
    out = []
    for e in a.session.scalars(policy.apply(visible(stmt, Evidence, a.ctx))):
        if not e.fields_json:
            continue
        f = json.loads(e.fields_json)
        week = next((v for k, v in f.items() if normalize(k).startswith("week")), None)
        try:
            start = date.fromisoformat(str(week)[:10])
        except (TypeError, ValueError):
            continue
        names = {k: str(v) for k, v in f.items() if not normalize(k).startswith("week") and v not in (None, "")}
        out.append(RotaWeek(start, e, names))
    return sorted(out, key=lambda w: w.start)


def on_call(a: Ask) -> Answer:
    """Who the on-call rota lists for a week or a period. Commit records, incident responders and
    statements are never used in place of the rota (DECISIONS.md 30); without a rota row the
    answer says it can't tell."""
    weeks = rota_weeks(a)
    period = find_period(a.question, a.ctx.as_of)
    if period:
        lo, hi = period.start.date(), period.end.date()
        span = ("the week of " if lo == hi else "") + period.label
    else:
        lo = hi = a.ctx.as_of.date()
        span = f"the week of {d(lo)}"
    covering = [w for w in weeks if w.start <= hi and w.end >= lo]
    notes = ["The rota is a hand-copied plan, not a record of who was on call",
             "Commit records are never used to tell who was on call (DECISIONS.md 30)"]
    weak = "The rota is a hand-copied plan (Team wiki). A swap made on the day would not show in it."
    change = "A PagerDuty schedule export, or another approved record of on-call handovers."
    if not covering:
        held = (f"the rota known at this date runs from the week of {d(weeks[0].start)} to the week of "
                f"{d(weeks[-1].start)}" if weeks else "no on-call rota is known at this date")
        ans = a.new(f"I can't say who was on call in {span}: no on-call rota row known at this date covers it "
                    f"({held}). Commit records and other sources are not used in its place (DECISIONS.md 30).",
                    status="uncertain", weakest_link="The on-call rota is the only approved source for who was on "
                    "call, and it has no row for this period.", would_change_mind=change)
        ans.factors = Factors(completeness="insufficient", notes=notes[1:])
        ans.trace.append("on-call: rota rows only; none covers the period")
        return ans
    src = covering[0].evidence.source.filename
    if len(covering) == 1:
        w = covering[0]
        listed = f"for the week of {d(w.start)}: {w.line()}"
        if lo != w.start or hi != w.start:
            listed = f"for {span.removeprefix('the week of ')} (the week of {d(w.start)}): {w.line()}"
    else:
        listed = f"for {span}: " + "; ".join(f"week of {d(w.start)}: {w.line()}" for w in covering[:_ROTA_SHOWN])
        if len(covering) > _ROTA_SHOWN:
            listed += f"; and {len(covering) - _ROTA_SHOWN} more week(s), listed below"
    short = (f"The on-call rota ({src}) lists, {listed}. The rota is a hand-copied plan, not a record "
             "of who was actually on call.")
    chain = [ChainLink(f"Rota, week of {d(w.start)}: {w.line()}", [w.evidence.evidence_key],
                       first_line(w.evidence.content)) for w in covering]
    ans = a.new(short, evidence_chain=chain, weakest_link=weak, would_change_mind=change)
    complete = covering[0].start <= lo and max(w.end for w in covering) >= hi
    ans.factors = Factors(completeness="complete" if complete else "partial", notes=list(notes))
    if not complete:
        ans.warnings.append(f"The rota covers only part of {span}: weeks of {d(covering[0].start)} to "
                            f"{d(covering[-1].start)}.")
    if period and period.assumed_year:
        ans.warnings.append(f"Read the date as {period.label} (no year was given).")
    if a.ents.persons or a.ents.unknown_names:
        ans.warnings.append("Names are given as the rota writes them; they are not matched to people here.")
    ans.trace.append("on-call: rota rows only; commit records not used (DECISIONS.md 30)")
    return ans


# ---------------------------------------------------------------- workforce continuity (T6c alternative)

def _hire_rows(a: Ask) -> list[tuple[dict, Evidence]]:
    stmt = (select(Evidence).join(SourceRecord, Evidence.source_record_id == SourceRecord.id)
            .where(SourceRecord.system == "Keka Hire").order_by(Evidence.id))
    out = []
    for e in a.session.scalars(policy.apply(visible(stmt, Evidence, a.ctx))):
        if e.fields_json:
            out.append(({normalize(k): ("" if v is None else str(v)) for k, v in json.loads(e.fields_json).items()}, e))
    return out


def _concentration(a: Ask) -> list[tuple[str, int, int, list[Evidence]]]:
    """Per project: open story points held by the single largest assignee, when 40% or more. No name."""
    rows = a.session.scalars(visible(select(Ticket), Ticket, a.ctx).order_by(Ticket.key)).all()
    evs = usable(a.session, a.ctx, [t.evidence_id for t in rows])
    out = []
    for proj in sorted({t.project_key for t in rows if t.evidence_id in evs}):
        open_rows = [t for t in rows if t.project_key == proj and t.evidence_id in evs and t.story_points
                     and t.status.lower() not in _DONE]
        pts = Counter()
        for t in open_rows:
            if t.assignee_alias:
                pts[t.assignee_alias] += t.story_points
        total = sum(t.story_points for t in open_rows)
        if len(open_rows) >= 3 and pts and total and max(pts.values()) / total >= 0.4:
            out.append((proj, max(pts.values()), total, [evs[t.evidence_id] for t in open_rows]))
    return out


def _reported_events(a: Ask) -> list[tuple[Claim, dict, Evidence]]:
    """CEO-reported events (DECISIONS.md 33): known at this time frame, with a usable source."""
    rows = a.session.scalars(released_by(select(Claim).where(Claim.subject_type == "reported_event"), Claim,
                                         a.ctx.release_cutoff).order_by(Claim.id)).all()
    evs = usable(a.session, a.ctx, [c.evidence_id for c in rows])
    return [(c, json.loads(c.value), evs[c.evidence_id]) for c in rows if c.evidence_id in evs]


def workforce_continuity(a: Ask) -> Answer:
    """An aggregate view from documented records: departures, roles, contractors and concentrated work.
    No one is scored, ranked or predicted (DECISIONS.md 34)."""
    s, ctx = a.session, a.ctx
    chain, parts = [], []
    people = s.scalars(released_by(select(Person).where(Person.worker_type == "employee",
                                                        Person.exit_date.is_not(None)), Person, ctx.release_cutoff)
                       .order_by(Person.exit_date, Person.id)).all()
    pev = usable(s, ctx, [p.source_evidence_id for p in people])
    people = [p for p in people if p.source_evidence_id in pev]
    gone = [p for p in people if p.exit_date <= ctx.as_of.date()]
    due = [p for p in people if p.exit_date > ctx.as_of.date()]
    if gone or due:
        bits = [f"{p.title or 'a role'} (exit {d(p.exit_date)})" for p in gone + due]
        parts.append(f"{len(gone)} confirmed departure(s) and {len(due)} confirmed upcoming exit(s) in the HR records: "
                     + ", ".join(bits))
        chain.append(ChainLink("Exit dates in the HR records", _keysort(pev[p.source_evidence_id] for p in gone + due)))
    else:
        parts.append("no confirmed departure in the HR records known at this date")
    hires = _hire_rows(a)
    if hires:
        by = Counter(f.get("status") or "status not written" for f, _ in hires)
        held = [(f, e) for f, e in hires if f.get("status", "").lower() in ("on hold", "open")]
        parts.append("requisitions: " + ", ".join(f"{n} {st.lower()}" for st, n in sorted(by.items())) + (
            " (" + "; ".join(f"{f.get('role') or f.get('req id')}, {f.get('team') or 'team not written'}, "
                             f"{f.get('status').lower()} since {f.get('status date') or 'an unwritten date'}"
                             + (f", note: {f['notes']}" if f.get("notes") else "") for f, _ in held) + ")" if held else ""))
        chain.append(ChainLink("Requisitions in the hiring tracker", _keysort(e for _, e in hires)))
    for proj, top, total, evs in _concentration(a):
        parts.append(f"one person holds {top} of the {total} open {proj} story points ({round(100 * top / total)}%)")
        chain.append(ChainLink(f"Open {proj} stories in Jira", _keysort(evs)))
    contractors = s.scalars(select(Person).where(Person.worker_type == "contractor",
                                                 Person.released_on <= ctx.release_cutoff)).all()
    cev = usable(s, ctx, [p.source_evidence_id for p in contractors])
    contractors = [p for p in contractors if p.source_evidence_id in cev]
    if contractors:
        parts.append(f"{len(contractors)} contractor(s) ({', '.join(sorted({p.title or 'role not written' for p in contractors}))}),"
                     " not counted as staff")
        chain.append(ChainLink("Contractor records", _keysort(cev.values()), role="context"))
    reports = _reported_events(a)
    if reports:
        parts.append(f"{len(reports)} resignation(s) reported in a CEO voice note and not verified by any HR record")
        chain.append(ChainLink("CEO-reported, not verified", _keysort(e for _, _, e in reports), role="context"))
    if not chain:
        return _none(a, "No HR, hiring or Jira record is known at this date, so continuity can't be described.",
                     "Keka, Keka Hire or Jira exports.")
    ans = a.new("Workforce continuity from the records, with no one scored or ranked: " + "; ".join(parts) + ".",
                evidence_chain=chain,
                weakest_link="These are documented facts only. Nothing here predicts who will leave, and no succession "
                             "or handover plan is in the records.",
                would_change_mind="An HR record of a departure, a requisition status change, or a documented "
                                  "handover plan.")
    ans.factors = Factors(completeness="partial", notes=["No individual is scored or ranked (DECISIONS.md 34)"])
    return ans


# ---------------------------------------------------------------- reported departure and its impact (T6d)

_V3_NAME = r"\b(v ?3|version (3|three))\b"
_LEAD_WORDS = ("leads", "lead", "owns", "owner", "responsible")
_HANDOVER = ("handover", "hand over", "backup", "back-up", "deputy", "succession", "cover for")
_NOT_NAMES = {"Bad", "Good", "News", "Notice", "What", "When", "Who", "How", "If", "I", "The", "She", "He", "They",
              "Someone", "Anyone", "Version", "Board", "So", "Okay", "Ok", "Update"}


def departure_impact(a: Ask) -> Answer:
    """What a reported (or hypothetical) departure does to the work, from records only.

    The report is a CEO assertion, never applied (DECISIONS.md 33): no Person, status, exit date or last
    working day is changed or worked out. A name links to a person only as the reviewed aliases allow at
    this time frame, and the answer says how. Only Jira assignments, documented responsibilities (rung 1-4,
    never Git or transcripts), release dates and stored conflicts are used."""
    s, ctx = a.session, a.ctx
    chain, parts, missing, notes, conflict_refs = [], [], [], [], []
    reports = _reported_events(a)
    m = a.ents.first_person()
    near = re.search(r"\b([A-Z][A-Za-z'-]+(?: [A-Z][A-Za-z'-]+)?)(?:'s)?\s+(?:has\s+|have\s+|just\s+)?"
                     r"(?:resign|quit|leav|left|handed)", a.question)
    if m is not None:
        name = m.text
    elif near and near.group(1).split()[0] not in _NOT_NAMES:
        name = near.group(1)
    else:
        name = next((n for n in a.ents.unknown_names if n not in _NOT_NAMES), None)
    if name is None and len(reports) == 1:
        name = reports[0][1]["name_as_written"]
    mine = [r for r in reports if name and normalize(r[1]["name_as_written"]) == normalize(name)]

    # 1. what has been reported
    if mine:
        c, v, ev = mine[0]
        quote = quote_from(ev.content, ["resigned", "resign"]) or first_line(ev.content)
        parts.append(f"Reported, not verified: a CEO voice note ({ev.source.filename}, known from "
                     f"{c.released_on:%d %b %Y %H:%M} IST; recording date unknown) says {quote.strip(chr(34))!r}"
                     + (f", and gives the notice period as {v['notice_as_written']!r}" if v.get("notice_as_written")
                        else "") + ".")
        chain.append(ChainLink("CEO-reported, not verified (DECISIONS.md 33)", [ev.evidence_key], quote, role="context"))
        missing += ["an HR record of the resignation", "the notice period", "a last working day"]
    else:
        parts.append("No record of this departure is known at this date; the question's own statement is treated as "
                     "unverified.")
        missing += ["any record of the departure"]

    # 2. identity, as the reviewed aliases allow at this time frame
    person, identity = None, "L"
    if name is None:
        parts.append("No name is given, so no person is identified.")
    else:
        res = resolve_person(s, name, ctx)
        if res.status == "resolved":
            person, identity = res.person, res.confidence or "L"
            alias = s.scalars(released_by(select(Alias).where(Alias.normalized == normalize(name),
                                                              Alias.status == "resolved"), Alias,
                                          ctx.release_cutoff)).first()
            if res.method == "alias" and alias is not None:
                parts.append(f"Identity: '{name}' links to {person.full_name} ({person.emp_id}) only through a reviewed "
                             f"{alias.kind.replace('_', ' ')} alias at confidence {alias.confidence}, known from "
                             f"{alias.released_on:%d %b %Y %H:%M} IST. It is a spelling, not an HR record, so the "
                             "identity is probable, not established.")
            else:
                parts.append(f"Identity: '{name}' matches {person.full_name} ({person.emp_id}) "
                             f"({res.method or 'exact name'}, confidence {identity}).")
        elif res.status == "ambiguous":
            parts.append(f"Identity: '{name}' could be more than one person, so the person is not identified.")
            missing.append("who the report is about")
        else:
            parts.append(f"Identity: '{name}' is not linked to any known person at this date, so the person is not "
                         "identified.")
            missing.append("who the report is about")

    # 3. HR status, unchanged
    if person is not None:
        pev = usable(s, ctx, [person.source_evidence_id])
        if pev:
            hr = pev[person.source_evidence_id]
            status = person.employment_status or "status not written"
            parts.append(f"HR record: Keka (exported {d(hr.exported_on)}) shows {person.full_name} as '{status}'"
                         + (f" with exit date {d(person.exit_date)}" if person.exit_date else " with no exit date")
                         + (". The export predates the report, so it neither confirms nor rules it out; no exit date or "
                            "last working day is set or worked out from the reported notice period." if mine else
                            ". No departure is recorded, and none is assumed."))
            chain.append(ChainLink(f"{person.full_name}'s Keka record", [hr.evidence_key]))

    # 4. which project "version three" is, from the records
    projects: dict[str, list[str]] = {}
    v3_links = []
    if re.search(C.VERSION, a.question, re.I):
        epics = s.scalars(released_by(select(Claim).where(Claim.subject_type == "epic", Claim.attribute == "name"),
                                      Claim, ctx.release_cutoff).order_by(Claim.subject_key)).all()
        eev = usable(s, ctx, [c.evidence_id for c in epics])
        for c in epics:
            if c.evidence_id in eev and re.search(_V3_NAME, c.value, re.I):
                projects.setdefault(c.subject_key.split("-")[0], []).append(c.value)
                v3_links.append(ChainLink(f"Jira epic {c.subject_key}: {c.value}", [eev[c.evidence_id].evidence_key]))
        board = [h for h in statements(a, "v3 version three", ("v3",), exclude_systems=("Jira", C.COMMIT_SYSTEM),
                                       limit=3) if (h.citation.trust_rung or 5) <= 2]
        v3_links += [statement_link(h, ("v3",), role="support") for h in board]
        if not projects:
            missing.append("which project 'version three' is")
            parts.append("Version three: no record known at this date ties it to a project, so its impact is not "
                         "established.")
        else:
            parts.append("Version three: the records tie it to " + ", ".join(
                f"{p} (Jira epics {', '.join(repr(n) for n in names)})" for p, names in sorted(projects.items()))
                + (" and the board update calls Atlas 'routing engine v3'" if board else "") + ".")
            chain += v3_links
    elif person is not None:
        held = s.scalars(visible(select(Ticket.project_key), Ticket, ctx)).all()
        projects = {p: [] for p in sorted(set(held))}

    # 5. the person's evidenced work on it
    if person is not None and projects:
        rows = s.scalars(visible(select(Ticket).where(Ticket.project_key.in_(list(projects))), Ticket, ctx)
                         .order_by(Ticket.key)).all()
        tev = usable(s, ctx, [t.evidence_id for t in rows])
        rows = [t for t in rows if t.evidence_id in tev]
        links = {al: resolve_person(s, al, ctx) for al in {t.assignee_alias for t in rows if t.assignee_alias}}
        theirs = [t for t in rows if t.assignee_alias and links[t.assignee_alias].person
                  and links[t.assignee_alias].person.id == person.id]
        epic_names = {c.subject_key: c.value for c in s.scalars(released_by(
            select(Claim).where(Claim.subject_type == "epic", Claim.attribute == "name"), Claim, ctx.release_cutoff))}
        if not theirs:
            missing.append(f"any {', '.join(projects)} work assigned to {person.full_name} in Jira")
        else:
            open_all = [t for t in rows if t.status.lower() not in _DONE]
            open_mine = [t for t in theirs if t.status.lower() not in _DONE]
            pts_all, pts_mine = sum(t.story_points or 0 for t in open_all), sum(t.story_points or 0 for t in open_mine)
            export = max((tev[t.evidence_id].exported_on for t in theirs if tev[t.evidence_id].exported_on), default=None)
            text = (f"Jira (export {d(export)}): {person.full_name} is assigned {len(theirs)} of {len(rows)} "
                    f"{'/'.join(projects)} stories and holds {pts_mine} of the {pts_all} open story points "
                    f"({round(100 * pts_mine / pts_all) if pts_all else 0}%) in {len(open_mine)} open stories")
            per_epic = []
            for ek in sorted({t.epic_key for t in open_mine if t.epic_key}):
                e_all = [t for t in open_all if t.epic_key == ek]
                e_mine = [t for t in open_mine if t.epic_key == ek]
                sole = " (all of its open work)" if len(e_mine) == len(e_all) else ""
                per_epic.append(f"{epic_names.get(ek, ek)}: {sum(t.story_points or 0 for t in e_mine)} of "
                                f"{sum(t.story_points or 0 for t in e_all)} open points{sole}")
            parts.append(text + (": " + "; ".join(per_epic) if per_epic else "") + ".")
            al_conf = sorted({links[t.assignee_alias].confidence or "L" for t in theirs})
            if any(cn != "H" for cn in al_conf):
                notes.append("Some Jira initials link to the person below High confidence")
            chain.append(ChainLink(f"{person.full_name}'s open stories in Jira", _keysort(tev[t.evidence_id]
                                                                                           for t in open_mine)))
            # stored conflicts on these stories are shown, never resolved
            mine_keys = {tev[t.evidence_id].evidence_key for t in open_mine}
            for ref, sides in conflicts_for(s, ctx, [t.evidence_id for t in open_mine]):
                touched = {e.evidence_key for e in sides.values()} & mine_keys
                if not touched or ref.conflict_key in {r.conflict_key for r, _ in conflict_refs}:
                    continue
                conflict_refs.append((ref, sides))
                parts.append(f"{ref.status.capitalize()} conflict {ref.conflict_key} ({ref.title}) touches "
                             f"{len(touched)} of these stories.")
        # documented responsibilities: plans and documents only (rung 1-4), never Git or transcripts
        first = person.full_name.split()[0]
        duty = [h for h in statements(a, f"{first} leads owns", (first,) + _LEAD_WORDS,
                                      exclude_systems=("Jira", C.COMMIT_SYSTEM), limit=4, require=(first,))
                if (h.citation.trust_rung or 5) <= 4
                and any(re.search(rf"\b{w}\b", quote_from(h.content, (first,) + _LEAD_WORDS) or "", re.I)
                        for w in _LEAD_WORDS)]
        for h in duty[:2]:
            q = quote_from(h.content, (first,) + _LEAD_WORDS)
            chain.append(ChainLink(f"{h.citation.filename} ({d(h.citation.exported_on)}) says", [h.citation.evidence_key],
                                   q, role="support"))
            parts.append(f"Documented responsibility: {h.citation.filename} ({d(h.citation.exported_on)}) says "
                         f"{q!r}.")
        if not duty:
            missing.append(f"a documented responsibility for {person.full_name}")
        handover = [h for h in statements(a, "handover backup succession", _HANDOVER,
                                          exclude_systems=("Jira", C.COMMIT_SYSTEM), limit=3)
                    if (h.citation.trust_rung or 5) <= 4]
        if handover:
            chain += [statement_link(h, _HANDOVER) for h in handover]
        else:
            missing.append("a handover plan or backup owner")
        mgr = manager_as_of(s, person, ctx)
        if mgr.status == "known" and mgr.manager:
            parts.append(f"Confirm first with {mgr.manager}, the manager on record: whether the report is true and who "
                         "it is about, the notice terms and last working day, and who takes the open work.")

    # 6. delivery date for the project, as recorded
    for v in release_views(a)[0]:
        if v.current and any(p.lower() in v.version.lower() for p in projects):
            cev = v.evidence[v.current.evidence_id]
            text = f"Delivery: Jira's {v.version} date is {d(date.fromisoformat(v.current.value))}"
            if v.original and v.original.value != v.current.value:
                text += f", moved from {d(date.fromisoformat(v.original.value))}"
            parts.append(text + ".")
            chain.append(ChainLink(f"{v.version} release date in Jira", [cev.evidence_key],
                                   _claim_quote(cev, v.current.value)))
    if missing:
        parts.append("Not established: " + "; ".join(dict.fromkeys(missing)) + ".")
    ans = a.new(" ".join(parts), status="uncertain", evidence_chain=chain,
                weakest_link="The resignation rests on one CEO voice note with no recording date; no HR record confirms "
                             "it" + (f", and the name links to a person only at confidence {identity}" if person and
                                     identity != "H" else "") + ".",
                would_change_mind="An HR record of the resignation (a letter or a Keka update) naming the person, with "
                                  "the notice terms and last working day, and a documented handover of the work above.")
    ans.factors = Factors(identity=identity if person else "L", completeness="partial",
                          notes=notes + ["The reported resignation is a CEO assertion, not an HR record (DECISIONS.md 33)"])
    for ref, sides in conflict_refs:   # shown with both sides; finalize() counts them, never resolves them
        ans.conflicts.append(ref)
        for side, key, summary in ref.sides:
            if key not in ans.keys():
                ev = next((e for e in sides.values() if e.evidence_key == key), None)
                ans.evidence_chain.append(ChainLink(f"{ref.conflict_key} side {side}: {summary}", [key],
                                                    ref.quotes.get(key) or (first_line(ev.content) if ev else None),
                                                    role="conflict"))
    return ans


# ---------------------------------------------------------------- fallback: evidence search

def evidence_search(a: Ask) -> Answer:
    m = a.ents.first_person()
    filters = Filters(exclude_systems=_no_commits(a))
    name_only = None
    if m is not None:
        if m.status == "ambiguous":
            return ambiguous(a, m)
        if m.status == "resolved":
            filters.person = m.text
        else:
            name_only = m.text
    period = find_period(a.question, a.ctx.as_of)
    if period:
        filters.date_from, filters.date_to = period.start.date(), period.end.date()
    try:
        r = search(a.session, a.question, a.ctx, filters, limit=5)
    except SearchError as exc:
        ans = a.new(f"I can't answer that from the records: {exc}", status="refused", refusal="unsupported",
                    weakest_link="The question has nothing to look up.",
                    would_change_mind="A question about something the records cover.")
        ans.factors = Factors(completeness="insufficient")
        return ans
    hits = [h for h in r.hits if not h.via_conflict]
    if name_only:
        hits = [h for h in hits if re.search(rf"\b{re.escape(name_only)}\b", h.content, re.I)]
    if not hits:
        ans = _none(a, "No record known at this date answers this. Searched for: " + ", ".join(r.terms) + ".",
                    "A record that covers this question.")
        ans.warnings += r.warnings
        if name_only:
            ans.warnings.append(f"'{name_only}' is not linked to any known person; only records naming it were "
                                "used.")
        return ans
    top = hits[0]
    words = r.terms or [top.content.split()[0]]
    q = quote_from(top.content, words) or first_line(top.content)
    c = top.citation
    when = d(c.exported_on) if c.exported_on else "undated"
    chain = [ChainLink(f"Closest record: {c.filename} ({when})", [c.evidence_key], q)]
    chain += [ChainLink(f"Also mentions it: {h.citation.filename}", [h.citation.evidence_key],
                        quote_from(h.content, words), role="context") for h in hits[1:3]]
    ans = a.new(f"There is no typed answer to this. The closest record is {c.filename} ({when}), which says: "
                f"\"{' '.join(q.split())}\".", status="uncertain", evidence_chain=chain,
                weakest_link="This is the closest keyword match, not an answer worked out from typed records.",
                would_change_mind="A record that addresses the question directly.")
    ans.factors = Factors(completeness="partial")
    ans.warnings += r.warnings
    if m is not None and m.status == "resolved" and m.resolution.confidence != "H":
        ans.factors.identity = m.resolution.confidence
    if name_only:
        ans.warnings.append(f"'{name_only}' is not linked to any known person; only records naming it were used.")
    return ans


HANDLERS = {
    "refusal": refusal,
    "payroll": payroll,
    "company_headcount": company_headcount,
    "department_headcount": department_headcount,
    "manager": manager,
    "incidents": incidents,
    "on_call": on_call,
    "workforce_continuity": workforce_continuity,
    "departure_impact": departure_impact,
    "release_date": release_date,
    "launch_readiness": launch_readiness,
    "ownership": ownership,
    "disagreement": disagreement,
    "search": evidence_search,
}
