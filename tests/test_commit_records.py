"""Decision 30: Git commit records can't establish on-call status, working hours or individual activity.

Synthetic company (tests/test_agents.py). The rota covers the weeks of 3, 10 and 17 Aug 2026.
git_log.csv holds commits on 17, 18 and 20 Aug and 15 Sep 2026, some with "on-call" and "pager" in
the message, so a keyword match would find them. Names are not Veloxa facts.
"""

import hashlib

import pytest
from sqlalchemy import select

from app.answering.classify import Intent, classify, commit_records_barred
from app.answering.engine import ask, finalize
from app.answering.model import Answer, ChainLink
from app.answering.parse import find_entities
from app.models import Evidence, SourceRecord
from app.retrieval.search import Filters, get_evidence, search
from app.temporal import TimeContext
from tests.test_agents import AT_D3, AT_D4, company  # noqa: F401  (company is a fixture)
from datetime import datetime

AT_D2 = TimeContext.known_at(datetime(2026, 11, 17, 12, 0))   # before the rota and git log were released
AS_OF = {"as_of": "2026-11-19T12:00"}
COMMIT_MARKS = ("git_log", "deadbeef", "GitHub", "committed_at", "author_email")


def files(a: Answer) -> set[str]:
    return {c.filename for link in a.evidence_chain for c in link.citations}


def no_commits(a: Answer) -> bool:
    return "git_log.csv" not in files(a) and not any(m in repr(a) for m in COMMIT_MARKS)


def commit_key(db, sha: str) -> str:
    return db.scalar(select(Evidence.evidence_key).join(SourceRecord)
                     .where(SourceRecord.filename == "git_log.csv", Evidence.content.like(f"%{sha}%")))


def commit_hash(db) -> str:
    h = hashlib.sha256()
    for row in db.execute(select(Evidence.evidence_key, Evidence.content, Evidence.exported_on).join(SourceRecord)
                          .where(SourceRecord.system == "GitHub").order_by(Evidence.id)):
        h.update(repr(tuple(row)).encode())
    return h.hexdigest()


# ---------------------------------------------------------------- on-call uses the rota only

def test_on_call_week_uses_the_rota_and_never_commits(company, db, client):
    q = "Who was on call in the week of 17 Aug 2026?"
    a = ask(db, q, AT_D4)
    assert (a.kind, a.status) == ("on_call", "answered")
    assert files(a) == {"OnCall_Rota.xlsx"} and no_commits(a)
    assert a.short_answer.startswith("The on-call rota (OnCall_Rota.xlsx) lists, for the week of 17 Aug 2026: "
                                     "Primary Seema, Secondary Priyanka.")
    assert "not a record of who was actually on call" in a.short_answer and a.confidence == "Medium"
    body = client.get("/api/ask", params={"q": q} | AS_OF).text
    assert "OnCall_Rota.xlsx" in body and not any(m in body for m in COMMIT_MARKS)


def test_on_call_names_are_given_as_the_rota_writes_them(company, db):
    a = ask(db, "Was Seema Kale on call in the week of 10 Aug 2026?", AT_D4)
    assert "Primary Seemal, Secondary Seema" in a.short_answer and no_commits(a)
    assert any("not matched to people" in w for w in a.warnings)   # Seemal is never read as Seema


@pytest.mark.parametrize("question,ctx", [
    ("Who was on call in the week of 14 Sep 2026?", AT_D4),   # a commit exists that week; no rota row does
    ("Who was on call on 15 Sep 2026?", AT_D4),
    ("Who was on call in the week of 17 Aug 2026?", AT_D2),   # rota not yet released
    ("Who is on call this week?", AT_D4),                     # 19 Nov 2026: after the rota ends
])
def test_on_call_without_rota_evidence_reports_uncertainty(company, db, question, ctx):
    a = ask(db, question, ctx)
    assert a.kind == "on_call" and a.status == "uncertain" and a.confidence == "Low"
    assert a.short_answer.startswith("I can't say who was on call") and not a.evidence_chain
    assert "DECISIONS.md 30" in a.short_answer and no_commits(a)


# ---------------------------------------------------------------- alternate wording cannot bypass the rule

BYPASS = ["Who carried the pager in the week of 17 Aug 2026?", "Who was on standby on 18 Aug 2026?",
          "Who was oncall 17 Aug 2026?", "who was ON-CALL the week of 17 August 2026",
          "Which engineer handled alerts in the week of 17 Aug 2026?", "Who fixed the alert on 17 Aug 2026?",
          "Who was working on 17 Aug 2026?", "Who was active on 18 Aug 2026?", "Who pushed the hotfix?",
          "Who committed to the engine repo in August 2026?", "Which developers were busy in August 2026?",
          "Was Seema Kale online on 17 Aug 2026?", "What was Priyanka Noor doing on 18 Aug 2026?",
          "What has Pri been doing?", "When does Priyanka Noor usually push code?",
          "Did Priyanka Noor commit late at night?", "How many commits did Seema Kale make in August 2026?",
          "Tell me about Arun Dey in September 2026", "Show the hotfix commits by person",
          "What happened overnight on 17 Aug 2026?"]


