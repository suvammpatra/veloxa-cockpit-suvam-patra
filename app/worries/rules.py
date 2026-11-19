"""Candidate rules for the CEO worry list (Phase 7; DECISIONS.md 11-16, 23-30; ARCHITECTURE.md 16.16).

Each rule reads typed records and evidence through the existing time rules and returns either a
Candidate (an explanation, an evidence chain and its scoring signals) or an Excluded record that says
why no worry was raised. Missing evidence is a reason to exclude, never a risk in itself.

What the rules never read: Git commits (decision 30), the leave register, the pulse survey, payroll
rows or payroll cost lines (decision 3), 09.eml (decision 23), the on-call rota as a record of people,
and nothing about a person's hours, health, family, motivation or feelings (decisions 11, 23, 28, 29).
No worry names an employee. Every citation is checked afterwards by the answer engine's finalize().
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.answering.classify import COMMIT_SYSTEM, Intent
from app.answering.handlers import (Ask, _claim_quote, _planned, d, first_line, inr, kit_items,
                                    pending_department_lines, quote_from, release_views, statements, usable)
from app.answering.model import ChainLink, Factors
from app.answering.parse import Entities
from app.models import Department, Evidence, FinancialTxn, Incident, Person, SourceRecord, Ticket
from app.repositories.temporal import visible
from app.retrieval import policy
from app.services.identity import normalize, resolve_person
from app.temporal import TimeContext

_DONE = {"done", "closed", "resolved"}
NO_GIT = ("Jira", COMMIT_SYSTEM)   # worry rules never read Git commit records (decision 30)
_READY = {"ready", "done", "complete", "completed"}


@dataclass
class Candidate:
    key: str                 # the rule's fixed key; also the final tie-break
    area: str
    title: str
    explanation: str
    why_it_matters: str
    topic: str               # fixed words, used by finalize() to decide which conflicts are about this worry
    chain: list[ChainLink]
    impact: int              # 1-3, fixed by the rule (ARCHITECTURE.md 16.16)
    impact_reason: str
    persistence: int         # 0-2
    persistence_reason: str
    weakest_link: str
    would_change: str
    factors: Factors = field(default_factory=Factors)
    notes: list[str] = field(default_factory=list)


@dataclass
class Excluded:
    key: str
    area: str
    reason: str


def _ask(session: Session, ctx: TimeContext, topic: str) -> Ask:
    return Ask(session, topic, ctx, Entities(), Intent("worry"))


def _fields(ev: Evidence) -> dict[str, str]:
    raw = json.loads(ev.fields_json) if ev.fields_json else {}
    return {normalize(k): ("" if v is None else str(v)) for k, v in raw.items()}


def _day(text: str | None) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10]) if text else None
    except ValueError:
        return None


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


def _keys(evs) -> list[str]:
    return sorted({e.evidence_key for e in evs}, key=lambda k: int(k[1:]))


# ---------------------------------------------------------------- 1. product delivery schedule

def delivery_schedule(session: Session, ctx: TimeContext) -> Candidate | Excluded:
    key, area = "delivery_schedule", "Product delivery"
    a = _ask(session, ctx, "release GA date schedule slip feature-complete open stories")
    views, _ = release_views(a)
    slipped = []
    for v in views:
        if v.current and v.original:
            cur, orig = _day(v.current.value), _day(v.original.value)
            if cur and orig and cur > orig:
                slipped.append(((cur - orig).days, v.version, v, cur, orig))
    if not slipped:
        why = ("No release date is known at this date." if not views else
               "No known release date has moved later than its original date at this date"
               + (" (the original date has no recorded time, so recorded-by mode can't compare)."
                  if ctx.mode.value == "recorded" else "."))
        return Excluded(key, area, why)
    days, version, v, cur, orig = max(slipped, key=lambda x: (x[0], x[1]))
    cev, oev = v.evidence[v.current.evidence_id], v.evidence[v.original.evidence_id]
    chain = [ChainLink(f"{version} release date in Jira", [cev.evidence_key], _claim_quote(cev, v.current.value)),
             ChainLink(f"{version} original release date in Jira", [oev.evidence_key],
                       _claim_quote(oev, v.original.value))]
    rows = session.scalars(visible(select(Ticket).where(Ticket.fix_version == version), Ticket, ctx)
                           .order_by(Ticket.key)).all()
    evs = usable(session, ctx, [t.evidence_id for t in rows])
    rows = [t for t in rows if t.evidence_id in evs]
    open_rows = [t for t in rows if t.status.lower() not in _DONE]
    total_pts, open_pts = sum(t.story_points or 0 for t in rows), sum(t.story_points or 0 for t in open_rows)
    export = max((evs[t.evidence_id].exported_on for t in rows if evs[t.evidence_id].exported_on), default=None)
    left = (cur - ctx.as_of.date()).days
    text = f"Jira's {version} date moved from {d(orig)} to {d(cur)}"
    if v.current.exported_on:
        text += f" (changed {d(v.current.exported_on)})"
    share = None
    if open_rows and total_pts:
        share = round(100 * open_pts / total_pts)
        chain.append(ChainLink(f"{len(open_rows)} {version} stories not Done at the Jira export of {d(export)}",
                               _keys(evs[t.evidence_id] for t in open_rows)))
        text += (f". At the Jira export of {d(export)}, {open_pts} of {total_pts} story points ({share}%) were not "
                 "Done")
    text += (f"; the new date is {left} days after the as-of date." if left >= 0 else
             f"; the new date passed {-left} days before the as-of date.")
    persistence = 1 + (1 if share is not None and share > 33 else 0)
    return Candidate(
        key, area, f"{version} delivery: GA moved to {d(cur)}", text,
        f"It is the main product date and it has already moved once, by {days} days."
        + (f" {share}% of its story points were still open at the last export." if share is not None else ""),
        "release GA date schedule slip feature-complete open stories", chain,
        3, "A committed product date", persistence,
        "The date moved" + (", and over a third of its story points are open" if persistence == 2 else ""),
        f"Jira is a snapshot (exported {d(export or cev.exported_on)}): it holds only the original and current "
        "dates, and each story's status at export.",
        "A Jira export showing the open stories closed, or a dated plan confirming the current date holds.")


# ---------------------------------------------------------------- 2. service reliability

def service_reliability(session: Session, ctx: TimeContext) -> Candidate | Excluded:
    key, area = "service_reliability", "Engineering reliability"
    rows = session.scalars(visible(select(Incident), Incident, ctx).order_by(Incident.opened_at, Incident.key)).all()
    evs = usable(session, ctx, [i.evidence_id for i in rows])
    rows = [i for i in rows if i.evidence_id in evs and i.opened_at <= ctx.as_of and i.service]
    if not rows:
        return Excluded(key, area, "No incident records are known at this date.")
    best = None
    for svc in sorted({i.service for i in rows}):
        sev1 = [i for i in rows if i.service == svc and i.severity.upper() == "SEV1"]
        window = max((sum(1 for j in sev1 if 0 <= (j.opened_at - i.opened_at).days <= 31) for i in sev1), default=0)
        if window >= 2 and (best is None or window > best[0]):
            best = (window, svc, sev1)
    if best is None:
        return Excluded(key, area, "No service had two or more SEV1 incidents within 31 days in the incident "
                                   "records known at this date.")
    _, svc, sev1 = best
    later = [i for i in rows if i.service == svc and i.opened_at > sev1[-1].opened_at]
    chain = [ChainLink(f"{len(sev1)} SEV1 incident(s) on {svc} (PagerDuty, IST)",
                       _keys(evs[i.evidence_id] for i in sev1))]
    text = (f"{len(sev1)} SEV1 incidents hit {svc} between {d(sev1[0].opened_at)} and {d(sev1[-1].opened_at)}.")
    if later:
        chain.append(ChainLink(f"Later incidents on {svc}: " + ", ".join(sorted(Counter(i.severity for i in later))),
                               _keys(evs[i.evidence_id] for i in later), role="context"))
        text += (f" No later SEV1 on it is in the records known at this date, but it had {len(later)} lower-severity "
                 f"incident(s) after that, the latest on {d(later[-1].opened_at)}.")
    else:
        text += f" No later incident on {svc} is in the records known at this date."
    a = _ask(session, ctx, f"{svc} SEV1 incident outage stability")
    mentions = [h for h in statements(a, f"{svc} SEV1", (svc,), exclude_systems=NO_GIT + ("PagerDuty",), limit=2,
                                      require=(svc,)) if (h.citation.trust_rung or 5) <= 4]
    for h in mentions:
        chain.append(ChainLink(f"{h.citation.filename} ({d(h.citation.exported_on)}) mentions {svc}",
                               [h.citation.evidence_key], quote_from(h.content, [svc]), role="context"))
    months = {(i.opened_at.year, i.opened_at.month) for i in rows if i.service == svc}
    persistence = 2 if len(months) >= 3 else 1 if len(months) == 2 else 0
    return Candidate(
        key, area, f"Repeated SEV1 incidents on {svc}", text,
        "SEV1 is the highest severity in the incident export, and repeated SEV1s on one service point to a "
        "problem that may not be fixed." + (f" {len(mentions)} other record(s) tie {svc} to other work; see the "
                                            "evidence." if mentions else ""),
        f"{svc} SEV1 incident outage stability", chain,
        3, "Repeated highest-severity incidents on a production service", persistence,
        f"Incidents on {svc} in {len(months)} different month(s)",
        "Incident rows give severity, service and times only, not the cause or the effect on customers.",
        f"A later incident export with no SEV1 on {svc}, or a post-incident review showing the cause fixed.")


# ---------------------------------------------------------------- 3. engineering capacity and ownership concentration

def capacity(session: Session, ctx: TimeContext) -> Candidate | Excluded:
    key, area = "capacity", "Engineering capacity"
    topic = "backend hiring requisitions on hold open work held by one assignee"
    stmt = (select(Evidence).join(SourceRecord, Evidence.source_record_id == SourceRecord.id)
            .where(SourceRecord.system == "Keka Hire").order_by(Evidence.id))
    held = []
    for e in session.scalars(policy.apply(visible(stmt, Evidence, ctx))):
        f = _fields(e)
        since = _day(f.get("status date"))
        if f.get("status", "").lower() == "on hold" and since and (ctx.as_of.date() - since).days >= 30:
            held.append((since, f.get("team") or "a team", f.get("role") or f.get("req id") or "a role", e))
    rows = session.scalars(visible(select(Ticket), Ticket, ctx).order_by(Ticket.key)).all()
    tev = usable(session, ctx, [t.evidence_id for t in rows])
    conc = None
    for proj in sorted({t.project_key for t in rows if t.evidence_id in tev}):
        open_rows = [t for t in rows if t.project_key == proj and t.evidence_id in tev
                     and t.status.lower() not in _DONE and t.story_points]
        pts = Counter()
        for t in open_rows:
            pts[t.assignee_alias or "(unassigned)"] += t.story_points
        total = sum(pts.values())
        if len(open_rows) < 3 or not total:
            continue
        top_alias, top = max(((a_, p) for a_, p in pts.items() if a_ != "(unassigned)"), key=lambda x: (x[1], x[0]),
                             default=(None, 0))
        if top_alias and top / total >= 0.4 and (conc is None or top / total > conc[1] / conc[2]):
            conc = (proj, top, total, open_rows)
    if not held and conc is None:
        return Excluded(key, area, "No requisition has been on hold for 30 days or more, and no project's open story "
                                   "points are 40% or more with one assignee, at this date.")
    chain, parts, teams = [], [], sorted({t for _, t, _, _ in held})
    if held:
        since = min(s for s, _, _, _ in held)
        chain.append(ChainLink(f"{len(held)} requisition(s) on hold in the hiring tracker",
                               _keys(e for _, _, _, e in held)))
        parts.append(f"{len(held)} {' and '.join(teams)} requisition(s) ({', '.join(sorted({r for _, _, r, _ in held}))})"
                     f" have been on hold since {d(since)}")
        fee = [x for x in session.scalars(visible(select(FinancialTxn), FinancialTxn, ctx).order_by(FinancialTxn.txn_date))
               if re.search(r"search fee|recruit", f"{x.narration} {x.vendor}", re.I)
               and not re.search(r"payroll|salar", f"{x.cost_centre} {x.vendor}", re.I)]
        fev = usable(session, ctx, [x.evidence_id for x in fee])
        fee = [x for x in fee if x.evidence_id in fev]
        if fee:
            chain.append(ChainLink(f"Recruiting fee in the GL: {inr(sum(x.amount_paise for x in fee))}",
                                   _keys(fev[x.evidence_id] for x in fee), role="context"))
            parts[-1] += f"; the GL records {inr(sum(x.amount_paise for x in fee))} in recruiting search fees"
    if conc is not None:
        proj, top, total, open_rows = conc
        export = max((tev[t.evidence_id].exported_on for t in open_rows if tev[t.evidence_id].exported_on), default=None)
        chain.append(ChainLink(f"Open {proj} stories at the Jira export of {d(export)}",
                               _keys(tev[t.evidence_id] for t in open_rows)))
        parts.append(f"one assignee holds {top} of the {total} open {proj} story points ({round(100 * top / total)}%) "
                     f"at the Jira export of {d(export)}")
    a = _ask(session, ctx, topic)
    plan = [h for h in statements(a, "hires hiring reqs", ("hires", "hiring", "req"), exclude_systems=NO_GIT, limit=2)
            if h.citation.system == "Email"]
    for h in plan:
        chain.append(ChainLink(f"{h.citation.filename} ({d(h.citation.exported_on)})", [h.citation.evidence_key],
                               quote_from(h.content, ("hires", "hiring", "req")), role="context"))
    on_hold_days = (ctx.as_of.date() - min(s for s, _, _, _ in held)).days if held else 0
    persistence = 2 if on_hold_days >= 60 else 1
    title = ("Engineering capacity: hiring on hold" + (" and open work concentrated" if conc else "")) if held else \
        f"Open {conc[0]} work concentrated on one assignee"
    if held and "Engineering" not in teams:
        title = title.replace("Engineering", " and ".join(teams))
    return Candidate(
        key, area, title, _sentence("; ".join(parts) + "."),
        "Fewer people than planned, and much open work resting with one person, raise the chance of further "
        "delay and leave little cover." + (" Emails on the plan and the hold are quoted below." if plan else ""),
        topic, chain, 2, "Delivery capacity for planned work", persistence,
        (f"On hold for {on_hold_days} days" if held else "Concentration at one export"),
        "Jira assignment shows who holds tickets at export, not who does the work; the hiring tracker shows "
        "status, not the reason.",
        "The requisitions reopened or filled, or a Jira export showing the open work spread across more people.")


# ---------------------------------------------------------------- 4. marketing launch versus product readiness

def launch_alignment(session: Session, ctx: TimeContext) -> Candidate | Excluded:
    key, area = "launch_alignment", "Marketing launch readiness"
    stmt = (select(Evidence).join(SourceRecord, Evidence.source_record_id == SourceRecord.id)
            .where(SourceRecord.filename.ilike("%launch%kit%")))
    kits = session.scalars(policy.apply(visible(stmt, Evidence, ctx)).order_by(Evidence.id)).all()
    if not kits:
        return Excluded(key, area, "No launch kit is known at this date.")
    src = max({e.source for e in kits}, key=lambda s: (s.exported_on or s.released_on, s.id))
    pages = [e for e in kits if e.source_record_id == src.id]
    kit_date = src.exported_on
    items = [(e, *it) for e in pages for it in kit_items(e)]
    planned = next((p for p in (_planned(e.content, (kit_date or ctx.as_of).year)[0] for e in pages) if p), None)
    views = [v for v in release_views(_ask(session, ctx, "launch"))[0] if v.current]
    words = set(re.findall(r"[a-z]+", src.filename.lower()))
    match = [v for v in views if set(re.findall(r"[a-z]+", v.version.lower())) & words - {"ga", "launch", "kit", "pdf"}]
    ga_view = match[0] if len(match) == 1 else (views[0] if len(views) == 1 else None)
    ga = _day(ga_view.current.value) if ga_view else None
    owner_left, owner_ev, notes = None, None, []
    for e in pages:
        m = re.search(r"\bOwner\s*[:\-]\s*([A-Z][A-Za-z'-]*(?: [A-Z][A-Za-z'-]*)?)", e.content)
        if m:
            r = resolve_person(session, m.group(1).rstrip("."), ctx)
            if r.status == "resolved" and r.person.exit_date and r.person.exit_date <= ctx.as_of.date():
                owner_left = r.person.exit_date
                owner_ev = usable(session, ctx, [r.person.source_evidence_id])
            elif r.status != "resolved":
                notes.append("The kit's owner, as written in the kit, is not linked to a known person, so whether "
                             "the owner is still here is not known.")
            break
    late = bool(planned and ga and ga > planned)
    if not late and owner_left is None:
        return Excluded(key, area, "The launch kit's planned date is not before the product's release date, and its "
                                   "owner has not left, at this date." if planned and ga else
                        "The launch kit and the release date can't be compared at this date (one of them is missing), "
                        "and the kit's owner has not left.")
    ready = [it for it in items if it[2].lower() in _READY]
    chain = [ChainLink(f"Kit item '{it[1]}': {it[2]}", [it[0].evidence_key], it[4]) for it in items]
    if not items:
        chain.append(ChainLink("Launch kit", [pages[0].evidence_key], first_line(pages[0].content)))
    text = f"The launch kit ({src.filename}, dated {d(kit_date)})"
    if late:
        gev = ga_view.evidence[ga_view.current.evidence_id]
        chain.append(ChainLink(f"Current {ga_view.version} date in Jira", [gev.evidence_key],
                               _claim_quote(gev, ga_view.current.value)))
        text += f" planned the launch for {d(planned)}, but Jira's {ga_view.version} date is {d(ga)}"
        if kit_date and ga_view.current.exported_on and ga_view.current.exported_on > kit_date:
            text += f", set on {d(ga_view.current.exported_on)} after the kit was written; no later kit is in the records"
    else:
        text += " is the latest kit in the records"
    if items:
        text += f". {len(ready)} of {len(items)} kit items are marked ready"
    if owner_left:
        text += f". The kit's listed owner left on {d(owner_left)}"
        if owner_ev:
            chain.append(ChainLink("Kit owner's employee record (exit date)", _keys(owner_ev.values()), role="context"))
    text += "."
    dept = session.scalar(select(Department).where(Department.name == "Marketing"))
    if dept is not None:
        for line, ev in pending_department_lines(_ask(session, ctx, "marketing"), dept):
            notes.append(f"An organisation change is {line}. It is announced, not in effect, and is not treated as "
                         "made (DECISIONS.md 18, 19).")
            chain.append(ChainLink("Announced Marketing reporting change (not in effect)", [ev.evidence_key],
                                   role="context"))
    gap = (ctx.as_of.date() - planned).days if planned else 0
    persistence = 2 if planned and gap >= 30 else 1
    return Candidate(
        key, area, "Marketing launch plan out of step with the product", text,
        ("Marketing and product are working to different dates, so launch material can go out of date or out before "
         "the product is ready" if late else "Launch material may go out of date")
        + (", and the kit has no current owner on record." if owner_left else "."),
        "launch kit marketing readiness planned date owner", chain,
        2, "Customer-facing launch readiness", persistence,
        (f"The kit's planned date passed {gap} days before the as-of date" if planned and gap > 0 else
         "A single mismatch at one date"),
        f"The kit is dated {d(kit_date)}; no later version is in the records, so later progress is not shown.",
        "A newer launch kit dated against the current release date, with a named owner.", notes=notes)


# ---------------------------------------------------------------- 5. recurring cost trend (financial)

def cost_trend(session: Session, ctx: TimeContext) -> Candidate | Excluded:
    key, area = "cost_trend", "Finance: recurring cost"
    rows = session.scalars(visible(select(FinancialTxn), FinancialTxn, ctx)
                           .order_by(FinancialTxn.txn_date, FinancialTxn.id)).all()
    fev = usable(session, ctx, [x.evidence_id for x in rows])
    rows = [x for x in rows if x.evidence_id in fev and x.txn_date <= ctx.as_of.date()
            and not re.search(r"payroll|salar", f"{x.cost_centre} {x.vendor}", re.I)]   # never payroll (decision 3)
    if not rows:
        return Excluded(key, area, "No ledger lines are known at this date.")
    series: dict[tuple[str, str], dict[tuple[int, int], list[FinancialTxn]]] = defaultdict(lambda: defaultdict(list))
    for x in rows:
        series[(x.vendor, x.cost_centre)][(x.txn_date.year, x.txn_date.month)].append(x)
    best = None
    for (vendor, cc), months in sorted(series.items()):
        if len(months) < 4:
            continue
        keys_ = sorted(months)
        amounts = [sum(x.amount_paise for x in months[k]) for k in keys_]
        run = 0
        for i in range(len(amounts) - 1, 0, -1):
            (y0, m0), (y1, m1) = keys_[i - 1], keys_[i]
            if (y1 * 12 + m1) - (y0 * 12 + m0) != 1:
                break                                  # a missing month: the periods are not comparable
            if amounts[i] > amounts[i - 1]:
                run += 1
            else:
                break
        if run >= 3 and amounts[-1] >= 1.2 * amounts[-1 - run]:
            rise = amounts[-1] / amounts[-1 - run] - 1
            if best is None or rise > best[0]:
                best = (rise, vendor, cc, run, [months[k] for k in keys_[-1 - run:]], amounts[-1 - run:])
    if best is None:
        return Excluded(key, area, "No recurring ledger line rose in three or more consecutive months by 20% or more "
                                   "at this date. Payroll lines are never read here.")
    rise, vendor, cc, run, groups, amounts = best
    first, last = groups[0][0], groups[-1][-1]
    chain = [ChainLink(f"{vendor} ({cc}) ledger lines, {d(first.txn_date)} to {d(last.txn_date)}",
                       _keys(fev[x.evidence_id] for g in groups for x in g))]
    a = _ask(session, ctx, "cost spend vendor trend")
    burn = [h for h in statements(a, "burn priority", ("burn",), exclude_systems=NO_GIT, limit=3)
            if h.citation.system == "Email"][:1]
    for h in burn:
        chain.append(ChainLink(f"{h.citation.filename} ({d(h.citation.exported_on)})", [h.citation.evidence_key],
                               quote_from(h.content, ("burn",)), role="context"))
    text = (f"{vendor} charges in the GL rose in each of the last {run} monthly entries, from {inr(amounts[0])} "
            f"(posted {d(first.txn_date)}) to {inr(amounts[-1])} (posted {d(last.txn_date)}), up {round(100 * rise)}%.")
    lines = [x for g in groups for x in g]
    narr = sorted({(x.narration or "").strip() for x in lines})
    notes = [("Each line's narration reads '" + narr[0] + "', as written; the posting date is not the period billed."
              if len(narr) == 1 and narr[0] else "The lines' narrations differ: " + "; ".join(f"'{n}'" for n in narr)
              + ". The posting date is not the period billed."),
             "The rise is measured from the first entry of the rising run"
             + (", which is the first entry for this vendor in the records, so whether it began earlier is not "
                "known." if len(series[(vendor, cc)]) == run + 1 else ".")]
    credits = [x for x in rows if (x.vendor, x.cost_centre) == (vendor, cc) and x.amount_paise < 0]
    multi = [g for g in groups if len(g) > 1]
    notes.append(f"{len(credits)} credit or reversal line(s) for this vendor and cost centre are netted within their "
                 "month." if credits else "No credit or reversal line for this vendor and cost centre is in the records.")
    if multi:
        notes.append(f"{len(multi)} month(s) hold more than one line; each month's lines are summed.")
    notes.append("Amounts are as posted; whether they include tax is not stated.")
    return Candidate(
        key, area, f"{vendor} costs rising month on month", text,
        "A recurring cost that keeps rising raises monthly spend." + (" An email sets burn as the priority; it is "
                                                                       "quoted below." if burn else ""),
        "cost spend vendor trend", chain, 2, "Recurring cost", 2 if run >= 5 else 1,
        f"{run} consecutive monthly increases",
        "The GL shows amounts, not usage; the reason for the rise is not in the records.",
        f"A later GL export showing {vendor} flat or falling, or a record explaining the increase.", notes=notes)


# ---------------------------------------------------------------- evaluated, never raised on their own

def contractor_continuity(session: Session, ctx: TimeContext) -> Excluded:
    key, area = "contractor_continuity", "Contractor dependency"
    people = session.scalars(select(Person).where(Person.worker_type == "contractor",
                                                  Person.released_on <= ctx.release_cutoff)
                             .order_by(Person.full_name)).all()
    if not people:
        return Excluded(key, area, "No contractor record is known at this date.")
    roles = sorted({p.title or "role not written" for p in people})
    return Excluded(key, area, f"{len(people)} contractor record(s) known ({', '.join(roles)}). No record shows a "
                               "continuity problem (an end date, a notice or a gap in cover), and a risk is not raised "
                               "from missing evidence. Contractors are listed apart from headcount and are not linked "
                               "to rota names (DECISIONS.md 22).")


def org_change(session: Session, ctx: TimeContext) -> Excluded:
    key, area = "org_change", "Organisation change"
    found = []
    for dept in session.scalars(select(Department).order_by(Department.name)):
        found += [dept.name for _ in pending_department_lines(_ask(session, ctx, dept.name), dept)]
    if not found:
        return Excluded(key, area, "No announced organisation change is known at this date.")
    return Excluded(key, area, f"Announced change(s) for {', '.join(sorted(set(found)))} are not in effect and rest "
                               "on transcripts. An announced change is not treated as made (DECISIONS.md 18, 19); it "
                               "is shown as a note on a related worry, not ranked on its own.")


def reported_metrics(session: Session, ctx: TimeContext) -> Excluded:
    return Excluded("reported_metrics", "Finance: revenue and burn",
                    "Revenue, profit and net burn can't be computed from the exports (ARCHITECTURE.md 9). Where "
                    "transcripts and board updates disagree on a figure, the conflict is shown when asked, not ranked "
                    "as a worry.")


RULES = (delivery_schedule, service_reliability, capacity, launch_alignment, cost_trend,
         contractor_continuity, org_change, reported_metrics)
