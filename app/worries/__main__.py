"""Print the worry list: python -m app.worries [--as-of 2026-11-19T12:00] [--mode known|recorded] [--json]"""

from __future__ import annotations

import argparse
import json

from app.config import get_settings
from app.database import make_engine, make_session_factory
from app.temporal import TimeContext
from app.worries.engine import evaluate, to_dict


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.worries")
    p.add_argument("--as-of", default=None)
    p.add_argument("--mode", choices=("known", "recorded"), default="known")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    ctx = TimeContext.recorded_by(args.as_of) if args.mode == "recorded" else TimeContext.known_at(args.as_of)
    with make_session_factory(make_engine(get_settings().database_url))() as s:
        wl = evaluate(s, ctx)
    if args.json:
        print(json.dumps(to_dict(wl), indent=2))
        return
    print(f"Worry list, {wl.mode} as of {wl.as_of:%Y-%m-%d %H:%M} IST; data up to "
          f"{wl.data_as_of:%d %b %Y}" if wl.data_as_of else f"Worry list, {wl.mode} as of {wl.as_of:%Y-%m-%d %H:%M} IST")
    if wl.message:
        print(wl.message)
    for w in wl.worries + wl.more:
        print(f"\n{w.rank}. {w.title}  [confidence {w.confidence}; score {w.score}]")
        print(f"   {w.explanation}")
        print(f"   Why it matters: {w.why_it_matters}")
        for c in w.conflicts:
            print(f"   Open conflict: {c['conflict_key']} ({c['status']}): {c['title']}")
        print(f"   Evidence: " + ", ".join(x["evidence_key"] for e in w.evidence for x in e.citations))
        print(f"   Would change it: {w.would_change}")
    print("\nNot raised:")
    for x in wl.excluded:
        print(f" - {x['area']}: {x['reason']}")


if __name__ == "__main__":
    main()
