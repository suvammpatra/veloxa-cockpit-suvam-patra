"""Phase 5: question answering. All data is synthetic (tests/sourcefiles.py); the names,
dates and amounts exist only to exercise the rules and are not Veloxa facts."""

import json
from datetime import date, datetime

import pytest
from sqlalchemy import select

from app.answering import engine as engine_mod
from app.answering.classify import Intent
from app.answering.confidence import Support, assess
from app.answering.engine import ask, finalize
from app.answering.handlers import coverage_from_name
from app.answering.llm import check_wording
from app.answering.model import Answer, ChainLink, render_text, to_dict
from app.answering.parse import find_period, split_as_of
from app.config import Settings
from app.database import make_session_factory
from app.ingestion.pipeline import Ingestor
from app.models import Evidence, SourceRecord
from app.privacy.payroll import PayrollStore
from app.retrieval.citations import validate
from app.temporal import TimeContext
from tests import sourcefiles as sf

D1, D3 = date(2026, 11, 16), date(2026, 11, 18)
AT_D1 = TimeContext.known_at(datetime(2026, 11, 16, 12, 0))
AT_D3 = TimeContext.known_at(datetime(2026, 11, 18, 12, 0))
BEFORE_D3 = TimeContext.known_at(datetime(2026, 11, 18, 9, 59))
BEFORE_D1 = TimeContext.known_at(datetime(2026, 11, 16, 9, 59))

GL_HEADER = ["Txn Date", "Voucher", "Vendor / Payee", "Ref", "Cost Centre", "Amount (Rs.)", "Narration", "Entered By"]
JIRA_HEADER = ["Key", "Type", "Summary", "Epic Link", "Assignee", "Story Points", "Status", "Created",
               "Resolved", "Fix Version"]
VERSION_HEADER = ["Version", "Release Date", "Original Release Date", "Last Changed", "Changed By"]
INC_HEADER = ["ID", "Severity", "Opened", "Resolved", "Service", "Responder"]
PAY_HEADER = ["Emp ID", "Name", "Month", "Days in Month", "Days Payable", "Gross (Rs.)", "Deductions (Rs.)",
              "Net (Rs.)", "Processed By"]
MAIL = dict(sender="a@example.test", to="b@example.test")
GROSS = {"T001": 71111, "T002": 72222, "T003": 73333, "T004": 74444, "T005": 75555, "T006": 76666}


