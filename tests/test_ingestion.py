"""Phase 3: ingestion of CSV, XLSX, PDF, DOCX, EML and TXT, with provenance and failure handling."""

import hashlib
import re
import json
from datetime import date, datetime

import pytest
from sqlalchemy import select, text

from app.ingestion import typed
from app.ingestion.identity_links import load_curated
from app.ingestion.pipeline import Ingestor
from app.models import (Alias, Claim, Commit, Conflict, Evidence, FinancialTxn, Incident, IngestionError,
                        Person, ReportingLine, SourceRecord, Ticket)
from app.privacy.payroll import PayrollStore
from app.repositories.temporal import visible
from app.services.identity import resolve_person
from app.services.org import department_members, manager_as_of
from app.temporal import TimeContext
from tests import sourcefiles as sf

D1, D2, D3 = date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18)
AT_D1 = datetime(2026, 11, 16, 12, 0)
AT_D3 = datetime(2026, 11, 18, 12, 0)

GL_HEADER = ["Txn Date", "Voucher", "Vendor / Payee", "Ref", "Cost Centre", "Amount (Rs.)", "Narration", "Entered By"]
JIRA_HEADER = ["Key", "Type", "Summary", "Epic Link", "Assignee", "Story Points", "Status", "Created",
               "Resolved", "Fix Version"]
INC_HEADER = ["ID", "Severity", "Opened", "Resolved", "Service", "Responder"]
GIT_HEADER = ["sha", "author_email", "committed_at", "repo", "message", "files_changed"]


@pytest.fixture
def factory(engine):
    from app.database import make_session_factory
    return make_session_factory(engine)


@pytest.fixture
def payroll_store():
    store = PayrollStore(":memory:")
    yield store
    store.dispose()


@pytest.fixture
def run(factory, payroll_store):
    def _run(*paths, day=D1, exported=None):
        return Ingestor(factory, release_day=day, payroll_store=payroll_store,
                        default_exported_on=exported).ingest(list(paths))
    return _run


def _file(report, name):
    return next(f for f in report.files if f.relative_path.endswith(name))


# ---------------------------------------------------------------- supported formats

def test_xlsx_keka_snapshot_builds_people_lines_and_unknown_history(run, db, tmp_path):
    report = run(sf.keka(tmp_path / "Employee_Master.xlsx", sf.staff_rows()))
    f = _file(report, "Employee_Master.xlsx")
    assert f.status == "ingested" and f.counts["people"] == 5 and f.counts["reporting_lines"] == 4
    src = db.scalar(select(SourceRecord))
    assert (src.system, src.trust_rung, src.exported_on) == ("Keka HRMS", 3, datetime(2026, 10, 31))
    assert "Exported 31-Oct-2026" in src.exported_basis
    mira = db.scalar(select(Person).where(Person.emp_id == "T002"))
    line = db.scalar(select(ReportingLine).where(ReportingLine.person_id == mira.id))
    assert line.start_exact is False and line.valid_from == datetime(2026, 10, 31)
    # Before the snapshot the manager is unknown, not assumed (DECISIONS.md 17).
    before = manager_as_of(db, mira, TimeContext.known_at(datetime(2026, 10, 30, 12, 0)))
    after = manager_as_of(db, mira, TimeContext.known_at(AT_D1))
    assert before.status == "unknown" and after.manager == "Lena Ortiz"
    # Asked today about March, department membership cannot be established (Phase 2 decision kept).
    march = TimeContext.recorded_by(datetime(2026, 3, 31, 12, 0), AT_D1)
    assert department_members(db, "ENGINEERING", march) is None
    assert department_members(db, "ENGINEERING", TimeContext.known_at(AT_D1)) == {
        p.id for p in db.scalars(select(Person).where(Person.emp_id.in_(["T002", "T003", "T004"])))}


def test_csv_git_log_converts_utc_to_ist(run, db, tmp_path):
    path = sf.csv_file(tmp_path / "engineering" / "git_log.csv", GIT_HEADER,
                       [["abc123", "Mira@Example.test", "2026-06-02T20:00:00+00:00", "engine", "fix", "3"]])
    report = run(path)
    assert _file(report, "git_log.csv").counts == {"commits": 1}
    c = db.scalar(select(Commit))
    assert c.committed_at == datetime(2026, 6, 3, 1, 30)  # next day in IST
    assert c.author_email == "mira@example.test"
    ev = db.get(Evidence, c.evidence_id)
    assert ev.locator == "row 2" and ev.exported_on == c.committed_at


