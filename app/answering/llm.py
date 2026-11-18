"""Optional LLM wording (DECISIONS.md 7; ARCHITECTURE.md 9, step 6).

Off by default. Everything works with no API key and no network. When it is
on and a phraser is supplied, the phraser may reword the short answer only.
It cannot add facts, citations or confidence, or change a refusal:

  * refusals, withheld and ambiguous answers are never reworded;
  * every number, evidence key and capitalised word in the new wording must
    already appear in the rule-built answer or its evidence chain;
  * confidence words and new evidence keys are rejected;
  * on any failure the rule-built wording is kept, with a note.

No provider is shipped. A phraser is any object with a rephrase() method.
"""

from __future__ import annotations

import re
from typing import Protocol

from app.answering.model import Answer

REWORDABLE = ("answered", "uncertain", "no_evidence")


class Phraser(Protocol):
    def rephrase(self, text: str, *, facts: list[str]) -> str: ...


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def _names(text: str) -> set[str]:
    return set(re.findall(r"\b[A-Z][A-Za-z0-9.&'-]+\b", text))


def check_wording(original: str, facts: list[str], new: str) -> str | None:
    """None if the new wording adds nothing; otherwise the reason it is rejected."""
    if not new or not new.strip():
        return "empty wording"
    if len(new) > 2 * len(original) + 200:
        return "wording much longer than the answer"
    allowed = original + "\n" + "\n".join(facts)
    extra_numbers = _numbers(new) - _numbers(allowed)
    if extra_numbers:
        return "adds numbers: " + ", ".join(sorted(extra_numbers))
    extra_names = {n for n in _names(new) - _names(allowed) if n.lower() not in _FUNCTION_WORDS}
    if extra_names:
        return "adds names or terms: " + ", ".join(sorted(extra_names))
    if re.search(r"\b(high|medium|low)\s+confidence\b|\bconfiden(t|ce)\b", new, re.I):
        return "states confidence"
    return None


_FUNCTION_WORDS = {"the", "a", "an", "in", "on", "it", "this", "that", "there", "these", "those", "as", "at", "by",
                   "for", "of", "to", "and", "but", "or", "no", "not", "yes", "so", "we", "our", "they", "its",
                   "i", "jira", "records", "record", "however", "also", "currently", "today"}


def polish(answer: Answer, phraser: Phraser | None) -> Answer:
    if phraser is None:
        answer.warnings.append("LLM wording is on but no phraser is configured; the rule-built wording is used.")
        return answer
    if answer.status not in REWORDABLE:
        return answer
    facts = [link.statement for link in answer.evidence_chain] + [link.quote for link in answer.evidence_chain
                                                                   if link.quote]
    try:
        new = phraser.rephrase(answer.short_answer, facts=facts)
    except Exception as exc:  # noqa: BLE001 - the LLM is optional; any failure keeps the template
        answer.warnings.append(f"LLM wording failed ({type(exc).__name__}); the rule-built wording is used.")
        return answer
    problem = check_wording(answer.short_answer, facts, new)
    if problem:
        answer.warnings.append(f"LLM wording rejected ({problem}); the rule-built wording is used.")
        return answer
    answer.template_answer = answer.short_answer
    answer.short_answer = new.strip()
    answer.wording = "llm"
    return answer
