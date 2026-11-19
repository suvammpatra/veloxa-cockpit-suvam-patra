"""Read-only readiness checks for the demo database (ARCHITECTURE.md 16.20).

Used by start.ps1 (must the server start?), verify.ps1 and setup-demo-data.ps1. The database is
opened read-only (SQLite mode=ro), so a missing database is reported, never created, and nothing
is ever written. Payroll amounts are never read; only the payroll store's presence is checked.

    python -m app.readiness            # PASS / WARN / FAIL lines; exit 0 when the cockpit can start
    python -m app.readiness --strict   # also require the expected Days 1-4 counts
    python -m app.readiness --json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import PROJECT_ROOT, Settings, get_settings

# The validated Days 1-4 release pack with the three reviewed files loaded (ARCHITECTURE.md 16.17-16.19).
EXPECTED = {"sources": 38, "evidence": 1847, "persons": 20, "aliases": 21, "reporting_lines": 18, "memberships": 19,
            "conflicts": 3, "claims": 9, "reported_events": 1, "tickets": 62, "incidents": 11}

QUERIES = {
    "sources": "select count(*) from source_record",
    "evidence": "select count(*) from evidence",
    "persons": "select count(*) from person",
    "employees": "select count(*) from person where worker_type = 'employee'",
    "contractors": "select count(*) from person where worker_type = 'contractor'",
    "aliases": "select count(*) from alias",
    "reviewed_aliases": "select count(*) from alias where origin = 'curated'",
    "reporting_lines": "select count(*) from reporting_line",
    "memberships": "select count(*) from department_membership",
    "announced_changes": "select count(*) from department_line where status = 'announced'",
    "conflicts": "select count(*) from conflict",
    "reviewed_conflicts": "select count(*) from conflict where origin = 'reviewed'",
    "claims": "select count(*) from claim",
    "reported_events": "select count(*) from claim where subject_type = 'reported_event'",
    "tickets": "select count(*) from ticket",
    "incidents": "select count(*) from incident",
}


@dataclass
class Check:
    name: str
    status: str          # PASS | WARN | FAIL
    detail: str


def inspect(db_path: Path) -> dict:
    """Counts from the database, opened read-only. {'exists': False} when the file is missing."""
    if not db_path.is_file():
        return {"exists": False}
    con = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        out: dict = {"exists": True}
        try:
            out["schema_version"] = con.execute("select value from app_meta where key = 'schema_version'").fetchone()
            out["schema_version"] = out["schema_version"][0] if out["schema_version"] else None
            for key, sql in QUERIES.items():
                out[key] = con.execute(sql).fetchone()[0]
            out["evidence_dates"] = list(con.execute("select min(exported_on), max(exported_on) from evidence").fetchone())
            out["release_days"] = [r[0] for r in con.execute(
                "select distinct substr(released_on, 1, 16) from source_record order by 1")]
        except sqlite3.DatabaseError as exc:
            out["error"] = str(exc)
        return out
    finally:
        con.close()


def _is_project_database(path: Path) -> bool:
    try:
        return path.resolve().is_relative_to((PROJECT_ROOT / "data").resolve())
    except OSError:
        return False


def checks(settings: Settings | None = None, *, strict: bool = False) -> tuple[list[Check], dict]:
    s = settings or get_settings()
    db, payroll = s.database_path, s.payroll_path
    out: list[Check] = []
    fix = "Run .\\setup-demo-data.ps1 to load the release pack into the demo data folder (README, 'Demo data')."
    if _is_project_database(db):
        out.append(Check("database path", "FAIL", f"{db} is the repository's own data folder, which is never used for "
                         "demo data. Set VELOXA_DATA_DIR to an external folder: run .\\setup.ps1."))
        return out, {}
    out.append(Check("database path", "PASS", str(db)))
    info = inspect(db)
    if not info["exists"]:
        out.append(Check("database file", "FAIL", f"No database at {db}. {fix}"))
        return out, info
    if "error" in info:
        out.append(Check("database opens", "FAIL", f"{db} could not be read: {info['error']}"))
        return out, info
    out.append(Check("database opens", "PASS", f"read-only; schema version {info.get('schema_version')}"))
    if not info["sources"] or not info["evidence"]:
        out.append(Check("demo data present", "FAIL", f"The database has {info['sources']} source records and "
                         f"{info['evidence']} evidence rows: it is empty. {fix}"))
        return out, info
    first, last = info["evidence_dates"]
    out.append(Check("evidence", "PASS", f"{info['evidence']} rows from {info['sources']} sources; dated "
                     f"{str(first)[:10]} to {str(last)[:10]}; released {', '.join(d[:10] for d in info['release_days'])}"))
    people_ok = info["employees"] > 0
    out.append(Check("people", "PASS" if people_ok else "FAIL",
                     f"{info['employees']} employees, {info['contractors']} contractor(s)" if people_ok else
                     "No employee records: the Keka export was not ingested. " + fix))
    reg = {"reviewed aliases": (info["reviewed_aliases"], "data\\aliases_reviewed.csv"),
           "reviewed conflicts": (info["reviewed_conflicts"], "data\\conflicts_reviewed.json"),
           "reviewed organisation records": (info["contractors"] + info["announced_changes"] + info["reported_events"],
                                             "data\\org_reviewed.json")}
    for name, (n, file) in reg.items():
        out.append(Check(name, "PASS" if n else "FAIL", f"{n} loaded" if n else
                         f"none loaded: {file} was not loaded. {fix}"))
    out.append(Check("payroll store", "PASS" if payroll.is_file() else "FAIL",
                     "present (amounts are never read here)" if payroll.is_file() else
                     f"missing at {payroll}: payroll totals can't be answered. {fix}"))
    diffs = {k: (info.get(k), v) for k, v in EXPECTED.items() if info.get(k) != v}
    if diffs:
        out.append(Check("expected Days 1-4 counts", "FAIL" if strict else "WARN",
                         "; ".join(f"{k} {got} (expected {want})" for k, (got, want) in diffs.items())))
    else:
        out.append(Check("expected Days 1-4 counts", "PASS", ", ".join(f"{k} {v}" for k, v in EXPECTED.items())))
    return out, info


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.readiness", description="Read-only checks of the demo database.")
    p.add_argument("--strict", action="store_true", help="Also require the expected Days 1-4 counts.")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    result, info = checks(strict=args.strict)
    ok = not any(c.status == "FAIL" for c in result)
    if args.json:
        print(json.dumps({"ok": ok, "checks": [asdict(c) for c in result], "counts": info}, default=str))
    else:
        for c in result:
            print(f"{c.status:4}  {c.name}: {c.detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
