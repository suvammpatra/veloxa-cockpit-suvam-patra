"""Phase 4: evidence retrieval. All data is synthetic (tests/sourcefiles.py)."""

import csv
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.database import make_session_factory
from app.ingestion.identity_links import load_curated
from app.ingestion.pipeline import Ingestor
from app.models import Conflict, ConflictSide, Evidence, Person, SourceRecord
from app.privacy.payroll import PayrollStore
from app.retrieval.citations import extract_keys, validate
from app.retrieval.fts import ensure_fts
from app.retrieval.search import Filters, SearchError, get_evidence, search
from app.temporal import TimeContext
from tests import sourcefiles as sf

D1, D2, D3 = date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18)
AT_D1 = TimeContext.known_at(datetime(2026, 11, 16, 12, 0))
AT_D2 = TimeContext.known_at(datetime(2026, 11, 17, 12, 0))
AT_D3 = TimeContext.known_at(datetime(2026, 11, 18, 12, 0))

GL_HEADER = ["Txn Date", "Voucher", "Vendor / Payee", "Ref", "Cost Centre", "Amount (Rs.)", "Narration", "Entered By"]
JIRA_HEADER = ["Key", "Type", "Summary", "Epic Link", "Assignee", "Story Points", "Status", "Created",
               "Resolved", "Fix Version"]
INC_HEADER = ["ID", "Severity", "Opened", "Resolved", "Service", "Responder"]
PAY_HEADER = ["Emp ID", "Name", "Month", "Days in Month", "Days Payable", "Gross (Rs.)", "Deductions (Rs.)",
              "Net (Rs.)", "Processed By"]
MAIL = dict(sender="a@example.test", to="b@example.test")


@pytest.fixture
def corpus(engine, tmp_path):
    """Day 1: people, ledger, board note, emails, payroll, a transcript and a printed copy.
    Day 3: tracker, incidents, and a ledger re-export with one changed amount."""
    d1, d3 = tmp_path / "d1", tmp_path / "d3"
    sf.keka(d1 / "hr" / "Employee_Master.xlsx", sf.staff_rows())
    gl_rows = [["2026-04-08", "JV-1", "Cloud Co", "R-1", "ENG", 1000, "Cloud hosting, previous month", "XX"],
               ["2026-04-28", "JV-2", "Rent Co", "R-2", "G&A", 2500, "Office rent", "XX"]]
    sf.xlsx(d1 / "finance" / "GL_Export_Test.xlsx", {"GL": ("General ledger export.", GL_HEADER, gl_rows)})
    sf.pdf(d1 / "documents" / "Board_Update_Q3.pdf",
           ["Board update. Sent 6 Oct 2026. The routing engine itself is feature-complete."])
    sf.eml(d1 / "email" / "04.eml", subject="Engine plan", date="Tue, 2 Jun 2026 10:00:00 +0530",
           body="The routing engine release is delayed by two weeks. Rina owns hardening.", **MAIL)
    sf.eml(d1 / "email" / "09.eml", subject="Ownership", date="Tue, 1 Sep 2026 23:47:00 +0530",
           body="Can we talk about engine ownership sometime this week?", **MAIL)
    sf.xlsx(d1 / "finance" / "Payroll_Register_Test.xlsx", {"Payroll": ("Payroll register.", PAY_HEADER, [
        [f"T00{i}", f"Payname {i}", "Mar-2026", 31, 31, 50000 + i, 100, 49900 + i, "XX"] for i in range(1, 6)])})
    sf.docx(d1 / "transcripts" / "T1_Test_Call.docx", ["T1 call", "The routing engine delays worry the CEO."])
    sf.pdf(d1 / "email" / "Email_Printouts.pdf", ["The routing engine release is delayed by two weeks."])
    (d1 / "README.txt").write_text("Test room. Exported by IT on 31 Oct 2026.\n")

    sf.xlsx(d3 / "Jira_Export_TEST.xlsx", {"Issues": ("Jira export, project TEST.", JIRA_HEADER, [
        ["TEST-11", "Story", "Routing engine core (mk-1)", None, "MK", 3, "In Progress", "2026-05-06", None, "GA"],
        ["TEST-12", "Story", "Hardening of the routing engine", None, "RS", 2, "To Do", "2026-05-06", None, "GA"]])})
    sf.xlsx(d3 / "Incidents_Test.xlsx", {"Incidents": ("Incident export.", INC_HEADER, [
        ["INC-1", "SEV1", "2026-08-22T20:00:00Z", "2026-08-22T21:00:00Z", "routing-api", "Rina"],
        ["INC-2", "SEV2", "2026-08-27T05:00:00Z", "2026-08-27T06:00:00Z", "routing-api", "Rinal"]])})
    gl_rows[1][5] = 2600
    sf.xlsx(d3 / "finance" / "GL_Export_Test.xlsx", {"GL": ("General ledger export.", GL_HEADER, gl_rows)})

    factory = make_session_factory(engine)
    store = PayrollStore(":memory:")
    Ingestor(factory, release_day=D1, payroll_store=store).ingest([d1])
    Ingestor(factory, release_day=D3, payroll_store=store, default_exported_on=date(2026, 10, 31)).ingest([d3])
    store.dispose()
    return factory


