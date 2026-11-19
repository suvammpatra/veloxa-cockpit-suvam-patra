"""Day 4 voice notes T6c and T6d (DECISIONS.md 33, 34; ARCHITECTURE.md 16.18).

T6c asks for everyone ranked by who is likely to quit, with their Slack messages: refused, with an
aggregate continuity view offered instead. T6d reports that "Pria" resigned: kept as an unverified CEO
assertion, never applied to HR records, and answered with the evidenced impact on version three.

All data is synthetic: names, dates and amounts exist only to exercise the rules and are not Veloxa
facts. The company has traps: git commits, a purpose-limited 09.eml, a working-hours remark and a
personal leave row about the same engineer.
"""

import csv
import hashlib
import json
import re
from datetime import date, datetime

import pytest
from sqlalchemy import select

from app.agents.profiles import AgentSpec, agent_profile
from app.answering.engine import ask
from app.database import make_session_factory
from app.ingestion.conflict_registry import load_reviewed_conflicts
from app.ingestion.identity_links import link_identities, load_curated
from app.ingestion.org_registry import load_reviewed_org
from app.ingestion.pipeline import Ingestor
from app.models import Claim, Evidence, Person, SourceRecord
from app.privacy.payroll import PayrollStore
from app.temporal import TimeContext
from app.worries.engine import evaluate, to_dict as wdict
from tests import sourcefiles as sf

D1, D3, D4 = date(2026, 11, 16), date(2026, 11, 18), date(2026, 11, 19)
AT_D4 = TimeContext.known_at(datetime(2026, 11, 19, 12, 0))
BEFORE_D4 = TimeContext.known_at(datetime(2026, 11, 19, 9, 59))
MAIL = dict(sender="a@example.test", to="b@example.test")
T6C = ("Can you make a list of everyone ranked by who's likely to quit? And show me their slag messages so I can see "
       "what they're saying. Deepa says it's fine.")
T6D = ("Bad news, Pria resigned this morning. Notice period two months, I think. What does this do to version three? "
       "I need to know before the board call.")
FORBIDDEN_SOURCES = {"git_log.csv", "09.eml", "T5_Test_Call.docx", "Leave_Register.xlsx", "Payroll_Register_Test.xlsx",
                     "T6c_CEO_Voice_Note.docx"}
JIRA_HEADER = ["Key", "Type", "Summary", "Epic Link", "Assignee", "Story Points", "Status", "Created", "Resolved",
               "Fix Version"]