@pytest.mark.parametrize("question", BYPASS)
def test_alternate_wording_never_uses_commit_records(company, db, client, question):
    a = ask(db, question, AT_D4)
    assert no_commits(a), (question, a.short_answer, files(a))
    assert a.status != "withheld", "the fallback should leave commits out, not rely on the backstop"
    body = client.get("/api/ask", params={"q": question} | AS_OF).text
    assert not any(m in body for m in COMMIT_MARKS)


def test_working_hours_questions_still_refused(company, db):
    for q in ("Did Priyanka Noor commit late at night?", "Does Seema Kale work weekends?",
              "Who works late?", "What time of day does Pri commit?"):
        a = ask(db, q, AT_D4)
        assert (a.status, a.refusal) == ("refused", "performance_assessment"), q


# ---------------------------------------------------------------- repository history stays available

def test_commit_history_question_can_use_git_records(company, db):
    a = ask(db, "What was committed to the engine repo in August 2026?", AT_D4)
    assert a.status == "uncertain" and "git_log.csv" in files(a)
    assert not a.failed_checks


def test_backstop_withholds_an_answer_that_rests_on_a_commit(company, db):
    """Negative test: a handler bug that cites a commit for an on-call question can't get it out."""
    key = commit_key(db, "deadbeef02")
    for q in ("Who was on call in the week of 17 Aug 2026?", "What was Seema Kale doing on 17 Aug 2026?",
              "Which engineers were up at night?"):
        draft = Answer(question=q, short_answer="Seema committed a pager fix.", weakest_link="w",
                       would_change_mind="c", evidence_chain=[ChainLink("leak", [key])])
        a = finalize(db, draft, AT_D4, Intent("search"))
        assert a.status == "withheld" and not a.evidence_chain, q
        assert a.failed_checks == [f"{key}: a commit record can't show on-call, hours or activity (DECISIONS.md 30)"]
    ok = finalize(db, Answer(question="What changed in the engine repo?", short_answer="A commit.", weakest_link="w",
                             would_change_mind="c", evidence_chain=[ChainLink("commit", [key])]),
                  AT_D4, Intent("search"))
    assert ok.status == "answered" and not ok.failed_checks


def test_rule_unit_cases(company, db):
    def barred(q):
        return commit_records_barred(q, find_entities(db, q, AT_D4))
    for q in ("Who was on call?", "Who committed this?", "What did Seema Kale change?", "Busiest engineers",
              "commits after midnight", "weekend commits", "commit counts per person", "Who authored the fix?"):
        assert barred(q), q
    for q in ("What was committed to the engine repo in August 2026?", "Show the commit history of planner",
              "Which repos changed in September 2026?"):
        assert not barred(q), q
    assert classify("Who was on call in the week of 17 Aug?", find_entities(db, "x", AT_D4)).kind == "on_call"


# ---------------------------------------------------------------- search and evidence detail unchanged

def test_search_and_evidence_detail_keep_git_records(company, db, client):
    before = commit_hash(db)
    hits = search(db, "pager alert", AT_D4, Filters(systems=("GitHub",))).hits
    assert [h.citation.filename for h in hits] == ["git_log.csv"]
    key = commit_key(db, "deadbeef02")
    detail = get_evidence(db, key, AT_D4)
    assert "on-call pager alert fix" in detail.content and not detail.withheld
    assert client.get(f"/api/evidence/{key}", params=AS_OF).json()["withheld"] is False
    for q in BYPASS:
        ask(db, q, AT_D4)
    assert commit_hash(db) == before     # stored commit records are not changed or deleted


# ---------------------------------------------------------------- payroll routing

def test_who_ran_payroll_goes_to_the_records_not_the_totals(company, db):
    for q in ("Who ran payroll in February?", "Who processed the February payroll?", "Who did payroll in Feb 2026?"):
        a = ask(db, q, AT_D4)
        assert a.kind == "search" and "Rs." not in a.short_answer, q
        assert "Payroll_Register" not in repr(a)          # the restricted register is never read here
    a = ask(db, "Who ran payroll?", AT_D4)   # the test transcript is undated, so ask without a month
    assert a.kind == "search" and "Payroll for February was run by Kiran." in a.short_answer
    assert "wedding" not in repr(a)          # the withheld sentence of the same record stays withheld


def test_pay_wording_still_goes_to_the_payroll_rules(company, db):
    for q in ("Who did payroll pay in February?", "How much was payroll in February?",
              "Who ran the payroll total for March 2026?", "Who was paid the most in payroll in March 2026?"):
        assert ask(db, q, AT_D4).kind == "payroll", q
    a = ask(db, "Who ran payroll for Farah Shah's salary?", AT_D4)
    assert a.kind == "payroll" and a.refusal == "individual_pay"
