"""Typed extraction from structured exports (ARCHITECTURE.md 5, Extract stage, by rule).

Each extractor reads the parsed rows of one file and writes typed facts that
point back to their evidence row. Rules:

  * A value that does not parse is logged against its row and the typed fact
    is skipped; the evidence row is still kept. Nothing is imputed.
  * A key already recorded from an earlier file is never overwritten. If the
    new values differ, a Conflict is stored with both rows as its sides.
  * Payroll amounts go only to the separate payroll store (DECISIONS.md 3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.dates import (month_range, parse_date, parse_instant,
                                 previous_month_range)
from app.models import (Claim, Commit, Conflict, ConflictSide, Department, DepartmentMembership,
                        Evidence, FinancialTxn, Incident, Person, Project, ReportingLine, SourceRecord,
                        Ticket)


@dataclass
class ExtractContext:
    session: Session
    source: SourceRecord
    released: datetime
    file_exported: datetime | None
    evidence: dict[str, Evidence]          # locator -> evidence row
    titles: dict[str, str] = field(default_factory=dict)  # sheet -> title line
    payroll_entries: list[dict] = field(default_factory=list)  # written after the main commit
    problems: list[tuple[str | None, str, str]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def error(self, locator, message):
        self.problems.append((locator, "error", message))

    def warn(self, locator, message):
        self.problems.append((locator, "warning", message))

    def count(self, what: str, n: int = 1):
        self.counts[what] = self.counts.get(what, 0) + n


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.casefold())


def col(fields: dict, *names: str):
    """The cell under the first header that starts with any of `names` (case and punctuation ignored)."""
    keys = {_norm(k): k for k in fields}
    for name in names:
        n = _norm(name)
        for nk, k in keys.items():
            if nk.startswith(n):
                return fields[k]
    return None


def _text(value) -> str | None:
    return None if value in (None, "") else str(value).strip()


def _int(value) -> int | None:
    try:
        return None if value in (None, "") else int(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def _paise(value) -> int | None:
    try:
        return int((Decimal(str(value).replace(",", "")) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None


def _day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def _rows(ctx: ExtractContext, units, sheet: str | None = None):
    for u in units:
        if u.fields is None:
            continue
        if sheet is not None and (u.sheet or "").casefold() != sheet.casefold():
            continue
        yield u, ctx.evidence[u.locator]


def _conflict_if_different(ctx: ExtractContext, label: str, old_ev_id: int, new_ev: Evidence,
                           old: dict, new: dict) -> None:
    diffs = {k: (old[k], new[k]) for k in old if old[k] != new[k]}
    if not diffs:
        ctx.count("already_recorded")
        return
    n = ctx.session.scalar(select(func.count(Conflict.id)).where(Conflict.origin == "rule")) + 1
    detail = "; ".join(f"{k}: {a!r} then {b!r}" for k, (a, b) in diffs.items())
    c = Conflict(conflict_key=f"C-RX-{n:04d}", title=f"A later file differs for {label}",
                 rule="Not resolved automatically (DECISIONS.md 1). The earlier record is kept.",
                 confidence="M", status="open", origin="rule", released_on=ctx.released)
    c.sides = [ConflictSide(evidence_id=old_ev_id, side="A", summary="Earlier record"),
               ConflictSide(evidence_id=new_ev.id, side="B", summary=detail)]
    ctx.session.add(c)
    ctx.warn(new_ev.locator, f"{label} was already recorded with different values; conflict {c.conflict_key} stored.")
    ctx.count("conflicts")


# ---------------------------------------------------------------- Keka employee master

def dept_code(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")[:16]


def employees(ctx: ExtractContext, units) -> None:
    """People, departments, memberships and reporting lines from one Keka snapshot.

    Keka has no history, so a membership or reporting line starts at the export
    date with start_exact False: before it, the answer is unknown (DECISIONS.md 17).
    A later snapshot that disagrees is stored as a conflict, not applied; how a
    confirmed change is applied is a separate decision (DECISIONS.md 18).
    """
    s = ctx.session
    if ctx.file_exported is None:
        ctx.error(None, "No export date for this snapshot; memberships and reporting lines not created.")
    snapshot = ctx.file_exported
    rows = []
    for u, ev in _rows(ctx, units):
        emp_id = _text(col(u.fields, "emp id", "employee id"))
        name = _text(col(u.fields, "full name", "name"))
        if not emp_id or not name:
            ctx.error(u.locator, "Missing Emp ID or name; row not used as a person.")
            continue
        joined_raw, exit_raw = col(u.fields, "join date"), col(u.fields, "exit date")
        joined, exited = parse_date(joined_raw), parse_date(exit_raw)
        if joined_raw not in (None, "") and joined is None:
            ctx.error(u.locator, f"Join date {joined_raw!r} does not parse; left empty.")
        if joined_raw in (None, ""):
            ctx.warn(u.locator, "No join date.")
        if exit_raw not in (None, "") and exited is None:
            ctx.error(u.locator, f"Exit date {exit_raw!r} does not parse; left empty.")
        rows.append((u, ev, emp_id, name, joined, exited))

    people: dict[str, Person] = {}
    for u, ev, emp_id, name, joined, exited in rows:
        existing = s.scalar(select(Person).where(Person.emp_id == emp_id))
        dept_name = _text(col(u.fields, "department"))
        record = {"full_name": name, "work_email": _text(col(u.fields, "work email", "email")),
                  "title": _text(col(u.fields, "title")), "join_date": joined, "exit_date": exited,
                  "employment_status": _text(col(u.fields, "status")),
                  "location": _text(col(u.fields, "location"))}
        if existing is not None:
            old = {k: getattr(existing, k) for k in record}
            _conflict_if_different(ctx, f"employee {emp_id}", existing.source_evidence_id or ev.id, ev, old, record)
            people[emp_id] = existing
            continue
        p = Person(emp_id=emp_id, worker_type="employee", source_evidence_id=ev.id,
                   released_on=ctx.released, **record)
        s.add(p)
        s.flush()
        people[emp_id] = p
        ctx.count("people")
        if snapshot is None:
            continue
        start, end = _validity(snapshot, exited)
        if dept_name:
            dept = s.scalar(select(Department).where(Department.name == dept_name))
            if dept is None:
                dept = Department(code=dept_code(dept_name), name=dept_name)
                s.add(dept)
                s.flush()
                ctx.count("departments")
            s.add(DepartmentMembership(person_id=p.id, department_id=dept.id, valid_from=start,
                                       start_exact=False, valid_to=end, released_on=ctx.released,
                                       source_evidence_id=ev.id))
        else:
            ctx.warn(u.locator, "No department.")

    if snapshot is None:
        return
    for u, ev, emp_id, _name, _j, exited in rows:
        mgr_id = _text(col(u.fields, "manager id", "manager"))
        p = people.get(emp_id)
        if not mgr_id or p is None or p.source_evidence_id != ev.id:
            continue
        mgr = people.get(mgr_id) or s.scalar(select(Person).where(Person.emp_id == mgr_id))
        if mgr is None:
            ctx.error(u.locator, f"Manager ID {mgr_id} is not a known employee; reporting line not created.")
            continue
        start, end = _validity(snapshot, exited)
        s.add(ReportingLine(person_id=p.id, manager_person_id=mgr.id, valid_from=start, start_exact=False,
                            valid_to=end, released_on=ctx.released, source_evidence_id=ev.id))
        ctx.count("reporting_lines")


def _validity(snapshot: datetime, exited: date | None) -> tuple[datetime, datetime | None]:
    """From the snapshot (or the exit day, if earlier) to the end of the exit day."""
    start = _day_start(snapshot.date())
    if exited is None:
        return start, None
    return min(start, _day_start(exited)), _day_start(exited) + timedelta(days=1)


# ---------------------------------------------------------------- general ledger

def gl(ctx: ExtractContext, units) -> None:
    s = ctx.session
    for u, ev in _rows(ctx, units):
        voucher, ref = _text(col(u.fields, "voucher")), _text(col(u.fields, "ref"))
        raw_date, raw_amt = col(u.fields, "txn date", "date"), col(u.fields, "amount")
        txn_date, amount = parse_date(raw_date), _paise(raw_amt)
        if not voucher:
            ctx.error(u.locator, "No voucher; not recorded as a transaction.")
            continue
        if txn_date is None:
            ctx.error(u.locator, f"Missing or unreadable date {raw_date!r}; not recorded as a transaction.")
            continue
        if amount is None:
            ctx.error(u.locator, f"Amount {raw_amt!r} is not a number; not recorded as a transaction.")
            continue
        narration = _text(col(u.fields, "narration"))
        # "previous month" lines describe the month before posting (ARCHITECTURE.md 4).
        if narration and "previous month" in narration.casefold():
            as_of = previous_month_range(txn_date)
        else:
            as_of = (_day_start(txn_date), _day_start(txn_date) + timedelta(hours=23, minutes=59, seconds=59))
        ev.exported_on, (ev.as_of_start, ev.as_of_end) = _day_start(txn_date), as_of
        record = {"txn_date": txn_date, "vendor": _text(col(u.fields, "vendor")) or "",
                  "cost_centre": _text(col(u.fields, "cost centre", "cost center")) or "",
                  "amount_paise": amount, "narration": narration,
                  "entered_by": _text(col(u.fields, "entered by"))}
        ref = ref or ""
        existing = s.scalar(select(FinancialTxn).where(FinancialTxn.voucher == voucher, FinancialTxn.ref == ref))
        if existing is not None:
            _conflict_if_different(ctx, f"GL {voucher} {ref}".strip(), existing.evidence_id, ev,
                                   {k: getattr(existing, k) for k in record}, record)
            continue
        s.add(FinancialTxn(voucher=voucher, ref=ref, evidence_id=ev.id, released_on=ctx.released,
                           exported_on=ev.exported_on, as_of_start=as_of[0], as_of_end=as_of[1], **record))
        ctx.count("gl_lines")


# ---------------------------------------------------------------- payroll (restricted)

def payroll(ctx: ExtractContext, units) -> None:
    """Amounts go to the payroll store only. Evidence rows were already stripped of them."""
    entries = ctx.payroll_entries
    for u, ev in _rows(ctx, units):
        emp_id = _text(col(u.fields, "emp id"))
        rng = month_range(col(u.fields, "month") or "")
        days_in, days_pay = _int(col(u.fields, "days in month")), _int(col(u.fields, "days payable"))
        gross = _paise(col(u.fields, "gross"))
        if not emp_id or rng is None:
            ctx.error(u.locator, "Missing Emp ID or unreadable month; payroll row not stored.")
            continue
        if days_in is None or days_pay is None or gross is None:
            ctx.error(u.locator, "Days or gross pay missing or not a number; payroll row not stored.")
            continue
        ev.as_of_start, ev.as_of_end = rng
        entries.append({"emp_id": emp_id, "month": rng[0].strftime("%Y-%m"), "days_in_month": days_in,
                        "days_payable": days_pay, "gross_paise": gross, "released_on": ctx.released})
    if entries:
        ctx.count("payroll_rows", len(entries))


# ---------------------------------------------------------------- Jira

def jira(ctx: ExtractContext, units) -> None:
    s = ctx.session
    for u, ev in _rows(ctx, units, sheet="Issues"):
        key = _text(col(u.fields, "key"))
        status = _text(col(u.fields, "status"))
        if not key or "-" not in key or not status:
            ctx.error(u.locator, "Missing issue key or status; ticket not recorded.")
            continue
        created_raw, resolved_raw = col(u.fields, "created"), col(u.fields, "resolved")
        created, resolved = parse_date(created_raw), parse_date(resolved_raw)
        for label, raw, val in (("Created", created_raw, created), ("Resolved", resolved_raw, resolved)):
            if raw not in (None, "") and val is None:
                ctx.error(u.locator, f"{label} date {raw!r} does not parse; left empty.")
        if created_raw in (None, ""):
            ctx.warn(u.locator, "No Created date.")
        record = {"issue_type": _text(col(u.fields, "type")), "summary": _text(col(u.fields, "summary")) or "",
                  "epic_key": _text(col(u.fields, "epic link", "epic")),
                  "assignee_alias": _text(col(u.fields, "assignee")),
                  "story_points": _int(col(u.fields, "story points")), "status": status,
                  "created": created, "resolved": resolved, "fix_version": _text(col(u.fields, "fix version"))}
        existing = s.scalar(select(Ticket).where(Ticket.key == key))
        if existing is not None:
            _conflict_if_different(ctx, f"ticket {key}", existing.evidence_id, ev,
                                   {k: getattr(existing, k) for k in record}, record)
            continue
        s.add(Ticket(key=key, project_key=key.split("-")[0], evidence_id=ev.id, released_on=ctx.released,
                     exported_on=ctx.file_exported, as_of_end=ctx.file_exported, **record))
        ctx.count("tickets")

    for u, ev in _rows(ctx, units, sheet="Epics"):
        key, name = _text(col(u.fields, "key")), _text(col(u.fields, "epic name", "name"))
        if key and name:
            _claim(ctx, ev, "epic", key, "name", name, exported=ctx.file_exported)

    for u, ev in _rows(ctx, units, sheet="Versions"):
        version = _text(col(u.fields, "version"))
        if not version:
            continue
        changed_raw = col(u.fields, "last changed")
        changed = parse_date(changed_raw)
        if changed is None:
            ctx.warn(u.locator, "No readable Last Changed date; the release date's recording time is unknown.")
        ev.exported_on = _day_start(changed) if changed else None
        for attr, header in (("release_date", "release date"), ("original_release_date", "original release")):
            d = parse_date(col(u.fields, header))
            if d:
                # Only the current date has a known recording time (Last Changed); the original's is unknown.
                _claim(ctx, ev, "release", version, attr, d.isoformat(),
                       exported=ev.exported_on if attr == "release_date" else None)
        by = _text(col(u.fields, "changed by"))
        if by:
            _claim(ctx, ev, "release", version, "changed_by", by, exported=ev.exported_on)

    title = " ".join(ctx.titles.values())
    m = re.search(r"project ([A-Z][A-Z0-9]+)", title)
    if m and s.scalar(select(Project).where(Project.key == m.group(1))) is None:
        s.add(Project(key=m.group(1), name=m.group(1), note=f"Named in the title of {ctx.source.filename}."))


def _claim(ctx, ev, subject_type, subject_key, attribute, value, *, exported):
    ctx.session.add(Claim(evidence_id=ev.id, subject_type=subject_type, subject_key=subject_key[:64],
                          attribute=attribute, value=value, extractor="rule", confidence=ev.confidence,
                          released_on=ctx.released, exported_on=exported))
    ctx.count("claims")


# ---------------------------------------------------------------- PagerDuty

def incidents(ctx: ExtractContext, units) -> None:
    s = ctx.session
    for u, ev in _rows(ctx, units):
        key, sev = _text(col(u.fields, "id")), _text(col(u.fields, "severity"))
        opened_raw, resolved_raw = col(u.fields, "opened"), col(u.fields, "resolved")
        opened, resolved = parse_instant(opened_raw), parse_instant(resolved_raw)
        if not key or not sev:
            ctx.error(u.locator, "Missing incident ID or severity; incident not recorded.")
            continue
        if opened is None:
            ctx.error(u.locator, f"Missing or unreadable Opened time {opened_raw!r}; incident not recorded.")
            continue
        if resolved_raw not in (None, "") and resolved is None:
            ctx.error(u.locator, f"Resolved time {resolved_raw!r} does not parse; left empty.")
        ev.exported_on, ev.as_of_start, ev.as_of_end = opened, opened, resolved
        record = {"severity": sev, "opened_at": opened, "resolved_at": resolved,
                  "service": _text(col(u.fields, "service")), "responder_alias": _text(col(u.fields, "responder"))}
        existing = s.scalar(select(Incident).where(Incident.key == key))
        if existing is not None:
            _conflict_if_different(ctx, f"incident {key}", existing.evidence_id, ev,
                                   {k: getattr(existing, k) for k in record}, record)
            continue
        s.add(Incident(key=key, evidence_id=ev.id, released_on=ctx.released, exported_on=opened,
                       as_of_start=opened, as_of_end=resolved, **record))
        ctx.count("incidents")


# ---------------------------------------------------------------- git

def git(ctx: ExtractContext, units) -> None:
    """Commits are stored for ownership and activity by repo. Commit times are never
    turned into a per-person signal (DECISIONS.md 23)."""
    s = ctx.session
    for u, ev in _rows(ctx, units):
        sha, author = _text(col(u.fields, "sha")), _text(col(u.fields, "author email", "author"))
        when_raw = col(u.fields, "committed at", "date")
        when = parse_instant(when_raw)
        if not sha or not author:
            ctx.error(u.locator, "Missing SHA or author; commit not recorded.")
            continue
        if when is None:
            ctx.error(u.locator, f"Missing or unreadable commit time {when_raw!r}; commit not recorded.")
            continue
        ev.exported_on, ev.as_of_start, ev.as_of_end = when, when, when
        record = {"author_email": author.casefold(), "committed_at": when, "repo": _text(col(u.fields, "repo")) or "",
                  "message": _text(col(u.fields, "message")), "files_changed": _int(col(u.fields, "files changed"))}
        existing = s.scalar(select(Commit).where(Commit.sha == sha))
        if existing is not None:
            _conflict_if_different(ctx, f"commit {sha[:10]}", existing.evidence_id, ev,
                                   {k: getattr(existing, k) for k in record}, record)
            continue
        s.add(Commit(sha=sha, evidence_id=ev.id, released_on=ctx.released, exported_on=when,
                     as_of_start=when, as_of_end=when, **record))
        ctx.count("commits")


EXTRACTORS = {"employees": employees, "gl": gl, "payroll": payroll, "jira": jira,
              "incidents": incidents, "git": git}