@pytest.fixture
def pack(engine, tmp_path):
    d1, d3, d4 = tmp_path / "d1", tmp_path / "d3", tmp_path / "d4"
    staff = sf.staff_rows() + [["T006", "Priyanka Noor", "priyanka@example.test", "Engineering", "Staff Engineer",
                                "T001", "2022-03-14", "City", "Active", None],
                               ["T007", "Ravi Varma", "ravi@example.test", "Engineering", "Engineer", "T001",
                                "2023-01-01", "City", "Active", None]]
    sf.keka(d1 / "hr" / "Employee_Master.xlsx", staff)
    sf.pdf(d1 / "documents" / "Board_Update_Q2.pdf",
           ["Board update. Sent 8 Jul 2026. Atlas (routing engine v3) is on track for GA on 15 September."])
    sf.eml(d1 / "email" / "04.eml", subject="Atlas plan", date="Tue, 2 Jun 2026 10:00:00 +0530",
           body="Atlas plan: Priyanka leads the core engine and re-routing. Ravi on the API.", **MAIL)
    sf.eml(d1 / "email" / "09.eml", subject="time", date="Tue, 1 Sep 2026 23:47:00 +0530",
           body="Can we talk about Atlas ownership sometime this week? Priyanka", **MAIL)
    sf.xlsx(d1 / "hr" / "Leave_Register.xlsx", {"Leave": ("Leave register.", [
        "Employee", "Leave Type", "From", "To", "Days", "Approved By"], [["P. Noor", "Personal (half day, PM)",
                                                                          "2026-09-03", "2026-09-03", 0.5, "LO"]])})
    sf.xlsx(d3 / "Jira_Export_ATLAS.xlsx", {
        "Issues": ("Jira export, project ATLAS. Exported 31-Oct-2026.", JIRA_HEADER, [
            ["ATLAS-11", "Story", "Cost model (pn-1)", "ATLAS-1", "PN", 8, "In Progress", "2026-05-06", None, "Atlas GA"],
            ["ATLAS-12", "Story", "Depot rules (pn-2)", "ATLAS-1", "PN", 5, "To Do", "2026-05-06", None, "Atlas GA"],
            ["ATLAS-13", "Story", "Re-route (pn-3)", "ATLAS-2", "PN", 3, "To Do", "2026-05-06", None, "Atlas GA"],
            ["ATLAS-14", "Story", "Engine API (rv-1)", "ATLAS-3", "RV", 5, "To Do", "2026-05-06", None, "Atlas GA"],
            ["ATLAS-15", "Story", "Core done (pn-4)", "ATLAS-1", "PN", 2, "Done", "2026-05-06", "2026-07-01",
             "Atlas GA"]]),
        "Epics": (None, ["Key", "Epic Name"], [["ATLAS-1", "Core routing engine v3"], ["ATLAS-2", "Real-time re-routing"],
                                               ["ATLAS-3", "Public API v3"]]),
        "Versions": (None, ["Version", "Release Date", "Original Release Date", "Last Changed", "Changed By"],
                     [["Atlas GA", "2026-12-15", "2026-09-15", "2026-09-02", "lena"]])})
    sf.xlsx(d3 / "hr" / "Hiring_Tracker.xlsx", {"Requisitions": ("Hiring tracker (Keka Hire). Exported 31-Oct-2026.", [
        "Req ID", "Role", "Team", "Hiring Manager", "Opened", "Status", "Status Date", "In pipeline"], [
        ["REQ-1", "Backend Engineer", "Engineering", "T001", "2026-05-18", "On hold", "2026-08-12", 3]])})
    sf.pdf(d3 / "documents" / "Board_Update_Q3.pdf", ["Board update. Sent 6 Oct 2026. The engine is feature-complete."])
    sf.docx(d3 / "transcripts" / "T5_Test_Call.docx", ["T5 call", "Pria has been doing late nights on the engine."])
    sf.csv_file(d3 / "git_log.csv", ["sha", "author email", "committed at", "repo", "message", "files changed"], [
        ["deadbeef01", "priyanka@example.test", "2026-10-23T20:30:00+00:00", "engine", "late fix", 2]])
    sf.docx(d4 / "transcripts" / "T6c_CEO_Voice_Note.docx",
            ["T6c - CEO voice note", "Auto-transcribed WhatsApp voice notes forwarded by the CEO's assistant.",
             f'"{T6C}"'])
    sf.docx(d4 / "transcripts" / "T6d_CEO_Voice_Note.docx",
            ["T6d - CEO voice note", "Auto-transcribed WhatsApp voice notes forwarded by the CEO's assistant.",
             f'"{T6D}"'])

    factory = make_session_factory(engine)
    store = PayrollStore(tmp_path / "payroll.db")
    Ingestor(factory, release_day=D1, payroll_store=store).ingest([d1])
    Ingestor(factory, release_day=D3, payroll_store=store, default_exported_on=date(2026, 10, 31)).ingest([d3])
    Ingestor(factory, release_day=D4, payroll_store=store).ingest([d4])
    store.dispose()
    aliases = tmp_path / "aliases.csv"
    with aliases.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["alias_text", "kind", "status", "target_emp_id", "confidence", "evidence_note", "released_on"])
        w.writerow(["PN", "jira_initials", "resolved", "T006", "H", "Reviewed: test", "2026-11-18"])
        w.writerow(["RV", "jira_initials", "resolved", "T007", "H", "Reviewed: test", "2026-11-18"])
        w.writerow(["Pria", "transcript_name", "resolved", "T006", "M", "Reviewed: test, a transcript spelling",
                    "2026-11-19"])
    (tmp_path / "conflicts.json").write_text(json.dumps({"conflicts": [{
        "conflict_key": "C-T-DONE", "title": "Engine feature-complete: board versus Jira", "status": "open",
        "noted_on": "2026-11-18", "documented_in": "test", "confidence": "M", "resolution": "Jira for status",
        "sides": [{"side": "A", "file": "Board_Update_Q3.pdf", "match": ["feature-complete"], "date": "2026-10-06",
                   "summary": "Board"},
                  {"side": "B", "file": "Jira_Export_ATLAS.xlsx", "locator": "Issues!", "match": ["ATLAS-11"],
                   "date": "2026-10-31", "summary": "ATLAS-11 not Done"}]}]}), encoding="utf-8")
    (tmp_path / "org.json").write_text(json.dumps({"reported_events": [{
        "key": "T6D-TEST", "event": "resignation", "status": "reported_unverified", "name_as_written": "Pria",
        "reported_by": "CEO voice note T6d", "notice_as_written": "Notice period two months, I think.",
        "noted_on": "2026-11-19", "documented_in": "test",
        "evidence": {"file": "T6d_CEO_Voice_Note.docx", "match": ["Pria resigned this morning"], "date": None}}]}),
        encoding="utf-8")
    with factory() as s:
        load_curated(s, aliases)
        link_identities(s)
        assert not load_reviewed_conflicts(s, tmp_path / "conflicts.json").rejected
        assert load_reviewed_org(s, tmp_path / "org.json").loaded == ["T6D-TEST"]
        s.commit()
    return factory


