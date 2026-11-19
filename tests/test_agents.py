"""Phase 6: the 14 evidence-grounded agent profiles. All data is synthetic: the names, dates
and amounts exist only to exercise the rules and are not Veloxa facts. The project roster
itself (ARCHITECTURE.md 8) is checked separately, against ARCHITECTURE.md."""

import csv
import json
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.agents import roster as roster_mod
from app.agents.profiles import (ELIGIBLE_SYSTEMS, NOT_ESTABLISHED, Fact, _Builder, agent_profile, all_profiles,
                                 find_agent, to_dict)
from app.agents.roster import AGENT_ROSTER, NO_AGENT, AgentSpec
from app.database import make_session_factory
from app.ingestion.conflict_registry import load_reviewed_conflicts
from app.ingestion.identity_links import link_identities, load_curated
from app.ingestion.org_registry import load_reviewed_org
from app.ingestion.pipeline import Ingestor
from app.models import Evidence, SourceRecord
from app.privacy.payroll import PayrollStore
from app.retrieval.citations import validate
from app.services.identity import resolve_person
from app.temporal import TimeContext
from tests import sourcefiles as sf

ROOT = Path(__file__).resolve().parent.parent
D1, D2, D3 = date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18)
AT_D4 = TimeContext.known_at(datetime(2026, 11, 19, 12, 0))
AT_D3 = TimeContext.known_at(datetime(2026, 11, 18, 12, 0))
MAIL = dict(sender="a@example.test", to="b@example.test")

#            emp_id, name,             department,     title,            manager, joined,       exit
STAFF = [("T001", "Carla Mendes", "Leadership", "Chief", None, "2019-01-01", None),
         ("T002", "Victor Moss", "Engineering", "Eng Head", "T001", "2020-01-01", None),
         ("T003", "Priyanka Noor", "Engineering", "Staff Eng", "T002", "2021-01-01", None),
         ("T004", "Arun Dey", "Engineering", "Frontend", "T002", "2022-01-01", None),
         ("T005", "Seema Kale", "Engineering", "SRE", "T002", "2023-01-01", None),
         ("T006", "Ravi Varma", "Engineering", "Backend", "T002", "2026-02-01", None),
         ("T007", "Mona Iyer", "Finance", "Fin Head", "T001", "2020-06-01", None),
         ("T008", "Kiran Sood", "Finance", "Analyst", "T007", "2023-06-01", None),
         ("T009", "Farah Shah", "Finance", "Payroll", "T007", "2024-06-01", None),
         ("T010", "Dina Joshi", "People & Ops", "People Head", "T001", "2021-07-01", None),
         ("T011", "Rohit Bansal", "People & Ops", "Talent", "T010", "2024-07-01", None),
         ("T012", "Lata Pillai", "People & Ops", "Office", "T010", "2025-07-01", None),
         ("T013", "Nilesh Bose", "Marketing", "Mkt Head", "T001", "2024-09-01", None),
         ("T014", "Asha Khan", "Marketing", "Performance", "T013", "2023-08-01", None),
         ("T015", "Sid Mehra", "Marketing", "Product Mkt", "T013", "2025-04-01", "2026-10-31"),
         ("T016", "Manav Kumar", "Sales", "Sales Lead", "T001", "2020-01-01", None),
         ("T017", "Diya Reddy", "Sales", "AE", "T016", "2024-01-01", None),
         ("T018", "Imran Sait", "Support", "Support Lead", "T001", "2023-02-01", None),
         ("T019", "Kavi Nair", "Support", "Associate", "T018", "2025-07-01", None)]
NON_AGENTS = ("Carla Mendes", "Manav Kumar", "Diya Reddy", "Imran Sait", "Kavi Nair")
TEST_ROSTER = tuple(AgentSpec(n, dep) for _, n, dep, *_ in STAFF if n not in NON_AGENTS)
GROSS = {e: 90000 + i * 1234 for i, (e, *_) in enumerate(STAFF)}
SECRETS = ["late nights", "likes it", "Can we talk", "ownership", "Marriage", "family", "Payroll_Register",
           "Leave_Register", "Resignation_Letter", "git_log", "Email_Printouts", "T5_Test_Call", "deadbeef"]


