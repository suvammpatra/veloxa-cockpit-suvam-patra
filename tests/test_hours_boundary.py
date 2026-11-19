"""Decision 23 boundary for remarks about a named person's working hours (ARCHITECTURE.md 16.13).

The synthetic company (tests/test_agents.py) holds a transcript line, "Pri has been doing late nights
but she likes it.", and a reviewed alias "Pri" -> Priyanka Noor from 19 Nov. Names are not Veloxa facts.

Boundary under test:
  * the answer engine never quotes or cites such a remark, however the question is phrased;
  * the raw evidence layer (search, evidence detail, citation check) still serves the record,
    because it is open evidence and no written rule restricts it there. That is pinned here so
    any change to it is deliberate.
"""

import pytest
from sqlalchemy import select

from app.answering.classify import Intent
from app.answering.engine import ask, finalize
from app.answering.handlers import hours_remark
from app.answering.model import Answer, ChainLink
from app.models import Evidence, SourceRecord
from app.retrieval.citations import validate
from app.retrieval.search import Filters, get_evidence, search
from tests.test_agents import AT_D3, AT_D4, company  # noqa: F401  (company is a fixture)

PHRASINGS = [
    "Has Pri been doing late nights?",            # direct, through the reviewed alias
    "Does Priyanka Noor stay late?",               # rephrased
    "Is Priyanka Noor working nights?",
    "How many hours does Priyanka Noor work?",
    "Priyanka Noor's working pattern?",
    "What has Pri been doing?",                   # indirect: a normal question about the person
    "What has Priyanka Noor been doing?",
    "What is Pri working on?",
    "Who has been doing late nights?",            # asks the cockpit to pick someone out by hours
    "Who works late?",
    "Tell me about late nights",                  # no person named
    "Does she like the late nights?",              # pronoun only
]


def t5_key(db):
    return db.scalar(select(Evidence.evidence_key).join(SourceRecord)
                     .where(SourceRecord.filename == "T5_Test_Call.docx", Evidence.locator == "para 2"))


@pytest.mark.parametrize("question", PHRASINGS)
@pytest.mark.parametrize("ctx", [AT_D3, AT_D4], ids=["before-alias", "after-alias"])
def test_answer_engine_never_quotes_the_remark(company, db, question, ctx):
    a = ask(db, question, ctx)
    assert t5_key(db) not in a.keys()
    assert "late nights but" not in repr(a) and "likes it" not in repr(a)


def test_working_hours_questions_are_refused_and_on_call_questions_are_not(company, db):
    for q in ("Who works late?", "Who has been doing late nights?", "Does Priyanka Noor stay late?",
              "How many hours does Priyanka Noor work?", "Priyanka Noor's working pattern?"):
        a = ask(db, q, AT_D4)
        assert (a.status, a.refusal, a.confidence_basis) == ("refused", "performance_assessment", "policy"), q
    assert ask(db, "Who was on call on weekends?", AT_D4).refusal is None
    assert ask(db, "How many incidents were there in August 2026?", AT_D4).status == "answered"


def test_fallback_does_not_reveal_that_anything_was_left_out(company, db):
    """A count of left-out records would hint at what they hold, so the answer is silent about it."""
    a = ask(db, "Tell me about late nights", AT_D4)
    assert not any("withheld" in w or "left out" in w for w in a.warnings) and "late nights but" not in repr(a)


def test_backstop_withholds_any_answer_that_cites_the_remark(company, db):
    """Negative test: a handler bug that cites the record cannot get it into an answer."""
    draft = Answer(question="t", short_answer="Pri has been doing late nights.", weakest_link="w",
                   would_change_mind="c", evidence_chain=[ChainLink("leak", [t5_key(db)])])
    a = finalize(db, draft, AT_D4, Intent("search"))
    assert a.status == "withheld" and not a.evidence_chain and "late nights" not in a.short_answer
    assert a.failed_checks == [f"{t5_key(db)}: withheld"]


def test_remark_detection_is_narrow(company, db):
    assert hours_remark(db, 'Says "Pri has been doing late nights but she likes it".', AT_D4)
    assert hours_remark(db, "Ravi Varma works weekends.", AT_D4)
    assert hours_remark(db, "Zed Unknown stays late most days.", AT_D4)      # an unlinked name still counts
    assert not hours_remark(db, "Weekend deploys are paused.", AT_D4)        # no person
    assert not hours_remark(db, "Pri leads the core engine.", AT_D4)        # a person, no working hours
    assert not hours_remark(db, "Hiring is paused while we close the round.", AT_D4)


def test_raw_evidence_layer_now_withholds_the_remark_but_keeps_the_record(company, db, client):
    """Decision 28 replaced the pinned 16.13 boundary: the record is kept, its text is not disclosed."""
    from app.retrieval.disclosure import MARKER
    key = t5_key(db)
    assert key not in [h.citation.evidence_key for h in search(db, "late nights", AT_D4).hits]
    detail = get_evidence(db, key, AT_D4)
    assert detail.content == MARKER and detail.withheld and detail.citation.locator == "para 2"
    assert validate(db, [key], AT_D4)[0].reason == "withheld"
    stored = db.scalar(select(Evidence.content).where(Evidence.evidence_key == key))
    assert stored == "Pri has been doing late nights but she likes it."  # the record itself is unchanged
    profile = client.get("/api/agents/priyanka-noor", params={"as_of": "2026-11-19T12:00"}).text
    assert key not in profile and "late nights" not in profile
