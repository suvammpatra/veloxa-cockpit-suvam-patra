"""Phase 2: data model, identity, time, org history, privacy, contractors."""

from datetime import date, datetime

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.models import (Alias, Claim, Conflict, ConflictSide, DepartmentLine, Evidence, Person, Position,
                        ReportingLine)
from app.privacy.payroll import FLOOR, PayrollStore
from app.repositories.temporal import visible
from app.services.identity import normalize, resolve_person
from app.services.org import department_members, department_reports_to, headcount, manager_as_of
from app.temporal import Mode, TimeContext, release_timestamp, resolve_as_of
from tests.factories import DAY1, DAY2, DAY3, contractor, department, employee, evidence, source

NOW = datetime(2026, 11, 18, 12, 0)


# ---------------------------------------------------------------- relationships and integrity

def test_source_evidence_claim_conflict_chain(db):
    src = source(db)
    a = evidence(db, src, "Board says feature-complete")
    b = evidence(db, src, "Tracker shows open stories")
    db.add(Claim(evidence_id=a.id, subject_type="project", subject_key="P1", attribute="status",
                 value="feature-complete", released_on=src.released_on))
    c = Conflict(conflict_key="C-TEST", title="Status disagrees")
    c.sides = [ConflictSide(evidence_id=a.id, side="A", summary="complete"),
               ConflictSide(evidence_id=b.id, side="B", summary="open")]
    db.add(c)
    db.commit()
    assert {e.evidence_key for e in db.get(type(src), src.id).evidence} == {a.evidence_key, b.evidence_key}
    assert [s.evidence.content for s in db.scalars(select(Conflict)).one().sides][0].startswith("Board")


def test_evidence_must_point_to_a_real_source(db):
    db.add(Evidence(evidence_key="E999", source_record_id=12345, locator="x", content="orphan",
                    released_on=DAY1))
    with pytest.raises(IntegrityError):
        db.commit()


@pytest.mark.parametrize("worker_type,emp_id", [("employee", None), ("contractor", "VX999")])
def test_emp_id_must_match_worker_type(db, worker_type, emp_id):
    db.add(Person(full_name="Test", worker_type=worker_type, emp_id=emp_id, released_on=DAY1))
    with pytest.raises(IntegrityError):
        db.commit()


def test_reporting_line_needs_exactly_one_manager(db):
    d = department(db, "T1")
    a = employee(db, "Test A", "T001", dept=d)
    b = employee(db, "Test B", "T002", dept=d)
    pos = Position(code="TST", title="Test Role")
    db.add(pos)
    db.flush()
    db.add(ReportingLine(person_id=a.id, manager_person_id=b.id, manager_position_id=pos.id,
                         valid_from=DAY1, released_on=DAY1))
    with pytest.raises(IntegrityError):
        db.commit()


def test_payroll_is_not_in_the_cockpit_database(engine):
    assert not [t for t in inspect(engine).get_table_names() if "payroll" in t]


# ---------------------------------------------------------------- identity

def test_sneha_and_snehal_never_merge(db):
    d = department(db, "ENG")
    sneha = employee(db, "Sneha Kulkarni", "T012", dept=d)
    snehal = contractor(db, "Snehal")
    ctx = TimeContext.known_at(NOW)
    assert resolve_person(db, "Snehal", ctx).person.id == snehal.id
    assert resolve_person(db, "Sneha", ctx).person.id == sneha.id
    assert normalize("Sneha") != normalize("Snehal")


def test_unresolved_alias_cannot_carry_a_target(db):
    p = employee(db, "Test A", "T001")
    db.add(Alias(alias_text="X", normalized="x", kind="transcript_name", status="unresolved",
                 target_person_id=p.id, evidence_note="none", released_on=DAY1))
    with pytest.raises(IntegrityError):
        db.commit()


def test_alias_resolves_misheard_name_with_its_evidence(db):
    p = employee(db, "Test Priya", "T007")
    db.add(Alias(alias_text="Pria", normalized="pria", kind="transcript_name", target_type="person",
                 target_person_id=p.id, confidence="H", evidence_note="role matches", released_on=DAY1))
    db.commit()
    r = resolve_person(db, "  PRIA ", TimeContext.known_at(NOW))
    assert (r.status, r.person.id, r.method, r.confidence) == ("resolved", p.id, "alias", "H")


def test_ambiguous_first_name_stays_ambiguous(db):
    employee(db, "Alex One", "T101")
    employee(db, "Alex Two", "T102")
    r = resolve_person(db, "Alex", TimeContext.known_at(NOW))
    assert r.status == "ambiguous" and r.person is None and len(r.candidates) == 2