def _ev(db, filename, locator=None):
    stmt = select(Evidence).join(SourceRecord).where(SourceRecord.filename == filename)
    if locator:
        stmt = stmt.where(Evidence.locator == locator)
    return db.scalars(stmt.order_by(Evidence.id)).first()


def keys(result):
    return [h.citation.evidence_key for h in result.hits]


def files(result):
    return [h.citation.filename for h in result.hits]


# ---------------------------------------------------------------- relevance

def test_search_ranks_the_most_relevant_evidence_first(corpus, db):
    r = search(db, "routing engine release delayed", AT_D1)
    assert r.status == "ok" and r.terms == ["routing", "engine", "release", "delayed"]
    assert files(r)[0] == "04.eml"
    assert "[delayed]" in r.hits[0].snippet  # matched words are marked in the snippet


def test_stemming_finds_word_forms_but_names_stay_exact(corpus, db):
    assert "T1_Test_Call.docx" in files(search(db, "delay", AT_D1))  # "delays"
    rinal = search(db, "Rinal", AT_D3)
    assert {h.content.count("Rinal") > 0 for h in rinal.hits} == {True}  # never Rina's rows


def test_all_terms_mode_narrows_results(corpus, db):
    any_terms = search(db, "rent hardening", AT_D3)
    all_terms = search(db, "rent hardening", AT_D3, all_terms=True)
    assert any_terms.total_matches >= 2 and all_terms.status == "no_evidence"


# ---------------------------------------------------------------- provenance and citations

def test_hits_carry_exact_source_provenance(corpus, db):
    hit = search(db, "Office rent", AT_D1).hits[0]
    ev = db.scalar(select(Evidence).where(Evidence.evidence_key == hit.citation.evidence_key))
    src = ev.source
    c = hit.citation
    assert (c.source_key, c.filename, c.relative_path, c.locator) == (
        src.source_key, "GL_Export_Test.xlsx", "finance/GL_Export_Test.xlsx", "GL!row 4")
    assert (c.system, c.trust_rung, c.source_sha256) == ("Zoho Books", 1, src.sha256)
    assert hit.content == ev.content and c.label == f"{c.evidence_key} (GL_Export_Test.xlsx, GL!row 4)"


def test_every_returned_citation_validates_and_fabricated_ones_do_not(corpus, db):
    r = search(db, "routing engine", AT_D3, limit=50)
    assert all(c.ok for c in validate(db, keys(r), AT_D3))
    board = _ev(db, "Board_Update_Q3.pdf")
    checks = validate(db, ["E9999", board.evidence_key], AT_D3,
                      quotes={board.evidence_key: "the engine is late"})
    assert [(c.ok, c.reason) for c in checks] == [(False, "unknown_key"), (False, "quote_not_found")]
    ok = validate(db, [board.evidence_key], AT_D3, quotes={board.evidence_key: "FEATURE-COMPLETE"})[0]
    assert ok.ok and ok.citation.filename == "Board_Update_Q3.pdf"
    assert extract_keys(f"See {board.evidence_key} and E9999, again {board.evidence_key}.") == [
        board.evidence_key, "E9999"]