def test_pdf_board_style_document_is_dated_from_its_text(run, db, tmp_path):
    run(sf.pdf(tmp_path / "Board_Update_Q3.pdf", ["Board update. Period: Jul to Sep. Sent 6 Oct 2026.", "Page two"]))
    src = db.scalar(select(SourceRecord))
    assert (src.trust_rung, src.exported_on) == (2, datetime(2026, 10, 6))
    assert [e.locator for e in src.evidence] == ["page 1", "page 2"]
    assert src.evidence[0].date_as_written == "6 Oct 2026"


def test_docx_transcript_has_no_export_date_and_low_confidence(run, db, tmp_path):
    run(sf.docx(tmp_path / "transcripts" / "T9_Test_Call.docx",
                ["T9 call", 'She said "forty-eight" & moved on.']))
    src = db.scalar(select(SourceRecord))
    assert (src.system, src.trust_rung, src.exported_on) == ("MeetNotes AI", 5, None)
    assert src.evidence[1].content == 'She said "forty-eight" & moved on.'
    assert {e.confidence for e in src.evidence} == {"L"}
    # Recorded-by queries exclude it: when it was recorded is unknown (ARCHITECTURE.md 11).
    assert not db.scalars(visible(select(Evidence), Evidence, TimeContext.recorded_by(AT_D3, AT_D3))).all()


def test_eml_is_dated_by_its_header_in_ist(run, db, tmp_path):
    run(sf.eml(tmp_path / "email" / "01.eml", sender="a@example.test", to="b@example.test",
               subject="Test", date="Sat, 28 Feb 2026 20:15:00 +0530", body="Body text."))
    src = db.scalar(select(SourceRecord))
    assert (src.trust_rung, src.exported_on) == (4, datetime(2026, 2, 28, 20, 15))
    ev = src.evidence[0]
    assert ev.locator == "message" and "Subject: Test" in ev.content and "Body text." in ev.content


def test_txt_readme_export_date_applies_to_undated_files_in_its_folder(run, db, tmp_path):
    room = tmp_path / "room"
    room.mkdir()
    (room / "README.txt").write_text("Test data room. Exported by IT on 31 Oct 2026.\n\nfinance/  ledgers\n")
    sf.xlsx(room / "hr" / "Hiring_Tracker.xlsx",
            {"Requisitions": (None, ["Req ID", "Role", "Status"], [["R-1", "Engineer", "Open"]])})
    run(room)
    readme = db.scalar(select(SourceRecord).where(SourceRecord.filename == "README.txt"))
    tracker = db.scalar(select(SourceRecord).where(SourceRecord.filename == "Hiring_Tracker.xlsx"))
    assert readme.role == "reference" and [e.locator for e in readme.evidence] == ["para 1", "para 2"]
    assert tracker.exported_on == datetime(2026, 10, 31) and "README.txt" in tracker.exported_basis
    assert json.loads(tracker.evidence[0].fields_json) == {"Req ID": "R-1", "Role": "Engineer", "Status": "Open"}


# ---------------------------------------------------------------- provenance

def test_provenance_is_preserved(run, db, tmp_path):
    path = sf.xlsx(tmp_path / "finance" / "GL_Export_Test.xlsx", {"GL": ("General ledger export.", GL_HEADER, [
        ["2026-04-08", "JV-1", "Cloud Co", "R-1", "ENG", 1000, "Cloud, previous month", "XX"],
        ["2026-04-28", "JV-2", "Rent Co", "R-2", "G&A", 2500.5, "Rent", "XX"]])})
    run(tmp_path / "finance", day=D3)
    src = db.scalar(select(SourceRecord))
    assert src.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert src.relative_path == "GL_Export_Test.xlsx" and src.size_bytes == path.stat().st_size
    assert src.released_on == datetime(2026, 11, 18, 10, 0)  # 10:00 IST on the release day
    first, second = src.evidence
    assert (first.locator, second.locator) == ("GL!row 3", "GL!row 4")
    assert int(second.evidence_key[1:]) == int(first.evidence_key[1:]) + 1
    t = db.scalar(select(FinancialTxn).where(FinancialTxn.voucher == "JV-1"))
    assert t.evidence_id == first.id and t.amount_paise == 100000
    # "previous month" lines describe the month before posting (ARCHITECTURE.md 4).
    assert (t.as_of_start, t.exported_on) == (datetime(2026, 3, 1), datetime(2026, 4, 8))
    assert db.scalar(select(FinancialTxn.amount_paise).where(FinancialTxn.voucher == "JV-2")) == 250050