def test_unknown_name_is_unresolved_not_guessed(db):
    employee(db, "Sneha Kulkarni", "T012")
    r = resolve_person(db, "Snehaa", TimeContext.known_at(NOW))
    assert r.status == "unresolved" and r.person is None


def test_alias_released_later_is_not_used_earlier(db):
    p = employee(db, "Test Priya", "T007")
    db.add(Alias(alias_text="P. N.", normalized="p. n.", kind="git_email", target_type="person",
                 target_person_id=p.id, evidence_note="day 3 only", released_on=DAY3))
    db.commit()
    assert resolve_person(db, "P. N.", TimeContext.known_at(DAY2)).status == "unresolved"
    assert resolve_person(db, "P. N.", TimeContext.known_at(DAY3)).status == "resolved"


# ---------------------------------------------------------------- time

def test_date_only_means_end_of_day_and_release_is_ten_am():
    assert resolve_as_of("2026-11-17") == datetime(2026, 11, 17, 23, 59, 59)
    assert release_timestamp(date(2026, 11, 17)) == datetime(2026, 11, 17, 10, 0)
    assert resolve_as_of("2026-08-22T20:41:00Z") == datetime(2026, 8, 23, 2, 11)  # UTC -> IST


def test_release_boundary_0959_versus_1000(db):
    s1, s2 = source(db, released=DAY1), source(db, released=DAY2)
    evidence(db, s1, "day one")
    evidence(db, s2, "day two")
    db.commit()

    def seen(at):
        return {e.content for e in db.scalars(visible(select(Evidence), Evidence, TimeContext.known_at(at)))}

    assert seen("2026-11-17T09:59:00+05:30") == {"day one"}
    assert seen("2026-11-17T10:00:00+05:30") == {"day one", "day two"}
    assert seen("2026-11-15") == set()


def test_recorded_mode_uses_export_date_but_never_unreleased_records(db):
    s = source(db, released=DAY1)
    evidence(db, s, "recorded in July", exported=datetime(2026, 7, 8))
    evidence(db, s, "transcript, date unknown", exported=None)
    later = source(db, released=DAY3)
    evidence(db, later, "recorded in June but released on day 3", exported=datetime(2026, 6, 2))
    db.commit()
    ctx = TimeContext.recorded_by("2026-08-01", knowledge_cutoff=DAY2)
    assert ctx.mode is Mode.RECORDED
    got = {e.content for e in db.scalars(visible(select(Evidence), Evidence, ctx))}
    assert got == {"recorded in July"}


# ---------------------------------------------------------------- org history (T6b)

def _org(db):
    mkt = department(db, "MKT", "Marketing")
    ceo = employee(db, "Test CEO", "T001")
    head = employee(db, "Test Head", "T006", dept=mkt)
    cro = Position(code="CRO", title="CRO")
    ceo_pos = Position(code="CEO", title="CEO")
    db.add_all([cro, ceo_pos])
    db.flush()
    snapshot = datetime(2026, 10, 31)
    db.add(ReportingLine(person_id=head.id, manager_person_id=ceo.id, valid_from=snapshot,
                         start_exact=False, released_on=DAY1))
    db.add(ReportingLine(person_id=head.id, manager_position_id=cro.id, valid_from=None,
                         status="announced", released_on=DAY3))
    db.add(DepartmentLine(department_id=mkt.id, reports_to_position_id=ceo_pos.id, valid_from=snapshot,
                          start_exact=False, released_on=DAY1))
    db.add(DepartmentLine(department_id=mkt.id, reports_to_position_id=cro.id, valid_from=None,
                          status="announced", released_on=DAY3))
    db.commit()
    return head


def test_reporting_line_before_snapshot_is_unknown_not_assumed(db):
    head = _org(db)
    ans = manager_as_of(db, head, TimeContext.known_at(NOW))
    assert ans.status == "known" and ans.manager == "Test CEO"
    earlier = manager_as_of(db, head, TimeContext.recorded_by("2026-08-01", knowledge_cutoff=NOW))
    assert earlier.status == "unknown" and "31 Oct 2026" in earlier.note


def test_announced_cro_change_is_pending_not_applied(db):
    _org(db)
    label, pend = department_reports_to(db, "MKT", TimeContext.known_at(NOW))
    assert label == "CEO"
    assert pend == ["Announced: reports to CRO, effective date not confirmed"]
    # before the announcement was released, there is nothing pending
    assert department_reports_to(db, "MKT", TimeContext.known_at(DAY2))[1] == []