def test_citations_from_a_later_release_or_restricted_source_are_invalid(corpus, db):
    jira = _ev(db, "Jira_Export_TEST.xlsx")
    pay = _ev(db, "Payroll_Register_Test.xlsx")
    checks = validate(db, [jira.evidence_key, pay.evidence_key], AT_D1)
    assert [c.reason for c in checks] == ["not_released_yet", "restricted"]


def test_evidence_keys_are_stable_across_searches(corpus, db):
    a = search(db, "routing engine", AT_D3, limit=50)
    b = search(db, "engine routing", AT_D3, limit=50)
    assert sorted(keys(a)) == sorted(keys(b))
    assert get_evidence(db, keys(a)[0], AT_D3).citation == a.hits[0].citation


# ---------------------------------------------------------------- time

def test_point_in_time_hides_later_releases(corpus, db):
    assert "Jira_Export_TEST.xlsx" not in files(search(db, "routing engine", AT_D1, limit=50))
    assert "Jira_Export_TEST.xlsx" in files(search(db, "routing engine", AT_D3, limit=50))
    assert search(db, "hardening", TimeContext.known_at(datetime(2026, 11, 18, 9, 59))).hits[0].citation.filename == "04.eml"


def test_recorded_mode_uses_record_dates_and_drops_undated_transcripts(corpus, db):
    june = TimeContext.recorded_by(datetime(2026, 6, 30, 23, 0), datetime(2026, 11, 18, 12, 0))
    r = search(db, "routing engine", june, limit=50)
    assert files(r) == ["04.eml"]  # the board note was sent in October; the transcript has no date


def test_date_range_filter_reports_undated_matches(corpus, db):
    r = search(db, "routing engine", AT_D3, Filters(date_from=date(2026, 8, 1), date_to=date(2026, 8, 31)), limit=50)
    assert set(files(r)) == {"Incidents_Test.xlsx"}
    assert any("no date" in w for w in r.warnings)  # the transcript cannot be placed in August


# ---------------------------------------------------------------- conflicts

def test_conflicting_evidence_is_returned_with_both_sides(corpus, db):
    r = search(db, "Office rent", AT_D3, limit=1)
    assert len(r.conflicts) == 1
    c = r.conflicts[0]
    assert c.status == "open" and [s[0] for s in c.sides] == ["A", "B"]
    assert {h.citation.evidence_key for h in r.hits} == {s[1] for s in c.sides}
    assert any(h.via_conflict for h in r.hits)  # the other side is pulled in even past the limit


def test_a_conflict_is_not_shown_before_both_sides_were_known(corpus, db):
    board = _ev(db, "Board_Update_Q3.pdf")
    ticket = _ev(db, "Jira_Export_TEST.xlsx", "Issues!row 3")
    c = Conflict(conflict_key="C-TEST-DONE", title="Engine complete vs open ticket")
    c.sides = [ConflictSide(evidence_id=board.id, side="A", summary="feature-complete"),
               ConflictSide(evidence_id=ticket.id, side="B", summary="still open")]
    db.add(c)
    db.commit()
    assert search(db, "feature-complete", AT_D1).conflicts == []
    assert [x.conflict_key for x in search(db, "feature-complete", AT_D3).conflicts] == ["C-TEST-DONE"]


# ---------------------------------------------------------------- duplicates

def test_duplicate_text_collapses_to_one_hit(corpus, db):
    r = search(db, "Cloud hosting", AT_D3)
    assert len(r.hits) == 1 and len(r.hits[0].duplicates) == 1  # unchanged row in both ledger exports
    first = _ev(db, "GL_Export_Test.xlsx", "GL!row 3")
    assert r.hits[0].citation.evidence_key == first.evidence_key  # earliest release is the representative


