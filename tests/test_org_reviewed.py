"""Day 4 approved follow-ups: invoice dates, the reviewed contractor, the announced reporting
change, and the Pria / Vicky aliases. Data is synthetic (tests/test_answering.py world)."""

import csv
import json
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.answering.engine import ask
from app.database import make_session_factory
from app.ingestion.dates import first_numeric_dmy
from app.ingestion.identity_links import link_identities, load_curated
from app.ingestion.org_registry import load_reviewed_org
from app.ingestion.pipeline import Ingestor
from app.models import Alias, DepartmentLine, Evidence, Incident, Person, Position, SourceRecord
from app.services.identity import resolve_person
from app.temporal import TimeContext
from tests import sourcefiles as sf
from tests.test_answering import AT_D1, AT_D3, MAIL, world  # noqa: F401  (world is a fixture)

ROOT = Path(__file__).resolve().parent.parent
D4 = date(2026, 11, 19)
AT_D4 = TimeContext.known_at(datetime(2026, 11, 19, 12, 0))
BEFORE_D4 = TimeContext.known_at(datetime(2026, 11, 19, 9, 59))

CONTRACTOR = {"key": "CTR-TEST", "name": "Q. Tester", "role_as_written": "On-call support",
              "engaged_through": "Test Infra", "noted_on": "2026-11-19", "documented_in": "test",
              "evidence": {"file": "Invoice_TEST-1.pdf", "match": ["Q. Tester", "On-call support"],
                           "date": "2026-10-01"},
              "not_linked_to": ["Rinal", "Rina"]}
CHANGE = {"key": "TEST-MKT-CRO", "department": "Marketing", "reports_to_position": "CRO", "position_title": "CRO",
          "status": "announced", "effective_date": None, "noted_on": "2026-11-19", "documented_in": "test",
          "evidence": {"file": "T7_Test_Note.docx", "match": ["marketing will report to the new CRO"], "date": None}}


@pytest.fixture
def org(world, engine, tmp_path):
    """The world plus a Day 4 invoice and a voice-note transcript."""
    d4 = tmp_path / "d4"
    sf.pdf(d4 / "documents" / "Invoice_TEST-1.pdf",
           ["TEST INFRA\nTAX INVOICE\nInvoice No.\nTEST-1\nDate\n01/10/2026\nDescription\n"
            "On-call support, Q. Tester, September 2026 (monthly retainer)"])
    sf.docx(d4 / "transcripts" / "T7_Test_Note.docx",
            ["T7 voice note", "So, marketing will report to the new CRO from next month. Still finalising."])
    Ingestor(make_session_factory(engine), release_day=D4, default_exported_on=date(2026, 10, 31)).ingest([d4])
    return world


def write(tmp_path, contractors=(), changes=(), name="org.json"):
    p = tmp_path / name
    p.write_text(json.dumps({"contractors": list(contractors), "announced_changes": list(changes)}),
                 encoding="utf-8")
    return p


def load(db, path):
    r = load_reviewed_org(db, path)
    db.commit()
    return r


# ---------------------------------------------------------------- 1. invoice date

def test_numeric_invoice_date_is_read_day_first_and_kept_as_written(org, db):
    src = db.scalar(select(SourceRecord).where(SourceRecord.filename == "Invoice_TEST-1.pdf"))
    ev = db.scalar(select(Evidence).where(Evidence.source_record_id == src.id))
    assert src.exported_on == datetime(2026, 10, 1)                       # 1 October, not 10 January
    assert ev.date_as_written == "01/10/2026"                             # the source string, unchanged
    assert "read as DD/MM/YYYY" in src.exported_basis and "'01/10/2026'" in src.exported_basis


def test_numeric_dates_are_read_only_for_invoices(engine, tmp_path):
    sf.pdf(tmp_path / "p" / "Board_Update_Test.pdf", ["Board update. Date 01/10/2026."])
    Ingestor(make_session_factory(engine), release_day=D4).ingest([tmp_path / "p"])
    with make_session_factory(engine)() as s:
        src = s.scalar(select(SourceRecord).where(SourceRecord.filename == "Board_Update_Test.pdf"))
        assert src.exported_on is None and "No export date" in src.exported_basis


def test_numeric_date_helper():
    assert first_numeric_dmy("Date\n01/10/2026") == (date(2026, 10, 1), "01/10/2026")
    assert first_numeric_dmy("31/02/2026 then 05/03/2026") == (date(2026, 3, 5), "05/03/2026")  # not a real date
    assert first_numeric_dmy("Ref 101/10/20261") is None


# ---------------------------------------------------------------- 2. contractor