def test_jira_release_date_claim_carries_last_changed_as_its_record_date(run, db, tmp_path):
    sf.xlsx(tmp_path / "Jira_Export_TEST.xlsx", {
        "Issues": ("Jira export, project TEST.", JIRA_HEADER,
                   [["TEST-11", "Story", "Work (mk-1)", "TEST-1", "MK", 3, "Done", "2026-05-06", "2026-05-18", "GA"]]),
        "Versions": (None, ["Version", "Release Date", "Original Release Date", "Last Changed", "Changed By"],
                     [["GA", "2026-12-15", "2026-09-15", "2026-09-02", "someone"]])})
    run(tmp_path, exported=date(2026, 10, 31))
    t = db.scalar(select(Ticket))
    assert (t.project_key, t.status, t.story_points, t.exported_on) == ("TEST", "Done", 3, datetime(2026, 10, 31))
    claims = {c.attribute: c for c in db.scalars(select(Claim).where(Claim.subject_type == "release"))}
    assert claims["release_date"].value == "2026-12-15"
    assert claims["release_date"].exported_on == datetime(2026, 9, 2)
    assert claims["original_release_date"].exported_on is None  # when it was first set is unknown


# ---------------------------------------------------------------- duplicates and re-exports

def test_duplicate_content_is_detected_and_not_ingested_twice(run, db, tmp_path):
    a = sf.keka(tmp_path / "a" / "Employee_Master.xlsx", sf.staff_rows())
    b = tmp_path / "b" / "Employee_Master_copy.xlsx"
    b.parent.mkdir()
    b.write_bytes(a.read_bytes())
    run(a)
    report = run(b, a, day=D2)
    assert [f.status for f in report.files] == ["duplicate", "duplicate"]
    assert "SRC-001" in report.files[0].message
    assert db.scalar(text("SELECT COUNT(*) FROM source_record")) == 1
    assert db.scalar(text("SELECT COUNT(*) FROM person")) == 5


def test_changed_reexport_keeps_the_earlier_record_and_stores_a_conflict(run, db, tmp_path):
    rows = [["2026-04-28", "JV-2", "Rent Co", "R-2", "G&A", 2500, "Rent", "XX"]]
    sf.xlsx(tmp_path / "d1" / "GL_Export_A.xlsx", {"GL": (None, GL_HEADER, rows)})
    rows[0][5] = 2600
    sf.xlsx(tmp_path / "d2" / "GL_Export_A.xlsx", {"GL": (None, GL_HEADER, rows)})
    run(tmp_path / "d1")
    report = run(tmp_path / "d2", day=D2)
    assert db.scalar(select(FinancialTxn.amount_paise)) == 250000  # nothing overwritten in place
    conflict = db.scalar(select(Conflict))
    assert conflict.status == "open" and len(conflict.sides) == 2 and "260000" in conflict.sides[1].summary
    assert report.files[0].warnings >= 2  # same name seen before, and the differing value


# ---------------------------------------------------------------- malformed files and extraction failures

def test_corrupt_file_fails_cleanly_and_the_run_continues(run, db, tmp_path):
    (tmp_path / "Pulse_Survey.xlsx").write_bytes(b"this is not a spreadsheet")
    sf.eml(tmp_path / "02.eml", sender="a@example.test", to="b@example.test", subject="Ok",
           date="Mon, 2 Mar 2026 10:00:00 +0530", body="Fine.")
    report = run(tmp_path)
    assert _file(report, "Pulse_Survey.xlsx").status == "failed" and not report.ok
    assert _file(report, "02.eml").status == "ingested"
    bad = db.scalar(select(SourceRecord).where(SourceRecord.filename == "Pulse_Survey.xlsx"))
    assert bad.status == "failed" and not bad.evidence
    assert "damaged" in bad.errors[0].message


