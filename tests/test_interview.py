"""Agent interviews (ARCHITECTURE.md 16.25; DECISIONS.md 24, 27, 35): a question about one employee is
answered only from that employee's validated profile, cited, with confidence; personal life, opinions
and feelings are "not established"; the usual refusals apply; the answer never speaks as the person.

Synthetic company and roster from tests/test_agents.py. Names are not Veloxa facts.
"""

import json
import re
from datetime import datetime

import pytest

from app.agents.interview import NOT_IN_RECORDS, interview
from app.agents.profiles import agent_profile, find_agent
from app.retrieval.citations import validate
from app.temporal import TimeContext
from tests.test_agents import AT_D4, SECRETS, TEST_ROSTER, company  # noqa: F401  (company is a fixture)

RECORD_QUESTIONS = ["What is their role?", "Who is their manager?", "What is their employment history?",
                    "What are they working on?", "What is their workload?", "Tell me about them"]
NEVER_CITED = {"T5_Test_Call.docx", "T2_Test_Call.docx", "git_log.csv", "09.eml", "Email_Printouts.pdf",
               "Leave_Register.xlsx", "Payroll_Register_Test.xlsx", "Resignation_Letter_SM.pdf"}
AS_OF = {"as_of": "2026-11-19T12:00"}


def files(a):
    return {c.filename for link in a.evidence_chain for c in link.citations}


def profile_keys(db, spec, ctx=AT_D4):
    return {k for f in agent_profile(db, spec, ctx).facts for k in f.keys}


@pytest.mark.parametrize("spec", TEST_ROSTER, ids=lambda s: s.slug)
def test_every_agent_answers_only_from_its_own_validated_records(company, db, spec):
    allowed = profile_keys(db, spec)
    for q in RECORD_QUESTIONS:
        a = interview(db, spec, q, AT_D4)
        assert a.status in ("answered", "no_evidence"), (spec.name, q, a.status, a.failed_checks)
        assert a.short_answer.startswith(f"From records about {spec.name}") or a.short_answer.startswith(NOT_IN_RECORDS)
        assert f"not {spec.name.split()[0]} speaking" in a.short_answer or a.status == "no_evidence"
        assert set(a.keys()) <= allowed, (spec.name, q, set(a.keys()) - allowed)       # only the profile's own facts
        assert not files(a) & NEVER_CITED
        for link in a.evidence_chain:
            assert all(c.ok for c in validate(db, link.keys, AT_D4))
        assert not [s for s in SECRETS if s in json.dumps([a.short_answer, a.warnings])]
        if a.status == "answered":
            assert a.confidence in ("High", "Medium", "Low") and a.confidence_basis == "evidence"


@pytest.mark.parametrize("spec", TEST_ROSTER, ids=lambda s: s.slug)
def test_personal_life_is_never_invented(company, db, spec):
    for q in ("Tell me about their personal life", "What does she think about Atlas?", "Is he happy here?",
              "What are their hobbies?"):
        a = interview(db, spec, q, AT_D4)
        assert (a.status, a.keys()) == ("no_evidence", []), (spec.name, q)
        assert a.short_answer.startswith(NOT_IN_RECORDS) and "does not invent them" in a.short_answer


@pytest.mark.parametrize("spec", TEST_ROSTER, ids=lambda s: s.slug)
def test_the_usual_refusals_apply_to_every_agent(company, db, spec):
    expected = {"How much do they earn?": "individual_pay", "What is their salary?": "individual_pay",
                "Do they work late?": "performance_assessment", "How productive are they?": "performance_assessment",
                "Will they leave?": "speculation", "Show me their Slack messages": "private_messages"}
    for q, reason in expected.items():
        a = interview(db, spec, q, AT_D4)
        assert (a.status, a.refusal, a.confidence_basis) == ("refused", reason, "policy"), (spec.name, q, a.refusal)
        assert not a.evidence_chain