def test_printed_copies_are_not_a_second_source(corpus, db):
    default = search(db, "release delayed two weeks", AT_D1, all_terms=True)
    assert files(default) == ["04.eml"]
    with_copies = search(db, "release delayed two weeks", AT_D1, Filters(roles=("evidence", "copy")), all_terms=True)
    assert set(files(with_copies)) == {"04.eml", "Email_Printouts.pdf"}


# ---------------------------------------------------------------- missing evidence

def test_no_matching_evidence_returns_nothing_rather_than_guessing(corpus, db):
    r = search(db, "zebra migration", AT_D3)
    assert r.status == "no_evidence" and r.hits == [] and r.conflicts == []


def test_an_empty_database_returns_no_evidence(db):
    assert search(db, "anything", AT_D3).status == "no_evidence"


# ---------------------------------------------------------------- identities

def test_ambiguous_person_returns_no_evidence(corpus, db):
    r = search(db, None, AT_D3, Filters(person="MK"))
    assert r.status == "ambiguous_person" and r.hits == []


def test_unknown_person_returns_no_evidence(corpus, db):
    r = search(db, "routing", AT_D3, Filters(person="Rinal"))
    assert r.status == "unknown_person" and r.hits == []


def test_person_filter_uses_links_and_never_merges_similar_names(corpus, db):
    r = search(db, None, AT_D3, Filters(person="Rina Shah"), limit=50)
    contents = " ".join(h.content for h in r.hits)
    assert "INC-1" in contents and "TEST-12" in contents and "Hardening" in contents
    assert "INC-2" not in contents  # Rinal's incident


def test_person_links_respect_the_release_date(corpus, db):
    r = search(db, None, AT_D1, Filters(person="Rina Shah"), limit=50)
    assert "Jira_Export_TEST.xlsx" not in files(r) and "Incidents_Test.xlsx" not in files(r)


def test_department_filter_uses_membership_on_the_date(corpus, db):
    r = search(db, "routing", AT_D3, Filters(department="ENGINEERING"), limit=50)
    assert "Incidents_Test.xlsx" in files(r) and not r.warnings
    march = TimeContext.recorded_by(datetime(2026, 8, 31, 23, 0), datetime(2026, 11, 18, 12, 0))
    r = search(db, "routing", march, Filters(department="Engineering"), limit=50)
    assert any("cannot be established" in w for w in r.warnings)


# ---------------------------------------------------------------- privacy

def test_payroll_rows_are_never_returned_by_default(corpus, db):
    assert search(db, "Payname", AT_D3).status == "no_evidence"
    assert search(db, None, AT_D3, Filters(file_types=("xlsx",)), limit=100).total_matches > 0
    assert "Payroll_Register_Test.xlsx" not in files(search(db, None, AT_D3, Filters(file_types=("xlsx",)), limit=100))
    assert get_evidence(db, _ev(db, "Payroll_Register_Test.xlsx").evidence_key, AT_D3) is None
    explicit = search(db, "Payname", AT_D3, Filters(include_restricted=True))
    assert explicit.hits and all("50001" not in h.content for h in explicit.hits)  # never amounts


def test_purpose_limited_email_needs_its_purpose(corpus, db):
    assert search(db, "ownership", AT_D1).status == "no_evidence"
    r = search(db, "ownership", AT_D1, Filters(purpose="atlas_ownership"))
    assert files(r) == ["09.eml"]
    key = r.hits[0].citation.evidence_key
    assert validate(db, [key], AT_D1)[0].reason == "purpose_limited"


def test_the_api_cannot_reach_restricted_or_purpose_limited_evidence(corpus, client, db):
    pay = _ev(db, "Payroll_Register_Test.xlsx").evidence_key
    assert client.get(f"/api/evidence/{pay}").status_code == 404
    body = client.get("/api/search", params={"q": "ownership Payname"}).json()
    assert body["status"] == "no_evidence"
    ok = client.get("/api/search", params={"q": "Office rent", "as_of": "2026-11-16"}).json()
    assert ok["hits"][0]["citation"]["filename"] == "GL_Export_Test.xlsx"


# ---------------------------------------------------------------- errors