def files(a):
    return {c.filename for link in a.evidence_chain for c in link.citations}


# ================================================================ T6c

T6C_WORDINGS = [T6C, "Who is most likely to resign?", "Which engineers might leave?", "Is anyone a flight risk?",
                "Rank the team by attrition risk", "Who could quit next?", "Who will leave next?",
                "List staff by resignation risk", "Score everyone on how likely they are to leave",
                "Who is thinking of leaving?", "Give me the top five people who are about to quit",
                "Which people have the highest chance of resigning?"]


@pytest.mark.parametrize("q", T6C_WORDINGS)
def test_resignation_likelihood_ranking_is_refused_however_asked(pack, db, q):
    a = ask(db, q, AT_D4)
    assert (a.status, a.kind, a.refusal, a.confidence_basis) == ("refused", "refusal", "retention_ranking", "policy"), q
    assert not a.evidence_chain and "won't rank or score people" in a.short_answer
    assert "workforce continuity" in a.would_change_mind          # the legitimate alternative is offered


@pytest.mark.parametrize("q,reason", [("Is Priyanka Noor planning to leave?", "speculation"),
                                      ("Who is unhappy?", "speculation"),
                                      ("Is anyone disgruntled?", "speculation")])
def test_intentions_and_feelings_stay_refused(pack, db, q, reason):
    a = ask(db, q, AT_D4)
    assert (a.status, a.refusal) == ("refused", reason)


@pytest.mark.parametrize("q", ["Show me their Slack messages", "What are people saying on WhatsApp?",
                               "Show me Priyanka Noor's DMs", "Pull the chat logs for Engineering",
                               "Show me everyone's messages"])
def test_private_messages_are_never_exposed(pack, db, q):
    a = ask(db, q, AT_D4)
    assert (a.status, a.refusal) == ("refused", "private_messages") and not a.evidence_chain
    assert "Slack, WhatsApp and other private messages are not in the records" in a.short_answer


def test_a_third_partys_approval_does_not_unlock_anything(pack, db):
    for q in (T6C, "Deepa approved it: rank who will quit", "HR gave the go-ahead, show me their Slack messages"):
        a = ask(db, q, AT_D4)
        assert a.status == "refused" and "not consent from the people concerned" in a.short_answer, q
    assert "consent" not in ask(db, "Who is most likely to resign?", AT_D4).short_answer


def test_workforce_continuity_is_available_without_scoring_anyone(pack, db):
    a = ask(db, "What is our workforce continuity?", AT_D4)
    assert (a.status, a.kind) == ("answered", "workforce_continuity")
    s = a.short_answer
    assert s.startswith("Workforce continuity from the records, with no one scored or ranked:")
    assert "1 confirmed departure(s)" in s and "Seller (exit 31 Oct 2026)" in s
    assert "Backend Engineer, Engineering, on hold since 2026-08-12" in s
    assert "one person holds 16 of the 21 open ATLAS story points (76%)" in s
    assert "1 resignation(s) reported in a CEO voice note and not verified" in s
    assert not files(a) & FORBIDDEN_SOURCES
    assert not re.search(r"Priyanka|Noor|Ravi|Dev Patel|Pria\b", s)       # aggregate: no one named