def test_confirmed_move_keeps_history_and_shows_vacant_cro(db):
    head = _org(db)
    move = datetime(2026, 12, 1)
    old = db.scalars(select(ReportingLine).where(ReportingLine.status == "confirmed")).one()
    old.valid_to = move  # closed, not overwritten
    cro = db.scalars(select(Position).where(Position.code == "CRO")).one()
    db.add(ReportingLine(person_id=head.id, manager_position_id=cro.id, valid_from=move, released_on=DAY3))
    db.commit()
    assert manager_as_of(db, head, TimeContext.known_at(datetime(2026, 11, 30))).manager == "Test CEO"
    assert manager_as_of(db, head, TimeContext.known_at(datetime(2026, 12, 2))).manager == "CRO (vacant)"


# ---------------------------------------------------------------- privacy

def _payroll(tmp_path, people: dict[str, int], month="2026-03"):
    store = PayrollStore(tmp_path / "payroll.db")
    store.add_entries([dict(emp_id=e, month=month, days_in_month=31, days_payable=31,
                            gross_paise=amt, released_on=DAY1) for e, amt in people.items()])
    return store


def test_individual_salary_is_always_refused(tmp_path):
    agg = _payroll(tmp_path, {"T1": 100}).aggregator()
    r = agg.individual("T1")
    assert not r.ok and r.refusal == "individual_pay" and r.total_paise is None


def test_group_below_floor_is_refused_and_at_floor_is_answered(tmp_path):
    people = {f"T{i}": 100 * i for i in range(1, FLOOR + 1)}
    agg = _payroll(tmp_path, people).aggregator()
    small = agg.total("small", "2026-03", lambda *_: set(list(people)[:FLOOR - 1]), released_cutoff=NOW)
    assert (small.ok, small.refusal) == (False, "below_floor")
    full = agg.total("full", "2026-03", lambda *_: set(people), released_cutoff=NOW)
    assert full.ok and full.member_count == FLOOR and full.total_paise == sum(people.values())


def test_differencing_across_dates_is_refused(tmp_path):
    """Same label, one person joins between two months: the second total is refused."""
    store = _payroll(tmp_path, {f"T{i}": 100 for i in range(1, 7)}, month="2026-01")
    store.add_entries([dict(emp_id=f"T{i}", month="2026-02", days_in_month=28, days_payable=28,
                            gross_paise=100, released_on=DAY1) for i in range(1, 8)])
    agg = store.aggregator()
    jan = agg.total("Team", "2026-01", lambda *_: {f"T{i}" for i in range(1, 7)}, released_cutoff=NOW)
    feb = agg.total("Team", "2026-02", lambda *_: {f"T{i}" for i in range(1, 8)}, released_cutoff=NOW)
    assert jan.ok and (feb.ok, feb.refusal) == (False, "differencing")


def test_unknown_membership_is_refused(tmp_path):
    agg = _payroll(tmp_path, {f"T{i}": 1 for i in range(1, 9)}).aggregator()
    r = agg.total("Team", "2026-03", lambda *_: None, released_cutoff=NOW)
    assert (r.ok, r.refusal) == (False, "membership_unknown")


def test_department_membership_unknown_before_snapshot(db):
    eng = department(db, "ENG")
    for i in range(5):
        employee(db, f"Eng {i}", f"E{i}", dept=eng)
    db.commit()
    assert len(department_members(db, "ENG", TimeContext.known_at(NOW))) == 5
    march = TimeContext.recorded_by("2026-03-31", knowledge_cutoff=NOW)
    assert department_members(db, "ENG", march) is None


def test_exception_flag_has_no_amount(tmp_path):
    store = PayrollStore(tmp_path / "p.db")
    store.add_entries([dict(emp_id="T18", month="2026-02", days_in_month=28, days_payable=28,
                            gross_paise=123456789, released_on=DAY1)])
    flags = store.aggregator().exception_flags(released_cutoff=NOW, join_dates={"T18": date(2026, 2, 3)})
    assert len(flags) == 1 and "26 days eligible" in flags[0].detail
    assert "1234567" not in flags[0].detail


# ---------------------------------------------------------------- contractors

def test_contractors_are_listed_but_not_counted(db):
    eng = department(db, "ENG")
    employee(db, "Test A", "T001", dept=eng)
    employee(db, "Test B", "T002", dept=eng, exit=date(2026, 10, 31))
    contractor(db, "Snehal")
    db.commit()
    hc = headcount(db, TimeContext.known_at(NOW))
    assert hc.employees == 1 and hc.contractors == ["Snehal"]
    assert headcount(db, TimeContext.known_at(DAY2)).contractors == []  # not yet known on day 2
