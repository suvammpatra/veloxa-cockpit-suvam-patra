"""The answer pipeline (ARCHITECTURE.md 9).

  question -> time frame -> names -> classification (sets purpose) -> handler
  (typed records, evidence retrieval) -> conflict detection -> citation
  validation -> evidence sufficiency -> confidence -> optional LLM wording

ask() takes no purpose and no privacy switch: the classifier decides purpose
from the question, so no caller can widen what is read.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.answering import handlers
from app.answering.classify import COMMIT_SYSTEM, Intent, classify, commit_records_barred
from app.answering.confidence import Support, assess
from app.answering.handlers import Ask, conflict_sentence, first_line
from app.answering.llm import Phraser, polish
from app.answering.model import Answer, ChainLink, Factors
from app.answering.parse import find_entities, split_as_of
from app.models import Evidence, Project, SourceRecord
from app.privacy.payroll import PayrollAggregator
from app.retrieval import fts
from app.retrieval.citations import extract_keys, validate
from app.retrieval.search import conflicts_for
from app.temporal import TimeContext

MAX_QUESTION_CHARS = 500


def ask(session: Session, question: str, ctx: TimeContext | None = None, *,
        payroll: PayrollAggregator | None = None, phraser: Phraser | None = None,
        llm_enabled: bool = False) -> Answer:
    question = (question or "").strip()
    if not question or len(question) > MAX_QUESTION_CHARS:
        why = "The question is empty." if not question else f"The question is longer than {MAX_QUESTION_CHARS} characters."
        a = Answer(question=question[:MAX_QUESTION_CHARS] or "(empty question)", short_answer=why, status="refused", refusal="bad_question",
                   kind="invalid", weakest_link="Nothing was asked.", would_change_mind="A question.")
        a.factors = Factors(completeness="insufficient")
        return finalize(session, a, ctx or TimeContext.known_at(None), Intent("invalid"))

    rest, asked_as_of = split_as_of(question)
    trace = []
    if ctx is None:
        ctx = TimeContext.known_at(asked_as_of)
        trace.append(f"time: known as of {ctx.as_of:%Y-%m-%d %H:%M} IST"
                     + (" (from the question)" if asked_as_of else " (now)"))
    else:
        trace.append(f"time: {ctx.mode.value} as of {ctx.as_of:%Y-%m-%d %H:%M} IST (given)")
    ents = find_entities(session, rest, ctx)
    trace.append("names: " + (", ".join(f"{m.text}={m.status}" for m in ents.persons) or "none")
                 + (f"; unknown {ents.unknown_names}" if ents.unknown_names else "")
                 + (f"; departments {[d.name for d in ents.departments]}" if ents.departments else "")
                 + (f"; projects {ents.projects}" if ents.projects else ""))
    intent = classify(rest, ents)
    trace.append(f"class: {intent.kind}" + (f", purpose {intent.purpose}" if intent.purpose else "")
                 + (f", refusal {intent.refusal}" if intent.refusal else ""))
    a = Ask(session, rest, ctx, ents, intent, payroll)
    draft = handlers.HANDLERS[intent.kind](a)
    draft.question = question
    draft.trace = trace + draft.trace
    if asked_as_of is not None and ctx.as_of != asked_as_of:
        draft.warnings.append("The question names an as-of date, but the date chosen in the interface is used.")
    answer = finalize(session, draft, ctx, intent)
    if llm_enabled:
        answer = polish(answer, phraser)
    return answer


def finalize(session: Session, a: Answer, ctx: TimeContext, intent: Intent) -> Answer:
    """Conflicts, citation checks, sufficiency and confidence. Handlers cannot skip this."""
    a.as_of, a.mode, a.purpose = ctx.as_of, ctx.mode.value, intent.purpose
    if not a.weakest_link or not a.would_change_mind:
        a.weakest_link = a.weakest_link or "Not stated."
        a.would_change_mind = a.would_change_mind or "Not stated."

    open_sup, resolved_sup = _detect_conflicts(session, a, ctx, intent)

    failures = []
    # Disclosure rules (decisions 28, 29) are enforced by validate(): a record with nothing
    # disclosable, or a quote from withheld text, fails with reason "withheld", and the whole
    # answer is then withheld, whatever handler put the citation there. Decision 30 is checked the
    # same way: a commit record cited for a question about people or on-call withholds the answer.
    for link in a.evidence_chain:
        link.citations = []
        if not link.keys:
            continue
        quotes = {link.keys[0]: link.quote} if link.quote else None
        for check in validate(session, link.keys, ctx, purpose=intent.purpose, quotes=quotes):
            if check.ok:
                link.citations.append(check.citation)
            else:
                failures.append(f"{check.evidence_key}: {check.reason}")
    failures += _commit_failures(session, a, ctx)
    chained = set(a.keys())
    for k in extract_keys(" ".join((a.short_answer, a.weakest_link, a.would_change_mind))):
        if k not in chained:
            failures.append(f"{k}: named in the answer but not in the evidence chain")
    if failures:
        return _withheld(a, failures)
    a.trace.append(f"citations: {len(chained)} checked, all valid")

    if a.status == "answered" and not any(link.keys or link.record for link in a.evidence_chain
                                           if link.role == "support"):
        a.status = "no_evidence"
        a.factors.completeness = "insufficient"
        a.trace.append("sufficiency: no supporting record, so not answered")

    supports = []
    if a.status in ("answered", "uncertain"):
        for link in a.evidence_chain:
            if link.role != "support":
                continue
            supports += [Support(c.trust_rung, c.system, c.source_key) for c in link.citations]
            if link.record:
                supports.append(Support(link.record_rung, link.record_system, link.record))
    f = a.factors
    result = assess(supports, open_conflicts=open_sup, resolved_conflicts=resolved_sup, identity=f.identity,
                    temporal=f.temporal, completeness=f.completeness, policy=f.policy,
                    corroborated=f.corroborated)
    a.confidence = result.level
    a.confidence_reasons = list(result.reasons) + list(f.notes)
    a.confidence_basis = "policy" if f.policy else ("evidence" if supports else "none")
    return a


def _commit_failures(session: Session, a: Answer, ctx: TimeContext) -> list[str]:
    """Decision 30 backstop. A question about a person, on-call, hours or activity may not rest on
    a Git commit record, whichever handler or fallback put it in the chain (conflict sides too).
    The question is read again here, so this does not depend on the classification."""
    keys = a.keys()
    if not keys or not commit_records_barred(a.question, find_entities(session, a.question, ctx)):
        return []
    found = session.scalars(select(Evidence.evidence_key).join(SourceRecord, Evidence.source_record_id == SourceRecord.id)
                            .where(Evidence.evidence_key.in_(keys), SourceRecord.system == COMMIT_SYSTEM))
    return [f"{k}: a commit record can't show on-call, hours or activity (DECISIONS.md 30)" for k in sorted(found)]


def _detect_conflicts(session: Session, a: Answer, ctx: TimeContext, intent: Intent) -> tuple[int, int]:
    """Attach stored conflicts touching any cited record; name both sides. Returns the open
    and resolved counts on supporting records (for confidence)."""
    keys = a.keys()
    if not keys:
        return 0, 0
    ids = list(session.scalars(select(Evidence.id).where(Evidence.evidence_key.in_(keys))))
    support_keys = {k for link in a.evidence_chain if link.role == "support" for k in link.keys}
    shown = {c.conflict_key for c in a.conflicts}
    open_n = resolved_n = 0
    projects = {w for p in session.scalars(select(Project)) for w in (p.key, p.name)}
    for ref, sides in conflicts_for(session, ctx, ids, purpose=intent.purpose):
        side_keys = {e.evidence_key for e in sides.values()}
        on_support = bool(side_keys & support_keys)
        chosen = ref.conflict_key in shown          # the handler already presents it (disagreement)
        relevant = chosen or ref.origin == "rule" or related(a.question, ref, projects)
        if on_support and relevant:
            if ref.status == "open":
                open_n += 1
            else:
                resolved_n += 1
        if chosen:
            continue
        if not relevant:
            # A whole page can be a side of several reviewed conflicts. One that is not about
            # this question stays visible as a note, but does not change the answer.
            files = sorted({e.source.filename for e in sides.values() if e.evidence_key in keys})
            a.warnings.append(f"{', '.join(files)} is also a side of {ref.conflict_key} ({ref.status}): "
                              f"{ref.title}.")
            a.trace.append(f"conflict: {ref.conflict_key} noted, not about this question")
            continue
        shown.add(ref.conflict_key)
        a.conflicts.append(ref)
        by_key = {e.evidence_key: e for e in sides.values()}
        for side, key, summary in ref.sides:
            if key not in a.keys():
                a.evidence_chain.append(ChainLink(f"{ref.conflict_key} side {side}: {summary}", [key],
                                                  ref.quotes.get(key) or first_line(by_key[key].content),
                                                  role="conflict"))
        if on_support and a.status in ("answered", "uncertain"):
            a.short_answer += " " + conflict_sentence(ref, by_key)
        a.trace.append(f"conflict: {ref.conflict_key} ({ref.status}){' on a supporting record' if on_support else ''}")
    return open_n, resolved_n


_GENERIC = {"board", "update", "updates", "record", "records", "source", "sources", "call", "calls", "transcript",
            "transcripts", "email", "versus", "what", "when", "does", "have", "tell", "about", "with", "side",
            # number and time words alone don't make a conflict relevant ("notice period two months" is not
            # about "two point two lakhs a month"; ARCHITECTURE.md 16.18)
            "one", "two", "three", "four", "five", "six", "day", "days", "week", "weeks", "month", "months", "year",
            "years", "morning", "today", "this", "that"}


def related(question: str, ref, generic: set[str] = frozenset()) -> bool:
    """Whether a reviewed conflict is about the question: a question word (or its word form)
    appears in the conflict's title or side summaries. Generic words, and project names
    (which nearly every engineering record shares), do not count."""
    skip = _GENERIC | {g.lower() for g in generic}
    q = {t.lower() for t in fts.terms(question) if len(t) >= 2} - skip
    text = " ".join([ref.title, *(s[2] for s in ref.sides)]).lower()
    tokens = {t for t in re.findall(r"[a-z0-9][a-z0-9.-]*", text) if len(t) >= 2} - skip

    def same(t: str, tok: str) -> bool:
        if len(t) <= 3 or len(tok) <= 3:   # short words and acronyms ("GA") must match exactly
            return t == tok
        return tok.startswith(t[:5]) or t.startswith(tok[:5])
    return any(same(t, tok) for t in q for tok in tokens)


def _withheld(a: Answer, failures: list[str]) -> Answer:
    a.failed_checks = failures
    a.trace.append("citations: failed " + "; ".join(failures))
    a.status = "withheld"
    a.short_answer = ("I can't give this answer: a cited record failed its check (" + "; ".join(failures)
                      + "). Nothing is asserted.")
    a.evidence_chain = []
    a.conflicts = []
    a.confidence = "Low"
    a.confidence_reasons = ["A citation failed validation, so no claim is made"]
    a.confidence_basis = "none"
    a.weakest_link = "The answer's own citations did not check out."
    a.would_change_mind = "Citations that exist, are known at this date, are allowed here and contain the quoted words."
    return a