@pytest.fixture
def company(engine, tmp_path, monkeypatch):
    d1, d2, d3 = tmp_path / "d1", tmp_path / "d2", tmp_path / "d3"
    rows = [[e, n, f"{n.split()[0].lower()}@test.example", dep, t, m, j, "City",
             "Notice period" if x else "Active", x] for e, n, dep, t, m, j, x in STAFF]
    sf.keka(d1 / "hr" / "Employee_Master.xlsx", rows)
    sf.xlsx(d1 / "finance" / "Payroll_Register_Test.xlsx", {"Payroll": ("Payroll register.", [
        "Emp ID", "Name", "Month", "Days in Month", "Days Payable", "Gross (Rs.)", "Deductions (Rs.)", "Net (Rs.)",
        "Processed By"], [[e, "x", "Mar-2026", 31, 31, g, 0, g, "XX"] for e, g in GROSS.items()])})
    sf.xlsx(d1 / "hr" / "Leave_Register.xlsx", {"Leave": ("Leave register.", [
        "Employee", "Leave Type", "From", "To", "Days", "Approved By"], [["F. Shah", "Marriage", "2026-02-09",
                                                                          "2026-02-27", 15, "MI"],
        # Leave types on no word list: withheld because they are leave records (ARCHITECTURE.md 16.19)
        ["P. Noor", "Personal (half day, PM)", "2026-09-03", "2026-09-03", 0.5, "VM"],
        ["K. Sood", "Exam", "2026-05-25", "2026-05-29", 5, "MI"],
        ["A. Dey", "Relocation", "2026-03-02", "2026-03-06", 5, "VM"],
        ["R. Varma", "Casual", "2026-07-10", "2026-07-10", 1, "VM"]])})
    (d1 / "README.txt").write_text("Test room. Exported by IT on 31 Oct 2026.\n")
    sf.pdf(d2 / "documents" / "Resignation_Letter_SM.pdf",
           ["15 September 2026. I am resigning to care for my family. Sid Mehra"])
    sf.xlsx(d3 / "Jira_Export_ATLAS.xlsx", {
        "Issues": ("Jira export, project ATLAS. Exported 31-Oct-2026.",
                   ["Key", "Type", "Summary", "Epic Link", "Assignee", "Story Points", "Status", "Created",
                    "Resolved", "Fix Version"],
                   [["ATLAS-2", "Story", "Engine (pn-1)", "ATLAS-1", "PN", 5, "In Progress", "2026-05-06", None, "GA"],
                    ["ATLAS-3", "Story", "Engine (pn-2)", "ATLAS-1", "PN", 3, "Done", "2026-05-06", "2026-07-01", "GA"],
                    ["ATLAS-4", "Story", "API (rv-1)", "ATLAS-1", "RV", 2, "To Do", "2026-05-06", None, "GA"]]),
        "Epics": (None, ["Key", "Epic Name"], [["ATLAS-1", "Core engine"]])})
    sf.xlsx(d3 / "Incidents_Aug-Oct_2026.xlsx", {"Incidents": ("Incident export.", [
        "ID", "Severity", "Opened", "Resolved", "Service", "Responder"], [
        ["INC-1", "SEV1", "2026-08-04T05:00:00Z", None, "api", "Seema"],
        ["INC-2", "SEV1", "2026-08-14T05:00:00Z", None, "api", "Seema"],
        ["INC-3", "SEV2", "2026-08-27T05:00:00Z", None, "api", "Seemal"],
        ["INC-4", "SEV3", "2026-09-27T05:00:00Z", None, "web", "Arun"]])})
    sf.xlsx(d3 / "OnCall_Rota.xlsx", {"On-call": ("Team wiki table, copied.", ["Week of", "Primary", "Secondary"], [
        ["2026-08-03", "Seema", "Arun"], ["2026-08-10", "Seemal", "Seema"], ["2026-08-17", "Seema", "Priyanka"]])})
    sf.csv_file(d3 / "git_log.csv", ["sha", "author email", "committed at", "repo", "message", "files changed"], [
        ["deadbeef01", "priyanka@test.example", "2026-06-02T18:30:00+00:00", "engine", "late fix", 3],
        # Decision 30 tests: commits inside rota weeks, worded to tempt a keyword match on "on-call"
        ["deadbeef02", "seema@test.example", "2026-08-17T21:30:00+00:00", "engine", "on-call pager alert fix", 2],
        ["deadbeef03", "priyanka@test.example", "2026-08-18T22:10:00+00:00", "engine", "on-call hotfix week of 17 Aug",
         1],
        ["deadbeef04", "arun@test.example", "2026-09-15T04:00:00+00:00", "web", "on-call handover notes", 1],
        ["deadbeef05", "ravi@test.example", "2026-08-20T06:00:00+00:00", "planner", "speed up graph load", 4]])
    sf.eml(d3 / "email" / "09.eml", subject="time", date="Tue, 1 Sep 2026 23:47:00 +0530",
           body="Can we talk about Atlas ownership sometime this week?", **MAIL)
    sf.pdf(d3 / "email" / "Email_Printouts.pdf", ["Email export. Can we talk about Atlas ownership sometime?"])
    sf.docx(d3 / "transcripts" / "T5_Test_Call.docx", ["T5 call", "Pri has been doing late nights but she likes it.",
                                                         "Seema covers the on-call rota on weekends."])
    sf.docx(d1 / "transcripts" / "T2_Test_Call.docx", [
        "T2 call",
        'Her team: Kiran on planning, and Farah Shah on payroll ("she was out for her wedding, that month was messy").',
        "Payroll for February was run by Kiran. Farah was away for her wedding that month.",
        "Deploys are frozen on weekends during the summit."])
    sf.docx(d3 / "transcripts" / "T6b_Test_Note.docx", ["T6b", "So, marketing will report to the new CRO soon."])
    sf.pdf(d3 / "documents" / "Board_Update_Q3.pdf", ["Board update. Sent 6 Oct 2026. The engine is feature-complete."])
    sf.pdf(d3 / "documents" / "Invoice_TEST-1.pdf", ["TAX INVOICE\nDate\n01/10/2026\nOn-call support, Q. Tester"])
    sf.xlsx(d3 / "hr" / "Hiring_Tracker.xlsx", {"Requisitions": ("Hiring tracker (Keka Hire). Exported 31-Oct-2026.", [
        "Req ID", "Role", "Team", "Hiring Manager", "Opened", "Status", "Status Date", "In pipeline"], [
        ["REQ-1", "Backend Engineer", "Engineering", "T002", "2026-05-18", "On hold", "2026-08-12", 3]])})

    factory = make_session_factory(engine)
    store = PayrollStore(tmp_path / "payroll.db")
    Ingestor(factory, release_day=D1, payroll_store=store).ingest([d1])
    Ingestor(factory, release_day=D2, payroll_store=store, default_exported_on=date(2026, 10, 31)).ingest([d2])
    Ingestor(factory, release_day=D3, payroll_store=store, default_exported_on=date(2026, 10, 31)).ingest([d3])
    store.dispose()

    aliases = tmp_path / "aliases.csv"
    with aliases.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["alias_text", "kind", "status", "target_emp_id", "confidence", "evidence_note", "released_on"])
        w.writerow(["Pri", "transcript_name", "resolved", "T003", "M", "Reviewed: test", "2026-11-19"])
        w.writerow(["Seemal", "pagerduty_name", "unresolved", "", "L", "Reviewed: test, never Seema", "2026-11-18"])
    reviewed = {
        "conflicts.json": {"conflicts": [{
            "conflict_key": "C-TEST-DONE", "title": "Engine feature-complete: board versus tracker", "status": "open",
            "noted_on": "2026-11-18", "documented_in": "test", "confidence": "M", "resolution": "Tracker for status",
            "sides": [{"side": "A", "file": "Board_Update_Q3.pdf", "match": ["feature-complete"], "date": "2026-10-06",
                       "summary": "Board"},
                      {"side": "B", "file": "Jira_Export_ATLAS.xlsx", "locator": "Issues!", "match": ["ATLAS-2"],
                       "date": "2026-10-31", "summary": "ATLAS-2 not Done"}]}]},
        "org.json": {"contractors": [{"key": "CTR-T", "name": "Q. Tester", "role_as_written": "On-call support",
                                      "noted_on": "2026-11-19", "documented_in": "test",
                                      "evidence": {"file": "Invoice_TEST-1.pdf", "match": ["Q. Tester"],
                                                   "date": "2026-10-01"}}],
                     "announced_changes": [{"key": "T-MKT", "department": "Marketing", "reports_to_position": "CRO",
                                            "status": "announced", "effective_date": None, "noted_on": "2026-11-19",
                                            "documented_in": "test",
                                            "evidence": {"file": "T6b_Test_Note.docx",
                                                         "match": ["marketing will report to the new CRO"],
                                                         "date": None}}]}}
    for name, data in reviewed.items():
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")
    with factory() as s:
        load_curated(s, aliases)
        link_identities(s)
        assert not load_reviewed_conflicts(s, tmp_path / "conflicts.json").rejected
        assert not load_reviewed_org(s, tmp_path / "org.json").rejected
        s.commit()
    monkeypatch.setattr(roster_mod, "AGENT_ROSTER", TEST_ROSTER)
    return factory


