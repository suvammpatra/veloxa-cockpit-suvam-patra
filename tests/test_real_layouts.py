"""Fixes from the first real source-pack run (ARCHITECTURE.md 16.9). The layouts are copied
in synthetic form; no source-pack content is used here."""

import json
from types import SimpleNamespace

from app.answering.engine import ask, related
from app.answering.handlers import kit_items, quote_from
from app.retrieval.search import ConflictRef, Filters, _side_quote, search
from tests.test_answering import AT_D3, world  # noqa: F401  (world is a fixture)
from tests.test_conflict_registry import DONE, load, write


def test_launch_kit_two_column_table_is_read():
    page = SimpleNamespace(content="Kit v1\nOwner: Pat. 1 Jul 2026.\nAsset\nStatus\nDeck (sales)\nReady\n"
                                   "Web page\nReady, unpublished\nPress note\nDraft\nLaunch date\n"
                                   "TBC with engineering (planned 22 Sep)")
    items = kit_items(page)
    assert [(i, s) for i, s, _, _ in items] == [("Deck (sales)", "Ready"), ("Web page", "Ready"),
                                                ("Press note", "Draft"), ("Launch date", "TBC")]
    assert all(q in page.content for _, _, _, q in items)  # quotes are exact substrings
    assert items[3][2] == "with engineering (planned 22 Sep)"


def test_short_words_match_whole_words_only():
    assert quote_from("Ref: GADS 0526; Vendor: Google", ["GA"]) is None
    assert quote_from("We moved GA to absorb reliability work.", ["GA"]) == "We moved GA to absorb reliability work."
    assert quote_from("Releases were delayed.", ["release"]) == "Releases were delayed."  # word forms still found


def test_side_quote_spans_a_label_and_its_value_on_separate_lines():
    ev = SimpleNamespace(content="Key numbers\nMetric\nValue\nARR (recurring)\nRs. 5.8 Cr\nCustomers\n61")
    side = SimpleNamespace(reference=json.dumps({"match": ["ARR", "5.8"]}))
    assert _side_quote(side, ev) == "ARR (recurring)\nRs. 5.8 Cr"
    one = SimpleNamespace(content="Sent 6 Oct. The engine itself is feature-complete. Hiring paused.")
    assert _side_quote(SimpleNamespace(reference=json.dumps({"match": ["feature-complete"]})), one) == \
        "The engine itself is feature-complete."


def test_conflict_relevance_to_a_question():
    def ref(title, *summaries):
        return ConflictRef("C-X", title, "open", None, None, [("A", "E1", s) for s in summaries])
    arr = ref("Annual recurring revenue: call transcripts versus board updates", "Board: Rs.5.8 Cr")
    done = ref("Atlas engine feature-complete: board update versus Jira", "ATLAS-16 not Done")
    ga = ref("GA timing: call versus email", "Email: GA moves")
    assert not related("Is the Atlas engine feature-complete?", arr)
    assert related("Is the Atlas engine feature-complete?", done)
    assert related("When is GA?", ga) and not related("What is the gap?", ga)
    assert not related("What did the board say?", arr)  # generic words do not count


def test_unrelated_conflict_on_a_cited_page_is_noted_not_asserted(world, db, tmp_path):
    rent = {"conflict_key": "C-TEST-RENT", "title": "Office rent amount", "status": "open",
            "noted_on": "2026-11-18", "documented_in": "test", "confidence": "M",
            "sides": [{"side": "A", "file": "Board_Update_Q3.pdf", "match": ["We moved Atlas GA"],
                       "date": "2026-10-06", "summary": "Board page"},
                      {"side": "B", "file": "05.eml", "match": ["Launch kit is done"], "date": "2026-07-22",
                       "summary": "Kit email"}]}
    load(db, write(tmp_path, DONE, rent))
    ans = ask(db, "Is the Atlas engine feature-complete?", AT_D3)
    assert "C-TEST-DONE" in ans.short_answer and "C-TEST-RENT" not in ans.short_answer
    assert [c.conflict_key for c in ans.conflicts] == ["C-TEST-DONE"]
    assert any("C-TEST-RENT (open): Office rent amount" in w for w in ans.warnings)  # still visible
    assert ans.confidence_reasons.count("1 open conflict(s) on a supporting record") == 1


def test_excluded_systems_are_left_out_before_the_limit(world, db):
    r = search(db, "Atlas GA", AT_D3, Filters(exclude_systems=("Jira",)), limit=5)
    assert r.hits and all(h.citation.system != "Jira" for h in r.hits)
    ga = ask(db, "When is Atlas GA?", AT_D3)
    stated = {c.filename for link in ga.evidence_chain for c in link.citations}
    assert {"Board_Update_Q2.pdf", "Board_Update_Q3.pdf"} <= stated


def test_a_printed_copy_cannot_leak_a_purpose_limited_email(world, db, engine, tmp_path, client):
    from datetime import date

    from sqlalchemy import select

    from app.database import make_session_factory
    from app.ingestion.pipeline import Ingestor
    from app.models import Evidence, SourceRecord
    from app.retrieval.search import get_evidence
    from tests import sourcefiles as sf
    sf.pdf(tmp_path / "copy" / "email" / "Email_Printouts.pdf",
           ["Email export. 09. Ownership. Can we talk about Atlas ownership sometime this week?"])
    Ingestor(make_session_factory(engine), release_day=date(2026, 11, 18),
             default_exported_on=date(2026, 10, 31)).ingest([tmp_path / "copy"])
    key = db.scalar(select(Evidence.evidence_key).join(SourceRecord)
                    .where(SourceRecord.filename == "Email_Printouts.pdf"))
    assert get_evidence(db, key, AT_D3) is None
    assert client.get(f"/api/evidence/{key}", params={"as_of": "2026-11-18"}).status_code == 404
    r = client.get("/api/search", params={"q": "ownership", "as_of": "2026-11-18"})
    assert "Can we talk about Atlas ownership" not in r.text
    assert "Email_Printouts.pdf" not in repr(ask(db, "Tell me about ownership", AT_D3))


def test_ownership_statements_must_name_the_project(world, db):
    ans = ask(db, "Who owns Atlas?", AT_D3)
    for link in ans.evidence_chain:
        if link.role == "context":
            content = next(c for c in link.citations).filename
            assert content in ("04.eml", "09.eml"), content
