"""Reviewed organisation records: contractors, announced changes and reported events (DECISIONS.md 18, 19, 22, 33).

Loaded from a reviewed JSON file after ingestion. Uses the existing tables, with no schema change:

  * A contractor is a Person with worker type "contractor" and no Emp ID. Only what the
    record states is stored: the name as written, the role as written, and the firm. No Emp
    ID, join date, location or email is invented. A contractor is never counted as an
    employee, and is never linked to any other name form (for example Snehal or Sneha).
  * An announced change is a DepartmentLine with status "announced" and no effective date.
    It is shown as pending and never applied: the current reporting lines stay as they are
    until a record gives an effective date (DECISIONS.md 18). The role it names is a
    Position with no holder (DECISIONS.md 19).
  * A reported event (DECISIONS.md 33) is something a person reported, such as the CEO's
    T6d voice note that "Pria resigned". It is stored as a Claim with subject type
    "reported_event", status "reported_unverified", the name and any notice period exactly
    as written, and no identity, exit date or last working day. It never changes a Person,
    an employment status or any HR record.

Every record must match exactly one ingested source record (the rules of
app.ingestion.conflict_registry.find_side). A record that does not is rejected with its
reason, and nothing is written for it. Loading twice changes nothing; different content
for a stored record is rejected, never overwritten.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.conflict_registry import LoadResult, find_side
from app.models import Claim, Department, DepartmentLine, Person, Position
from app.temporal import release_timestamp


def _ref(spec: dict) -> dict:
    if not isinstance(spec, dict) or not spec.get("file") or not spec.get("match"):
        raise ValueError("An evidence reference needs file and match.")
    return {"side": "-", "summary": "-", **spec}


REPORTED_EVENTS = ("resignation",)
_NOT_IN_A_REPORT = ("emp_id", "person", "exit_date", "last_working_day", "effective_date", "confirmed")


def _check(data) -> tuple[list[dict], list[dict]]:
    contractors, changes, _ = _check_all(data)
    return contractors, changes


def _check_all(data) -> tuple[list[dict], list[dict], list[dict]]:
    if not isinstance(data, dict):
        raise ValueError("The file must be a JSON object.")
    contractors, changes = data.get("contractors", []), data.get("announced_changes", [])
    reports = data.get("reported_events", [])
    keys = [c.get("key") for c in contractors + changes + reports]
    if any(not k for k in keys) or len(set(keys)) != len(keys):
        raise ValueError("Every record needs a key, and keys must be unique.")
    for c in contractors:
        for f in ("name", "role_as_written", "noted_on", "documented_in", "evidence"):
            if not c.get(f):
                raise ValueError(f"{c['key']}: missing {f}.")
        if any(f in c for f in ("emp_id", "join_date", "email", "location")):
            raise ValueError(f"{c['key']}: a contractor record takes no Emp ID, dates or personal details.")
        _ref(c["evidence"])
        date.fromisoformat(c["noted_on"])
    for ch in changes:
        for f in ("department", "reports_to_position", "status", "noted_on", "documented_in", "evidence"):
            if not ch.get(f):
                raise ValueError(f"{ch['key']}: missing {f}.")
        if ch["status"] != "announced":
            raise ValueError(f"{ch['key']}: only announced changes are loaded here; a confirmed change needs "
                             "its own dated record.")
        if ch.get("effective_date") is not None:
            raise ValueError(f"{ch['key']}: an announced change has no effective date.")
        _ref(ch["evidence"])
        for extra in ch.get("also_stated_in", []):
            _ref(extra)
        date.fromisoformat(ch["noted_on"])
    for r in reports:
        for f in ("event", "status", "name_as_written", "reported_by", "noted_on", "documented_in", "evidence"):
            if not r.get(f):
                raise ValueError(f"{r['key']}: missing {f}.")
        if r["event"] not in REPORTED_EVENTS:
            raise ValueError(f"{r['key']}: unknown event {r['event']!r}.")
        if r["status"] != "reported_unverified":
            raise ValueError(f"{r['key']}: a reported event is loaded only as reported_unverified; a confirmed "
                             "change needs its own HR record.")
        if any(f in r for f in _NOT_IN_A_REPORT):
            raise ValueError(f"{r['key']}: a reported event takes no identity, exit date or last working day.")
        _ref(r["evidence"])
        date.fromisoformat(r["noted_on"])
    return contractors, changes, reports


def load_reviewed_org(session: Session, path: Path) -> LoadResult:
    contractors, changes, reports = _check_all(json.loads(Path(path).read_text(encoding="utf-8")))
    result = LoadResult()

    for c in contractors:
        ev, why = find_side(session, _ref(c["evidence"]))
        if why:
            result.rejected[c["key"]] = [why]
            continue
        released = max(release_timestamp(date.fromisoformat(c["noted_on"])), ev.released_on)
        note = (f"{c['key']}: contractor via {c.get('engaged_through') or 'an unnamed firm'}, as written in "
                f"{ev.evidence_key} ({ev.source.filename}). Reviewed: {c['documented_in']}. Not linked to "
                f"{', '.join(c.get('not_linked_to') or []) or 'any other name form'}.")
        clash = session.scalar(select(Person).where(Person.full_name == c["name"],
                                                    Person.worker_type == "employee"))
        if clash is not None:
            result.rejected[c["key"]] = [f"An employee is already named {c['name']!r}; not loaded."]
            continue
        existing = session.scalar(select(Person).where(Person.full_name == c["name"],
                                                       Person.worker_type == "contractor"))
        if existing is not None:
            same = (existing.source_evidence_id, existing.title, existing.note, existing.released_on) == \
                   (ev.id, c["role_as_written"], note, released)
            (result.unchanged.append(c["key"]) if same else result.rejected.setdefault(c["key"], [
                "A contractor with this name is already stored with different content; not overwritten."]))
            continue
        session.add(Person(emp_id=None, worker_type="contractor", full_name=c["name"], title=c["role_as_written"],
                           note=note, source_evidence_id=ev.id, released_on=released))
        session.flush()
        result.loaded.append(c["key"])

    for ch in changes:
        ev, why = find_side(session, _ref(ch["evidence"]))
        problems = [why] if why else []
        extra_keys = []
        for extra in ch.get("also_stated_in", []):
            e2, why2 = find_side(session, _ref(extra))
            problems += [why2] if why2 else []
            if e2 is not None:
                extra_keys.append(f"{e2.evidence_key} ({e2.source.filename})")
        dept = session.scalar(select(Department).where(Department.name == ch["department"]))
        if dept is None:
            problems.append(f"No department named {ch['department']!r} has been ingested.")
        if problems:
            result.rejected[ch["key"]] = problems
            continue
        pos = session.scalar(select(Position).where(Position.code == ch["reports_to_position"]))
        if pos is None:
            pos = Position(code=ch["reports_to_position"], title=ch.get("position_title") or ch["reports_to_position"])
            session.add(pos)
            session.flush()
        released = max(release_timestamp(date.fromisoformat(ch["noted_on"])), ev.released_on)
        note = (f"{ch['key']}: announced, effective date not confirmed. Source {ev.evidence_key} "
                f"({ev.source.filename})" + (f"; also stated in {', '.join(extra_keys)}" if extra_keys else "")
                + f". Reviewed: {ch['documented_in']}.")
        existing = session.scalar(select(DepartmentLine).where(
            DepartmentLine.department_id == dept.id, DepartmentLine.reports_to_position_id == pos.id,
            DepartmentLine.status == "announced"))
        if existing is not None:
            same = (existing.source_evidence_id, existing.note, existing.released_on, existing.valid_from) == \
                   (ev.id, note, released, None)
            (result.unchanged.append(ch["key"]) if same else result.rejected.setdefault(ch["key"], [
                "This announced change is already stored with different content; not overwritten."]))
            continue
        session.add(DepartmentLine(department_id=dept.id, reports_to_position_id=pos.id, status="announced",
                                   valid_from=None, start_exact=False, valid_to=None, released_on=released,
                                   source_evidence_id=ev.id, note=note))
        session.flush()
        result.loaded.append(ch["key"])

    for r in reports:
        ev, why = find_side(session, _ref(r["evidence"]))
        if why:
            result.rejected[r["key"]] = [why]
            continue
        released = max(release_timestamp(date.fromisoformat(r["noted_on"])), ev.released_on)
        value = json.dumps({"key": r["key"], "status": "reported_unverified", "name_as_written": r["name_as_written"],
                            "reported_by": r["reported_by"], "notice_as_written": r.get("notice_as_written"),
                            "documented_in": r["documented_in"]}, sort_keys=True)
        existing = session.scalar(select(Claim).where(Claim.subject_type == "reported_event",
                                                      Claim.subject_key == r["key"]))
        if existing is not None:
            same = (existing.evidence_id, existing.attribute, existing.value, existing.released_on) ==                    (ev.id, r["event"], value, released)
            (result.unchanged.append(r["key"]) if same else result.rejected.setdefault(r["key"], [
                "This reported event is already stored with different content; not overwritten."]))
            continue
        session.add(Claim(evidence_id=ev.id, subject_type="reported_event", subject_key=r["key"], attribute=r["event"],
                          value=value, extractor="rule", confidence="L", released_on=released, exported_on=None,
                          as_of_start=None, as_of_end=None))
        session.flush()
        result.loaded.append(r["key"])
    return result