def test_reviewed_contractor_is_stored_without_invented_details(org, db, tmp_path):
    r = load(db, write(tmp_path, [CONTRACTOR]))
    assert r.loaded == ["CTR-TEST"]
    p = db.scalar(select(Person).where(Person.full_name == "Q. Tester"))
    assert (p.worker_type, p.emp_id, p.join_date, p.work_email, p.location) == ("contractor", None, None, None, None)
    assert p.title == "On-call support"
    ev = db.get(Evidence, p.source_evidence_id)
    assert ev.source.filename == "Invoice_TEST-1.pdf" and "Q. Tester" in ev.content
    assert "Not linked to Rinal, Rina" in p.note
    again = load(db, write(tmp_path, [CONTRACTOR]))
    assert again.unchanged == ["CTR-TEST"] and db.scalar(select(func.count(Person.id)).where(
        Person.worker_type == "contractor")) == 1


def test_contractor_never_changes_employee_counts_or_payroll(org, db, tmp_path):
    before = ask(db, "How many employees do we have?", AT_D4)
    dept_before = ask(db, "How many people are in Engineering?", AT_D4)
    pay_before = ask(db, "Company payroll total for March 2026", AT_D4, payroll=org["payroll"])
    load(db, write(tmp_path, [CONTRACTOR]))
    after = ask(db, "How many employees do we have?", AT_D4)
    assert before.short_answer.split(" on ")[0] == after.short_answer.split(" on ")[0] == "5 employees"
    assert "1 contractor(s) are known and not counted: Q. Tester" in after.short_answer
    assert "Invoice_TEST-1.pdf" in {c.filename for l in after.evidence_chain for c in l.citations}
    assert ask(db, "How many people are in Engineering?", AT_D4).short_answer == dept_before.short_answer
    pay_after = ask(db, "Company payroll total for March 2026", AT_D4, payroll=org["payroll"])
    assert pay_before.status == pay_after.status == "answered"
    assert pay_after.short_answer == pay_before.short_answer and "across 6 people" in pay_after.short_answer


def test_contractor_is_not_linked_to_similar_names(org, db, tmp_path):
    load(db, write(tmp_path, [CONTRACTOR]))
    link_identities(db)
    db.commit()
    assert resolve_person(db, "Rinal", AT_D4).status == "unresolved"
    inc = db.scalar(select(Incident).where(Incident.responder_alias == "Rinal"))
    assert inc.responder_person_id is None
    assert resolve_person(db, "Q. Tester", AT_D4).person.worker_type == "contractor"
    assert resolve_person(db, "Tester", AT_D4).status == "unresolved"  # no guessing from a surname


def test_contractor_records_are_validated(org, db, tmp_path):
    with pytest.raises(ValueError, match="no Emp ID"):
        load_reviewed_org(db, write(tmp_path, [dict(CONTRACTOR, emp_id="X1")]))
    r = load(db, write(tmp_path, [dict(CONTRACTOR, evidence=dict(CONTRACTOR["evidence"], date="2026-01-10"))]))
    assert "dated 2026-10-01, the file says 2026-01-10" in r.rejected["CTR-TEST"][0]
    assert db.scalar(select(func.count(Person.id)).where(Person.worker_type == "contractor")) == 0


# ---------------------------------------------------------------- 3. announced reporting change

def test_announced_change_is_stored_pending_with_a_vacant_role(org, db, tmp_path):
    assert load(db, write(tmp_path, changes=[CHANGE])).loaded == ["TEST-MKT-CRO"]
    line = db.scalar(select(DepartmentLine))
    assert (line.status, line.valid_from, line.department.name, line.reports_to.code) == (
        "announced", None, "Marketing", "CRO")
    assert db.scalar(select(func.count(Position.id))) == 1 and "effective date not confirmed" in line.note
    assert load(db, write(tmp_path, changes=[CHANGE])).unchanged == ["TEST-MKT-CRO"]
    with pytest.raises(ValueError, match="only announced changes"):
        load_reviewed_org(db, write(tmp_path, changes=[dict(CHANGE, status="confirmed")]))
    with pytest.raises(ValueError, match="no effective date"):
        load_reviewed_org(db, write(tmp_path, changes=[dict(CHANGE, effective_date="2026-12-01")]))


def test_announcement_is_shown_but_never_applied(org, db, tmp_path):
    load(db, write(tmp_path, changes=[CHANGE]))
    now = ask(db, "Who does Omar Haddad report to?", AT_D4)
    assert now.short_answer.startswith("Omar Haddad reports to Lena Ortiz on 19 Nov 2026.")
    assert ("Pending for Marketing, not in effect: announced that Marketing will report to CRO (no holder on "
            "record), effective date not confirmed") in now.short_answer
    later = ask(db, "Who will Omar Haddad report to on 1 Jan 2027?", AT_D4)
    assert "reports to Lena Ortiz on 1 Jan 2027" in later.short_answer  # still not applied
    dept = ask(db, "Who does Marketing report to?", AT_D4)
    assert dept.status == "uncertain" and "No confirmed line for Marketing" in dept.short_answer
    assert "Pending, not in effect" in dept.short_answer
    assert {c.filename for l in dept.evidence_chain for c in l.citations} == {"T7_Test_Note.docx"}


