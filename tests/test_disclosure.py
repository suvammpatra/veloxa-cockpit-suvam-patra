"""Disclosure rules (DECISIONS.md 28, 29; ARCHITECTURE.md 16.14): withheld sentences never leave
through search, evidence detail, citations, answers or profiles; the stored records stay unchanged.

Synthetic company (tests/test_agents.py). The test records are:
  T5 para 2  "Pri has been doing late nights but she likes it."       -> withheld (working hours)
  T5 para 3  "Seema covers the on-call rota on weekends."             -> visible (operational)
  T2 para 2  one sentence mixing team roles and a wedding             -> withheld whole
  T2 para 3  "Payroll for February was run by Kiran." + a wedding     -> first sentence visible
  T2 para 4  "Deploys are frozen on weekends during the summit."     -> visible (no person)
  Leave register row with leave type "Marriage"                       -> withheld
"""

import hashlib
import json

import pytest
from sqlalchemy import select

from app.agents.profiles import all_profiles, to_dict
from app.answering.engine import ask
from app.models import Evidence, SourceRecord
from app.retrieval.citations import validate
from app.retrieval.disclosure import MARKER, redact
from app.retrieval.search import Filters, get_evidence, search
from tests.test_agents import AT_D4, TEST_ROSTER, company  # noqa: F401  (company is a fixture)

# Fragments of the withheld sentences themselves. Single words such as "wedding" are not used,
# because the refusal text and echoes of the asker's own question may contain them.
REMARKS = ("doing late nights but", "she likes it", "out for her wedding", "away for her wedding",
           "Leave Type: Marriage", "that month was messy", "Kiran on planning")
AS_OF = {"as_of": "2026-11-19T12:00"}


def key(db, filename, locator):
    return db.scalar(select(Evidence.evidence_key).join(SourceRecord)
                     .where(SourceRecord.filename == filename, Evidence.locator == locator))


def leave_key(db):
    return db.scalar(select(Evidence.evidence_key).join(SourceRecord)
                     .where(SourceRecord.filename == "Leave_Register.xlsx").order_by(Evidence.id))


def no_remark(text):
    return not any(r.lower() in text.lower() for r in REMARKS)


def evidence_hash(db):
    h = hashlib.sha256()
    for row in db.execute(select(Evidence.evidence_key, Evidence.content, Evidence.locator, Evidence.released_on,
                                 Evidence.exported_on).order_by(Evidence.id)):
        h.update(repr(tuple(row)).encode())
    return h.hexdigest()


# ---------------------------------------------------------------- 1, 4: raw search

SEARCHES = [("late nights", None), ("Pri late", None), ("likes", None), ("doing", "Priyanka Noor"),
            ("late nights", "Priyanka Noor"), (None, "Priyanka Noor"), ("wedding", None), ("married", None),
            ("Farah", None), ("Farah Shah away", None), ("messy month", None), ("Marriage", None),
            ("payroll", "Farah Shah"), (None, "Farah Shah"), ("her wedding February", None)]


@pytest.mark.parametrize("q,person", SEARCHES)
def test_raw_search_never_returns_a_withheld_sentence(company, db, client, q, person):
    params = {k: v for k, v in (("q", q), ("person", person)) if v} | AS_OF
    try:
        r = search(db, q, AT_D4, Filters(person=person))
        assert no_remark(json.dumps([(h.content, h.snippet) for h in r.hits], default=str))
    except Exception as exc:  # a search with no words and no filter is refused, which discloses nothing
        assert "Give search words" in str(exc)
    resp = client.get("/api/search", params=params)
    assert resp.status_code in (200, 400)
    if resp.status_code == 200:   # "terms" echoes the asker's own words, so check what the system returned
        body = resp.json()
        assert no_remark(json.dumps([body["hits"], body["conflicts"], body["warnings"]]))


# ---------------------------------------------------------------- 2, 5: evidence detail

@pytest.mark.parametrize("filename,locator", [("T5_Test_Call.docx", "para 2"), ("T2_Test_Call.docx", "para 2"),
                                              ("T2_Test_Call.docx", "para 3")])
def test_evidence_detail_withholds_the_sentence(company, db, client, filename, locator):
    k = key(db, filename, locator)
    hit = get_evidence(db, k, AT_D4)
    assert hit.withheld and MARKER in hit.content and no_remark(hit.content)
    resp = client.get(f"/api/evidence/{k}", params=AS_OF)
    assert resp.status_code == 200 and no_remark(resp.text) and resp.json()["withheld"] is True
    lk = leave_key(db)
    assert client.get(f"/api/evidence/{lk}", params=AS_OF).json()["content"] == MARKER