@pytest.mark.parametrize("name,content,expected", [
    ("empty.txt", b"", "empty"),
    ("blank.docx", b"PK\x03\x04 broken", "Not a valid .docx"),
    ("headers_missing.eml", b"just some words\n", "No email headers"),
    ("broken.pdf", b"%PDF-1.4 not really", "Not a readable PDF"),
])
def test_malformed_files_are_recorded_as_failed(run, db, tmp_path, name, content, expected):
    (tmp_path / name).write_bytes(content)
    report = run(tmp_path / name)
    assert report.files[0].status == "failed"
    assert expected in db.scalar(select(IngestionError.message))


def test_bad_rows_are_logged_with_their_locator_and_kept_as_evidence(run, db, tmp_path):
    sf.xlsx(tmp_path / "GL_Export_B.xlsx", {"GL": (None, GL_HEADER, [
        ["2026-04-08", "JV-1", "Cloud Co", "R-1", "ENG", "abc", "Cloud", "XX"],
        ["2026-04-09", "JV-3", "Other Co", "R-3", "ENG", 10, "Other", "XX"]])})
    report = run(tmp_path)
    f = _file(report, "GL_Export_B.xlsx")
    assert f.status == "partial" and f.counts == {"gl_lines": 1} and f.errors == 1
    err = db.scalar(select(IngestionError).where(IngestionError.severity == "error"))
    assert err.locator == "GL!row 2" and "'abc' is not a number" in err.message
    assert db.scalar(select(Evidence).where(Evidence.locator == "GL!row 2")) is not None


def test_extraction_failure_rolls_back_that_file_only(run, db, tmp_path, monkeypatch):
    def boom(ctx, units):
        raise RuntimeError("extractor broke")
    monkeypatch.setitem(typed.EXTRACTORS, "gl", boom)
    sf.xlsx(tmp_path / "GL_Export_C.xlsx", {"GL": (None, GL_HEADER, [["2026-04-08", "JV-1", "C", "R", "E", 1, "N", "X"]])})
    report = run(tmp_path)
    assert report.files[0].status == "failed"
    src = db.scalar(select(SourceRecord))
    assert src.status == "failed" and not src.evidence  # no half-written evidence
    assert "extractor broke" in src.errors[0].message


def test_unsupported_and_template_files_are_skipped_and_logged(run, db, tmp_path):
    (tmp_path / "photo.png").write_bytes(b"\x89PNG")
    sf.xlsx(tmp_path / "templates" / "Evidence_Index.xlsx", {"Index": (None, ["Ref", "File"], [["E1", "x"]])})
    report = run(tmp_path)
    assert {f.status for f in report.files} == {"skipped"}
    assert db.scalar(text("SELECT COUNT(*) FROM source_record")) == 0
    messages = db.scalars(select(IngestionError.message)).all()
    assert any("Unsupported file type .png" in m for m in messages)
    assert any("never evidence" in m for m in messages)


# ---------------------------------------------------------------- missing dates

def test_missing_dates_are_never_imputed(run, db, tmp_path):
    sf.xlsx(tmp_path / "Incidents_Test.xlsx", {"Incidents": ("Incident export.", INC_HEADER, [
        ["INC-1", "SEV1", "2026-08-22T20:00:00Z", "2026-08-22T21:00:00Z", "api", "Rina"],
        ["INC-2", "SEV2", None, None, "api", "Rina"]])})
    sf.eml(tmp_path / "03.eml", sender="a@example.test", to="b@example.test", subject="No date",
           date=None, body="Undated.")
    report = run(tmp_path)
    inc = db.scalar(select(Incident))
    assert inc.key == "INC-1" and inc.opened_at == datetime(2026, 8, 23, 1, 30)  # 23 Aug IST
    assert db.scalar(select(Incident).where(Incident.key == "INC-2")) is None
    assert any("Opened time" in m for m in db.scalars(select(IngestionError.message)))
    mail = db.scalar(select(SourceRecord).where(SourceRecord.filename == "03.eml"))
    assert mail.exported_on is None and "No readable Date header" in mail.exported_basis
    assert _file(report, "03.eml").warnings >= 1


def test_snapshot_without_export_date_creates_people_but_no_dated_history(run, db, tmp_path):
    report = run(sf.keka(tmp_path / "Employee_Master.xlsx", sf.staff_rows(), exported=None))
    f = report.files[0]
    assert f.status == "partial" and f.counts["people"] == 5 and "reporting_lines" not in f.counts
    assert db.scalar(text("SELECT COUNT(*) FROM department_membership")) == 0