@pytest.fixture
def world(engine, tmp_path):
    """Day 1: staff, ledger, two board notes, three emails, payroll, a transcript.
    Day 3: Jira with a moved GA date, incidents, a launch kit, a ledger re-export."""
    d1, d3 = tmp_path / "d1", tmp_path / "d3"
    staff = sf.staff_rows() + [["T006", "Omar Haddad", "omar@example.test", "Marketing", "Marketer", "T001",
                                "2024-01-01", "City", "Active", None]]
    sf.keka(d1 / "hr" / "Employee_Master.xlsx", staff)
    gl_rows = [["2026-04-08", "JV-1", "Cloud Co", "R-1", "ENG", 1000, "Cloud hosting, previous month", "XX"],
               ["2026-04-28", "JV-2", "Rent Co", "R-2", "G&A", 2500, "Office rent", "XX"]]
    sf.xlsx(d1 / "finance" / "GL_Export_Test.xlsx", {"GL": ("General ledger export.", GL_HEADER, gl_rows)})
    sf.pdf(d1 / "documents" / "Board_Update_Q2.pdf", ["Board update. Sent 8 Jul 2026. Atlas is on track for GA "
                                                      "on 15 September."])
    sf.pdf(d1 / "documents" / "Board_Update_Q3.pdf", ["Board update. Sent 6 Oct 2026. We moved Atlas GA. The "
                                                      "routing engine itself is feature-complete."])
    sf.eml(d1 / "email" / "04.eml", subject="Atlas plan", date="Tue, 2 Jun 2026 10:00:00 +0530",
           body="Atlas plan: 15 Sep GA is achievable if two hires land by July. Mira leads the core engine. "
                "Rina owns hardening.", **MAIL)
    sf.eml(d1 / "email" / "05.eml", subject="Kit", date="Wed, 22 Jul 2026 11:00:00 +0530",
           body="Launch kit is done. Just need a date from engineering.", **MAIL)
    sf.eml(d1 / "email" / "09.eml", subject="Ownership", date="Tue, 1 Sep 2026 23:47:00 +0530",
           body="Can we talk about Atlas ownership sometime this week?", **MAIL)
    pay = [[e, f"Payname {e}", "Mar-2026", 31, 31, g, 100, g - 100, "XX"] for e, g in GROSS.items()]
    pay += [[e, f"Payname {e}", "Nov-2026", 30, 30, g, 100, g - 100, "XX"] for e, g in GROSS.items() if e != "T005"]
    sf.xlsx(d1 / "finance" / "Payroll_Register_Test.xlsx", {"Payroll": ("Payroll register.", PAY_HEADER, pay)})
    sf.docx(d1 / "transcripts" / "T1_Test_Call.docx", ["T1 call", "Atlas GA is on track, maybe September."])
    (d1 / "README.txt").write_text("Test room. Exported by IT on 31 Oct 2026.\n")

    sf.xlsx(d3 / "Jira_Export_ATLAS.xlsx", {
        "Issues": ("Jira export, project ATLAS. Exported 31-Oct-2026.", JIRA_HEADER, [
            ["ATLAS-2", "Story", "Core engine (rs-1)", None, "RS", 5, "In Progress", "2026-05-06", None, "Atlas GA"],
            ["ATLAS-3", "Story", "Engine API (rs-2)", None, "RS", 3, "Done", "2026-05-06", "2026-07-01", "Atlas GA"],
            ["ATLAS-4", "Story", "Engine UI (mk-1)", None, "MK", 2, "To Do", "2026-05-06", None, "Atlas GA"],
            ["ATLAS-5", "Story", "Hardening (rs-3)", None, "RS", 2, "To Do", "2026-05-06", None, "Atlas GA"]]),
        "Versions": (None, VERSION_HEADER, [["Atlas GA", "2026-12-15", "2026-09-15", "2026-09-02", "lena"]])})
    sf.xlsx(d3 / "Incidents_Aug-Oct_2026.xlsx", {"Incidents": ("Incident export.", INC_HEADER, [
        ["INC-1", "SEV1", "2026-08-22T20:00:00Z", "2026-08-22T21:00:00Z", "routing-api", "Rina"],
        ["INC-2", "SEV2", "2026-08-27T05:00:00Z", "2026-08-27T06:00:00Z", "routing-api", "Rinal"],
        ["INC-3", "SEV1", "2026-09-10T06:00:00Z", "2026-09-10T07:00:00Z", "routing-api", "Rina"]])})
    sf.pdf(d3 / "documents" / "Atlas_Launch_Kit_v1.pdf", [
        "Atlas launch kit v1. Owner: Dev. Dated 21 Jul 2026.\nDeck: Ready\nWebsite page: Ready, unpublished\n"
        "Press note: Draft\nLaunch date: TBC with engineering (planned 22 Sep)"])
    sf.eml(d3 / "email" / "08.eml", subject="Dates", date="Thu, 3 Sep 2026 09:00:00 +0530",
           body="Atlas GA moves to 15 December. Plan accordingly.", **MAIL)
    gl_rows[1][5] = 2600
    sf.xlsx(d3 / "finance" / "GL_Export_Test.xlsx", {"GL": ("General ledger export.", GL_HEADER, gl_rows)})

    factory = make_session_factory(engine)
    store = PayrollStore(tmp_path / "payroll.db")
    Ingestor(factory, release_day=D1, payroll_store=store).ingest([d1])
    Ingestor(factory, release_day=D3, payroll_store=store, default_exported_on=date(2026, 10, 31)).ingest([d3])
    yield {"factory": factory, "payroll": store.aggregator()}
    store.dispose()


def key_of(db, filename):
    return db.scalars(select(Evidence.evidence_key).join(SourceRecord).where(SourceRecord.filename == filename)
                      .order_by(Evidence.id)).first()


def files(ans):
    return {c.filename for link in ans.evidence_chain for c in link.citations}


def assert_five_fields(ans):
    assert ans.question and ans.short_answer and ans.weakest_link and ans.would_change_mind
    assert ans.confidence in ("High", "Medium", "Low") and ans.confidence_reasons


def assert_citations_hold(db, ans, ctx):
    """Every key validates again at the same time frame, and every quote is in its record."""
    for link in ans.evidence_chain:
        if not link.keys:
            continue
        assert all(c.ok for c in validate(db, link.keys, ctx, purpose=ans.purpose)), link
        if link.quote:
            content = db.scalar(select(Evidence.content).where(Evidence.evidence_key == link.keys[0]))
            assert link.quote in content


def q(db, world, text, ctx=AT_D3, **kw):
    ans = ask(db, text, ctx, payroll=world["payroll"], **kw)
    assert_five_fields(ans)
    assert_citations_hold(db, ans, ctx)
    return ans


# ---------------------------------------------------------------- headcount

def test_company_headcount_counts_employees_on_the_date(world, db):
    ans = q(db, world, "How many employees do we have?", AT_D1)
    assert (ans.kind, ans.status) == ("company_headcount", "answered")
    assert ans.short_answer.startswith("5 employees on 16 Nov 2026")  # T005 left on 31 Oct
    assert files(ans) == {"Employee_Master.xlsx"} and ans.confidence == "Medium"
    assert ans.confidence_basis == "evidence"


