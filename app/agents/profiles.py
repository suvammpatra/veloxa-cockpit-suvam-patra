"""Evidence-grounded agent profiles (ARCHITECTURE.md 16.11; DECISIONS.md 23, 24).

A profile states only what system records show about one of the 14 agents, at one time
frame. Every fact carries its evidence keys (validated), the source date, the date it
became known, a confidence and its valid period. A field with no eligible record says
"Not established" and why.

Eligible evidence is an allowlist of record systems:

  Keka HRMS   identity, title, department, reporting line, join and exit dates
  Keka Hire   requisitions where the person is the hiring manager (by Emp ID)
  Jira        tickets assigned to the person (through a name link, with its confidence)
  PagerDuty   incidents the person responded to (through a name link)
  Team wiki   on-call rota weeks (a hand-copied plan; through a name link)

plus, by review, the record behind an announced organisation change and the sides of a
stored conflict that touches the person's records. Never used: call transcripts and
voice notes, emails, git commits and their times (decision 23), the leave register,
the pulse survey, payroll (restricted) and letters. So a statement such as a transcript's
remark about someone's hours can never enter a profile, whatever name links exist.

Every cited key also passes app.retrieval.citations.validate at the time frame, with no
purpose, so restricted, purpose-limited, copied and not-yet-known records are refused a
second time. A fact that fails either check is dropped and listed in failed_checks.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import roster as _roster
from app.agents.roster import AgentSpec
from app.answering.classify import Intent
from app.answering.handlers import Ask, d, employed_at, org_context, pending_department_lines, usable
from app.answering.parse import Entities
from app.models import (Alias, Claim, DepartmentMembership, Evidence, Incident, Person, SourceRecord, Ticket)
from app.repositories.temporal import released_by, valid_at, visible
from app.retrieval.citations import Citation, validate
from app.retrieval.search import conflicts_for
from app.services.identity import normalize, resolve_person
from app.services.org import manager_as_of
from app.temporal import TimeContext

ELIGIBLE_SYSTEMS = frozenset({"Keka HRMS", "Keka Hire", "Jira", "PagerDuty", "Team wiki"})
NOT_ESTABLISHED = "Not established"
FIELDS = ("role", "department", "reporting_manager", "employment", "responsibilities", "current_projects",
          "workload_indicators", "historical_events", "pending_changes")
_RANK = {"L": 0, "M": 1, "H": 2}
_DONE = {"done", "closed", "resolved"}


def _min_conf(*codes: str | None) -> str:
    codes = [c for c in codes if c]
    return min(codes, key=lambda c: _RANK[c]) if codes else "L"


@dataclass
class Fact:
    field: str
    statement: str
    keys: list[str]
    confidence: str                  # H | M | L
    valid: str                       # the period the fact holds for, as far as the records show
    notes: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    source_date: date | None = None  # when the source recorded it (latest export among the keys)
    known_from: datetime | None = None  # when it could be known (latest release among the keys)


@dataclass
class Missing:
    field: str
    reason: str


@dataclass
class Profile:
    agent: str
    name: str
    agent_group: str                 # ARCHITECTURE.md 8
    status: str                      # active | departed | not_yet_joined | identity_not_established
    as_of: datetime
    mode: str
    emp_id: str | None = None
    identity_confidence: str | None = None
    facts: list[Fact] = field(default_factory=list)
    missing: list[Missing] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    sources_not_used: str = ("Call transcripts, voice notes, emails, git commits, the leave register, the pulse "
                             "survey, payroll and letters are not used for profiles (ARCHITECTURE.md 16.11).")

    def field_values(self) -> dict[str, list[str] | str]:
        out: dict[str, list[str] | str] = {}
        for f in FIELDS:
            got = [x.statement for x in self.facts if x.field == f]
            out[f] = got or NOT_ESTABLISHED
        return out


def to_dict(p: Profile) -> dict:
    def conv(v):
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [conv(x) for x in v]
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        return v
    d_ = conv(asdict(p))
    d_["fields"] = conv(p.field_values())
    return d_


# ---------------------------------------------------------------- identity

def find_employee(session: Session, spec: AgentSpec, ctx: TimeContext) -> Person | None:
    """The one employee whose Keka full name is exactly the roster name. No alias, no first name."""
    rows = [p for p in session.scalars(select(Person).where(Person.worker_type == "employee",
                                                            Person.released_on <= ctx.release_cutoff))
            if normalize(p.full_name) == normalize(spec.name)]
    return rows[0] if len(rows) == 1 else None


def _name_forms(session: Session, person: Person, ctx: TimeContext, forms: set[str]) -> dict[str, tuple[str, str]]:
    """Name forms that resolve to this person at the time frame: form -> (confidence, how linked)."""
    out = {}
    for form in sorted(f for f in forms if f):
        r = resolve_person(session, form, ctx)
        if r.status != "resolved" or r.person.id != person.id:
            continue
        rows = session.scalars(released_by(select(Alias).where(Alias.normalized == normalize(form),
                                                               Alias.target_person_id == person.id),
                                           Alias, ctx.release_cutoff)).all()
        if any(a.origin == "curated" for a in rows):
            how = "reviewed alias"
        elif rows:
            how = "rule-based link, not reviewed"
        else:
            how = {"first_name": "unique first name", "exact_name": "exact name", "email": "work email",
                   "emp_id": "Emp ID"}.get(r.method or "", r.method or "rule")
        out[form] = (r.confidence or "L", how)
    return out


def _link_note(forms: dict[str, tuple[str, str]], used: set[str]) -> tuple[str, list[str]]:
    conf = _min_conf(*(forms[f][0] for f in used))
    notes = [f"'{f}' linked to this person by {forms[f][1]} at {forms[f][0]}" for f in sorted(used)]
    return conf, notes


# ---------------------------------------------------------------- building

class _Builder:
    def __init__(self, session: Session, spec: AgentSpec, ctx: TimeContext):
        self.s, self.spec, self.ctx = session, spec, ctx
        self.at = ctx.as_of
        self.profile = Profile(agent=spec.slug, name=spec.name, agent_group=spec.department,
                               status="identity_not_established", as_of=ctx.as_of, mode=ctx.mode.value)
        self.allowed_extra: set[int] = set()   # reviewed exceptions: announced-change and conflict-side records

    def ev(self, ids) -> dict[int, Evidence]:
        return {i: e for i, e in usable(self.s, self.ctx, ids).items() if e.source.system in ELIGIBLE_SYSTEMS}

    def add(self, field_: str, statement: str, evs, confidence: str, valid: str, notes=()):
        evs = [e for e in evs if e is not None]
        if not evs:
            return
        self.profile.facts.append(Fact(field_, statement, sorted({e.evidence_key for e in evs},
                                                                 key=lambda k: int(k[1:])),
                                       _min_conf(confidence, *(e.confidence for e in evs)), valid, list(notes)))

    def miss(self, field_: str, reason: str):
        self.profile.missing.append(Missing(field_, reason))

    # -------------------------------------------------------------- sections

    def build(self) -> Profile:
        p = find_employee(self.s, self.spec, self.ctx)
        rec = self.ev([p.source_evidence_id]).get(p.source_evidence_id) if p else None
        if p is None or rec is None:
            for f in FIELDS:
                self.miss(f, "No employee record with this exact name is known at this date.")
            return self.finish()
        self.person, self.rec = p, rec
        self.profile.emp_id, self.profile.identity_confidence = p.emp_id, "H"
        snap = rec.exported_on
        left = p.exit_date is not None and p.exit_date < self.at.date()
        joined = p.join_date is None or p.join_date <= self.at.date()
        self.profile.status = "departed" if left else ("active" if joined else "not_yet_joined")
        self.employment(p, rec, snap, left, joined)
        if left:
            for f in ("role", "department", "reporting_manager"):
                self.miss(f, f"Not applicable: left on {d(p.exit_date)}. Ask with an earlier date for the "
                             "history.")
        elif not joined:
            for f in ("role", "department", "reporting_manager"):
                self.miss(f, f"Not applicable: joins on {d(p.join_date)}.")
        else:
            self.role(p, rec, snap)
            self.department(p)
            self.manager(p)
        self.responsibilities(p)
        self.work(p)
        self.pending(p, left)
        self.attach_conflicts()
        return self.finish()

    def employment(self, p: Person, rec: Evidence, snap, left: bool, joined: bool):
        snap_text = f"Keka export of {d(snap)}" if snap else "Keka"
        if p.join_date:
            self.add("historical_events", f"Joined on {d(p.join_date)}.", [rec], "H", f"from {d(p.join_date)}")
        else:
            self.miss("historical_events", "No join date is recorded.")
        if p.exit_date:
            verb = "Left" if left else "Exit date recorded as"
            self.add("historical_events", f"{verb} {d(p.exit_date)}.", [rec], "H", f"to {d(p.exit_date)}")
        state = (f"Not employed on {d(self.at)}: left on {d(p.exit_date)}" if left else
                 f"Not employed on {d(self.at)}: joins on {d(p.join_date)}" if not joined else
                 f"Employed on {d(self.at)}")
        written = f"; status written as '{p.employment_status}' in the {snap_text}" if p.employment_status else ""
        self.add("employment", state + written + ".", [rec], "H", f"on {d(self.at)}")

    def role(self, p: Person, rec: Evidence, snap):
        if not p.title:
            self.miss("role", "No title is recorded.")
            return
        if snap and self.at < snap:
            self.miss("role", f"Not established for {d(self.at)}: titles are recorded only in the Keka export of "
                              f"{d(snap)} ('{p.title}'); earlier titles are not recorded.")
            return
        self.add("role", p.title, [rec], "H", f"from {d(snap)} (Keka snapshot; start unknown)" if snap else "unknown",
                 [f"Recorded in the Keka export of {d(snap)}; earlier titles are not recorded."] if snap else [])

    def department(self, p: Person):
        rows = self.s.scalars(valid_at(select(DepartmentMembership).where(DepartmentMembership.person_id == p.id),
                                       DepartmentMembership, self.at, release_cutoff=self.ctx.release_cutoff)).all()
        evs = self.ev([r.source_evidence_id for r in rows])
        row = next((r for r in rows if r.source_evidence_id in evs), None)
        if row is None:
            first = self.s.scalars(released_by(select(DepartmentMembership).where(
                DepartmentMembership.person_id == p.id), DepartmentMembership, self.ctx.release_cutoff)
                .order_by(DepartmentMembership.valid_from)).first()
            when = f"; membership is recorded from {d(first.valid_from)}" if first and first.valid_from else ""
            self.miss("department", f"Not established for {d(self.at)}{when}. It is not assumed back to the join "
                                    "date (DECISIONS.md 17).")
            return
        notes = []
        if not row.start_exact:
            notes.append(f"Known from {d(row.valid_from)} (Keka snapshot); before that it is unknown.")
        if row.department.name != self.spec.department:
            notes.append(f"ARCHITECTURE.md 8 groups this agent under {self.spec.department}; the record says "
                         f"{row.department.name}.")
        self.add("department", row.department.name, [evs[row.source_evidence_id]], "H",
                 f"from {d(row.valid_from)}" + (f" to {d(row.valid_to)}" if row.valid_to else ""), notes)

    def manager(self, p: Person):
        res = manager_as_of(self.s, p, org_context(self.ctx, self.at))
        evs = self.ev([res.source_evidence_id])
        if res.status != "known" or res.source_evidence_id not in evs:
            self.miss("reporting_manager", f"Not established for {d(self.at)}. {res.note or ''}".strip())
            return
        self.add("reporting_manager", res.manager, [evs[res.source_evidence_id]], "H",
                 f"on {d(self.at)} (Keka snapshot; start unknown)",
                 ["A change shows only with a later export or a dated announcement (DECISIONS.md 18)."])

    def responsibilities(self, p: Person):
        """Only what a record assigns: requisitions where this Emp ID is the hiring manager (Keka Hire)."""
        rows = self.s.scalars(select(Evidence).join(SourceRecord).where(SourceRecord.system == "Keka Hire")
                              .order_by(Evidence.id)).all()
        evs = self.ev([e.id for e in rows])
        mine = []
        for e in evs.values():
            fields = json.loads(e.fields_json or "{}")
            mgr = next((v for k, v in fields.items() if normalize(k) == "hiring manager"), None)
            if p.emp_id and mgr and str(mgr).strip() == p.emp_id:
                mine.append((e, fields))
        if not mine:
            self.miss("responsibilities", "No record assigns responsibilities to this person. The title is under "
                                          "role, and assigned tickets are under current projects.")
            return
        for e, f in mine:
            req = next((v for k, v in f.items() if normalize(k) in ("req id", "requisition")), "a requisition")
            role = next((v for k, v in f.items() if normalize(k) == "role"), None)
            status = next((v for k, v in f.items() if normalize(k) == "status"), None)
            when = next((v for k, v in f.items() if normalize(k) == "status date"), None)
            text = f"Hiring manager for {req}" + (f" ({role})" if role else "") + \
                   (f"; status '{status}'" + (f" since {when}" if when else "") if status else "") + \
                   f" at the Keka Hire export of {d(e.exported_on)}."
            self.add("responsibilities", text, [e], "H", f"at {d(e.exported_on)}")

    def work(self, p: Person):
        s, ctx = self.s, self.ctx
        tickets = s.scalars(visible(select(Ticket), Ticket, ctx).order_by(Ticket.key)).all()
        incidents = s.scalars(visible(select(Incident), Incident, ctx).order_by(Incident.opened_at)).all()
        rota = [e for e in s.scalars(select(Evidence).join(SourceRecord).where(SourceRecord.system == "Team wiki")
                                     .order_by(Evidence.id)).all() if e.fields_json]
        rota_rows = []
        for e in rota:
            f = json.loads(e.fields_json)
            week = next((v for k, v in f.items() if normalize(k).startswith("week")), None)
            names = {k: v for k, v in f.items() if not normalize(k).startswith("week") and v}
            rota_rows.append((e, week, names))
        forms = _name_forms(s, p, ctx, {t.assignee_alias for t in tickets} | {i.responder_alias for i in incidents}
                            | {str(v) for _, _, n in rota_rows for v in n.values()})

        # Jira: projects (epics) and open work, at the export
        mine = [t for t in tickets if t.assignee_alias in forms]
        tev = self.ev([t.evidence_id for t in mine])
        mine = [t for t in mine if t.evidence_id in tev]
        if mine:
            conf, notes = _link_note(forms, {t.assignee_alias for t in mine})
            export = max((tev[t.evidence_id].exported_on for t in mine if tev[t.evidence_id].exported_on),
                         default=None)
            epic_names = {c.subject_key: c.value for c in s.scalars(released_by(
                select(Claim).where(Claim.subject_type == "epic", Claim.attribute == "name"), Claim,
                ctx.release_cutoff))}
            for proj in sorted({t.project_key for t in mine}):
                ts = [t for t in mine if t.project_key == proj]
                epics = Counter(epic_names.get(t.epic_key, t.epic_key) for t in ts if t.epic_key)
                text = (f"{proj}: {len(ts)} ticket(s) assigned in the Jira export of {d(export)}"
                        + (": " + ", ".join(f"{n} ({c})" for n, c in sorted(epics.items())) if epics else "") + ".")
                self.add("current_projects", text, [tev[t.evidence_id] for t in ts], conf,
                         f"at the Jira export of {d(export)}", notes + ["Jira is a status snapshot with no history."])
                open_ts = [t for t in ts if t.status.lower() not in _DONE]
                pts = sum(t.story_points or 0 for t in open_ts)
                self.add("workload_indicators",
                         f"{proj}: {len(open_ts)} of {len(ts)} assigned ticket(s) not Done ({pts} story points) at "
                         f"the Jira export of {d(export)}.", [tev[t.evidence_id] for t in ts], conf,
                         f"at the Jira export of {d(export)}", notes)
        else:
            self.miss("current_projects", "No Jira ticket is linked to this person at this date.")

        # PagerDuty: incidents responded to, up to the as-of date (IST)
        mine_i = [i for i in incidents if i.responder_alias in forms and i.opened_at <= self.at]
        iev = self.ev([i.evidence_id for i in mine_i])
        mine_i = [i for i in mine_i if i.evidence_id in iev]
        if mine_i:
            conf, notes = _link_note(forms, {i.responder_alias for i in mine_i})
            sev = Counter(i.severity for i in mine_i)
            self.add("workload_indicators",
                     f"Responded to {len(mine_i)} incident(s) ({', '.join(f'{n} {k}' for k, n in sorted(sev.items()))})"
                     f" opened {d(mine_i[0].opened_at)} to {d(mine_i[-1].opened_at)} (PagerDuty, IST).",
                     [iev[i.evidence_id] for i in mine_i], conf,
                     f"{d(mine_i[0].opened_at)} to {d(mine_i[-1].opened_at)}", notes)

        # On-call rota: a hand-copied plan (rung 4), up to the as-of date
        rev = self.ev([e.id for e, _, _ in rota_rows])
        weeks = []
        for e, week, names in rota_rows:
            if e.id not in rev or not week or str(week) > self.at.date().isoformat():
                continue
            roles = [k for k, v in names.items() if str(v) in forms]
            if roles:
                weeks.append((week, roles, e, {str(names[k]) for k in roles}))
        if weeks:
            conf, notes = _link_note(forms, set().union(*(w[3] for w in weeks)))
            roles = Counter(r for _, rs, _, _ in weeks for r in rs)
            self.add("workload_indicators",
                     f"On the on-call rota for {len(weeks)} week(s), weeks of {weeks[0][0]} to {weeks[-1][0]} "
                     f"({', '.join(f'{k} {n}' for k, n in sorted(roles.items()))}). The rota is a copied plan, "
                     "not a record of who was on call.", [w[2] for w in weeks], conf,
                     f"weeks of {weeks[0][0]} to {weeks[-1][0]}", notes)
        if not any(f.field == "workload_indicators" for f in self.profile.facts):
            self.miss("workload_indicators", "No ticket, incident or rota record is linked to this person at this "
                                             "date. Commit times are never used (DECISIONS.md 23).")

    def pending(self, p: Person, left: bool):
        member = None if left else self.s.scalars(valid_at(
            select(DepartmentMembership).where(DepartmentMembership.person_id == p.id), DepartmentMembership,
            self.at, release_cutoff=self.ctx.release_cutoff)).first()
        changes = []
        if member is not None:
            shim = Ask(self.s, "", self.ctx, Entities(), Intent("agent"))
            changes = pending_department_lines(shim, member.department)
        if not changes:
            self.miss("pending_changes", "No announced change affecting this person is known at this date.")
            return
        for text, e in changes:
            self.allowed_extra.add(e.id)
            self.profile.facts.append(Fact("pending_changes", f"Pending, not in effect: {text}.", [e.evidence_key],
                                           "L", "no effective date",
                                           ["An announcement only; the current reporting line is unchanged "
                                            "(DECISIONS.md 18)."]))

    def attach_conflicts(self):
        keys = {k for f in self.profile.facts for k in f.keys}
        ids = list(self.s.scalars(select(Evidence.id).where(Evidence.evidence_key.in_(keys)))) if keys else []
        for ref, sides in conflicts_for(self.s, self.ctx, ids):
            self.allowed_extra |= set(sides)
            self.profile.conflicts.append({"conflict_key": ref.conflict_key, "title": ref.title, "status": ref.status,
                                           "working_position" if ref.status == "open" else "resolution":
                                               ref.resolution,
                                           "sides": [{"side": s, "evidence_key": k, "summary": m}
                                                     for s, k, m in ref.sides]})
            for f in self.profile.facts:
                if set(f.keys) & {e.evidence_key for e in sides.values()}:
                    f.notes.append(f"Touched by {ref.status} conflict {ref.conflict_key}: {ref.title}.")
                    if ref.status == "open":
                        f.confidence = "L"
                    else:
                        f.confidence = _min_conf(f.confidence, "M")

    def finish(self) -> Profile:
        """Second check on every fact: each key must pass citation validation at this time frame (no purpose,
        nothing restricted) and come from an eligible system or a reviewed exception."""
        kept = []
        for f in self.profile.facts:
            checks = validate(self.s, f.keys, self.ctx)
            bad = [f"{c.evidence_key}: {c.reason}" for c in checks if not c.ok]
            evs = {e.evidence_key: e for e in self.s.scalars(select(Evidence).where(Evidence.evidence_key.in_(f.keys)))}
            bad += [f"{k}: source not eligible for profiles" for k, e in evs.items()
                    if e.source.system not in ELIGIBLE_SYSTEMS and e.id not in self.allowed_extra]
            if bad:
                self.profile.failed_checks.append(f"{f.field}: dropped ({'; '.join(bad)})")
                continue
            f.citations = [c.citation for c in checks]
            f.source_date = max((c.exported_on.date() for c in f.citations if c.exported_on), default=None)
            f.known_from = max(c.released_on for c in f.citations)
            kept.append(f)
        self.profile.facts = kept
        have = {f.field for f in kept}
        self.profile.missing = [m for m in self.profile.missing if m.field not in have]
        for fld in FIELDS:
            if fld not in have and not any(m.field == fld for m in self.profile.missing):
                self.profile.missing.append(Missing(fld, "No eligible record supports this field."))
        return self.profile


def agent_profile(session: Session, spec: AgentSpec, ctx: TimeContext) -> Profile:
    return _Builder(session, spec, ctx).build()


def find_agent(slug_or_name: str, roster=None) -> AgentSpec | None:
    roster = roster or _roster.AGENT_ROSTER
    key = normalize(slug_or_name).replace(" ", "-")
    return next((a for a in roster if a.slug == key or normalize(a.name) == normalize(slug_or_name)), None)


def all_profiles(session: Session, ctx: TimeContext, roster=None) -> list[Profile]:
    return [agent_profile(session, a, ctx) for a in (roster or _roster.AGENT_ROSTER)]
