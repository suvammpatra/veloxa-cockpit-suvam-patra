"""The CEO worry list (Phase 7; DECISIONS.md 11-16; ARCHITECTURE.md 16.16).

  rules (app.worries.rules) -> finalize() from the answer engine -> well-supported check ->
  score -> rank -> duplicate check -> top three, then the rest, then what was excluded

Every candidate goes through the same finalize() as an answer: each cited record is checked at the
time frame (released, allowed, quote present, disclosure rules 28 and 29, the decision 30 backstop),
stored conflicts on cited records are attached, and confidence is computed by rule. Nothing here
uses an LLM, and nothing here is ranked by one.

Score (fixed weights; the same records always give the same order):
  score = 3 x impact (1-3) + 2 x strength (Low 1, Medium 2, High 3) + recency (0-2) + persistence (0-2)
  recency     latest supporting evidence date within 31 days of the as-of date 2, within 92 days 1, else 0
  tie-break   higher impact, then higher strength, then the rule key
The number of records never enters the score.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.answering.classify import COMMIT_SYSTEM, Intent
from app.answering.engine import finalize
from app.answering.model import Answer
from app.temporal import IST, TimeContext
from app.worries.rules import RULES, Candidate, Excluded

TOP = 3
STRENGTH = {"High": 3, "Medium": 2, "Low": 1}
WEIGHTS = {"impact": 3, "strength": 2, "recency": 1, "persistence": 1}


@dataclass
class EvidenceItem:
    statement: str
    role: str                     # support | context | conflict
    quote: str | None
    citations: list[dict]         # evidence_key, filename, locator, system, trust_rung, evidence_date, known_since


@dataclass
class Worry:
    rank: int
    key: str
    area: str
    title: str
    explanation: str
    why_it_matters: str
    confidence: str
    confidence_reasons: list[str]
    conflicts: list[dict]
    uncertainty: list[str]
    would_change: str
    evidence: list[EvidenceItem]
    evidence_dates: dict          # earliest / latest date the supporting records describe
    known_since: datetime | None  # when the latest supporting record became known (released)
    score: int
    score_parts: dict
    related: list[str] = field(default_factory=list)


@dataclass
class WorryList:
    as_of: datetime
    mode: str
    evaluated_at: datetime
    data_as_of: datetime | None   # the latest record the shown worries rest on (decision 16)
    worries: list[Worry]          # at most three (decision 13)
    more: list[Worry]             # ranked fourth and lower, still reachable (decision 14)
    excluded: list[dict]          # every rule that raised nothing, and why
    message: str | None = None    # the empty state, or why fewer than three are shown


def _recency(latest: datetime | None, ctx: TimeContext) -> int:
    if latest is None:
        return 0
    days = (ctx.as_of.date() - latest.date()).days
    return 2 if days <= 31 else 1 if days <= 92 else 0


def _validated(session: Session, c: Candidate, ctx: TimeContext) -> Answer:
    draft = Answer(question=c.topic, short_answer=c.explanation, status="answered", kind="worry",
                   evidence_chain=c.chain, weakest_link=c.weakest_link, would_change_mind=c.would_change)
    draft.factors = c.factors
    return finalize(session, draft, ctx, Intent("worry"))


def _citation(cit) -> dict:
    return {"evidence_key": cit.evidence_key, "filename": cit.filename, "locator": cit.locator, "system": cit.system,
            "trust_rung": cit.trust_rung, "evidence_date": cit.exported_on, "known_since": cit.released_on}


def _worry(c: Candidate, ans: Answer, ctx: TimeContext) -> Worry:
    support = [cit for link in ans.evidence_chain if link.role == "support" for cit in link.citations]
    dates = sorted(cit.exported_on for cit in support if cit.exported_on)
    strength = STRENGTH[ans.confidence]
    parts = {"impact": c.impact, "strength": strength, "recency": _recency(dates[-1] if dates else None, ctx),
             "persistence": c.persistence}
    score = sum(WEIGHTS[k] * v for k, v in parts.items())
    reasons = {"impact": c.impact_reason, "strength": f"Confidence {ans.confidence}",
               "recency": f"Latest supporting record dated {dates[-1]:%d %b %Y}" if dates else "No dated record",
               "persistence": c.persistence_reason}
    uncertainty = [ans.weakest_link] + list(c.notes) + [w for w in ans.warnings if w not in c.notes]
    return Worry(
        rank=0, key=c.key, area=c.area, title=c.title, explanation=ans.short_answer, why_it_matters=c.why_it_matters,
        confidence=ans.confidence, confidence_reasons=list(ans.confidence_reasons),
        conflicts=[{"conflict_key": r.conflict_key, "title": r.title, "status": r.status, "resolution": r.resolution,
                    "sides": [{"side": s, "evidence_key": k, "summary": t} for s, k, t in r.sides]}
                   for r in ans.conflicts],
        uncertainty=uncertainty, would_change=ans.would_change_mind,
        evidence=[EvidenceItem(link.statement, link.role, link.quote, [_citation(x) for x in link.citations])
                  for link in ans.evidence_chain],
        evidence_dates={"earliest": dates[0] if dates else None, "latest": dates[-1] if dates else None},
        known_since=max((cit.released_on for cit in support), default=None),
        score=score, score_parts={k: {"value": v, "weight": WEIGHTS[k], "why": reasons[k]} for k, v in parts.items()})


def _support_keys(w: Worry) -> set[str]:
    return {x["evidence_key"] for e in w.evidence if e.role == "support" for x in e.citations}


def evaluate(session: Session, ctx: TimeContext, *, now: datetime | None = None) -> WorryList:
    """The worry list at a time frame. `now` is only the evaluation timestamp; it never changes the result."""
    evaluated_at = now or datetime.now(IST).replace(tzinfo=None)
    excluded, ranked = [], []
    for rule in RULES:
        result = rule(session, ctx)
        if isinstance(result, Excluded):
            excluded.append(asdict(result))
            continue
        ans = _validated(session, result, ctx)
        if ans.status == "withheld":
            excluded.append({"key": result.key, "area": result.area,
                             "reason": "A cited record failed its check, so nothing is shown: "
                                       + "; ".join(ans.failed_checks)})
            continue
        git = sorted({cit.evidence_key for link in ans.evidence_chain for cit in link.citations
                      if cit.system == COMMIT_SYSTEM})
        if git:   # the worry list is never built on commit records, whatever the wording (decision 30)
            excluded.append({"key": result.key, "area": result.area,
                             "reason": f"Cites Git commit records ({', '.join(git)}), which a worry may not rest on "
                                       "(DECISIONS.md 30)."})
            continue
        rungs = [cit.trust_rung for link in ans.evidence_chain if link.role == "support" for cit in link.citations]
        if not any(r is not None and r <= 4 for r in rungs):
            excluded.append({"key": result.key, "area": result.area,
                             "reason": "Not well supported: no supporting record outside call transcripts passed its "
                                       "check at this date (DECISIONS.md 13)."})
            continue
        ranked.append(_worry(result, ans, ctx))
    ranked.sort(key=lambda w: (-w.score, -w.score_parts["impact"]["value"], -w.score_parts["strength"]["value"], w.key))
    kept: list[Worry] = []
    for w in ranked:
        dup = next((k for k in kept if _support_keys(w) <= _support_keys(k)), None)
        if dup is not None:   # same supporting records as a higher-ranked worry: not a separate risk
            dup.related.append(w.key)
            excluded.append({"key": w.key, "area": w.area, "reason": f"Duplicate of '{dup.title}': its supporting "
                                                                     "records are all cited there."})
            continue
        kept.append(w)
    for i, w in enumerate(kept, 1):
        w.rank = i
    shown, more = kept[:TOP], kept[TOP:]
    message = None
    if not shown:
        message = ("No worry is well supported by the records known at this date. The list is left empty rather than "
                   "filled (DECISIONS.md 13).")
    elif len(shown) < TOP:
        message = (f"Only {len(shown)} worr{'y is' if len(shown) == 1 else 'ies are'} well supported by the records "
                   "known at this date; no slot is filled to reach three (DECISIONS.md 13).")
    latest = [w.evidence_dates["latest"] for w in shown if w.evidence_dates["latest"]]
    return WorryList(as_of=ctx.as_of, mode=ctx.mode.value, evaluated_at=evaluated_at,
                     data_as_of=max(latest) if latest else None, worries=shown, more=more, excluded=excluded,
                     message=message)


def to_dict(wl: WorryList) -> dict:
    def conv(v):
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [conv(x) for x in v]
        if isinstance(v, datetime):
            return v.isoformat()
        return v
    return conv(asdict(wl))
