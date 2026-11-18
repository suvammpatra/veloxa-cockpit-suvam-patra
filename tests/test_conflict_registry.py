"""The reviewed conflict registry. Data is synthetic (tests/test_answering.py world fixture);
the test conflicts exist only to exercise the loader, retrieval and answers."""

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.answering.engine import ask, finalize
from app.answering.classify import Intent
from app.answering.model import Answer, ChainLink
from app.ingestion.conflict_registry import load_reviewed_conflicts
from app.ingestion.pipeline import Ingestor
from app.models import Conflict, ConflictSide, Evidence, SourceRecord
from app.privacy.payroll import PayrollStore
from app.retrieval.search import search
from app.temporal import TimeContext
from tests import sourcefiles as sf
from tests.test_answering import AT_D1, AT_D3, MAIL, world  # noqa: F401  (world is a fixture)

AT_D2 = TimeContext.known_at(datetime(2026, 11, 17, 12, 0))
ROOT = Path(__file__).resolve().parent.parent

DONE = {"conflict_key": "C-TEST-DONE", "title": "Engine feature-complete: board versus tracker", "status": "open",
        "noted_on": "2026-11-18", "documented_in": "test", "confidence": "M",
        "resolution": "Tracker for ticket status, the board for what the board was told",
        "would_overturn": "A tracker history showing the stories were done in October",
        "sides": [
            {"side": "A", "file": "Board_Update_Q3.pdf", "match": ["feature-complete"], "date": "2026-10-06",
             "summary": "Board: the engine is feature-complete"},
            {"side": "B", "file": "Jira_Export_ATLAS.xlsx", "locator": "Issues!", "match": ["ATLAS-2"],
             "date": "2026-10-31", "summary": "ATLAS-2 core engine not Done"},
            {"side": "B", "file": "Jira_Export_ATLAS.xlsx", "locator": "Issues!", "match": ["ATLAS-4"],
             "date": "2026-10-31", "summary": "ATLAS-4 not Done"}]}
GA = {"conflict_key": "C-TEST-GA", "title": "GA timing: call versus email", "status": "resolved",
      "noted_on": "2026-11-18", "documented_in": "test", "confidence": "M",
      "resolution": "The dated email governs; the call is undated",
      "sides": [
          {"side": "A", "file": "T1_Test_Call.docx", "match": ["on track, maybe September"], "date": None,
           "summary": "Call: on track, maybe September"},
          {"side": "B", "file": "08.eml", "match": ["moves to 15 December"], "date": "2026-09-03",
           "summary": "Email: GA moves to 15 December"}]}
PLAN = {"conflict_key": "C-TEST-PLAN", "title": "Two plan statements", "status": "open",
        "noted_on": "2026-11-17", "documented_in": "test", "confidence": "L",
        "sides": [
            {"side": "A", "file": "04.eml", "match": ["15 Sep GA"], "date": "2026-06-02", "summary": "Plan: 15 Sep"},
            {"side": "B", "file": "Board_Update_Q2.pdf", "match": ["on track for GA"], "date": "2026-07-08",
             "summary": "Board: on track"}]}


def write(tmp_path, *conflicts, name="reviewed.json"):
    p = tmp_path / name
    p.write_text(json.dumps({"conflicts": list(conflicts)}), encoding="utf-8")
    return p


def load(db, path):
    r = load_reviewed_conflicts(db, path)
    db.commit()
    return r


def reviewed(db):
    return db.scalars(select(Conflict).where(Conflict.origin == "reviewed").order_by(Conflict.conflict_key)).all()


# ---------------------------------------------------------------- loading

def test_valid_conflicts_load_with_their_sides_dates_and_status(world, db, tmp_path):
    r = load(db, write(tmp_path, DONE, GA, PLAN))
    assert (r.loaded, r.rejected) == (["C-TEST-DONE", "C-TEST-GA", "C-TEST-PLAN"], {})
    done = reviewed(db)[0]
    assert (done.status, done.origin, done.documented_in, done.released_on) == (
        "open", "reviewed", "test", datetime(2026, 11, 18, 10, 0))
    assert done.resolution.startswith("Tracker for ticket status")  # kept as written, status stays open
    sides = sorted((s.side, s.evidence.source.filename, s.evidence.locator) for s in done.sides)
    assert sides == [("A", "Board_Update_Q3.pdf", "page 1"), ("B", "Jira_Export_ATLAS.xlsx", "Issues!row 3"),
                     ("B", "Jira_Export_ATLAS.xlsx", "Issues!row 5")]
    assert db.scalar(select(Conflict.status).where(Conflict.conflict_key == "C-TEST-GA")) == "resolved"