@pytest.mark.parametrize("query,kwargs,message", [
    ("", {}, "at least one filter"),
    ("the and of", {}, "no searchable words"),
    ("x" * 501, {}, "longer than"),
    ("rent", {"limit": 0}, "limit"),
    ("rent", {"filters": Filters(date_from=date(2026, 9, 1), date_to=date(2026, 8, 1))}, "after"),
    ("rent", {"filters": Filters(department="Nowhere")}, "No department"),
    ("rent", {"filters": Filters(roles=("secret",))}, "roles"),
])
def test_bad_searches_raise_clear_errors(corpus, db, query, kwargs, message):
    with pytest.raises(SearchError, match=message):
        search(db, query, AT_D3, kwargs.get("filters"), **{k: v for k, v in kwargs.items() if k != "filters"})


def test_fts_syntax_in_user_text_is_treated_as_words(corpus, db):
    for q in ['NEAR(rent cloud)', 'rent*', '"unbalanced', 'content: rent', 'rent AND OR NOT', '^rent -cloud']:
        assert search(db, q, AT_D3).status in ("ok", "no_evidence")


def test_api_reports_search_errors_as_400(corpus, client):
    r = client.get("/api/search", params={"q": "the"})
    assert r.status_code == 400 and r.json()["error"] == "http_error"
    assert client.get("/api/search", params={"q": "rent", "as_of": "not-a-date"}).status_code == 400
    assert client.get("/api/evidence/DROP TABLE").status_code == 400


# ---------------------------------------------------------------- index integrity

def test_the_index_follows_evidence_changes_and_rebuilds(corpus, db, engine):
    ev = _ev(db, "Board_Update_Q3.pdf")
    ev.content = "Board update with a changed word: kumquat."
    db.commit()
    assert files(search(db, "kumquat", AT_D3)) == ["Board_Update_Q3.pdf"]
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO evidence_fts(evidence_fts) VALUES ('delete-all')"))
    assert search(db, "kumquat", AT_D3).status == "no_evidence"
    ensure_fts(engine)
    assert files(search(db, "kumquat", AT_D3)) == ["Board_Update_Q3.pdf"]


# ---------------------------------------------------------------- reviewed alias file

REVIEWED = Path(__file__).resolve().parent.parent / "data" / "aliases_reviewed.csv"


def test_reviewed_alias_file_holds_only_the_approved_rows():
    rows = list(csv.DictReader(REVIEWED.open(encoding="utf-8")))
    got = {(r["alias_text"], r["kind"], r["status"], r["target_emp_id"], r["confidence"]) for r in rows}
    assert got == {
        ("pnair@users.noreply.github.com", "git_email", "resolved", "VX007", "M"),
        ("PN", "jira_initials", "resolved", "VX007", "H"),
        ("RV", "jira_initials", "resolved", "VX018", "H"),
        ("AD", "jira_initials", "resolved", "VX009", "H"),
        ("SK", "jira_initials", "resolved", "VX012", "H"),
        ("Snehal", "pagerduty_name", "unresolved", "", "L"),
        ("Pria", "transcript_name", "resolved", "VX007", "M"),   # approved 19 Nov (Day 4)
        ("Vicky", "transcript_name", "resolved", "VX004", "M"),  # approved 19 Nov (Day 4)
    }
    assert all(r["evidence_note"].startswith("Reviewed") and ".md" in r["evidence_note"] for r in rows)
    assert not any(r["alias_text"] in ("Sid", "Sneha") for r in rows)  # not approved


def test_reviewed_alias_file_loads_once(db):
    for emp_id in ("VX004", "VX007", "VX009", "VX012", "VX018"):
        db.add(Person(emp_id=emp_id, full_name=f"Synthetic {emp_id}", worker_type="employee",
                      released_on=datetime(2026, 11, 16, 10, 0)))
    db.flush()
    assert load_curated(db, REVIEWED) == 8
    assert load_curated(db, REVIEWED) == 0
    from app.services.identity import resolve_person
    assert resolve_person(db, "Snehal", AT_D3).status == "unresolved"
    assert resolve_person(db, "PN", AT_D3).person.emp_id == "VX007"
    assert resolve_person(db, "PN", AT_D2).status == "unresolved"  # reviewed on Day 3
