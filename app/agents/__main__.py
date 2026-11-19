"""Show agent profiles from the command line.

  python -m app.agents                      list the 14 agents
  python -m app.agents "Priya Nair" [--as-of 2026-11-19] [--mode known|recorded]
"""

from __future__ import annotations

import argparse
import sys

from app.agents.profiles import NOT_ESTABLISHED, agent_profile, all_profiles, find_agent
from app.config import get_settings
from app.database import init_db, make_engine, make_session_factory
from app.logging_config import setup_logging
from app.temporal import TimeContext


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.agents", description="Evidence-grounded agent profiles.")
    ap.add_argument("agent", nargs="?")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--mode", choices=("known", "recorded"), default="known")
    args = ap.parse_args(argv)
    setup_logging("WARNING")
    engine = make_engine(get_settings().database_url)
    init_db(engine)
    try:
        ctx = TimeContext.recorded_by(args.as_of) if args.mode == "recorded" else TimeContext.known_at(args.as_of)
    except ValueError:
        print(f"--as-of is not a date or time: {args.as_of!r}", file=sys.stderr)
        return 2
    try:
        with make_session_factory(engine)() as s:
            if not args.agent:
                for p in all_profiles(s, ctx):
                    print(f"{p.agent_group:<13} {p.name:<22} {p.emp_id or '-':<6} {p.status}")
                return 0
            spec = find_agent(args.agent)
            if spec is None:
                print("No agent by that name. There are 14 agents (ARCHITECTURE.md 8).", file=sys.stderr)
                return 2
            p = agent_profile(s, spec, ctx)
        print(f"{p.name} ({p.agent_group}) - {p.status}; {p.mode} as of {p.as_of:%Y-%m-%d %H:%M} IST")
        for field_, value in p.field_values().items():
            if value == NOT_ESTABLISHED:
                why = next((m.reason for m in p.missing if m.field == field_), "")
                print(f"  {field_}: {NOT_ESTABLISHED} ({why})")
                continue
            for f in (x for x in p.facts if x.field == field_):
                refs = ", ".join(c.label for c in f.citations[:3]) + (" ..." if len(f.citations) > 3 else "")
                print(f"  {field_}: {f.statement} [{f.confidence}; {f.valid}] {refs}")
                for n in f.notes:
                    print(f"      note: {n}")
        for c in p.conflicts:
            print(f"  conflict: {c['conflict_key']} ({c['status']}): {c['title']}")
        for fc in p.failed_checks:
            print(f"  dropped: {fc}")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
