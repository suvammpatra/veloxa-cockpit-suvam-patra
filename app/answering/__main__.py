"""Ask a question from the command line.

  python -m app.answering "Who does Nikhil Bose report to?" [--as-of 2026-11-18] [--mode known|recorded]

Prints the five fields. There is no purpose or privacy switch: the question decides.
"""

from __future__ import annotations

import argparse
import sys

from app.answering.engine import ask
from app.answering.model import render_text
from app.config import get_settings
from app.database import init_db, make_engine, make_session_factory
from app.logging_config import setup_logging
from app.privacy.payroll import PayrollStore
from app.temporal import TimeContext


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.answering", description="Ask the cockpit a question.")
    p.add_argument("question")
    p.add_argument("--as-of", default=None, help="Date or time; a date means the end of that day (IST).")
    p.add_argument("--mode", choices=("known", "recorded"), default="known")
    args = p.parse_args(argv)

    setup_logging("WARNING")
    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    store = PayrollStore(settings.payroll_path) if settings.payroll_path.exists() else None
    try:
        ctx = None
        if args.as_of or args.mode == "recorded":
            try:
                ctx = (TimeContext.recorded_by(args.as_of) if args.mode == "recorded"
                       else TimeContext.known_at(args.as_of))
            except ValueError:
                print(f"--as-of is not a date or time: {args.as_of!r}", file=sys.stderr)
                return 2
        with make_session_factory(engine)() as s:
            answer = ask(s, args.question, ctx, payroll=store.aggregator() if store else None,
                         llm_enabled=False)
        print(render_text(answer))
        return 0
    finally:
        if store:
            store.dispose()
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
