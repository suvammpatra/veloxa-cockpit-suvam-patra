"""Synthetic test records. Not Veloxa facts: names and dates exist only to exercise rules."""

from __future__ import annotations

import hashlib
import itertools
from datetime import date, datetime

from app.models import Department, DepartmentMembership, Evidence, Person, SourceRecord

DAY1 = datetime(2026, 11, 16, 10, 0)
DAY2 = datetime(2026, 11, 17, 10, 0)
DAY3 = datetime(2026, 11, 18, 10, 0)

_seq = itertools.count(1)


def source(db, *, filename=None, released=DAY1, exported=None, rung=3, file_type="xlsx"):
    n = next(_seq)
    src = SourceRecord(
        source_key=f"SRC-{n:03d}", filename=filename or f"test_{n}.{file_type}", file_type=file_type,
        trust_rung=rung, sha256=hashlib.sha256(str(n).encode()).hexdigest(),
        released_on=released, exported_on=exported,
    )
    db.add(src)
    db.flush()
    return src


def evidence(db, src, content="test content", *, locator=None, exported=None):
    n = next(_seq)
    ev = Evidence(evidence_key=f"E{n:03d}", source_record_id=src.id, locator=locator or f"row {n}",
                  content=content, released_on=src.released_on,
                  exported_on=exported if exported is not None else src.exported_on)
    db.add(ev)
    db.flush()
    return ev


def department(db, code, name=None):
    d = Department(code=code, name=name or code)
    db.add(d)
    db.flush()
    return d


def employee(db, name, emp_id, *, dept=None, joined=date(2024, 1, 1), exit=None,
             released=DAY1, member_from=datetime(2026, 10, 31), start_exact=False):
    p = Person(emp_id=emp_id, full_name=name, worker_type="employee", join_date=joined,
               exit_date=exit, released_on=released)
    db.add(p)
    db.flush()
    if dept is not None:
        db.add(DepartmentMembership(person_id=p.id, department_id=dept.id, valid_from=member_from,
                                    start_exact=start_exact, released_on=released))
        db.flush()
    return p


def contractor(db, name, *, released=DAY3):
    p = Person(emp_id=None, full_name=name, worker_type="contractor", released_on=released)
    db.add(p)
    db.flush()
    return p