def spec(name):
    return find_agent(name, TEST_ROSTER)


def facts(p, field_):
    return [f for f in p.facts if f.field == field_]


def dump(p):
    return json.dumps(to_dict(p))


# ---------------------------------------------------------------- the project roster

def test_project_roster_is_exactly_the_fourteen_in_architecture():
    from collections import Counter
    assert len(AGENT_ROSTER) == 14 and len({a.slug for a in AGENT_ROSTER}) == 14
    assert Counter(a.department for a in AGENT_ROSTER) == {"Engineering": 5, "Finance": 3, "People & Ops": 3,
                                                           "Marketing": 3}
    section8 = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8").split("## 8. The 14 agents")[1].split("## 9.")[0]
    for a in AGENT_ROSTER:
        row = next(line for line in section8.splitlines() if line.startswith(f"| {a.department} |"))
        assert a.name in row
    assert not set(NO_AGENT) & {a.name for a in AGENT_ROSTER}


# ---------------------------------------------------------------- scope

def test_fourteen_profiles_and_none_for_the_other_five(company, db, client):
    from collections import Counter
    ps = all_profiles(db, AT_D4, TEST_ROSTER)
    assert len(ps) == 14 and Counter(p.agent_group for p in ps) == {"Engineering": 5, "Finance": 3,
                                                                    "People & Ops": 3, "Marketing": 3}
    assert {p.status for p in ps} == {"active", "departed"} and all(p.identity_confidence == "H" for p in ps)
    for name in NON_AGENTS + ("Q. Tester", "Seemal"):
        assert find_agent(name, TEST_ROSTER) is None
        assert client.get(f"/api/agents/{name}").status_code == 404
    listed = client.get("/api/agents", params={"as_of": "2026-11-19T12:00"}).json()
    assert len(listed) == 14 and {r["name"] for r in listed} == {a.name for a in TEST_ROSTER}