def test_company_headcount_before_the_snapshot_says_it_may_be_low(world, db):
    ans = q(db, world, "What was our headcount on 15 Oct 2026?", AT_D1)
    assert ans.short_answer.startswith("6 employees on 15 Oct 2026")
    assert "may be low" in ans.weakest_link and "The records cover the question only in part" in " ".join(
        ans.confidence_reasons)


def test_department_headcount_and_historical_membership_uncertainty(world, db):
    now = q(db, world, "How many people are in Engineering?", AT_D1)
    assert (now.kind, now.status) == ("department_headcount", "answered")
    assert now.short_answer.startswith("3 employees in Engineering")
    then = q(db, world, "How many people were in Engineering on 1 Aug 2026?", AT_D1)
    assert then.status == "uncertain" and "cannot be established" in then.short_answer
    assert "31 Oct 2026" in then.short_answer and then.confidence == "Low"


# ---------------------------------------------------------------- manager

def test_manager_as_of_now_and_before_the_record(world, db):
    now = q(db, world, "Who does Mira Kale report to?", AT_D1)
    assert (now.kind, now.status) == ("manager", "answered")
    assert "reports to Lena Ortiz" in now.short_answer and now.confidence == "Medium"
    then = q(db, world, "Who did Mira Kale report to on 1 Aug 2026?", AT_D1)
    assert then.status == "uncertain" and "not known" in then.short_answer and "31 Oct 2026" in then.short_answer


def test_manager_for_someone_who_has_left(world, db):
    ans = q(db, world, "Who does Dev Patel report to?", AT_D1)
    assert "left on 31 Oct 2026" in ans.short_answer and ans.status == "answered"


def test_ambiguous_and_unknown_people_are_not_guessed(world, db):
    amb = q(db, world, "Who does MK report to?", AT_D3)
    assert amb.status == "ambiguous" and "Mira Kale" in amb.short_answer and "Mohan Kale" in amb.short_answer
    assert amb.confidence == "Low" and not amb.evidence_chain
    unknown = q(db, world, "Who does Zara Quinn report to?", AT_D1)
    assert unknown.status == "no_evidence" and "Zara" in unknown.short_answer


def test_initials_are_unknown_before_the_tracker_was_released(world, db):
    ans = q(db, world, "Who does MK report to?", BEFORE_D3)
    assert ans.status == "no_evidence"  # no alias row for MK existed yet


# ---------------------------------------------------------------- payroll

def _no_amounts(ans):
    text = json.dumps(to_dict(ans))
    for g in GROSS.values():
        for form in (str(g), f"{g:,}", f"{str(g)[:2]},{str(g)[2:]}"):
            assert form not in text


def test_company_payroll_total_comes_from_the_restricted_function(world, db):
    ans = q(db, world, "What is the company payroll total for March 2026?")
    assert (ans.kind, ans.status) == ("payroll", "answered")
    assert ans.short_answer == "Gross payroll for the company, March 2026: Rs.4,43,331 across 6 people."
    assert ans.evidence_chain[0].record and not ans.evidence_chain[0].keys
    assert ans.confidence == "Medium"  # rung 1 total, capped: membership predates the Keka snapshot
    _no_amounts(ans)


def test_individual_salary_requests_are_refused(world, db):
    for text in ("What does Mira Kale earn?", "What is the salary of T002?", "Who is the highest paid?",
                 "How much is Zara paid?", "What is Mira's pay in March 2026?"):
        ans = q(db, world, text)
        assert (ans.status, ans.refusal) == ("refused", "individual_pay"), text
        assert ans.confidence == "High" and ans.confidence_basis == "policy" and not ans.evidence_chain
        assert "not confidence in any business fact" in render_text(ans)
        _no_amounts(ans)


def test_historical_department_payroll_is_refused_as_membership_unknown(world, db):
    ans = q(db, world, "What was Engineering payroll for March 2026?")
    assert (ans.status, ans.refusal) == ("refused", "membership_unknown")
    assert "31 Oct 2026" in ans.short_answer and "before it" in ans.short_answer
    _no_amounts(ans)


def test_small_groups_and_differencing_are_refused(world, db):
    small = q(db, world, "Engineering payroll total for November 2026")
    assert small.refusal == "below_floor"
    first = q(db, world, "Company payroll total for March 2026")
    second = q(db, world, "Company payroll total for November 2026")  # one person fewer
    assert first.status == "answered" and second.refusal == "differencing"
    _no_amounts(second)