# ---------------------------------------------------------------- 3: citation output

def test_citations_refuse_withheld_text(company, db):
    t5, t2_mixed = key(db, "T5_Test_Call.docx", "para 2"), key(db, "T2_Test_Call.docx", "para 3")
    assert validate(db, [t5], AT_D4)[0].reason == "withheld"                       # nothing disclosable
    assert validate(db, [t2_mixed], AT_D4,
                    quotes={t2_mixed: "Farah was away for her wedding"})[0].reason == "withheld"
    ok = validate(db, [t2_mixed], AT_D4, quotes={t2_mixed: "Payroll for February was run by Kiran."})[0]
    assert ok.ok                                                                     # the other sentence is fine


# ---------------------------------------------------------------- 6 and answers generally

ANSWERS = ["Has Pri been doing late nights?", "What has Pri been doing?", "Tell me about late nights",
           "Does she like the late nights?", "Why was Farah Shah away in February?", "Tell me about the wedding",
           "Was anyone married this year?", "What happened with payroll in February?", "Who was on leave?",
           "What did the T2 call say about Farah Shah?", "Is Farah Shah married?"]


@pytest.mark.parametrize("question", ANSWERS)
def test_answers_never_carry_a_withheld_sentence(company, db, client, question):
    a = ask(db, question, AT_D4)
    assert no_remark(a.short_answer) and all(no_remark(link.quote or "") for link in a.evidence_chain)
    assert no_remark(client.get("/api/ask", params={"q": question} | AS_OF).text)


def test_profiles_carry_no_withheld_sentence(company, db):
    for p in all_profiles(db, AT_D4, TEST_ROSTER):
        assert no_remark(json.dumps(to_dict(p)))


# ---------------------------------------------------------------- 7, 8: operational work stays available

def test_on_call_and_incident_questions_are_still_answered(company, db):
    for q in ("Who was on call on weekends?", "Is Seema Kale on call this weekend?",
              "Who covers the on-call rota on weekends?"):
        a = ask(db, q, AT_D4)
        assert a.refusal is None, q
    sev = ask(db, "SEV1 incidents in August 2026", AT_D4)
    assert sev.status == "answered" and sev.short_answer.startswith("2 SEV1 incidents")


def test_incident_rota_and_operational_text_stay_visible(company, db):
    rota = search(db, "Seema", AT_D4, Filters(systems=("Team wiki",)))
    assert rota.hits and not any(h.withheld for h in rota.hits)
    incidents = search(db, "Seema", AT_D4, Filters(systems=("PagerDuty",)))
    assert incidents.hits and not any(h.withheld for h in incidents.hits)
    weekend_rota = get_evidence(db, key(db, "T5_Test_Call.docx", "para 3"), AT_D4)
    assert weekend_rota.content == "Seema covers the on-call rota on weekends." and not weekend_rota.withheld
    freeze = get_evidence(db, key(db, "T2_Test_Call.docx", "para 4"), AT_D4)
    assert freeze.content == "Deploys are frozen on weekends during the summit." and not freeze.withheld


# ---------------------------------------------------------------- 9: unrelated sentences of the same record

def test_other_sentences_of_the_same_record_stay_visible(company, db):
    hit = get_evidence(db, key(db, "T2_Test_Call.docx", "para 3"), AT_D4)
    assert hit.content.startswith("Payroll for February was run by Kiran.") and MARKER in hit.content
    found = search(db, "payroll February", AT_D4)
    mixed = next(h for h in found.hits if h.citation.locator == "para 3" and "T2" in h.citation.filename)
    assert "Payroll for February" in mixed.content and no_remark(mixed.content) and no_remark(mixed.snippet or "")
    a = ask(db, "Who ran payroll in February?", AT_D4)
    assert no_remark(repr(a))


def test_a_sentence_that_cannot_be_separated_is_withheld_whole(company, db):
    hit = get_evidence(db, key(db, "T2_Test_Call.docx", "para 2"), AT_D4)
    assert hit.content == MARKER          # team roles and the wedding share one sentence


# ---------------------------------------------------------------- 10: stored records unchanged

def test_original_records_are_unchanged(company, db, client):
    before = evidence_hash(db)
    for q, person in SEARCHES:
        if q or person:
            search(db, q, AT_D4, Filters(person=person))
    for question in ANSWERS:
        ask(db, question, AT_D4)
    for f, loc in (("T5_Test_Call.docx", "para 2"), ("T2_Test_Call.docx", "para 3")):
        client.get(f"/api/evidence/{key(db, f, loc)}", params=AS_OF)
    assert evidence_hash(db) == before
    stored = db.scalar(select(Evidence.content).where(Evidence.evidence_key == key(db, "T2_Test_Call.docx", "para 3")))
    assert stored == "Payroll for February was run by Kiran. Farah was away for her wedding that month."


