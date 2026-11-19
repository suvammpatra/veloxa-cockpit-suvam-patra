"""Read-only readiness checks behind start.ps1, verify.ps1 and setup-demo-data.ps1 (ARCHITECTURE.md 16.20)."""

import hashlib
import json

from app.config import PROJECT_ROOT, Settings, get_settings
from app.database import init_db, make_engine
from app.readiness import EXPECTED, checks, inspect, main
from tests.test_t6cd import pack  # noqa: F401  (a loaded company with all three reviewed files)
from tests.test_worries import firm  # noqa: F401  (a loaded company without reviewed aliases)


def by_name(result):
    return {c.name: c for c in result}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_missing_database_is_reported_and_never_created(tmp_path):
    s = Settings(data_dir=tmp_path / "demo")
    result, info = checks(s)
    assert info == {"exists": False} and by_name(result)["database file"].status == "FAIL"
    assert "setup-demo-data.ps1" in by_name(result)["database file"].detail
    assert not (tmp_path / "demo").exists()


def test_an_empty_database_is_not_ready_and_is_not_changed(tmp_path):
    s = Settings(data_dir=tmp_path)
    eng = make_engine(s.database_url)
    init_db(eng)
    eng.dispose()
    before = digest(s.database_path)
    result, info = checks(s)
    c = by_name(result)["demo data present"]
    assert c.status == "FAIL" and "it is empty" in c.detail and info["sources"] == 0
    assert digest(s.database_path) == before                     # opened read-only


def test_the_repository_data_folder_is_refused_without_opening_it():
    project_db = PROJECT_ROOT / "data" / "cockpit.db"
    before = project_db.stat().st_mtime_ns if project_db.exists() else None
    result, info = checks(Settings(data_dir=PROJECT_ROOT / "data"))
    assert [c.status for c in result] == ["FAIL"] and "never used for demo data" in result[0].detail and info == {}
    assert (project_db.stat().st_mtime_ns if project_db.exists() else None) == before


def test_a_loaded_database_is_ready_and_strict_mode_needs_the_days_1_to_4_counts(pack, settings):  # noqa: F811
    before = digest(settings.database_path)
    result, info = checks(settings)
    names = by_name(result)
    for name in ("database opens", "evidence", "people", "reviewed aliases", "reviewed conflicts",
                 "reviewed organisation records", "payroll store"):
        assert names[name].status == "PASS", (name, names[name].detail)
    assert names["expected Days 1-4 counts"].status == "WARN"   # a test company, not the release pack
    strict, _ = checks(settings, strict=True)
    assert by_name(strict)["expected Days 1-4 counts"].status == "FAIL"
    assert info["reported_events"] == 1 and info["evidence"] > 0
    assert digest(settings.database_path) == before


def test_missing_reviewed_files_are_named(firm, settings):  # noqa: F811
    result, _ = checks(settings)
    c = by_name(result)["reviewed aliases"]
    assert c.status == "FAIL" and "data\\aliases_reviewed.csv was not loaded" in c.detail


def test_inspect_counts_match_the_expected_keys(pack, settings):  # noqa: F811
    info = inspect(settings.database_path)
    assert set(EXPECTED) <= set(info)


def test_command_line_exit_codes_and_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VELOXA_DATA_DIR", str(tmp_path / "nowhere"))
    get_settings.cache_clear()
    assert main(["--json"]) == 1
    body = json.loads(capsys.readouterr().out)
    assert body["ok"] is False and body["counts"] == {"exists": False}
    assert not (tmp_path / "nowhere").exists()
