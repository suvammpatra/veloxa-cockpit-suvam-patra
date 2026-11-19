"""The PowerShell workflow scripts (README, 'Set up and run'; ARCHITECTURE.md 16.20).

Parsing and the refusal paths only: these tests never start a server, never ingest and never touch
a real demo or project database. Windows only; the refusal tests need the project's .venv.
"""

import hashlib
import shutil
import socket
import sqlite3
import subprocess
import sys

import pytest

from app.config import PROJECT_ROOT, Settings
from app.database import init_db, make_engine

SCRIPTS = ["setup.ps1", "setup-demo-data.ps1", "start.ps1", "verify.ps1", "scripts/common.ps1"]
POWERSHELL = shutil.which("powershell")
VENV = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
windows = pytest.mark.skipif(sys.platform != "win32" or not POWERSHELL, reason="Windows PowerShell scripts")
needs_venv = pytest.mark.skipif(not VENV.exists(), reason="run .\\setup.ps1 first to create .venv")


def run(script, *args):
    r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PROJECT_ROOT / script),
                        *args], capture_output=True, text=True, timeout=300, cwd=PROJECT_ROOT)
    return r.returncode, r.stdout + r.stderr


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("script", SCRIPTS)
def test_scripts_are_ascii(script):
    # Windows PowerShell 5.1 reads a script without a byte-order mark as ANSI, so non-ASCII text breaks it.
    assert all(b < 128 for b in (PROJECT_ROOT / script).read_bytes()), script


@windows
@pytest.mark.parametrize("script", SCRIPTS)
def test_scripts_parse(script):
    cmd = ("$e = $null; [System.Management.Automation.Language.Parser]::ParseFile("
           f"'{PROJECT_ROOT / script}', [ref]$null, [ref]$e) | Out-Null; $e.Count")
    out = subprocess.run([POWERSHELL, "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=120)
    assert out.stdout.strip() == "0", out.stdout + out.stderr


@windows
@needs_venv
def test_start_refuses_a_missing_database_and_creates_nothing(tmp_path):
    folder, port = tmp_path / "no-demo-data", free_port()
    code, out = run("start.ps1", "-DataDir", str(folder), "-Port", str(port))
    assert code == 1 and "Not starting: the demo database is not ready" in out and "setup-demo-data.ps1" in out
    assert not folder.exists()
    with socket.socket() as s:                                   # nothing was left listening
        assert s.connect_ex(("127.0.0.1", port)) != 0


@windows
@needs_venv
def test_start_refuses_an_empty_database(tmp_path):
    s = Settings(data_dir=tmp_path / "demo")
    s.data_path.mkdir()
    eng = make_engine(s.database_url)
    init_db(eng)
    eng.dispose()
    code, out = run("start.ps1", "-DataDir", str(s.data_path), "-Port", str(free_port()))
    assert code == 1 and "it is empty" in out


@windows
@pytest.mark.parametrize("script", ["start.ps1", "setup-demo-data.ps1"])
def test_the_repository_data_folder_is_refused(script):
    project_db = PROJECT_ROOT / "data" / "cockpit.db"
    before = project_db.stat().st_mtime_ns if project_db.exists() else None
    code, out = run(script, "-DataDir", str(PROJECT_ROOT / "data"))
    if not VENV.exists():
        assert code == 1 and ".venv" in out
    else:
        assert code == 1 and "is inside the repository" in out
    assert (project_db.stat().st_mtime_ns if project_db.exists() else None) == before


@windows
@needs_venv
def test_demo_data_is_never_loaded_twice(tmp_path):
    """A folder that already holds data is refused, so nothing is duplicated or overwritten."""
    pack = tmp_path / "pack"
    for day in ("Day1_Mon_16Nov", "Day2_Tue_17Nov", "Day3_Wed_18Nov", "Day4_Thu_19Nov"):
        (pack / day).mkdir(parents=True)
        (pack / day / "placeholder.txt").write_text("x")
    s = Settings(data_dir=tmp_path / "demo")
    s.data_path.mkdir()
    eng = make_engine(s.database_url)
    init_db(eng)
    eng.dispose()
    with sqlite3.connect(s.database_path) as con:      # a test database standing in for a half-loaded folder
        con.execute("insert into person (full_name, worker_type, emp_id, released_on) "
                    "values ('Test Person', 'employee', 'T1', '2026-11-16 10:00:00')")
    before = hashlib.sha256(s.database_path.read_bytes()).hexdigest()
    code, out = run("setup-demo-data.ps1", "-DataDir", str(s.data_path), "-SourcePack", str(pack))
    assert code == 1 and "already holds data" in out and "Not ingesting again" in out
    assert hashlib.sha256(s.database_path.read_bytes()).hexdigest() == before
    assert not (s.data_path / "payroll.db").exists()