def test_announcement_respects_point_in_time(org, db, tmp_path):
    load(db, write(tmp_path, changes=[CHANGE]))
    for ctx in (AT_D3, BEFORE_D4):        # before the 10:00 release on 19 Nov
        ans = ask(db, "Who does Omar Haddad report to?", ctx)
        assert "Pending" not in ans.short_answer and "reports to Lena Ortiz" in ans.short_answer
    recorded = TimeContext.recorded_by("2026-11-19", knowledge_cutoff=datetime(2026, 11, 19, 12))
    assert "Pending" not in ask(db, "Who does Marketing report to?", recorded).short_answer  # undated transcript


def test_the_project_org_file_holds_only_the_approved_records():
    data = json.loads((ROOT / "data" / "org_reviewed.json").read_text(encoding="utf-8"))
    [ctr] = data["contractors"]
    assert (ctr["name"], ctr["evidence"]["file"], ctr["evidence"]["date"]) == ("S. Patil", "Invoice_PIS-114.pdf",
                                                                              "2026-10-01")
    assert set(ctr["not_linked_to"]) == {"Snehal", "Sneha"} and not {"emp_id", "join_date"} & set(ctr)
    [ch] = data["announced_changes"]
    assert (ch["department"], ch["reports_to_position"], ch["status"], ch["effective_date"]) == (
        "Marketing", "CRO", "announced", None)


def test_the_project_org_file_loads_nothing_without_the_source_pack(db):
    r = load(db, ROOT / "data" / "org_reviewed.json")
    assert r.loaded == [] and set(r.rejected) == {"CTR-S-PATIL", "T6B-MKT-CRO", "T6D-RESIGNATION-REPORT"}
    assert db.scalar(select(func.count(Person.id))) == 0 and db.scalar(select(func.count(DepartmentLine.id))) == 0
    from app.models import Claim
    assert db.scalar(select(func.count(Claim.id))) == 0       # the T6d report is not stored without its source


# ---------------------------------------------------------------- 4. aliases

def test_pria_and_vicky_resolve_at_medium_from_their_review_date_and_sid_does_not(db):
    for emp_id, name in (("VX004", "Vikram Menon"), ("VX007", "Priya Nair"), ("VX009", "Arjun Das"),
                         ("VX012", "Sneha Kulkarni"), ("VX018", "Rahul Verma"), ("VX008", "Siddharth Mehta")):
        db.add(Person(emp_id=emp_id, full_name=name, worker_type="employee", released_on=datetime(2026, 11, 16, 10)))
    db.flush()
    load_curated(db, ROOT / "data" / "aliases_reviewed.csv")
    for alias, target in (("Pria", "Priya Nair"), ("Vicky", "Vikram Menon")):
        r = resolve_person(db, alias, AT_D4)
        assert (r.status, r.person.full_name, r.confidence, r.method) == ("resolved", target, "M", "alias")
        assert resolve_person(db, alias, AT_D3).status == "unresolved"  # reviewed on 19 Nov
    assert resolve_person(db, "Sid", AT_D4).status == "unresolved"
    assert resolve_person(db, "Snehal", AT_D4).status == "unresolved"
    assert resolve_person(db, "Sneha", AT_D4).person.full_name == "Sneha Kulkarni"  # never Snehal
    rows = db.scalars(select(Alias).where(Alias.alias_text.in_(("Pria", "Vicky")))).all()
    assert all((a.origin, a.confidence) == ("curated", "M") and a.evidence_note.startswith("Reviewed")
               for a in rows)


def test_a_medium_alias_stays_visible_in_the_answer(world, db, tmp_path):
    p = tmp_path / "a.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["alias_text", "kind", "status", "target_emp_id", "confidence", "evidence_note", "released_on"])
        w.writerow(["Mimi", "transcript_name", "resolved", "T002", "M", "Reviewed: test note", "2026-11-18"])
    load_curated(db, p)
    db.commit()
    ans = ask(db, "Who does Mimi report to?", AT_D3)
    assert "Mira Kale reports to Lena Ortiz" in ans.short_answer
    assert ans.confidence == "Medium" and "A name was linked to a person at confidence M" in " ".join(
        ans.confidence_reasons)