def test_rule_unit_cases(company, db):
    assert redact(db, "Ravi Varma works weekends.", AT_D4).reasons == ["working_hours"]
    assert redact(db, "Ravi Varma covers on-call on weekends.", AT_D4).reasons == []
    assert redact(db, "She was in hospital in March.", AT_D4).reasons == ["personal_circumstance"]
    assert redact(db, "Customer engagement rose in Q3.", AT_D4).reasons == []    # "engagement" is not a trigger
    assert redact(db, "Payroll ran late in February.", AT_D4).reasons == []
    row = "Employee: Farah Shah; Note: Approved by MI. Back on 2 Mar; Leave Type: Marriage; Days: 15"
    assert redact(db, row, AT_D4).text == MARKER   # a table row is one unit: the name goes with the cell


# ---------------------------------------------------------------- leave records, whatever the leave type (16.19)

LEAVE_ROWS = ("Employee: F. Shah", "Employee: P. Noor", "Employee: K. Sood", "Employee: A. Dey", "Employee: R. Varma",
              "Personal (half day", "Leave Type")


def leave_keys(db):
    return list(db.scalars(select(Evidence.evidence_key).join(SourceRecord)
                           .where(SourceRecord.filename == "Leave_Register.xlsx").order_by(Evidence.id)))


def no_leave_row(text):
    return not any(f in text for f in LEAVE_ROWS)


def test_every_leave_row_is_withheld_whatever_its_type(company, db, client):
    keys = leave_keys(db)
    assert len(keys) == 5
    for k in keys:
        hit = get_evidence(db, k, AT_D4)
        assert hit.content == MARKER and hit.withheld, k                    # the record is kept, its text is not shown
        body = client.get(f"/api/evidence/{k}", params=AS_OF).json()
        assert body["content"] == MARKER and body["withheld"] is True
        assert validate(db, [k], AT_D4)[0].reason == "withheld"            # no answer can cite it
    stored = db.scalar(select(Evidence.content).where(Evidence.evidence_key == keys[1]))
    assert stored.startswith("Employee: P. Noor; Leave Type: Personal (half day, PM)")   # source unchanged


@pytest.mark.parametrize("q", ["leave", "Personal", "Exam", "Relocation", "Casual", "Noor", "half day", "approved",
                               "Sood", "Leave Type"])
def test_leave_rows_never_reach_search(company, db, client, q):
    r = search(db, q, AT_D4, Filters())
    assert no_leave_row(json.dumps([(h.content, h.snippet) for h in r.hits]))
    body = client.get("/api/search", params={"q": q} | AS_OF).json()
    assert no_leave_row(json.dumps([body["hits"], body["conflicts"], body["warnings"]]))


@pytest.mark.parametrize("question", ["Who took exam leave?", "Who relocated?", "What leave did Priyanka Noor take?",
                                      "Did Pri take personal leave?", "Show the leave register",
                                      "Who was on leave in September 2026?", "Who took casual leave in July 2026?"])
def test_leave_rows_never_reach_answers(company, db, client, question):
    a = ask(db, question, AT_D4)
    assert no_leave_row(a.short_answer) and all(no_leave_row(link.quote or "") for link in a.evidence_chain)
    assert not {c.filename for link in a.evidence_chain for c in link.citations} & {"Leave_Register.xlsx"}
    assert no_leave_row(json.dumps(client.get("/api/ask", params={"q": question} | AS_OF).json()["evidence_chain"]))


def test_leave_rows_never_reach_profiles(company, db):
    for p in all_profiles(db, AT_D4, TEST_ROSTER):
        assert no_leave_row(json.dumps(to_dict(p)))


def test_other_hr_and_work_rows_stay_visible(company, db):
    keka = db.scalar(select(Evidence.evidence_key).join(SourceRecord)
                     .where(SourceRecord.filename == "Employee_Master.xlsx").order_by(Evidence.id))
    jira = db.scalar(select(Evidence.evidence_key).join(SourceRecord)
                     .where(SourceRecord.filename == "Jira_Export_ATLAS.xlsx").order_by(Evidence.id))
    for k in (keka, jira):
        assert not get_evidence(db, k, AT_D4).withheld, k
    assert redact(db, "Key: ATLAS-2; Type: Story; Status: Done", AT_D4).reasons == []
    assert redact(db, "Employee: A. Dey; Leave Type: Casual; Days: 1", AT_D4).text == MARKER
    assert redact(db, "Employee: A. Dey; Type of leave: Study; Days: 1", AT_D4).text == MARKER