def test_payroll_needs_a_month_and_a_store(world, db):
    assert q(db, world, "What is our total payroll?").status == "uncertain"
    ans = ask(db, "Company payroll total for March 2026", AT_D3, payroll=None)
    assert ans.status == "no_evidence"


# ---------------------------------------------------------------- incidents

def test_incidents_in_a_month_with_linked_and_unlinked_responders(world, db):
    ans = q(db, world, "How many incidents were there in August 2026?")
    assert (ans.kind, ans.status) == ("incidents", "answered")
    assert ans.short_answer.startswith("2 incidents opened in August 2026 (IST): 1 SEV1, 1 SEV2")
    assert "Rina Shah (1)" in ans.short_answer and "'Rinal' (not linked to a known person) (1)" in ans.short_answer
    assert "Rinal" in ans.weakest_link


def test_incident_days_are_ist_days(world, db):
    ans = q(db, world, "How many incidents on 22 Aug 2026?")
    assert ans.short_answer == "No incidents were recorded on 22 Aug 2026 (IST)."
    assert q(db, world, "Incidents on 23 Aug 2026").short_answer.startswith("1 incidents opened on 23 Aug 2026")


def test_incident_severity_filter_and_period_outside_the_records(world, db):
    assert q(db, world, "SEV1 incidents in August 2026").short_answer.startswith("1 SEV1 incidents")
    outside = q(db, world, "Incidents in March 2026")
    assert outside.status == "uncertain" and outside.short_answer.startswith(
        "Coverage unavailable: no incident record covers March 2026.")
    assert "August 2026 to October 2026" in outside.short_answer and "not a count of zero" in outside.short_answer
    # October is inside the months the file name states, with no incident: none recorded, not unavailable.
    october = q(db, world, "Incidents in October 2026")
    assert (october.status, october.short_answer) == ("answered", "No incidents were recorded in October 2026 (IST).")
    assert "as the file name states (Incidents_Aug-Oct_2026.xlsx)" in october.weakest_link


def test_a_file_name_never_overrides_the_incidents_in_the_file():
    from app.answering.handlers import incident_coverage
    aug, sep, nov = datetime(2026, 8, 23), datetime(2026, 9, 10), datetime(2026, 11, 2)
    named = incident_coverage([aug, sep], ["Incidents_Aug-Oct_2026.xlsx"])
    assert (named.start, named.end, named.contradicted) == (datetime(2026, 8, 1), datetime(2026, 10, 31, 23, 59, 59),
                                                            None)
    clash = incident_coverage([aug, nov], ["Incidents_Aug-Oct_2026.xlsx"])  # November is outside the name
    assert (clash.start, clash.end) == (datetime(2026, 8, 1), datetime(2026, 11, 30, 23, 59, 59))
    assert clash.contradicted == "Incidents_Aug-Oct_2026.xlsx" and "is not used" in clash.basis
    plain = incident_coverage([aug, sep], ["Incidents_Test.xlsx"])
    assert (plain.start, plain.end) == (datetime(2026, 8, 1), datetime(2026, 9, 30, 23, 59, 59))


def test_incident_coverage_comes_from_the_file_name_when_it_states_one():
    assert coverage_from_name("Incidents_Aug-Oct_2026.xlsx") == (datetime(2026, 8, 1),
                                                                datetime(2026, 10, 31, 23, 59, 59))
    for name in ("Incidents_Test.xlsx", "Incidents_Oct-Aug_2026.xlsx", "Incidents_Foo-Bar_2026.xlsx"):
        assert coverage_from_name(name) is None


def test_question_dates_and_periods():
    ref = datetime(2026, 11, 18, 12)
    cases = {
        "in August 2026": ("August 2026", datetime(2026, 8, 1), datetime(2026, 8, 31, 23, 59, 59), False),
        "on 22 Aug 2026": ("22 Aug 2026", datetime(2026, 8, 22), datetime(2026, 8, 22, 23, 59, 59), False),
        "on Aug 22": ("22 Aug 2026", datetime(2026, 8, 22), datetime(2026, 8, 22, 23, 59, 59), True),
        "on 2026-08-22": ("22 Aug 2026", datetime(2026, 8, 22), datetime(2026, 8, 22, 23, 59, 59), False),
        "for 2026-03": ("March 2026", datetime(2026, 3, 1), datetime(2026, 3, 31, 23, 59, 59), False),
        "in December": ("December 2025", datetime(2025, 12, 1), datetime(2025, 12, 31, 23, 59, 59), True),
        "between 1 Aug and 15 Aug 2026": ("1 Aug 2026 to 15 Aug 2026", datetime(2026, 8, 1),
                                          datetime(2026, 8, 15, 23, 59, 59), False),
        "from 1 Aug 2026 to 15 Aug": ("1 Aug 2026 to 15 Aug 2026", datetime(2026, 8, 1),
                                      datetime(2026, 8, 15, 23, 59, 59), False),
        "from November 2025 to February": ("November 2025 to February 2026", datetime(2025, 11, 1),
                                           datetime(2026, 2, 28, 23, 59, 59), False),
    }
    for text, (label, start, end, assumed) in cases.items():
        p = find_period(text, ref)
        assert (p.label, p.start, p.end, p.assumed_year) == (label, start, end, assumed), text
    assert find_period("what may happen next", ref) is None  # "may" is a verb here
    assert find_period("Total for 2026", ref) is None
    rest, when = split_as_of("Headcount as of 31 Oct 2026?")
    assert (rest, when) == ("Headcount ?", datetime(2026, 10, 31, 23, 59, 59))