def test_missing_ambiguous_or_misdated_references_reject_the_whole_conflict(world, db, tmp_path):
    bad = [
        dict(DONE, conflict_key="C-NO-FILE", sides=[DONE["sides"][0], dict(DONE["sides"][1], file="Nope.xlsx")]),
        dict(DONE, conflict_key="C-NO-WORDS", sides=[DONE["sides"][0], dict(DONE["sides"][1], match=["ATLAS-99"])]),
        dict(DONE, conflict_key="C-TWO-ROWS", sides=[DONE["sides"][0], dict(DONE["sides"][1], match=["Atlas GA"],
                                                                            locator=None)]),
        dict(DONE, conflict_key="C-BAD-DATE", sides=[dict(DONE["sides"][0], date="2026-10-07"), DONE["sides"][1]]),
        dict(DONE, conflict_key="C-UNDATED", sides=[dict(GA["sides"][0], date="2026-09-01"), DONE["sides"][1]]),
        dict(DONE, conflict_key="C-PAYROLL", sides=[DONE["sides"][0], {"side": "B", "file": "Payroll_Register_Test.xlsx",
                                                                     "match": ["T001"], "date": "2026-10-31",
                                                                     "summary": "pay"}]),
    ]
    evidence_before = db.scalar(select(func.count(Evidence.id)))
    r = load(db, write(tmp_path, *bad))
    assert r.loaded == [] and sorted(r.rejected) == sorted(c["conflict_key"] for c in bad)
    assert "has not been ingested" in r.rejected["C-NO-FILE"][0]
    assert "no ingested record holds these words" in r.rejected["C-NO-WORDS"][0]
    assert "records hold these words" in r.rejected["C-TWO-ROWS"][0]
    assert "dated 2026-10-06, the file says 2026-10-07" in r.rejected["C-BAD-DATE"][0]
    assert "dated unknown, the file says 2026-09-01" in r.rejected["C-UNDATED"][0]
    assert "restricted" in r.rejected["C-PAYROLL"][0]
    assert reviewed(db) == [] and db.scalar(select(func.count(ConflictSide.id)).join(Conflict).where(
        Conflict.origin == "reviewed")) == 0
    assert db.scalar(select(func.count(Evidence.id))) == evidence_before  # nothing fabricated


def test_a_copy_cannot_be_a_conflict_side(world, db, tmp_path, engine):
    sf.pdf(tmp_path / "copy" / "Email_Printouts.pdf", ["Atlas GA moves to 15 December. Plan accordingly. Copy."])
    from app.database import make_session_factory
    Ingestor(make_session_factory(engine), release_day=date(2026, 11, 18)).ingest([tmp_path / "copy"])
    side = {"side": "B", "file": "Email_Printouts.pdf", "match": ["Copy"], "date": None, "summary": "copy"}
    r = load(db, write(tmp_path, dict(GA, sides=[GA["sides"][0], side])))
    assert "failed, copied, reference or restricted" in r.rejected["C-TEST-GA"][0]