def test_agents_link_only_by_exact_name(company, db):
    nickname = AgentSpec("Pri Noor", "Engineering")    # an alias or partial name never makes an agent
    p = agent_profile(db, nickname, AT_D4)
    assert p.status == "identity_not_established" and not p.facts and p.emp_id is None
    assert resolve_person(db, "Pri", AT_D4).person.full_name == "Priyanka Noor"  # the alias exists, unused here


# ---------------------------------------------------------------- evidence

def test_every_fact_cites_valid_eligible_evidence(company, db):
    for p in all_profiles(db, AT_D4, TEST_ROSTER):
        assert p.failed_checks == []
        for f in p.facts:
            assert f.citations and len(f.citations) == len(f.keys), (p.name, f.field)
            assert all(c.ok for c in validate(db, f.keys, AT_D4))
            assert f.confidence in ("H", "M", "L") and f.valid and f.known_from
            for c in f.citations:
                assert c.system in ELIGIBLE_SYSTEMS or f.field == "pending_changes", (p.name, c.filename)


def test_unsupported_fields_say_not_established(company, db):
    p = agent_profile(db, spec("Mona Iyer"), AT_D4)
    values = p.field_values()
    for field_ in ("responsibilities", "current_projects", "workload_indicators", "pending_changes"):
        assert values[field_] == NOT_ESTABLISHED
        assert any(m.field == field_ and m.reason for m in p.missing)
    assert values["role"] == ["Fin Head"] and values["reporting_manager"] == ["Carla Mendes"]