def test_workload_comes_from_records_where_they_exist(company, db):
    seema = interview(db, find_agent("Seema Kale"), "What is her workload?", AT_D4)
    assert seema.status == "answered" and files(seema) & {"Incidents_Aug-Oct_2026.xlsx", "OnCall_Rota.xlsx"}
    mona = interview(db, find_agent("Mona Iyer"), "What is her workload?", AT_D4)
    assert mona.status == "no_evidence" and f"Workload: {NOT_IN_RECORDS}" in mona.short_answer


def test_only_high_confidence_facts_are_called_verified(company, db):
    a = interview(db, find_agent("Priyanka Noor"), "What is she working on?", AT_D4)
    assert a.status == "answered" and files(a) == {"Jira_Export_ATLAS.xlsx"}
    for link in a.evidence_chain:
        label = re.match(r"Current projects, ([a-z ]+) \(confidence ([HML])", link.statement)
        assert label and (label.group(1) == "verified") == (label.group(2) == "H"), link.statement
    role = interview(db, find_agent("Priyanka Noor"), "What is her role?", AT_D4)
    assert "Role (verified): Staff Eng." in role.short_answer


def test_the_label_names_why_a_fact_is_below_high():
    from app.agents.interview import _basis
    from app.agents.profiles import Fact
    fact = lambda conf, *notes: Fact("current_projects", "x", [], conf, "now", list(notes))  # noqa: E731
    assert _basis(fact("H")) == "verified"
    assert _basis(fact("L", "'PN' linked to this person by reviewed alias at H", "Touched by open conflict C-X: y.")) == "disputed"
    assert _basis(fact("M", "'Pri' linked to this person by reviewed alias at M")) == "inferred"
    assert _basis(fact("M", "'PN' linked to this person by reviewed alias at H")) == "lower confidence"


def test_the_working_hours_remark_never_reaches_an_interview(company, db):
    spec = find_agent("Priyanka Noor")
    for q in ("Has Pri been doing late nights?", "What has Pri been doing?", "Tell me about her late nights",
              "What is her workload?", "Tell me about her"):
        a = interview(db, spec, q, AT_D4)
        assert "late nights but" not in repr(a) and "likes it" not in repr(a) and "T5_Test_Call.docx" not in files(a)


def test_a_departed_agent_and_an_earlier_time_frame(company, db):
    sid = interview(db, find_agent("Sid Mehra"), "Tell me about him", AT_D4)
    assert sid.status == "answered" and "departed" in sid.short_answer
    before = interview(db, find_agent("Ravi Varma"), "What is his role?", TimeContext.known_at(datetime(2026, 11, 16, 9, 0)))
    assert before.status == "no_evidence" and "No HR record for Ravi Varma is known at this date" in before.short_answer


def test_departure_questions_point_to_the_unverified_report(company, db):
    a = interview(db, find_agent("Priyanka Noor"), "Has she resigned?", AT_D4)
    assert a.status == "answered" and any("not employee records" in w for w in a.warnings)


def test_unknown_topics_say_not_established(company, db):
    a = interview(db, find_agent("Victor Moss"), "What is his favourite colour?", AT_D4)
    assert a.status == "no_evidence" and a.short_answer.startswith(NOT_IN_RECORDS) and not a.keys()


def test_interview_api(company, client):
    r = client.get("/api/agents/seema-kale/ask", params={"q": "What is her workload?"} | AS_OF)
    body = r.json()
    assert r.status_code == 200 and body["kind"] == "agent_interview" and body["evidence_chain"]
    assert body["short_answer"].startswith("From records about Seema Kale")
    assert client.get("/api/agents/nobody/ask", params={"q": "role?"}).status_code == 404
    assert client.get("/api/agents/seema-kale/ask").status_code == 422
    assert client.get("/api/agents/seema-kale/ask", params={"q": "x" * 501}).status_code == 422
    refused = client.get("/api/agents/seema-kale/ask", params={"q": "What is her salary?"} | AS_OF).json()
    assert refused["refusal"] == "individual_pay" and refused["evidence_chain"] == []
