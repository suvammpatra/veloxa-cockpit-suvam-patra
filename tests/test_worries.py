"""Phase 7: the CEO worry list (DECISIONS.md 11-16, 23-30; ARCHITECTURE.md 16.16).

All data is synthetic: names, dates and amounts exist only to exercise the rules and are not
Veloxa facts. The company has every worry signal and also privacy traps: payroll lines that rise
faster than any other cost, payroll amounts, a wedding remark, a marriage leave row, a remark
about someone's late nights, late-night git commits and a purpose-limited 09.eml.
"""

import json
from datetime import date, datetime

import pytest

from app.database import make_session_factory
from app.ingestion.conflict_registry import load_reviewed_conflicts
from app.ingestion.identity_links import link_identities
from app.ingestion.org_registry import load_reviewed_org
from app.ingestion.pipeline import Ingestor
from app.models import Evidence
from app.privacy.payroll import PayrollStore
from app.retrieval.citations import validate
from app.temporal import TimeContext
from app.worries import engine as worry_engine
from app.worries import rules
from app.worries.engine import evaluate, to_dict
from tests import sourcefiles as sf

D1, D3 = date(2026, 11, 16), date(2026, 11, 18)
AT_D4 = TimeContext.known_at(datetime(2026, 11, 19, 12, 0))
AT_D1 = TimeContext.known_at(datetime(2026, 11, 16, 12, 0))
BEFORE_D1 = TimeContext.known_at(datetime(2026, 11, 16, 9, 59))
NOW = datetime(2026, 11, 19, 12, 0)
MAIL = dict(sender="a@example.test", to="b@example.test")
GL_HEADER = ["Txn Date", "Voucher", "Vendor / Payee", "Ref", "Cost Centre", "Amount (Rs.)", "Narration", "Entered By"]
PAY_HEADER = ["Emp ID", "Name", "Month", "Days in Month", "Days Payable", "Gross (Rs.)", "Deductions (Rs.)",
              "Net (Rs.)", "Processed By"]
GROSS = {"T001": 91357, "T002": 82468, "T003": 73579, "T004": 64681, "T005": 55792}
SECRETS = ["wedding", "Marriage", "late nights", "git_log", "deadbeef", "Payroll_Register", "Leave_Register",
           "Salaries", "PAYROLL", "09.eml", "Can we talk", *[f"{g:,}" for g in GROSS.values()],
           *[str(g) for g in GROSS.values()]]