def test_hiring_manager_is_the_only_recorded_responsibility(company, db):
    p = agent_profile(db, spec("Victor Moss"), AT_D4)
    [f] = facts(p, "responsibilities")
    assert f.statement.startswith("Hiring manager for REQ-1 (Backend Engineer); status 'On hold' since 2026-08-12")
    assert f.citations[0].system == "Keka Hire" and f.confidence == "H"


# ---------------------------------------------------------------- confidence of name links

def test_medium_confidence_links_stay_medium_and_say_so(company, db):
    ravi = agent_profile(db, spec("Ravi Varma"), AT_D4)
    [proj] = facts(ravi, "current_projects")
    assert proj.confidence == "M" and "'RV' linked to this person by rule-based link, not reviewed at M" in proj.notes
    seema = agent_profile(db, spec("Seema Kale"), AT_D4)
    inc = next(f for f in facts(seema, "workload_indicators") if "incident" in f.statement)
    assert inc.confidence == "M" and any("'Seema'" in n and "at M" in n for n in inc.notes)


# ---------------------------------------------------------------- decision 23 and privacy

def test_decision_23_statement_never_reaches_the_profile(company, db):
    p = agent_profile(db, spec("Priyanka Noor"), AT_D4)
    text = dump(p)
    for s in SECRETS:
        assert s not in text, s
    cited = {c.filename for f in p.facts for c in f.citations}
    assert not cited & {"T5_Test_Call.docx", "git_log.csv", "09.eml", "Email_Printouts.pdf"}


def test_no_profile_holds_pay_leave_letter_or_restricted_content(company, db):
    for p in all_profiles(db, AT_D4, TEST_ROSTER):
        text = dump(p)
        for s in SECRETS:
            assert s not in text, (p.name, s)
        for g in GROSS.values():
            assert str(g) not in text and f"{g:,}" not in text


def test_injected_restricted_facts_are_dropped(company, db):
    """Negative test: even if a bug put ineligible records into a profile, the final check removes them."""
    def key(filename):
        return db.scalar(select(Evidence.evidence_key).join(SourceRecord).where(SourceRecord.filename == filename))
    b = _Builder(db, spec("Priyanka Noor"), AT_D4)
    b.build()
    before = len(b.profile.facts)
    for fname in ("Payroll_Register_Test.xlsx", "09.eml", "T5_Test_Call.docx", "git_log.csv", "Leave_Register.xlsx",
                  "Email_Printouts.pdf", "Resignation_Letter_SM.pdf"):
        b.profile.facts.append(Fact("workload_indicators", f"leak from {fname}", [key(fname)], "H", "x"))
    p = b.finish()
    assert len(p.facts) == before and len(p.failed_checks) == 7
    reasons = " ".join(p.failed_checks)
    for why in ("restricted", "purpose_limited", "role_copy", "not eligible"):
        assert why in reasons
    assert "leak from" not in dump(p)


def test_endpoints_take_no_privacy_switch(company, db, client):
    r = client.get("/api/agents/priyanka-noor", params={"as_of": "2026-11-19T12:00", "purpose": "atlas_ownership",
                                                       "include_restricted": "true"})
    assert r.status_code == 200
    for s in SECRETS:
        assert s not in r.text
    pay = db.scalar(select(Evidence.evidence_key).join(SourceRecord)
                    .where(SourceRecord.filename == "Payroll_Register_Test.xlsx"))
    assert client.get(f"/api/evidence/{pay}").status_code == 404
    found = client.get("/api/search", params={"q": "ownership", "person": "Priyanka Noor",
                                               "as_of": "2026-11-19T12:00"}).text
    assert "Can we talk" not in found and "Email_Printouts" not in found


# ---------------------------------------------------------------- time

def test_departure_is_respected_and_history_kept(company, db):
    sid = spec("Sid Mehra")
    after = agent_profile(db, sid, AT_D4)
    assert after.status == "departed" and after.field_values()["role"] == NOT_ESTABLISHED
    assert "Not applicable: left on 31 Oct 2026" in next(m.reason for m in after.missing if m.field == "role")
    assert [f.statement for f in facts(after, "historical_events")] == ["Joined on 1 Apr 2025.", "Left 31 Oct 2026."]
    on_the_day = agent_profile(db, sid, TimeContext.known_at("2026-10-31"))   # known now? No: before release
    assert on_the_day.status == "identity_not_established"
    hindsight = agent_profile(db, sid, TimeContext.recorded_by("2026-10-31", knowledge_cutoff=AT_D4.as_of))
    assert hindsight.status == "active" and hindsight.field_values()["department"] == ["Marketing"]
    earlier = agent_profile(db, sid, TimeContext.recorded_by("2026-10-15", knowledge_cutoff=AT_D4.as_of))
    assert earlier.status == "identity_not_established"  # the Keka export was not recorded by 15 Oct


