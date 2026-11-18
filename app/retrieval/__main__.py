"""Search ingested evidence from the command line.

  python -m app.retrieval "atlas release date" [--as-of 2026-11-18] [--mode known|recorded]
                          [--person NAME] [--department CODE] [--limit 10]
"""

from __future__ import annotations

import argparse
import sys

from app.config import get_settings
from app.database import init_db, make_engine, make_session_factory
from app.logging_config import setup_logging
from app.retrieval.search import Filters, SearchError, search
from app.temporal import TimeContext


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.retrieval", description="Search ingested evidence.")
    p.add_argument("query", nargs="?", default=None)
    p.add_argument("--as-of", default=None, help="Date or time; a date means the end of that day (IST).")
    p.add_argument("--mode", choices=("known", "recorded"), default="known")
    p.add_argument("--person")
    p.add_argument("--department")
    p.add_argument("--limit", type=int, default=10)
    args = p.parse_args(argv)

    setup_logging("WARNING")
    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    try:
        ctx = (TimeContext.recorded_by(args.as_of) if args.mode == "recorded" else TimeContext.known_at(args.as_of))
        with make_session_factory(engine)() as s:
            try:
                r = search(s, args.query, ctx, Filters(person=args.person, department=args.department),
                           limit=args.limit)
            except SearchError as exc:
                print(f"Search not run: {exc}", file=sys.stderr)
                return 2
        direct = [h for h in r.hits if not h.via_conflict]
        extra = len(r.hits) - len(direct)
        print(f"{r.status}: {len(direct)} of {r.total_matches} matches shown"
              + (f", plus {extra} conflict side(s)" if extra else "")
              + f"; {r.mode} as of {r.as_of:%Y-%m-%d %H:%M} IST")
        for w in r.warnings:
            print(f"  note: {w}")
        for h in r.hits:
            tag = " (other side of a conflict)" if h.via_conflict else ""
            dup = f" [same text: {', '.join(h.duplicates)}]" if h.duplicates else ""
            print(f"- {h.citation.label} rung {h.citation.trust_rung or '-'}{tag}{dup}")
            print("    " + " ".join((h.snippet or h.content).split())[:200])
        for c in r.conflicts:
            print(f"! {c.conflict_key} {c.title}: " + "; ".join(f"{side} {key}" for side, key, _ in c.sides))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
