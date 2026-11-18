"""Question classification and purpose (ARCHITECTURE.md 9, steps 1-2).

The kind and the purpose come only from the question's words and the names
in it. No caller can supply a purpose: ask() and the API take none. The only
purpose that unlocks anything is "atlas_ownership", and only a question that
names Atlas and asks about ownership gets it (DECISIONS.md 23).

Privacy and policy refusals are checked first, before any retrieval:
  * performance_assessment  commit times or performance read as a judgement of a person (decision 23)
  * speculation             a person's intentions or feelings (decisions 11, 23)
  * not_computable          revenue, profit, net burn, margins (section 9; no export contains revenue)
Individual pay is refused in the payroll handler, once names are known.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.answering.parse import Entities


@dataclass(frozen=True)
class Intent:
    kind: str
    purpose: str | None = None
    refusal: str | None = None


def _has(pattern: str, text: str, flags=re.I) -> bool:
    return re.search(pattern, text, flags) is not None


PAY = r"\b(salary|salaries|payroll|pay|paid|earn|earns|earning|earnings|ctc|compensation|wages?|take[- ]home)\b"
COMMIT = r"\b(commit|commits|committed|committing|git)\b"
COMMIT_TIME = r"\b(late|night|nights|nightly|weekend|weekends|hours|overtime|midnight|time of day|pattern|patterns)\b"
PERFORMANCE = (r"\b(performance review|underperform\w*|productiv\w*|overwork\w*|work ethic|hard[- ]working|lazy|"
               r"slack(ing|er)|effort|rate (her|him|them)|rating of)\b")
SPECULATION = (r"\b(flight risk|attrition risk|unhappy|dissatisf\w*|disgruntled|morale|motive|motivation|"
               r"burn(ed|t)?[- ]?out|feel|feels|feeling|frustrat\w*|"
               r"(will|going to|plan(s|ning)? to|about to|likely to|thinking (of|about)|might|may|want(s)? to)"
               r"\s+(resign|quit|leave))\b")
NOT_COMPUTABLE = r"\b(revenue|profit|profits|profitability|net burn|margin|margins|ebitda|net income|bookings)\b"
DISAGREE = (r"\b(disagree\w*|conflict\w*|contradict\w*|inconsisten\w*|discrepanc\w*|mismatch\w*|"
            r"(do|does) the (sources|records) agree|which (source|record) is right)\b")
LAUNCH = (r"\b(launch kit|launch readiness|launch[- ]ready|ready (to|for) (the )?launch|marketing (launch|readiness)|"
          r"launch assets)\b")
OWNERSHIP = r"\b(own|owns|owned|owner|owners|ownership|who leads|who is leading|responsible for|accountable for)\b"
RELEASE = (r"\b(GA|general availability|release date|launch date|ship date|go[- ]live|"
           r"when (will|is|does|did) .{0,40}\b(launch|release|ship|go live))\b")
INCIDENT = r"\b(incident|incidents|outage|outages|sev ?[1-4]|downtime|paged)\b"
HEADCOUNT = (r"\b(headcount|head count|how many (people|employees|staff|engineers|members|persons)|"
             r"number of (people|employees|staff)|team size|how big)\b")
MANAGER = r"\b(report(s|ed|ing)? to|manager|manages|managed|boss|line manager|sit(s)? under)\b"


def classify(question: str, ents: Entities) -> Intent:
    q = question
    person = bool(ents.persons or ents.unknown_names)

    if _has(COMMIT, q) and _has(COMMIT_TIME, q):
        return Intent("refusal", refusal="performance_assessment")
    if _has(PERFORMANCE, q) or (_has(r"\bperformance\b", q) and person):
        return Intent("refusal", refusal="performance_assessment")
    if _has(SPECULATION, q) and person:
        return Intent("refusal", refusal="speculation")
    if _has(NOT_COMPUTABLE, q):
        return Intent("refusal", refusal="not_computable")
    if _has(PAY, q):
        return Intent("payroll")
    if _has(DISAGREE, q):
        return Intent("disagreement")
    if _has(LAUNCH, q) or (_has(r"\blaunch\b", q) and _has(r"\b(ready|readiness|kit)\b", q)):
        return Intent("launch_readiness")
    if _has(OWNERSHIP, q) and ents.projects:
        purpose = "atlas_ownership" if "atlas" in ents.projects else None
        return Intent("ownership", purpose=purpose)
    if _has(RELEASE, q, flags=0) or _has(RELEASE.replace(r"GA|", ""), q):
        return Intent("release_date")
    if _has(INCIDENT, q):
        return Intent("incidents")
    if _has(HEADCOUNT, q):
        return Intent("department_headcount" if ents.departments else "company_headcount")
    if _has(MANAGER, q) and (person or ents.departments):
        return Intent("manager")
    return Intent("search")
