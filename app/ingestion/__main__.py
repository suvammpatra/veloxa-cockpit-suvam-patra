"""Command line for ingestion.

  python -m app.ingestion ingest PATH [PATH ...] --release-day YYYY-MM-DD [--exported-on YYYY-MM-DD]
  python -m app.ingestion status
  python -m app.ingestion aliases FILE.csv
  python -m app.ingestion conflicts FILE.json

PATH is a file or a folder (read recursively). --release-day is required: it is
the day the pack was released to me, and every record from it is known from
10:00 IST that day (DECISIONS.md 2). --exported-on is used only for files that
carry no date of their own.

Exit codes: 0 all files ingested (some may be partial), 1 a file failed, 2 bad usage.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from app.config import get_settings
from app.database import init_db, make_engine, make_session_factory
from app.ingestion.conflict_registry import load_reviewed_conflicts
from app.ingestion.identity_links import link_identities, load_curated
from app.ingestion.pipeline import Ingestor, IngestReport
from app.logging_config import setup_logging
from app.models import Alias, Evidence, IngestionError, SourceRecord
from app.privacy.payroll import PayrollStore


def _day(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{text!r} is not a date (YYYY-MM-DD)") from exc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.ingestion", description="Ingest Veloxa source files.")
    sub = p.add_subparsers(dest="command", required=True)
    ing = sub.add_parser("ingest", help="Ingest files or folders.")
    ing.add_argument("paths", nargs="+", type=Path)
    ing.add_argument("--release-day", type=_day, required=True,
                     help="Day the pack was released (records known from 10:00 IST).")
    ing.add_argument("--exported-on", type=_day, default=None,
                     help="Export date for files that carry no date of their own.")
    sub.add_parser("status", help="List ingested sources and logged problems.")
    al = sub.add_parser("aliases", help="Load reviewed alias rows from a CSV file.")
    al.add_argument("file", type=Path)
    co = sub.add_parser("conflicts", help="Load reviewed conflicts from a JSON file (after ingesting).")
    co.add_argument("file", type=Path)
    return p


def print_report(report: IngestReport, out=sys.stdout) -> None:
    for f in report.files:
        counts = ", ".join(f"{k} {v}" for k, v in sorted(f.counts.items()))
        line = f"{f.status:<9} {f.source_key or '-':<8} {f.relative_path}"
        if f.units:
            line += f"  units {f.units}"
        if counts:
            line += f"  [{counts}]"
        if f.errors or f.warnings:
            line += f"  errors {f.errors}, warnings {f.warnings}"
        if f.message:
            line += f"  ({f.message})"
        print(line, file=out)
    totals = {s: len(report.by_status(s)) for s in ("ingested", "partial", "failed", "duplicate", "skipped")}
    print("Totals: " + ", ".join(f"{k} {v}" for k, v in totals.items()), file=out)
    if report.identities:
        print("Name links: " + ", ".join(f"{k} {v}" for k, v in report.identities.items()), file=out)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    setup_logging("WARNING")
    settings.data_path.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.database_url)
    init_db(engine)
    factory = make_session_factory(engine)
    try:
        if args.command == "ingest":
            store = PayrollStore(settings.payroll_path)
            try:
                report = Ingestor(factory, release_day=args.release_day, payroll_store=store,
                                  default_exported_on=args.exported_on).ingest(args.paths)
            finally:
                store.dispose()
            print_report(report)
            return 0 if report.ok else 1
        if args.command == "status":
            with factory() as s:
                for src in s.scalars(select(SourceRecord).order_by(SourceRecord.id)):
                    n = s.scalar(select(func.count(Evidence.id)).where(Evidence.source_record_id == src.id))
                    exported = f"{src.exported_on:%Y-%m-%d}" if src.exported_on else "unknown"
                    print(f"{src.source_key}  {src.status:<8} rung {src.trust_rung or '-'}  {src.role:<9} "
                          f"units {n:<4} released {src.released_on:%Y-%m-%d %H:%M}  exported {exported:<10}  "
                          f"{src.relative_path}")
                errs = s.scalars(select(IngestionError).order_by(IngestionError.id)).all()
                print(f"Logged problems: {sum(e.severity == 'error' for e in errs)} errors, "
                      f"{sum(e.severity == 'warning' for e in errs)} warnings")
                for e in errs:
                    print(f"  {e.severity:<7} {e.filename} {e.locator or ''}: {e.message}")
            return 0
        if args.command == "aliases":
            with factory() as s:
                try:
                    n = load_curated(s, args.file)
                except (ValueError, OSError) as exc:
                    s.rollback()
                    print(f"Alias file not loaded: {exc}", file=sys.stderr)
                    return 2
                stats = link_identities(s)
                s.commit()
                total = s.scalar(select(func.count(Alias.id)))
            print(f"Loaded {n} reviewed alias rows ({total} alias rows in total). Name links: {stats}")
            return 0
        if args.command == "conflicts":
            with factory() as s:
                try:
                    r = load_reviewed_conflicts(s, args.file)
                except (ValueError, OSError) as exc:
                    s.rollback()
                    print(f"Conflict file not loaded: {exc}", file=sys.stderr)
                    return 2
                s.commit()
            for key in r.loaded:
                print(f"loaded     {key}")
            for key in r.unchanged:
                print(f"unchanged  {key} (already stored)")
            for key, why in r.rejected.items():
                print(f"rejected   {key}")
                for w in why:
                    print(f"           {w}")
            print(f"Totals: loaded {len(r.loaded)}, unchanged {len(r.unchanged)}, rejected {len(r.rejected)}")
            return 1 if r.rejected else 0
    finally:
        engine.dispose()
    return 2


if __name__ == "__main__":
    sys.exit(main())