# ---------------------------------------------------------------- Atlas GA date over time

def test_ga_date_with_original_and_dated_statements(world, db):
    ans = q(db, world, "When is Atlas GA?")
    assert (ans.kind, ans.status) == ("release_date", "answered")
    assert ("Atlas GA: GA date 15 Dec 2026 in Jira (last changed 2 Sep 2026 by lena). The original date was "
            "15 Sep 2026. 08.eml states the same date.") in ans.short_answer
    stated = [c.filename for link in ans.evidence_chain if link.role == "context" for c in link.citations]
    assert stated == ["04.eml", "Board_Update_Q2.pdf", "Board_Update_Q3.pdf", "T1_Test_Call.docx"]  # oldest first
    assert "09.eml" not in files(ans)
    # Jira and an email from another system state the same current date: corroboration.
    agree = next(link for link in ans.evidence_chain if link.statement == "08.eml gives the same date")
    assert agree.role == "support" and agree.quote == "Atlas GA moves to 15 December."
    assert ans.confidence == "High" and "Two independent systems agree (Email, Jira)" in ans.confidence_reasons


def test_ga_history_question_is_capped_by_missing_jira_history(world, db):
    ans = q(db, world, "How has the Atlas GA date changed?")
    assert ans.kind == "release_date" and ans.confidence == "Medium"
    assert "Jira holds no history of the date between its original and current values" in ans.confidence_reasons


def test_ga_without_corroboration_is_medium(world, db):
    ctx = TimeContext.recorded_by("2026-09-02", knowledge_cutoff=datetime(2026, 11, 18, 12))
    ans = q(db, world, "When is Atlas GA?", ctx)  # 08.eml (3 Sep) not yet recorded
    assert ans.status == "answered" and "15 Dec 2026" in ans.short_answer and ans.confidence == "Medium"


def test_ga_date_recorded_by_a_date_before_the_change_does_not_leak(world, db):
    before = TimeContext.recorded_by("2026-09-01", knowledge_cutoff=datetime(2026, 11, 18, 12))
    after = TimeContext.recorded_by("2026-09-03", knowledge_cutoff=datetime(2026, 11, 18, 12))
    b = q(db, world, "When is Atlas GA?", before)
    assert b.status == "uncertain" and "15 Dec" not in to_dict(b).__repr__()
    assert files(b) == {"04.eml", "Board_Update_Q2.pdf"}  # recorded by 1 Sep; no transcript, no Oct board
    a = q(db, world, "When is Atlas GA?", after)
    assert a.status == "answered" and "15 Dec 2026" in a.short_answer


def test_ga_date_known_before_the_tracker_release(world, db):
    ans = q(db, world, "When is Atlas GA?", BEFORE_D3)
    assert ans.status == "uncertain" and "15 Dec" not in repr(to_dict(ans))
    assert "Jira_Export_ATLAS.xlsx" not in files(ans)


# ---------------------------------------------------------------- launch readiness

def test_marketing_launch_readiness(world, db):
    ans = q(db, world, "Is marketing ready for the Atlas launch?")
    assert (ans.kind, ans.status) == ("launch_readiness", "answered")
    s = ans.short_answer
    assert s.startswith("Not ready on the records: the launch kit (Atlas_Launch_Kit_v1.pdf, dated 21 Jul 2026) "
                        "marks 2 of 4 items ready")
    assert "Press note (Draft)" in s and "Launch date (TBC)" in s
    assert "planned launch date was 22 Sep 2026, which has passed" in s
    assert "Jira's GA date is 15 Dec 2026" in s and "after the kit was written" in s
    assert "its owner, Dev Patel, left on 31 Oct 2026" in s
    # Two systems support different parts of the answer; that is not corroboration.
    assert ans.confidence == "Medium" and ans.confidence_reasons[0].startswith("Best support is one rung 3")


def test_launch_readiness_before_the_kit_was_released_quotes_statements(world, db):
    ans = q(db, world, "Is marketing ready for the Atlas launch?", AT_D1)
    assert ans.status == "uncertain" and files(ans) == {"05.eml"}