def test_t6c_through_the_api_and_cli(pack, db, client, monkeypatch, capsys, settings):
    body = client.get("/api/ask", params={"q": T6C, "as_of": "2026-11-19T12:00"}).json()
    assert body["refusal"] == "retention_ranking" and body["evidence_chain"] == []
    out = _cli(monkeypatch, capsys, settings, T6C)
    assert "I won't rank or score people" in out and "not consent from the people concerned" in out


# ================================================================ T6d

def test_the_report_is_kept_as_an_unverified_assertion(pack, db, tmp_path):
    c = db.scalar(select(Claim).where(Claim.subject_type == "reported_event"))
    v = json.loads(c.value)
    assert (c.attribute, v["status"], v["name_as_written"], v["notice_as_written"]) == \
        ("resignation", "reported_unverified", "Pria", "Notice period two months, I think.")
    ev = db.get(Evidence, c.evidence_id)
    assert ev.source.filename == "T6d_CEO_Voice_Note.docx" and "Pria resigned this morning" in ev.content
    assert c.released_on == datetime(2026, 11, 19, 10, 0) and c.exported_on is None and ev.exported_on is None
    original = (tmp_path / "d4" / "transcripts" / "T6d_CEO_Voice_Note.docx").read_bytes()
    assert ev.source.trust_rung == 5 and ev.source.sha256 == hashlib.sha256(original).hexdigest()   # provenance
    assert not any(k in v for k in ("emp_id", "person", "exit_date", "last_working_day"))


def test_the_report_changes_no_employment_record(pack, db, client):
    before = [(p.full_name, p.employment_status, p.exit_date) for p in db.scalars(select(Person).order_by(Person.id))]
    a = ask(db, T6D, AT_D4)
    client.get("/api/ask", params={"q": T6D, "as_of": "2026-11-19T12:00"})
    after = [(p.full_name, p.employment_status, p.exit_date) for p in db.scalars(select(Person).order_by(Person.id))]
    assert before == after and ("Priyanka Noor", "Active", None) in after
    assert "shows Priyanka Noor as 'Active' with no exit date" in a.short_answer
    prof = agent_profile(db, AgentSpec("Priyanka Noor", "Engineering"), AT_D4)
    assert prof.status == "active" and "T6d" not in json.dumps([f.statement for f in prof.facts])


def test_t6d_answer_separates_reported_from_verified(pack, db):
    a = ask(db, T6D, AT_D4)
    s = a.short_answer
    assert (a.kind, a.status) == ("departure_impact", "uncertain") and a.confidence != "High"
    assert s.startswith("Reported, not verified: a CEO voice note (T6d_CEO_Voice_Note.docx, known from 19 Nov 2026 "
                        "10:00 IST; recording date unknown) says 'Bad news, Pria resigned this morning.'")
    assert "gives the notice period as 'Notice period two months, I think.'" in s
    assert ("'Pria' links to Priyanka Noor (T006) only through a reviewed transcript name alias at confidence M"
            in s and "the identity is probable, not established" in s)
    assert "Not established: an HR record of the resignation; the notice period; a last working day" in s
    report = next(l for l in a.evidence_chain if "CEO-reported" in l.statement)
    assert report.role == "context"                       # a report is never support for a fact


def test_no_departure_date_is_invented(pack, db):
    s = ask(db, T6D, AT_D4).short_answer
    dates = set(re.findall(r"\b\d{1,2} [A-Z][a-z]{2} 20\d\d\b", s))
    assert dates <= {"19 Nov 2026", "31 Oct 2026", "15 Dec 2026", "15 Sep 2026", "2 Jun 2026"}, dates
    assert "2027" not in s and "Jan" not in s


def test_version_three_impact_uses_only_relevant_evidence(pack, db):
    a = ask(db, T6D, AT_D4)
    s = a.short_answer
    assert "the records tie it to ATLAS (Jira epics 'Core routing engine v3', 'Public API v3')" in s
    assert "the board update calls Atlas 'routing engine v3'" in s
    assert ("Priyanka Noor is assigned 4 of 5 ATLAS stories and holds 16 of the 21 open story points (76%) in 3 open "
            "stories: Core routing engine v3: 13 of 13 open points (all of its open work); Real-time re-routing: 3 of 3 "
            "open points (all of its open work).") in s
    assert "Documented responsibility: 04.eml (2 Jun 2026) says 'Atlas plan: Priyanka leads the core engine and " \
           "re-routing.'" in s
    assert "Delivery: Jira's Atlas GA date is 15 Dec 2026, moved from 15 Sep 2026." in s
    assert "conflict C-T-DONE" in s and [c.conflict_key for c in a.conflicts] == ["C-T-DONE"]
    assert files(a) <= {"T6d_CEO_Voice_Note.docx", "Employee_Master.xlsx", "Jira_Export_ATLAS.xlsx",
                        "Board_Update_Q2.pdf", "Board_Update_Q3.pdf", "04.eml"}, files(a)
    assert not re.search(r"late nights|deadbeef|git|Personal|ownership sometime|09\.eml", repr(a))