# ---------------------------------------------------------------- identities

def _engineering_files(tmp_path):
    sf.xlsx(tmp_path / "Jira_Export_T.xlsx", {"Issues": (None, JIRA_HEADER, [
        ["T-1", "Story", "a", None, "MK", 1, "Done", "2026-05-01", None, None],
        ["T-2", "Story", "b", None, "RS", 2, "To Do", "2026-05-01", None, None]])})
    sf.xlsx(tmp_path / "Incidents_T.xlsx", {"Incidents": (None, INC_HEADER, [
        ["INC-1", "SEV1", "2026-08-04T05:12:00Z", None, "api", "Rina"],
        ["INC-2", "SEV2", "2026-08-27T05:12:00Z", None, "api", "Rinal"]])})
    sf.csv_file(tmp_path / "git_log.csv", GIT_HEADER, [
        ["s1", "rina.s@example.test", "2026-06-01T10:00:00+00:00", "engine", "x", "1"],
        ["s2", "rshah@users.noreply.example", "2026-06-02T10:00:00+00:00", "engine", "y", "1"]])


def test_ambiguous_initials_are_not_linked(run, db, tmp_path):
    sf.keka(tmp_path / "Employee_Master.xlsx", sf.staff_rows())
    _engineering_files(tmp_path)
    run(tmp_path)
    mk = db.scalar(select(Ticket).where(Ticket.key == "T-1"))
    assert mk.assignee_person_id is None  # Mira Kale and Mohan Kale share MK
    alias = db.scalar(select(Alias).where(Alias.alias_text == "MK"))
    assert alias.status == "ambiguous" and alias.target_person_id is None
    assert "Mira Kale" in alias.evidence_note and "Mohan Kale" in alias.evidence_note


def test_exact_rules_link_with_a_cited_record(run, db, tmp_path):
    sf.keka(tmp_path / "Employee_Master.xlsx", sf.staff_rows())
    _engineering_files(tmp_path)
    run(tmp_path)
    rina = db.scalar(select(Person).where(Person.emp_id == "T004"))
    assert db.scalar(select(Ticket).where(Ticket.key == "T-2")).assignee_person_id == rina.id
    assert db.scalar(select(Commit).where(Commit.sha == "s1")).author_person_id == rina.id
    email_alias = db.scalar(select(Alias).where(Alias.kind == "git_email", Alias.status == "resolved"))
    assert email_alias.confidence == "H" and email_alias.origin == "rule"
    assert db.get(Evidence, rina.source_evidence_id).evidence_key in email_alias.evidence_note
    # The no-reply address matches no work email, so it stays unlinked until a reviewed alias says otherwise.
    assert db.scalar(select(Commit).where(Commit.sha == "s2")).author_person_id is None


def test_similar_first_names_are_never_merged(run, db, tmp_path):
    sf.keka(tmp_path / "Employee_Master.xlsx", sf.staff_rows())
    _engineering_files(tmp_path)
    run(tmp_path)
    inc1 = db.scalar(select(Incident).where(Incident.key == "INC-1"))
    inc2 = db.scalar(select(Incident).where(Incident.key == "INC-2"))
    assert inc1.responder_person_id is not None and inc2.responder_person_id is None
    assert db.scalar(select(Alias).where(Alias.alias_text == "Rinal")).status == "unresolved"


def test_a_link_made_by_a_later_release_is_not_visible_earlier(run, db, tmp_path):
    _engineering_files(tmp_path / "eng")
    run(tmp_path / "eng", day=D1)                      # names arrive before the people file
    assert db.scalar(select(Ticket).where(Ticket.key == "T-2")).assignee_person_id is None
    sf.keka(tmp_path / "hr" / "Employee_Master.xlsx", sf.staff_rows())
    run(tmp_path / "hr", day=D3)
    assert db.scalar(select(Ticket).where(Ticket.key == "T-2")).assignee_person_id is not None
    assert resolve_person(db, "RS", TimeContext.known_at(AT_D1)).status == "unresolved"
    assert resolve_person(db, "RS", TimeContext.known_at(AT_D3)).person.full_name == "Rina Shah"