# ---------------------------------------------------------------- purpose: Atlas ownership and 09.eml

def test_ownership_question_may_cite_the_purpose_limited_email(world, db):
    ans = q(db, world, "Who owns Atlas?")
    assert (ans.kind, ans.purpose) == ("ownership", "atlas_ownership")
    assert "Rina Shah holds the most Atlas tickets: 3 of 4, 2 of the 3 open" in ans.short_answer
    assert "could be more than one person" in ans.short_answer  # MK
    assert {"09.eml", "04.eml"} <= files(ans)
    quotes = {link.quote for link in ans.evidence_chain}
    assert "Can we talk about Atlas ownership sometime this week?" in quotes  # the body, never a header
    assert "Atlas_Launch_Kit_v1.pdf" not in files(ans)  # a document's "Owner:" label is not a statement
    assert ans.confidence == "Medium"


def test_other_questions_never_see_the_purpose_limited_email(world, db):
    for text in ("When is Atlas GA?", "Tell me about ownership", "Can we talk sometime this week?",
                 "What did people email about Atlas?"):
        ans = q(db, world, text)
        assert "09.eml" not in files(ans), text
        assert ans.purpose is None


def test_purpose_cannot_be_supplied_by_the_caller(world, db, client, settings, engine):
    import inspect
    assert "purpose" not in inspect.signature(ask).parameters
    r = client.get("/api/ask", params={"q": "Can we talk sometime this week?", "purpose": "atlas_ownership",
                                       "as_of": "2026-11-18"})
    assert r.status_code == 200 and "09.eml" not in r.text


# ---------------------------------------------------------------- source disagreement

def test_source_disagreement_names_both_sides(world, db):
    ans = q(db, world, "Do the sources disagree about office rent?")
    assert (ans.kind, ans.status) == ("disagreement", "answered")
    assert ans.short_answer.startswith("Yes: 1 recorded disagreement(s) about office rent.")
    assert [link.statement[:20] for link in ans.evidence_chain] == ["C-RX-0001 side A: Ea", "C-RX-0001 side B: am"]
    assert ans.confidence == "Low" and "open conflict" in " ".join(ans.confidence_reasons)


def test_disagreement_is_not_shown_before_both_sides_are_known(world, db):
    assert q(db, world, "Are there any conflicts?", AT_D1).status == "no_evidence"
    assert q(db, world, "Are there any conflicts?", AT_D3).status == "answered"


def test_fallback_answer_surfaces_a_conflict_on_its_record(world, db):
    ans = q(db, world, "Tell me about office rent")
    assert (ans.kind, ans.status) == ("search", "uncertain")
    assert "The records disagree (C-RX-0001, open)" in ans.short_answer
    assert ans.confidence == "Low" and [c.conflict_key for c in ans.conflicts] == ["C-RX-0001"]


# ---------------------------------------------------------------- fallback, missing evidence, unsupported

def test_fallback_quotes_the_closest_record(world, db):
    ans = q(db, world, "What did the board say about feature-complete?")
    assert ans.status == "uncertain" and "Board_Update_Q3.pdf" in ans.short_answer
    assert "feature-complete" in ans.evidence_chain[0].quote


def test_missing_evidence_and_unsupported_questions(world, db):
    none = q(db, world, "What is the weather on Mars?")
    assert none.status == "no_evidence" and none.confidence == "Low"
    words = q(db, world, "the of")
    assert (words.status, words.refusal) == ("refused", "unsupported")
    for bad in ("", "   ", "x" * 501, 'routing" OR *'):
        ans = ask(db, bad, AT_D3)
        assert_five_fields(ans)


def test_unlinked_name_is_never_merged_with_a_similar_one(world, db):
    ans = q(db, world, "What did Rinal do in August 2026?")
    assert "Rina Shah" not in ans.short_answer
    assert all("Rinal" in (link.quote or "") or "Rinal" in link.statement or not link.keys
               for link in ans.evidence_chain if link.role == "support")


# ---------------------------------------------------------------- policy refusals

@pytest.mark.parametrize("text,reason", [
    ("Is Mira Kale committing late at night?", "performance_assessment"),
    ("Who commits on weekends?", "performance_assessment"),
    ("How productive is Rina Shah?", "performance_assessment"),
    ("Rate Rina's performance", "performance_assessment"),
    ("Is Rina Shah planning to leave?", "speculation"),
    ("Is Mira Kale unhappy about Atlas ownership?", "speculation"),
    ("What is our profit?", "not_computable"),
    ("What was revenue in Q2?", "not_computable"),
])
def test_policy_refusals(world, db, text, reason):
    ans = q(db, world, text)
    assert (ans.status, ans.refusal, ans.confidence_basis) == ("refused", reason, "policy")
    assert not ans.evidence_chain and "09.eml" not in repr(to_dict(ans))


