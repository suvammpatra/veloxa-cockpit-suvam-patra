"""The five-field answer (ARCHITECTURE.md 6) and its parts.

Every answer has, in order:
  1. question
  2. short_answer
  3. evidence_chain   links in reasoning order, each with evidence keys or a typed record
  4. confidence       High, Medium or Low, with the rule-based reasons
  5. weakest_link and would_change_mind

Handlers fill a draft. The engine then validates every citation and computes
confidence from the validated sources; a handler cannot set confidence itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from app.retrieval.citations import Citation
from app.retrieval.search import ConflictRef

# answered    a typed answer or a direct record
# uncertain   records exist but do not settle the question; the answer says what is unknown
# no_evidence nothing known at this date supports an answer
# ambiguous   a name could be more than one person; no person is picked
# refused     a policy forbids the answer (privacy, purpose, not computable)
# withheld    a citation failed its check, so nothing is asserted
STATUSES = ("answered", "uncertain", "no_evidence", "ambiguous", "refused", "withheld")
LEVELS = {"H": "High", "M": "Medium", "L": "Low"}


@dataclass
class ChainLink:
    statement: str
    keys: list[str] = field(default_factory=list)   # evidence keys behind the statement
    quote: str | None = None                          # exact words from the first key's text
    role: str = "support"                             # support | context | conflict
    record: str | None = None                         # a typed record with no citable key (payroll totals)
    record_rung: int | None = None
    record_system: str | None = None
    citations: list[Citation] = field(default_factory=list)  # filled after validation


@dataclass
class Factors:
    """Inputs to the confidence rule (app.answering.confidence). Set by handlers from
    what they found; the level itself is computed, never chosen."""
    identity: str | None = None          # H | M | L confidence of a name link the answer rests on
    temporal: str = "exact"              # exact | approximate | unknown
    completeness: str = "complete"       # complete | partial | insufficient
    policy: bool = False                 # the answer is a fixed policy refusal
    corroborated: bool = False           # two supporting records state the same fact (not just related facts)
    notes: list[str] = field(default_factory=list)


@dataclass
class Answer:
    question: str
    short_answer: str
    evidence_chain: list[ChainLink] = field(default_factory=list)
    confidence: str = "Low"
    confidence_reasons: list[str] = field(default_factory=list)
    # What the confidence is about. "evidence": a business fact from records. "policy": the
    # refusal itself, a fixed rule; the business question was not answered. "none": no support.
    confidence_basis: str = "none"
    weakest_link: str = ""
    would_change_mind: str = ""
    status: str = "answered"
    kind: str = "search"                 # which handler answered
    refusal: str | None = None
    purpose: str | None = None           # set by the classifier only
    as_of: datetime | None = None
    mode: str | None = None
    conflicts: list[ConflictRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)   # what each pipeline stage did
    factors: Factors = field(default_factory=Factors)
    failed_checks: list[str] = field(default_factory=list)
    wording: str = "template"            # template | llm
    template_answer: str | None = None   # the rule-built short answer when an LLM reworded it

    def keys(self) -> list[str]:
        out: list[str] = []
        for link in self.evidence_chain:
            for k in link.keys:
                if k not in out:
                    out.append(k)
        return out


def to_dict(answer: Answer) -> dict:
    def conv(v):
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [conv(x) for x in v]
        if isinstance(v, datetime):
            return v.isoformat()
        return v
    d = conv(asdict(answer))
    d.pop("factors", None)
    return d


def render_text(a: Answer) -> str:
    """The five fields as plain text, for the command line."""
    lines = [f"Question: {a.question}", f"Short answer: {a.short_answer}", "Evidence chain:"]
    if not a.evidence_chain:
        lines.append("  (none)")
    for i, link in enumerate(a.evidence_chain, 1):
        refs = ", ".join(c.label for c in link.citations) if link.citations else ", ".join(link.keys)
        if link.record:
            refs = (refs + "; " if refs else "") + link.record
        tag = "" if link.role == "support" else f" [{link.role}]"
        lines.append(f"  {i}. {link.statement}{tag}")
        if refs:
            lines.append(f"     {refs}")
        if link.quote:
            lines.append(f'     "{" ".join(link.quote.split())}"')
    if a.confidence_basis == "policy":
        lines.append(f"Confidence: {a.confidence}, in the refusal as a policy decision. This is not confidence "
                     "in any business fact: the question was not answered.")
    else:
        lines.append(f"Confidence: {a.confidence} ({'; '.join(a.confidence_reasons)})")
    lines.append(f"Weakest link: {a.weakest_link}")
    lines.append(f"What would change my mind: {a.would_change_mind}")
    when = f"{a.mode} as of {a.as_of:%Y-%m-%d %H:%M} IST" if a.as_of else ""
    lines.append(f"[{a.status}; {a.kind}{'; ' + a.refusal if a.refusal else ''}; {when}; wording {a.wording}]")
    for w in a.warnings:
        lines.append(f"  note: {w}")
    return "\n".join(lines)