def test_nothing_is_established_before_the_keka_export_was_recorded(company, db):
    """Recorded by 1 Aug, with today's knowledge: the Keka export (31 Oct) did not exist yet, so the
    profile establishes nothing rather than back-dating the snapshot."""
    p = agent_profile(db, spec("Arun Dey"), TimeContext(as_of=datetime(2026, 8, 1, 23, 59, 59),
                                                        mode=AT_D4.mode.__class__.RECORDED,
                                                        knowledge_cutoff=AT_D4.as_of))
    assert p.status == "identity_not_established"  # recorded-by 1 Aug: no Keka export yet
    known = agent_profile(db, spec("Arun Dey"), AT_D4)
    assert known.field_values()["role"] == ["Frontend"]


def test_pending_cro_change_is_shown_never_applied(company, db):
    n = spec("Nilesh Bose")
    now = agent_profile(db, n, AT_D4)
    assert now.field_values()["reporting_manager"] == ["Carla Mendes"]
    [pend] = facts(now, "pending_changes")
    assert pend.statement.startswith("Pending, not in effect: announced that Marketing will report to CRO")
    assert pend.confidence == "L" and "effective date not confirmed" in pend.statement
    future = agent_profile(db, n, TimeContext.known_at("2027-02-01"))
    assert future.field_values()["reporting_manager"] == ["Carla Mendes"] and facts(future, "pending_changes")
    assert not facts(agent_profile(db, n, AT_D3), "pending_changes")              # before it was reviewed
    recorded = TimeContext.recorded_by("2026-11-19", knowledge_cutoff=AT_D4.as_of)
    assert not facts(agent_profile(db, n, recorded), "pending_changes")         # undated source
    sid_after = agent_profile(db, spec("Sid Mehra"), AT_D4)
    assert not facts(sid_after, "pending_changes")                              # he had left


# ---------------------------------------------------------------- separation and uncertainty

def test_similar_names_and_contractors_stay_separate(company, db):
    seema = agent_profile(db, spec("Seema Kale"), AT_D4)
    inc = next(f for f in facts(seema, "workload_indicators") if "incident" in f.statement)
    rota = next(f for f in facts(seema, "workload_indicators") if "rota" in f.statement)
    assert inc.statement.startswith("Responded to 2 incident(s) (2 SEV1)")      # not Seemal's SEV2
    assert rota.statement.startswith("On the on-call rota for 3 week(s)") and "Primary 2, Secondary 1" in rota.statement
    assert resolve_person(db, "Seemal", AT_D4).status == "unresolved"
    for p in all_profiles(db, AT_D4, TEST_ROSTER):
        assert "Q. Tester" not in dump(p) and "Invoice_TEST-1" not in dump(p)


def test_conflicts_and_gaps_are_surfaced_as_uncertainty(company, db):
    p = agent_profile(db, spec("Priyanka Noor"), AT_D4)
    assert [c["conflict_key"] for c in p.conflicts] == ["C-TEST-DONE"] and p.conflicts[0]["status"] == "open"
    [proj] = facts(p, "current_projects")
    assert proj.confidence == "L" and any("open conflict C-TEST-DONE" in n for n in proj.notes)
    [dept] = facts(p, "department")
    assert any("before that it is unknown" in n for n in dept.notes)


def test_working_hours_questions_about_a_person_are_refused(company, db):
    """Decision 23 outside the profile: the answer engine must not quote the transcript remark either."""
    from app.answering.engine import ask
    for q in ("Has Pri been doing late nights?", "Does Priyanka Noor work weekends?",
              "Is Seema Kale working late?"):
        a = ask(db, q, AT_D4)
        assert (a.status, a.refusal) == ("refused", "performance_assessment"), q
        assert "late nights but" not in repr(a) and not a.evidence_chain
    ok = ask(db, "How many incidents were there in August 2026?", AT_D4)   # no person: not refused
    assert ok.status == "answered"