# ---------------------------------------------------------------- citation validation

def _draft(db, keys, quote=None, short="A claim."):
    a = Answer(question="test", short_answer=short, weakest_link="w", would_change_mind="c",
               evidence_chain=[ChainLink("statement", keys, quote)])
    return a


def test_invalid_citations_withhold_the_answer(world, db):
    board = key_of(db, "Board_Update_Q3.pdf")
    jira = key_of(db, "Jira_Export_ATLAS.xlsx")
    mail9 = key_of(db, "09.eml")
    cases = [(["E9999"], AT_D3, "unknown_key"), ([jira], AT_D1, "not_released_yet"),
             ([mail9], AT_D3, "purpose_limited"), ([key_of(db, "Payroll_Register_Test.xlsx")], AT_D3, "restricted")]
    for keys, ctx, reason in cases:
        ans = finalize(db, _draft(db, keys), ctx, Intent("search"))
        assert ans.status == "withheld" and reason in ans.failed_checks[0], reason
        assert not ans.evidence_chain and ans.confidence == "Low"
    ok = finalize(db, _draft(db, [board]), AT_D3, Intent("search"))
    assert ok.status == "answered" and ok.evidence_chain[0].citations[0].filename == "Board_Update_Q3.pdf"
    allowed = finalize(db, _draft(db, [mail9]), AT_D3, Intent("ownership", purpose="atlas_ownership"))
    assert allowed.status == "answered"


def test_false_quotations_and_uncited_keys_are_caught(world, db):
    board = key_of(db, "Board_Update_Q3.pdf")
    false = finalize(db, _draft(db, [board], quote="the engine is late"), AT_D3, Intent("search"))
    assert false.status == "withheld" and "quote_not_found" in false.failed_checks[0]
    true = finalize(db, _draft(db, [board], quote="feature-complete"), AT_D3, Intent("search"))
    assert true.status == "answered"
    stray = finalize(db, _draft(db, [board], short=f"See {board} and E9999."), AT_D3, Intent("search"))
    assert stray.status == "withheld" and stray.failed_checks == ["E9999: named in the answer but not in the "
                                                                  "evidence chain"]


def test_a_handler_bug_cannot_leak_a_later_record(world, db, monkeypatch):
    jira = key_of(db, "Jira_Export_ATLAS.xlsx")

    def leaky(a):
        return a.new("Leaked.", evidence_chain=[ChainLink("from the future", [jira])])
    monkeypatch.setitem(engine_mod.handlers.HANDLERS, "company_headcount", leaky)
    ans = ask(db, "How many employees?", AT_D1)
    assert ans.status == "withheld" and "not_released_yet" in ans.failed_checks[0]


# ---------------------------------------------------------------- confidence

def test_confidence_rules():
    S = Support
    assert assess([S(1, "Zoho Books", "SRC-1")]).level == "High"
    assert assess([S(3, "Keka HRMS", "SRC-2")]).level == "Medium"
    assert assess([S(3, "Keka HRMS", "SRC-2"), S(3, "Keka HRMS", "SRC-9")], corroborated=True).level == "Medium"
    assert assess([S(3, "Keka HRMS", "SRC-2"), S(3, "Jira", "SRC-3")], corroborated=True).level == "High"
    assert assess([S(3, "Keka HRMS", "SRC-2"), S(3, "Jira", "SRC-3")]).level == "Medium"  # related, not agreeing
    assert assess([S(3, "Keka HRMS", "SRC-2"), S(5, "MeetNotes AI", "SRC-4")], corroborated=True).level == "Medium"
    assert assess([S(5, "MeetNotes AI", "SRC-4")]).level == "Low"
    assert assess([S(None, None, "SRC-5")]).level == "Low"
    assert assess([]).level == "Low"
    assert assess([S(1, "Zoho Books", "SRC-1")], open_conflicts=1).level == "Low"
    assert assess([S(1, "Zoho Books", "SRC-1")], resolved_conflicts=1).level == "Medium"
    assert assess([S(1, "Zoho Books", "SRC-1")], identity="M").level == "Medium"
    assert assess([S(1, "Zoho Books", "SRC-1")], identity="L").level == "Low"
    assert assess([S(1, "Zoho Books", "SRC-1")], temporal="approximate").level == "Medium"
    assert assess([S(1, "Zoho Books", "SRC-1")], temporal="unknown").level == "Low"
    assert assess([S(1, "Zoho Books", "SRC-1")], completeness="partial").level == "Medium"
    assert assess([S(1, "Zoho Books", "SRC-1")], completeness="insufficient").level == "Low"
    assert assess([], policy=True).level == "High"
    a1 = assess([S(3, "Keka HRMS", "SRC-2")], identity="M", temporal="approximate")
    assert a1 == assess([S(3, "Keka HRMS", "SRC-2")], identity="M", temporal="approximate")  # deterministic
    assert "(no change)" in a1.reasons[1]