@pytest.fixture
def firm(engine, tmp_path):
    d1, d3 = tmp_path / "d1", tmp_path / "d3"
    staff = sf.staff_rows()
    staff[4] = ["T005", "Dev Patel", "dev@example.test", "Marketing", "Marketer", "T001", "2023-01-01", "City",
                "Notice period", "2026-10-31"]
    sf.keka(d1 / "hr" / "Employee_Master.xlsx", staff)
    months = ["2026-04-08", "2026-05-08", "2026-06-08", "2026-07-08", "2026-08-08"]
    gl = [[m, f"JV-C{i}", "Cloud Co", f"CL-{i}", "ENG-INF", a, "Cloud, previous month", "XX"]
          for i, (m, a) in enumerate(zip(months, (1000, 1100, 1250, 1400, 1600)))]
    pay_days = ["2026-04-28", "2026-05-28", "2026-06-28", "2026-07-28", "2026-08-28"]
    gl += [[m, f"PAY-{i}", "Salaries (payroll)", f"PR-{i}", "PAYROLL", a, "Salaries", "XX"]   # rises 100%
           for i, (m, a) in enumerate(zip(pay_days, (5000, 6000, 7000, 8500, 10000)))]
    gl += [["2026-06-30", "JV-H1", "Hire Partners", "HP-1", "PPL-HIR", 1770, "Search fee, 2 backend roles", "XX"],
           ["2026-05-31", "RENT-1", "Rent Co", "R-1", "G&A", 2500, "Office rent", "XX"],
           ["2026-06-30", "RENT-2", "Rent Co", "R-2", "G&A", 2500, "Office rent", "XX"]]
    sf.xlsx(d1 / "finance" / "GL_Export_Test.xlsx", {"GL": ("General ledger export.", GL_HEADER, gl)})
    sf.xlsx(d1 / "finance" / "Payroll_Register_Test.xlsx", {"Payroll": ("Payroll register.", PAY_HEADER, [
        [e, f"Payname {e}", "Mar-2026", 31, 31, g, 100, g - 100, "XX"] for e, g in GROSS.items()])})
    sf.xlsx(d1 / "hr" / "Leave_Register.xlsx", {"Leave": ("Leave register.", [
        "Employee", "Leave Type", "From", "To", "Days", "Approved By"], [["R. Shah", "Marriage", "2026-02-09",
                                                                          "2026-02-27", 15, "LO"]])})
    sf.eml(d1 / "email" / "04.eml", subject="Atlas plan", date="Tue, 2 Jun 2026 10:00:00 +0530",
           body="Atlas plan: 15 Sep GA is achievable if the two backend hires land by July.", **MAIL)
    sf.eml(d1 / "email" / "06.eml", subject="Pausing reqs", date="Wed, 12 Aug 2026 10:12:00 +0530",
           body="Pausing REQ-1 until the round closes. Burn is the priority this quarter.", **MAIL)
    sf.eml(d1 / "email" / "09.eml", subject="time", date="Tue, 1 Sep 2026 23:47:00 +0530",
           body="Can we talk about Atlas ownership and routing-api sometime this week?", **MAIL)
    sf.docx(d1 / "transcripts" / "T2_Test_Call.docx", ["T2 call", "Rina Shah was away for her wedding in February.",
                                                       "Cloud costs are fine, says finance."])

    sf.xlsx(d3 / "Jira_Export_ATLAS.xlsx", {
        "Issues": ("Jira export, project ATLAS. Exported 31-Oct-2026.",
                   ["Key", "Type", "Summary", "Epic Link", "Assignee", "Story Points", "Status", "Created",
                    "Resolved", "Fix Version"],
                   [["ATLAS-2", "Story", "Core engine 1", None, "RS", 8, "In Progress", "2026-05-06", None, "Atlas GA"],
                    ["ATLAS-3", "Story", "Core engine 2", None, "RS", 5, "To Do", "2026-05-06", None, "Atlas GA"],
                    ["ATLAS-4", "Story", "Engine UI", None, "MK", 2, "To Do", "2026-05-06", None, "Atlas GA"],
                    ["ATLAS-5", "Story", "Hardening", None, "MO", 3, "To Do", "2026-05-06", None, "Atlas GA"],
                    ["ATLAS-6", "Story", "Engine API", None, "MK", 5, "Done", "2026-05-06", "2026-07-01", "Atlas GA"]]),
        "Versions": (None, ["Version", "Release Date", "Original Release Date", "Last Changed", "Changed By"],
                     [["Atlas GA", "2026-12-15", "2026-09-15", "2026-09-02", "lena"]])})
    sf.xlsx(d3 / "Incidents_Aug-Oct_2026.xlsx", {"Incidents": ("Incident export.", [
        "ID", "Severity", "Opened", "Resolved", "Service", "Responder"], [
        ["INC-1", "SEV1", "2026-08-04T05:00:00Z", "2026-08-04T07:00:00Z", "routing-api", "Rina"],
        ["INC-2", "SEV1", "2026-08-14T05:00:00Z", "2026-08-14T06:00:00Z", "routing-api", "Rina"],
        ["INC-3", "SEV1", "2026-08-23T05:00:00Z", "2026-08-23T06:00:00Z", "routing-api", "Rinal"],
        ["INC-4", "SEV2", "2026-09-05T05:00:00Z", "2026-09-05T06:00:00Z", "routing-api", "Rinal"],
        ["INC-5", "SEV3", "2026-10-09T05:00:00Z", "2026-10-09T06:00:00Z", "web", "Mira"],
        ["INC-6", "SEV2", "2026-10-22T05:00:00Z", "2026-10-22T06:00:00Z", "routing-api", "Rina"]])})
    sf.xlsx(d3 / "hr" / "Hiring_Tracker.xlsx", {"Requisitions": ("Hiring tracker (Keka Hire). Exported 31-Oct-2026.", [
        "Req ID", "Role", "Team", "Hiring Manager", "Opened", "Status", "Status Date", "In pipeline"], [
        ["REQ-1", "Backend Engineer", "Engineering", "T001", "2026-05-18", "On hold", "2026-08-12", 3],
        ["REQ-2", "Designer", "Marketing", "T001", "2026-09-17", "Open", "2026-09-17", 4]])})
    sf.pdf(d3 / "documents" / "Atlas_Launch_Kit_v1.pdf", [
        "Atlas launch kit v1. Owner: Dev Patel. Dated 21 Jul 2026.\nDeck: Ready\nWebsite page: Ready\n"
        "Press note: Draft\nLaunch date: TBC with engineering (planned 22 Sep)"])
    sf.pdf(d3 / "documents" / "Board_Update_Q3.pdf", ["Board update. Sent 6 Oct 2026. The engine is feature-complete."])
    sf.pdf(d3 / "documents" / "Invoice_TEST-1.pdf", ["TAX INVOICE\nDate\n01/10/2026\nOn-call support, Q. Tester"])
    sf.eml(d3 / "email" / "08.eml", subject="August", date="Mon, 24 Aug 2026 09:05:00 +0530",
           body="Third SEV1 this month. Pausing perf work to stabilise routing-api.", **MAIL)
    sf.docx(d3 / "transcripts" / "T5_Test_Call.docx", ["T5 call", "Rina has been doing late nights on routing-api."])
    sf.docx(d3 / "transcripts" / "T6b_Test_Note.docx", ["T6b", "So, marketing will report to the new CRO soon."])
    sf.xlsx(d3 / "OnCall_Rota.xlsx", {"On-call": ("Team wiki table, copied.", ["Week of", "Primary", "Secondary"], [
        ["2026-08-03", "Rina", "Mira"], ["2026-08-17", "Rinal", "Rina"]])})
    sf.csv_file(d3 / "git_log.csv", ["sha", "author email", "committed at", "repo", "message", "files changed"], [
        ["deadbeef01", "rina.s@example.test", "2026-08-23T20:30:00+00:00", "routing-api", "hotfix SEV1", 2],
        ["deadbeef02", "rina.s@example.test", "2026-08-24T21:30:00+00:00", "routing-api", "late night fix", 1]])

    factory = make_session_factory(engine)
    store = PayrollStore(tmp_path / "payroll.db")
    Ingestor(factory, release_day=D1, payroll_store=store).ingest([d1])
    Ingestor(factory, release_day=D3, payroll_store=store, default_exported_on=date(2026, 10, 31)).ingest([d3])
    store.dispose()
    reviewed = {
        "conflicts.json": {"conflicts": [{
            "conflict_key": "C-T-DONE", "title": "Engine feature-complete: board versus Jira", "status": "open",
            "noted_on": "2026-11-18", "documented_in": "test", "confidence": "M", "resolution": "Jira for status",
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
        link_identities(s)
        assert not load_reviewed_conflicts(s, tmp_path / "conflicts.json").rejected
        assert not load_reviewed_org(s, tmp_path / "org.json").rejected
        s.commit()
    return factory


def run(db, ctx=AT_D4):
    return evaluate(db, ctx, now=NOW)


def by_key(wl):
    return {w.key: w for w in wl.worries + wl.more}


def cited(w):
    return [c for e in w.evidence for c in e.citations]


# ---------------------------------------------------------------- candidates, ranking, the cap

def test_candidates_and_deterministic_ranking(firm, db):
    wl = run(db)
    assert [w.key for w in wl.worries] == ["service_reliability", "delivery_schedule", "capacity"]
    assert [w.key for w in wl.more] == ["cost_trend", "launch_alignment"]       # 13 each: strength breaks the tie
    assert [w.score for w in wl.worries + wl.more] == [16, 15, 14, 13, 13]
    assert [w.rank for w in wl.worries + wl.more] == [1, 2, 3, 4, 5]
    assert {x["key"] for x in wl.excluded} == {"contractor_continuity", "org_change", "reported_metrics"}
    for w in wl.worries + wl.more:     # the score is the documented formula, nothing else
        p = w.score_parts
        assert w.score == 3 * p["impact"]["value"] + 2 * p["strength"]["value"] + p["recency"]["value"] \
            + p["persistence"]["value"]
    scores = [(w.score, w.score_parts["impact"]["value"], w.score_parts["strength"]["value"]) for w in wl.worries + wl.more]
    assert scores == sorted(scores, key=lambda s: (-s[0], -s[1], -s[2]))


def test_each_rule_says_what_it_found(firm, db):
    w = by_key(run(db))
    assert w["service_reliability"].explanation.startswith("3 SEV1 incidents hit routing-api between 4 Aug 2026 and "
                                                           "23 Aug 2026.")
    assert "2 lower-severity incident(s)" in w["service_reliability"].explanation
    assert "moved from 15 Sep 2026 to 15 Dec 2026" in w["delivery_schedule"].explanation
    assert "18 of 23 story points (78%) were not Done" in w["delivery_schedule"].explanation
    assert "Cloud Co charges in the GL rose in each of the last 4 monthly entries" in w["cost_trend"].explanation
    assert "1 Engineering requisition(s) (Backend Engineer) have been on hold since 12 Aug 2026" in \
        w["capacity"].explanation
    assert "one assignee holds 13 of the 18 open ATLAS story points (72%)" in w["capacity"].explanation
    assert "planned the launch for 22 Sep 2026, but Jira's Atlas GA date is 15 Dec 2026" in \
        w["launch_alignment"].explanation
    assert "The kit's listed owner left on 31 Oct 2026" in w["launch_alignment"].explanation


def test_never_more_than_three_shown(firm, db, monkeypatch):
    extra = [lambda s, c, k=k: rules.Candidate(k, "x", k, "x.", "x", "routing-api SEV1", [
        rules.ChainLink("x", [rules._keys([s.query(Evidence).filter(Evidence.evidence_key.like("E%")).first()])[0]])],
        3, "x", 2, "x", "x", "x") for k in ("zz1", "zz2", "zz3")]
    monkeypatch.setattr(worry_engine, "RULES", rules.RULES + tuple(extra))
    wl = run(db)
    assert len(wl.worries) == 3 and len(wl.worries + wl.more) >= 4


def test_fewer_than_three_when_evidence_is_thin(firm, db):
    wl = run(db, AT_D1)                     # Day 1 only: the ledger, no Jira, incidents, tracker or kit
    assert [w.key for w in wl.worries] == ["cost_trend"] and not wl.more
    assert wl.message.startswith("Only 1 worry is well supported")
    reasons = {x["key"]: x["reason"] for x in wl.excluded}
    assert reasons["delivery_schedule"] == "No release date is known at this date."
    assert reasons["service_reliability"] == "No incident records are known at this date."
    assert reasons["launch_alignment"] == "No launch kit is known at this date."
    assert reasons["contractor_continuity"] == "No contractor record is known at this date."


def test_empty_state_before_any_records(firm, db):
    wl = run(db, BEFORE_D1)
    assert not wl.worries and not wl.more and wl.data_as_of is None
    assert wl.message.startswith("No worry is well supported")


def test_no_risk_is_raised_from_missing_evidence(firm, db):
    reasons = {x["key"]: x["reason"] for x in run(db).excluded}
    assert "a risk is not raised from missing evidence" in reasons["contractor_continuity"]   # a contractor exists


# ---------------------------------------------------------------- evidence, conflicts, time

def test_every_citation_is_valid_at_the_time_frame(firm, db):
    for ctx in (AT_D4, AT_D1, TimeContext.recorded_by("2026-08-20", knowledge_cutoff=AT_D4.as_of)):
        for w in run(db, ctx).worries:
            assert w.evidence and any(e.role == "support" for e in w.evidence)
            for e in w.evidence:
                checks = validate(db, [c["evidence_key"] for c in e.citations], ctx,
                                  quotes={e.citations[0]["evidence_key"]: e.quote} if e.quote else None)
                assert all(c.ok for c in checks), (w.key, e.statement, [c.reason for c in checks])
                for c in e.citations:
                    assert c["known_since"] <= ctx.release_cutoff
                    if ctx.mode.value == "recorded":
                        assert c["evidence_date"] and c["evidence_date"] <= ctx.as_of


def test_point_in_time_recorded_mode(firm, db):
    ctx = TimeContext.recorded_by("2026-08-20", knowledge_cutoff=AT_D4.as_of)
    w = by_key(run(db, ctx))
    assert w["service_reliability"].explanation.startswith("2 SEV1 incidents hit routing-api")   # not the 23 Aug one
    assert "delivery_schedule" not in w          # the GA change of 2 Sep was not yet recorded
    assert "launch_alignment" not in w


def test_open_conflict_is_shown_and_lowers_confidence(firm, db):
    w = by_key(run(db))["delivery_schedule"]
    assert [c["conflict_key"] for c in w.conflicts] == ["C-T-DONE"] and w.conflicts[0]["status"] == "open"
    assert w.confidence == "Low" and w.score_parts["strength"]["value"] == 1
    assert "The records disagree (C-T-DONE, open)" in w.explanation          # visible, never resolved silently
    assert any("open conflict" in r for r in w.confidence_reasons)


def test_announced_change_is_a_note_not_a_fact(firm, db):
    wl = run(db)
    launch = by_key(wl)["launch_alignment"]
    assert any("announced, not in effect" in u for u in launch.uncertainty)
    reasons = {x["key"]: x["reason"] for x in wl.excluded}
    assert "not treated as made" in reasons["org_change"]
    before = by_key(run(db, TimeContext.known_at(datetime(2026, 11, 18, 12, 0))))["launch_alignment"]
    assert not any("announced" in u for u in before.uncertainty)            # reviewed on 19 Nov, not before


# ---------------------------------------------------------------- privacy (decisions 3, 11, 23-30)

def test_no_private_detail_in_the_list(firm, db, client):
    for ctx in (AT_D4, AT_D1):
        text = json.dumps(to_dict(run(db, ctx)))
        assert not [s for s in SECRETS if s in text], [s for s in SECRETS if s in text]
    body = client.get("/api/worries", params={"as_of": "2026-11-19T12:00"}).text
    assert not [s for s in SECRETS if s in body]


def test_no_employee_is_named_in_a_worry(firm, db):
    names = ["Lena", "Mira", "Mohan", "Rina", "Dev Patel", "Q. Tester", "RS", "MK"]
    for w in run(db).worries + run(db).more:
        words = " ".join([w.title, w.explanation, w.why_it_matters, *w.uncertainty])
        assert not [n for n in names if f" {n} " in f" {words} " or f"{n}," in words], (w.key, words)


def test_no_git_records_and_backstop(firm, db, monkeypatch):
    for w in run(db).worries + run(db).more:
        assert not [c for c in cited(w) if c["system"] == "GitHub" or c["filename"] == "git_log.csv"]
    git_key = db.query(Evidence).filter(Evidence.content.like("%deadbeef01%")).one().evidence_key

    def git_activity(s, c):   # a buggy rule that tries to infer activity from commits
        return rules.Candidate("git_activity", "x", "Late fixes on routing-api", "Who worked late on routing-api.", "x",
                               "who worked late at night on routing-api", [rules.ChainLink("commits", [git_key])],
                               3, "x", 2, "x", "x", "x")
    def repo_history(s, c):   # neutral wording that the decision 30 question rule would allow
        return rules.Candidate("repo_history", "x", "routing-api changes", "routing-api had hotfixes.", "x",
                               "routing-api repository changes", [rules.ChainLink("commits", [git_key])],
                               2, "x", 1, "x", "x", "x")
    monkeypatch.setattr(worry_engine, "RULES", (git_activity, repo_history))
    wl = run(db)
    assert not wl.worries and len(wl.excluded) == 2
    assert all("DECISIONS.md 30" in x["reason"] for x in wl.excluded)
    assert wl.excluded[1]["reason"].startswith("Cites Git commit records")


def test_withheld_text_can_not_support_a_worry(firm, db, monkeypatch):
    t2 = db.query(Evidence).filter(Evidence.content.like("%her wedding%")).one().evidence_key

    def personal(s, c):
        return rules.Candidate("personal", "x", "Absence", "Someone was away.", "x", "absence",
                               [rules.ChainLink("absence", [t2], "Rina Shah was away for her wedding in February.")],
                               2, "x", 1, "x", "x", "x")
    monkeypatch.setattr(worry_engine, "RULES", (personal,))
    wl = run(db)
    assert not wl.worries and "withheld" in wl.excluded[0]["reason"] and "wedding" not in json.dumps(to_dict(wl))


def test_payroll_lines_are_never_a_cost_trend(firm, db):
    w = by_key(run(db))["cost_trend"]          # payroll rose 100%, cloud 60%: only cloud may be raised
    assert w.title == "Cloud Co costs rising month on month"
    assert all(c["filename"] == "GL_Export_Test.xlsx" or c["system"] == "Email" for c in cited(w))


# ---------------------------------------------------------------- support, duplicates, stability

def test_transcript_only_support_is_not_shown(firm, db, monkeypatch):
    t6 = db.query(Evidence).filter(Evidence.content.like("%new CRO%")).one().evidence_key

    def heard(s, c):
        return rules.Candidate("heard", "x", "Heard on a call", "A call said so.", "x", "marketing CRO",
                               [rules.ChainLink("call", [t6])], 3, "x", 2, "x", "x", "x")
    monkeypatch.setattr(worry_engine, "RULES", (heard,))
    wl = run(db)
    assert not wl.worries and wl.excluded[0]["reason"].startswith("Not well supported")


def test_duplicate_support_is_merged(firm, db, monkeypatch):
    def copy_of_reliability(s, c):
        r = rules.service_reliability(s, c)
        r.key, r.impact = "zz_copy", 1
        return r
    monkeypatch.setattr(worry_engine, "RULES", (rules.service_reliability, copy_of_reliability))
    wl = run(db)
    assert [w.key for w in wl.worries] == ["service_reliability"] and wl.worries[0].related == ["zz_copy"]
    assert wl.excluded[0]["reason"].startswith("Duplicate of")


def test_same_records_give_the_same_list(firm, db, client):
    a, b = to_dict(evaluate(db, AT_D4, now=NOW)), to_dict(evaluate(db, AT_D4, now=datetime(2026, 11, 20, 8, 0)))
    a.pop("evaluated_at"), b.pop("evaluated_at")
    assert a == b
    api = client.get("/api/worries", params={"as_of": "2026-11-19T12:00"}).json()
    api.pop("evaluated_at")
    assert api == a


def test_page_and_api_errors(firm, client):
    page = client.get("/")
    assert page.status_code == 200 and "What to worry about" in page.text and "Ask a question" in page.text
    assert "Agents" in page.text and "/api/agents" in page.text                # the agent picker (ARCHITECTURE.md 9)
    assert "innerHTML" not in page.text                                    # record text is never parsed as HTML
    assert client.get("/api/worries", params={"as_of": "not a date"}).status_code == 400
    assert client.get("/api/worries", params={"mode": "other"}).status_code == 422


# ---------------------------------------------------------------- cost trend: comparable periods (Phase 8 review)

def _ledger(engine, tmp_path, rows):
    sf.xlsx(tmp_path / "d1" / "finance" / "GL_Export_Test.xlsx", {"GL": ("General ledger export.", GL_HEADER, rows)})
    Ingestor(make_session_factory(engine), release_day=D1).ingest([tmp_path / "d1"])


def _line(day, amount, ref, narration="Cloud, previous month"):
    return [day, f"JV-{ref}", "Cloud Co", ref, "ENG-INF", amount, narration, "XX"]


def test_a_missing_month_breaks_the_run(engine, tmp_path, db):
    _ledger(engine, tmp_path, [_line("2026-04-08", 1000, "A1"), _line("2026-05-08", 1100, "A2"),
                               _line("2026-07-08", 1300, "A4"), _line("2026-08-08", 1400, "A5"),
                               _line("2026-09-08", 1600, "A6")])          # no June line
    wl = run(db)
    assert not wl.worries and {x["key"]: x for x in wl.excluded}["cost_trend"]["reason"].startswith(
        "No recurring ledger line rose")


def test_credits_are_netted_by_month_and_disclosed(engine, tmp_path, db):
    _ledger(engine, tmp_path, [_line("2026-04-08", 1000, "B1"), _line("2026-05-08", 1100, "B2"),
                               _line("2026-06-08", 1300, "B3"), _line("2026-06-20", -100, "B3C", "Credit note"),
                               _line("2026-07-08", 1400, "B4"), _line("2026-08-08", 1600, "B5")])
    w = run(db).worries[0]
    assert w.key == "cost_trend"
    assert "from Rs.1,000 (posted 8 Apr 2026) to Rs.1,600 (posted 8 Aug 2026), up 60%" in w.explanation
    assert "1 credit or reversal line(s) for this vendor and cost centre are netted within their month." in w.uncertainty
    assert "1 month(s) hold more than one line; each month's lines are summed." in w.uncertainty
    assert any("narrations differ" in u for u in w.uncertainty)
    assert len([c for c in cited(w) if c["filename"] == "GL_Export_Test.xlsx"]) == 6   # every line, the credit too
