"""Agent interviews: questions about one employee, answered from that employee's records
(ARCHITECTURE.md 16.25; DECISIONS.md 24, 27, 35).

One shared, deterministic engine serves all 14 agents. It is not a model of the person and never
speaks as them. For a question about the selected employee it:

  1. applies the answer engine's refusal rules first, with the employee as the person asked
     about: individual pay, working hours and performance, intentions and feelings, ranking by
     who might leave, and private messages are refused exactly as in /api/ask;
  2. maps the question to profile fields by fixed word rules: role, department, reporting line,
     employment and history, responsibilities, projects, workload and pending changes. Personal
     life, opinions and feelings map to "not established": the records do not hold them, and
     none are invented (decision 24);
  3. answers only from the employee's evidence-grounded profile (app.agents.profiles) at the
     same time frame. Every statement is a profile fact with its evidence keys, already limited
     to the allowlisted systems (decision 27) and validated. Only a High-confidence fact is
     labelled verified; below High the label gives the reason: disputed (an open conflict),
     inferred (a name link below High) or lower confidence;
  4. passes the draft through the answer engine's finalize(): every key is validated again
     (time frame, source policy, disclosure rules), stored conflicts are attached, and confidence
     is set by the usual rule.

A field with no eligible record answers "Not established in available records" with the reason.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.agents.profiles import Profile, agent_profile
from app.agents.roster import AgentSpec
from app.answering import classify as C
from app.answering import handlers
from app.answering.classify import Intent, classify
from app.answering.engine import finalize
from app.answering.model import Answer, ChainLink, Factors
from app.answering.parse import PersonMention, find_entities
from app.services.identity import resolve_person
from app.temporal import TimeContext

NOT_IN_RECORDS = "Not established in available records"
LABELS = {"role": "Role", "department": "Department", "reporting_manager": "Reporting manager",
          "employment": "Employment", "historical_events": "History", "responsibilities": "Responsibilities",
          "current_projects": "Current projects", "workload_indicators": "Workload", "pending_changes": "Pending changes"}
OVERVIEW = ("role", "department", "reporting_manager", "employment", "responsibilities", "current_projects",
            "workload_indicators", "pending_changes")

# Personal life, opinions and feelings: never in the records the profile may read, never invented.
PERSONAL = (r"\b(personal|private|family|married|marriage|spouse|wife|husband|partner|kids?|children|parents?|"
            r"hobb\w*|interests?|outside work|after work|life|home|health|feel\w*|happy|unhappy|mood|stress\w*|"
            r"think\w*|opinions?|believes?|views?|likes?|dislikes?|enjoys?|motivat\w*|personality|character|friends?)\b")
TOPICS = [
    ("role", r"\b(role|title|job|position|designation|what (does|do|did) \w+ do)\b", ("role", "department")),
    ("department", r"\b(department|team|function|group)\b", ("department",)),
    ("manager", r"\b(manager|managed by|reports? to|reporting|boss|line manager|who manages)\b", ("reporting_manager",)),
    ("history", r"\b(history|joined|join|joining|start(ed|ing)?|tenure|how long|since when|career|background|left|leav\w*|"
                r"exit\w*|resign\w*|quit|notice|employ\w*|still (here|at|with)|status|active|departed)\b",
     ("employment", "historical_events")),
    ("responsibilities", r"\b(responsib\w*|in charge|owns?|ownership|accountab\w*|hiring|requisitions?|reqs?)\b",
     ("responsibilities",)),
    ("projects", r"\b(projects?|working on|work on|tickets?|jira|atlas|stories|epics?|tasks?|assigned|deliver\w*)\b",
     ("current_projects",)),
    ("workload", r"\b(workload|busy|capacity|load|on[- ]call|rota|incidents?|pager|bandwidth|how much work|stretched)\b",
     ("workload_indicators",)),
    ("pending", r"\b(changes?|pending|announced|moving|move|new manager|reorg\w*|cro)\b", ("pending_changes",)),
]
OVERVIEW_WORDS = r"\b(who is|who's|tell me about|about (her|him|them)|summary|summari[sz]e|overview|profile|introduce|everything)\b"
DEPARTURE_WORDS = r"\b(resign\w*|quit|leav\w*|notice|last (working )?day)\b"
RANKING = r"\b(rank\w*|list\w*|everyone|all|who|whom|which|top|most|scor\w*|team|staff|people|anyone|engineers?)\b"


def _ents_with(session: Session, spec: AgentSpec, question: str, ctx: TimeContext):
    """The question's names, with the selected employee added as the person asked about, so the
    refusal rules that need a named person (pay, hours, intentions) apply to every question."""
    ents = find_entities(session, question, ctx)
    res = resolve_person(session, spec.name, ctx)
    if not any(m.person and res.person and m.person.id == res.person.id for m in ents.persons):
        ents.persons.insert(0, PersonMention(text=spec.name, status=res.status, resolution=res))
    return ents, res


def _fields_for(question: str) -> tuple[str, tuple[str, ...]]:
    fields: list[str] = []
    for _, pattern, fs in TOPICS:
        if re.search(pattern, question, re.I):
            fields += [f for f in fs if f not in fields]
    if fields:
        return "topics", tuple(fields)
    if re.search(OVERVIEW_WORDS, question, re.I):
        return "overview", OVERVIEW
    return "unknown", ()


def _basis(fact) -> str:
    """How far a profile fact is established. High confidence is verified; below High, the label names
    the reason the profile recorded: an open conflict, a name link below High, or a weaker record."""
    if fact.confidence == "H":
        return "verified"
    if any(n.startswith("Touched by open conflict") for n in fact.notes):
        return "disputed"
    if any(re.search(r"linked to this person by .+ at [ML]$", n) for n in fact.notes):
        return "inferred"
    return "lower confidence"


def _draft(question: str, status: str, short: str, chain=(), *, weak: str, change: str, factors: Factors,
           warnings=()) -> Answer:
    a = Answer(question=question, short_answer=short, status=status, kind="agent_interview",
               evidence_chain=list(chain), weakest_link=weak, would_change_mind=change)
    a.factors = factors
    a.warnings = list(warnings)
    return a


def _from_profile(question: str, spec: AgentSpec, profile: Profile, fields: tuple[str, ...]) -> Answer:
    first = spec.name.split()[0]
    head = f"From records about {spec.name} ({spec.department}, {profile.status.replace('_', ' ')}), not {first} speaking."
    chain, parts, notes, confs, missing_any = [], [], [], [], False
    missing = {m.field: m.reason for m in profile.missing}
    for f in fields:
        facts = [x for x in profile.facts if x.field == f]
        if not facts:
            missing_any = True
            reason = missing.get(f) or "No eligible record covers this."
            parts.append(f"{LABELS[f]}: {NOT_IN_RECORDS}. {reason}")
            continue
        for x in facts:
            basis = _basis(x)
            parts.append(f"{LABELS[f]} ({basis}): {x.statement}")
            chain.append(ChainLink(f"{LABELS[f]}, {basis} (confidence {x.confidence}; {x.valid}): {x.statement}",
                                   list(x.keys)))
            confs.append(x.confidence)
            notes += [n for n in x.notes if n not in notes]
    if not chain:
        return _draft(question, "no_evidence", f"{head} " + " ".join(parts),
                      weak="No eligible record covers the question.",
                      change="A newer HR, hiring, Jira or incident export that covers it.",
                      factors=Factors(completeness="insufficient"))
    identity = "L" if "L" in confs else ("M" if "M" in confs else None)
    if profile.identity_confidence in ("M", "L") and (identity is None or profile.identity_confidence == "L"):
        identity = profile.identity_confidence
    return _draft(question, "answered", head + " " + " ".join(p if p.endswith(".") else p + "." for p in parts), chain,
                  weak=("Profiles read only Keka HRMS, Keka Hire, Jira, PagerDuty and the on-call rota (DECISIONS.md 27); "
                        "each statement is a record about the person, not their own words."),
                  change="A newer HR, hiring or Jira export, or a record that states this directly.",
                  factors=Factors(identity=identity, completeness="partial" if missing_any else "complete",
                                  notes=["Records about the person, not the person speaking (DECISIONS.md 35)"]),
                  warnings=notes)


def interview(session: Session, spec: AgentSpec, question: str, ctx: TimeContext) -> Answer:
    question = (question or "").strip()
    intent = Intent("agent_interview")
    if not question:
        draft = _draft("(empty question)", "refused", "Ask a question about this employee's records.",
                       weak="Nothing was asked.", change="A question.", factors=Factors(completeness="insufficient"))
        return finalize(session, draft, ctx, intent)
    ents, res = _ents_with(session, spec, question, ctx)
    kind = classify(question, ents)
    a = handlers.Ask(session, question, ctx, ents, kind)
    first = spec.name.split()[0]
    if kind.kind == "refusal":
        if kind.refusal == "retention_ranking" and not re.search(RANKING, question, re.I):
            # One named person's intentions, not a ranking: the intentions refusal is the accurate text.
            return finalize(session, handlers.refusal(a, "speculation"), ctx, Intent("refusal", refusal="speculation"))
        return finalize(session, handlers.refusal(a), ctx, kind)
    if kind.kind == "payroll" or re.search(C.PAY, question, re.I):
        return finalize(session, handlers.refusal(a, "individual_pay"), ctx, Intent("refusal", refusal="individual_pay"))
    if re.search(PERSONAL, question, re.I):
        draft = _draft(question, "no_evidence",
                       f"{NOT_IN_RECORDS}. The records hold no account of {spec.name}'s personal life, opinions or "
                       f"feelings, and the cockpit does not invent them or speak as {first} (DECISIONS.md 24, 35). "
                       "Personal circumstances that do appear in records are withheld (DECISIONS.md 29).",
                       weak="Nothing in the records answers this, by design.",
                       change=f"Only {first}'s own account, which is not a company record.",
                       factors=Factors(completeness="insufficient"))
        return finalize(session, draft, ctx, intent)
    how, fields = _fields_for(question)
    if how == "unknown":
        draft = _draft(question, "no_evidence",
                       f"{NOT_IN_RECORDS}. The records about {spec.name} cover role, department, reporting line, "
                       "employment history, responsibilities, current projects, workload and pending changes; "
                       "ask about one of those.",
                       weak="The question is outside what the records show about a person.",
                       change="A question about the person's role, work or history.",
                       factors=Factors(completeness="insufficient"))
        return finalize(session, draft, ctx, intent)
    profile = agent_profile(session, spec, ctx)
    if profile.status == "identity_not_established":
        draft = _draft(question, "no_evidence",
                       f"{NOT_IN_RECORDS}. No HR record for {spec.name} is known at this date.",
                       weak="There is no employee record to read at this date.",
                       change="An HR export that includes the person.", factors=Factors(completeness="insufficient"))
        return finalize(session, draft, ctx, intent)
    draft = _from_profile(question, spec, profile, fields)
    if re.search(DEPARTURE_WORDS, question, re.I):
        draft.warnings.append("Reported but unverified events, such as a resignation mentioned in a CEO voice note, are "
                              "not employee records; the main question box shows them as unverified (DECISIONS.md 33).")
    others = sorted({m.person.full_name for m in ents.persons if m.person and not (res.person and m.person.id == res.person.id)})
    if others:
        draft.warnings.append(f"This interview answers about {spec.name} only; {', '.join(others)} is not covered here.")
    return finalize(session, draft, ctx, intent)