def test_handlers_cannot_set_confidence(world, db):
    board = key_of(db, "Board_Update_Q3.pdf")
    d = _draft(db, [board])
    d.confidence, d.confidence_reasons = "High", ["I say so"]
    t = key_of(db, "T1_Test_Call.docx")
    d.evidence_chain = [ChainLink("transcript only", [t])]
    ans = finalize(db, d, AT_D3, Intent("search"))
    assert ans.confidence == "Low" and "I say so" not in ans.confidence_reasons


# ---------------------------------------------------------------- point-in-time leakage

def test_nothing_is_known_before_the_first_release(world, db):
    for text in ("How many employees?", "When is Atlas GA?", "How many incidents in August 2026?",
                 "Who owns Atlas?", "Is marketing ready for the Atlas launch?", "Tell me about office rent"):
        ans = q(db, world, text, BEFORE_D1)
        assert ans.status in ("no_evidence", "uncertain") and not ans.evidence_chain, text


def test_answers_at_day_one_cite_only_day_one_records(world, db):
    for text in ("When is Atlas GA?", "Who owns Atlas?", "Tell me about routing engine", "Are there any conflicts?",
                 "How many incidents in August 2026?"):
        ans = q(db, world, text, AT_D1)
        for link in ans.evidence_chain:
            assert all(c.released_on <= AT_D1.as_of for c in link.citations), text


def test_as_of_in_the_question_sets_the_time_frame(world, db):
    ans = ask(db, "How many incidents in August 2026, as of 16 Nov 2026?")
    assert ans.as_of == datetime(2026, 11, 16, 23, 59, 59) and ans.status == "no_evidence"


# ---------------------------------------------------------------- LLM (optional)

class _Phraser:
    def __init__(self, fn):
        self.fn, self.calls = fn, 0

    def rephrase(self, text, *, facts):
        self.calls += 1
        return self.fn(text)


def test_llm_is_off_by_default_and_needs_no_key(world, db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert Settings().llm_enabled is False
    p = _Phraser(lambda t: "Reworded.")
    ans = q(db, world, "How many employees do we have?", AT_D1, phraser=p)
    assert p.calls == 0 and ans.wording == "template"


def test_llm_may_reword_but_not_add_facts_or_change_confidence(world, db):
    base = q(db, world, "How many employees do we have?", AT_D1)
    good = q(db, world, "How many employees do we have?", AT_D1, llm_enabled=True,
             phraser=_Phraser(lambda t: "On 16 Nov 2026 there were 5 employees."))
    assert good.wording == "llm" and good.template_answer == base.short_answer
    assert (good.confidence, good.status, good.keys()) == (base.confidence, base.status, base.keys())
    for bad in (lambda t: "There were 7 employees.", lambda t: "5 employees, says Zara.",
                lambda t: "5 employees, with high confidence."):
        ans = q(db, world, "How many employees do we have?", AT_D1, llm_enabled=True, phraser=_Phraser(bad))
        assert ans.wording == "template" and any("rejected" in w for w in ans.warnings)


def test_llm_failures_and_refusals_keep_the_rule_wording(world, db):
    def boom(t):
        raise RuntimeError("no network")
    ans = q(db, world, "How many employees do we have?", AT_D1, llm_enabled=True, phraser=_Phraser(boom))
    assert ans.wording == "template" and any("failed" in w for w in ans.warnings)
    p = _Phraser(lambda t: "Sure, it is fine.")
    refused = q(db, world, "What does Mira Kale earn?", llm_enabled=True, phraser=p)
    assert p.calls == 0 and refused.status == "refused"
    assert check_wording("5 employees.", [], "5 employees.") is None


# ---------------------------------------------------------------- output

def test_text_rendering_and_api(world, db, client):
    ans = q(db, world, "Who does Mira Kale report to?", AT_D1)
    text = render_text(ans)
    for label in ("Question:", "Short answer:", "Evidence chain:", "Confidence:", "Weakest link:",
                  "What would change my mind:"):
        assert label in text
    r = client.get("/api/ask", params={"q": "How many employees?", "as_of": "nonsense"})
    assert r.status_code == 400
    r = client.get("/api/ask", params={"q": "How many employees?", "as_of": "2026-11-16"})
    body = r.json()
    assert r.status_code == 200 and {"question", "short_answer", "evidence_chain", "confidence", "weakest_link",
                                     "would_change_mind"} <= set(body)