@pytest.mark.parametrize("change,message", [
    ({"status": "settled"}, "status must be open or resolved"),
    ({"status": "resolved", "resolution": ""}, "needs its resolution text"),
    ({"conflict_key": "C-RX-0009"}, "C-RX- keys belong to ingestion"),
    ({"noted_on": "18 Nov"}, "noted_on must be a date"),
    ({"sides": [DONE["sides"][1], DONE["sides"][2]]}, "at least two sides"),
    ({"documented_in": ""}, "missing documented_in"),
])
def test_malformed_files_are_refused_before_anything_is_written(world, db, tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        load_reviewed_conflicts(db, write(tmp_path, dict(DONE, **change)))
    assert reviewed(db) == []


def test_duplicate_loading_adds_nothing_and_never_overwrites(world, db, tmp_path):
    path = write(tmp_path, DONE, GA)
    assert load(db, path).loaded == ["C-TEST-DONE", "C-TEST-GA"]
    again = load(db, path)
    assert (again.loaded, again.unchanged, again.rejected) == ([], ["C-TEST-DONE", "C-TEST-GA"], {})
    changed = load(db, write(tmp_path, dict(DONE, status="resolved"), name="changed.json"))
    assert "not overwritten" in changed.rejected["C-TEST-DONE"][0]
    assert db.scalar(select(Conflict.status).where(Conflict.conflict_key == "C-TEST-DONE")) == "open"
    assert len(reviewed(db)) == 2
    with pytest.raises(ValueError, match="appears twice"):
        load_reviewed_conflicts(db, write(tmp_path, DONE, DONE, name="twice.json"))


# ---------------------------------------------------------------- retrieval and answers

def test_search_returns_every_side_of_a_reviewed_conflict(world, db, tmp_path):
    load(db, write(tmp_path, DONE))
    r = search(db, "feature-complete", AT_D3)
    ref = next(c for c in r.conflicts if c.conflict_key == "C-TEST-DONE")
    assert [s[0] for s in ref.sides] == ["A", "B", "B"] and ref.origin == "reviewed"
    assert {h.citation.filename for h in r.hits if h.via_conflict} == {"Jira_Export_ATLAS.xlsx"}
    board_key = ref.sides[0][1]
    assert ref.quotes[board_key] == "The routing engine itself is feature-complete."


def test_feature_complete_answer_names_both_sides_and_stays_open(world, db, tmp_path):
    load(db, write(tmp_path, DONE))
    ans = ask(db, "Is the Atlas engine feature-complete?", AT_D3)
    assert "The records disagree (C-TEST-DONE, open): side A" in ans.short_answer
    assert "(Board_Update_Q3.pdf)" in ans.short_answer and "(Jira_Export_ATLAS.xlsx): 2 records" in ans.short_answer
    assert "Working position, not a resolution: Tracker for ticket status" in ans.short_answer
    chained = {c.filename for link in ans.evidence_chain for c in link.citations}
    assert {"Board_Update_Q3.pdf", "Jira_Export_ATLAS.xlsx"} <= chained
    assert ans.confidence == "Low" and "1 open conflict(s) on a supporting record" in ans.confidence_reasons
    assert db.scalar(select(Conflict.status).where(Conflict.conflict_key == "C-TEST-DONE")) == "open"


def test_disagreement_question_lists_reviewed_conflicts_with_what_would_overturn_them(world, db, tmp_path):
    load(db, write(tmp_path, DONE))
    ans = ask(db, "Do the sources disagree about feature-complete?", AT_D3)
    assert ans.kind == "disagreement" and ans.short_answer.startswith("Yes: 1 recorded disagreement(s)")
    assert ans.would_change_mind == "C-TEST-DONE: A tracker history showing the stories were done in October"
    quotes = [link.quote for link in ans.evidence_chain]
    assert "The routing engine itself is feature-complete." in quotes


def test_resolved_conflict_caps_confidence_at_medium_and_shows_its_resolution(world, db, tmp_path):
    before = ask(db, "When is Atlas GA?", AT_D3)
    assert before.confidence == "High"  # Jira and 08.eml agree
    load(db, write(tmp_path, GA))
    after = ask(db, "When is Atlas GA?", AT_D3)
    assert "The records disagree (C-TEST-GA, resolved)" in after.short_answer
    assert "Resolved: The dated email governs; the call is undated." in after.short_answer
    assert after.confidence == "Medium" and "1 resolved conflict(s) on a supporting record" in after.confidence_reasons


def test_conflicts_are_hidden_before_they_were_noted_or_before_every_side_is_known(world, db, tmp_path):
    load(db, write(tmp_path, DONE, PLAN))
    plan_keys = lambda ctx: [c.conflict_key for c in search(db, "GA", ctx, limit=50).conflicts]  # noqa: E731
    assert "C-TEST-PLAN" not in plan_keys(AT_D1)      # sides known on Day 1, conflict noted on Day 2
    assert "C-TEST-PLAN" in plan_keys(AT_D2)
    early = ask(db, "Is the Atlas engine feature-complete?", TimeContext.known_at(datetime(2026, 11, 18, 9, 59)))
    keys = lambda ans: [c.conflict_key for c in ans.conflicts]  # noqa: E731
    assert "C-TEST-DONE" not in early.short_answer and "C-TEST-DONE" not in keys(early)  # tracker not released
    late = ask(db, "Is the Atlas engine feature-complete?", AT_D3)
    assert "C-TEST-DONE" in keys(late)
    recorded = TimeContext.recorded_by("2026-10-10", knowledge_cutoff=datetime(2026, 11, 18, 12))
    assert "C-TEST-DONE" not in keys(ask(db, "Is the Atlas engine feature-complete?", recorded))  # exported 31 Oct


def test_answers_never_cite_fabricated_conflict_evidence(world, db, tmp_path):
    load(db, write(tmp_path, DONE, GA, PLAN))
    for c in reviewed(db):
        for s in c.sides:
            ref = json.loads(s.reference)
            terms = ref["match"] if isinstance(ref["match"], list) else [ref["match"]]
            assert all(t.lower() in s.evidence.content.lower() for t in terms)
    d = Answer(question="t", short_answer="x", weakest_link="w", would_change_mind="c",
               evidence_chain=[ChainLink("side", ["E9999"])])
    assert finalize(db, d, AT_D3, Intent("disagreement")).status == "withheld"


# ---------------------------------------------------------------- the project's reviewed file

def test_the_project_conflict_file_holds_only_documented_conflicts():
    data = json.loads((ROOT / "data" / "conflicts_reviewed.json").read_text(encoding="utf-8"))
    by_key = {c["conflict_key"]: c for c in data["conflicts"]}
    assert set(by_key) == {"C-ARR", "C-BURN", "C-ATLAS-DONE"}
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    for key, c in by_key.items():
        assert key in architecture and "ARCHITECTURE.md" in c["documented_in"]
        assert c["status"] == "open"  # no conflict is marked resolved without a reviewer
        assert {s["side"] for s in c["sides"]} == {"A", "B"}
    jira = [s["match"][0] for s in by_key["C-ATLAS-DONE"]["sides"] if s["side"] == "B"]
    assert jira == ["ATLAS-16", "ATLAS-19", "ATLAS-21", "ATLAS-24", "ATLAS-25"]


def test_the_project_conflict_file_loads_nothing_without_the_source_pack(db):
    r = load(db, ROOT / "data" / "conflicts_reviewed.json")
    assert r.loaded == [] and set(r.rejected) == {"C-ARR", "C-BURN", "C-ATLAS-DONE"}
    assert all("has not been ingested" in why[0] for why in r.rejected.values())
    assert db.scalar(select(func.count(Conflict.id))) == 0