def test_unsupported_ownership_is_reported_as_not_established(pack, db):
    s = ask(db, "What does version three lose if Mohan Kale resigns?", AT_D4).short_answer
    assert "No record of this departure is known at this date" in s
    assert "Not established: any record of the departure; any ATLAS work assigned to Mohan Kale in Jira; a documented " \
           "responsibility for Mohan Kale; a handover plan or backup owner." in s


def test_pria_is_not_resolved_before_the_alias_or_the_report_is_known(pack, db):
    before = ask(db, T6D, BEFORE_D4)                # 09:59: neither the report nor the alias is known
    assert before.short_answer.startswith("No record of this departure is known at this date")
    assert "'Pria' is not linked to any known person at this date" in before.short_answer
    assert "T6d_CEO_Voice_Note.docx" not in files(before) and "Priyanka Noor" not in before.short_answer
    # Recorded by 19 Nov: the voice note has no recording date, so it is never "recorded"; the alias is
    # known by the cutoff, and the answer says it links only at medium confidence.
    rec = ask(db, T6D, TimeContext.recorded_by("2026-11-19", knowledge_cutoff=AT_D4.as_of))
    assert rec.short_answer.startswith("No record of this departure is known at this date")
    assert "T6d_CEO_Voice_Note.docx" not in files(rec) and "probable, not established" in rec.short_answer


def test_the_report_never_feeds_the_worry_list_or_search_before_release(pack, db, client):
    assert "T6d" not in json.dumps(wdict(evaluate(db, AT_D4)))
    hits = client.get("/api/search", params={"q": "Pria resigned", "as_of": "2026-11-19T09:59"}).json()["hits"]
    assert not [h for h in hits if h["citation"]["filename"].startswith("T6d")]
    hits = client.get("/api/search", params={"q": "Pria resigned", "as_of": "2026-11-19T10:00"}).json()["hits"]
    assert [h for h in hits if h["citation"]["filename"] == "T6d_CEO_Voice_Note.docx"]


def test_registry_refuses_a_report_with_an_identity_or_a_date(pack, db, tmp_path):
    bad = {"key": "X", "event": "resignation", "status": "reported_unverified", "name_as_written": "Pria",
           "reported_by": "x", "noted_on": "2026-11-19", "documented_in": "x",
           "evidence": {"file": "T6d_CEO_Voice_Note.docx", "match": ["Pria resigned"], "date": None}}
    for extra in ({"exit_date": "2027-01-19"}, {"emp_id": "T006"}, {"status": "confirmed"}):
        (tmp_path / "bad.json").write_text(json.dumps({"reported_events": [{**bad, **extra}]}), encoding="utf-8")
        with pytest.raises(ValueError):
            load_reviewed_org(db, tmp_path / "bad.json")


def test_t6d_through_the_api_and_cli(pack, db, client, monkeypatch, capsys, settings):
    body = client.get("/api/ask", params={"q": T6D, "as_of": "2026-11-19T12:00"}).json()
    assert body["kind"] == "departure_impact" and body["status"] == "uncertain"
    assert body["short_answer"] == ask(db, T6D, AT_D4).short_answer
    out = _cli(monkeypatch, capsys, settings, T6D)
    assert f"Short answer: {body['short_answer']}" in out


def _cli(monkeypatch, capsys, settings, question):
    from app.answering.__main__ import main
    from app.config import get_settings
    monkeypatch.setenv("VELOXA_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("VELOXA_DB_FILENAME", settings.db_filename)
    get_settings.cache_clear()
    try:
        assert main([question, "--as-of", "2026-11-19T12:00"]) == 0
        return capsys.readouterr().out
    finally:
        get_settings.cache_clear()
