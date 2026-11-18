"""Confidence by rule (ARCHITECTURE.md 9, step 7). No model decides it.

Base, from the validated sources that support the answer:
  High    a rung 1-2 source, or two independent systems that agree
  Medium  the best support is one rung 3-4 source
  Low     transcript-only or unranked support, or no support

Then caps, each of which can only lower the level:
  open conflict on a supporting record      -> Low
  resolved conflict on a supporting record  -> at most Medium
  name link at M / L                         -> at most Medium / Low
  time approximate / unknown                 -> at most Medium / Low
  evidence partial / insufficient            -> at most Medium / Low

Independence: two supports count as independent only when they come from
different systems (ARCHITECTURE.md 9). Two rows of one export are one source.
A policy refusal is High: it rests on a fixed rule, not on evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

ORDER = {"L": 0, "M": 1, "H": 2}
NAMES = {"H": "High", "M": "Medium", "L": "Low"}


@dataclass(frozen=True)
class Support:
    rung: int | None
    system: str | None
    source: str          # source key or record name, to tell sources apart


@dataclass(frozen=True)
class Assessment:
    code: str            # H | M | L
    reasons: tuple[str, ...]

    @property
    def level(self) -> str:
        return NAMES[self.code]


def assess(supports: list[Support], *, open_conflicts: int = 0, resolved_conflicts: int = 0,
           identity: str | None = None, temporal: str = "exact", completeness: str = "complete",
           policy: bool = False, corroborated: bool = False) -> Assessment:
    """`corroborated` is True only when the supports state the same fact. Supports for
    different parts of one answer (a kit status and a GA date) are not corroboration."""
    if policy:
        return Assessment("H", ("Confidence in the refusal as a policy decision, not in any business fact; "
                                "the question was not answered",))
    if not supports:
        return Assessment("L", ("No record supports an answer",))

    reasons: list[str] = []
    ranked = [s for s in supports if s.rung is not None]
    best = min((s.rung for s in ranked), default=None)
    systems = sorted({s.system or s.source for s in ranked if s.rung <= 4})
    if best is not None and best <= 2:
        code = "H"
        top = next(s for s in ranked if s.rung == best)
        reasons.append(f"Rests on a rung {best} source ({top.system or top.source})")
    elif corroborated and len(systems) >= 2:
        code = "H"
        reasons.append(f"Two independent systems agree ({', '.join(systems[:3])})")
    elif best is not None and best <= 4:
        code = "M"
        reasons.append(f"Best support is one rung {best} source ({systems[0]})")
    else:
        code = "L"
        reasons.append("Support is transcript-only or from an unranked source")

    def cap(limit: str, why: str) -> None:
        nonlocal code
        if ORDER[limit] < ORDER[code]:
            code = limit
            reasons.append(why)
        else:
            reasons.append(why + " (no change)")

    if open_conflicts:
        cap("L", f"{open_conflicts} open conflict(s) on a supporting record")
    elif resolved_conflicts:
        cap("M", f"{resolved_conflicts} resolved conflict(s) on a supporting record")
    if identity in ("M", "L"):
        cap(identity, f"A name was linked to a person at confidence {identity}")
    if temporal == "approximate":
        cap("M", "The dates involved are approximate")
    elif temporal == "unknown":
        cap("L", "When the record applies is unknown")
    if completeness == "partial":
        cap("M", "The records cover the question only in part")
    elif completeness == "insufficient":
        cap("L", "The records are not enough to settle the question")
    return Assessment(code, tuple(reasons))