def test_reviewed_alias_file_links_what_rules_cannot(run, db, tmp_path):
    sf.keka(tmp_path / "Employee_Master.xlsx", sf.staff_rows())
    _engineering_files(tmp_path)
    run(tmp_path)
    alias_csv = tmp_path / "aliases.csv"
    alias_csv.write_text("alias_text,kind,status,target_emp_id,confidence,evidence_note,released_on\n"
                         "rshah@users.noreply.example,git_email,resolved,T004,M,Test review note,2026-11-18\n")
    assert load_curated(db, alias_csv) == 1
    from app.ingestion.identity_links import link_identities
    link_identities(db)
    assert db.scalar(select(Commit).where(Commit.sha == "s2")).author_person_id is not None
    bad = tmp_path / "bad.csv"
    bad.write_text("alias_text,kind,status,target_emp_id,confidence,evidence_note,released_on\n"
                   "x,git_email,resolved,T999,M,note,2026-11-18\n")
    with pytest.raises(ValueError, match="not a known person"):
        load_curated(db, bad)


# ---------------------------------------------------------------- payroll privacy

def test_payroll_amounts_never_reach_the_cockpit_database(run, db, tmp_path, payroll_store):
    header = ["Emp ID", "Name", "Month", "Days in Month", "Days Payable", "Gross (Rs.)", "Deductions (Rs.)",
              "Net (Rs.)", "Processed By"]
    rows = [[f"T00{i}", f"Person {i}", "Mar-2026", 31, 31, 123457 + i, 1000, 122457 + i, "XX"] for i in range(1, 6)]
    sf.xlsx(tmp_path / "Payroll_Register_Test.xlsx", {"Payroll": ("Payroll register.", header, rows)})
    report = run(tmp_path)
    assert report.files[0].counts == {"payroll_rows": 5}
    ev = db.scalars(select(Evidence)).all()
    assert all("123458" not in e.content and "Gross" not in (e.fields_json or "") for e in ev)
    assert "Days Payable: 31" in ev[0].content
    dump = "\n".join(db.connection().connection.iterdump())
    assert "123458" not in dump and "122458" not in dump
    agg = payroll_store.aggregator().total(
        "company", "2026-03", lambda _l, _m: {f"T00{i}" for i in range(1, 6)}, released_cutoff=AT_D1)
    assert agg.ok and agg.total_paise == sum(123457 + i for i in range(1, 6)) * 100


# ---------------------------------------------------------------- CLI

def test_cli_ingest_and_status(tmp_path, monkeypatch, capsys):
    from app.config import get_settings
    from app.ingestion.__main__ import main

    monkeypatch.setenv("VELOXA_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    try:
        sf.keka(tmp_path / "pack" / "Employee_Master.xlsx", sf.staff_rows())
        (tmp_path / "pack" / "broken.pdf").write_bytes(b"%PDF nope")
        assert main(["ingest", str(tmp_path / "pack"), "--release-day", "2026-11-16"]) == 1
        out = capsys.readouterr().out
        assert re.search(r"ingested  SRC-00\d  Employee_Master\.xlsx", out)
        assert re.search(r"failed    SRC-00\d  broken\.pdf", out)
        assert main(["status"]) == 0
        out = capsys.readouterr().out
        assert "released 2026-11-16 10:00" in out and "exported 2026-10-31" in out
        assert str(tmp_path) not in out  # only paths relative to the ingested folder are stored
        with pytest.raises(SystemExit):
            main(["ingest", str(tmp_path / "pack")])  # --release-day is required
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------- schema guard

def _old_schema(engine, with_source: bool):
    from app.database import init_db
    init_db(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE app_meta SET value='1' WHERE key='schema_version'"))
        if with_source:
            conn.execute(text("INSERT INTO source_record (source_key, filename, file_type, sha256, released_on, "
                              "status, ingested_at, role, access) VALUES ('SRC-001','x.csv','csv','h','2026-11-16 10:00:00',"
                              "'ingested','2026-11-16 10:00:00','evidence','open')"))


def test_old_empty_schema_is_rebuilt(engine):
    from app.database import SCHEMA_VERSION, init_db
    _old_schema(engine, with_source=False)
    init_db(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT value FROM app_meta")).scalar() == SCHEMA_VERSION


def test_old_schema_holding_sources_is_never_dropped(engine):
    from app.database import SchemaMismatch, init_db
    _old_schema(engine, with_source=True)
    with pytest.raises(SchemaMismatch):
        init_db(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM source_record")).scalar() == 1
