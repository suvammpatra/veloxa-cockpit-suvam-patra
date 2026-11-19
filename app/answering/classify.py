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
  * retention_ranking       ranking or scoring people by how likely they are to leave (decision 34)
  * private_messages        Slack, WhatsApp or other private messages (decision 34)

On-call questions go to the on_call handler, which reads only the on-call rota. Whether Git
commit records may be used at all is decided by commit_records_barred() (DECISIONS.md 30).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.answering.parse import Entities
from app.retrieval import disclosure


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
WORK_HOURS = disclosure.WORK_HOURS   # one definition, shared with the disclosure rules (decision 28)
ON_CALL = disclosure.OPERATIONAL   # on-call, rota, incidents, deploys, releases: operational, never refused
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
# T6c (DECISIONS.md 34): no one is ranked or scored by how likely they are to leave, and private
# messages are never read. QUIT_WORDS near a likelihood word asks for a prediction about people.
QUIT_WORDS = r"(quit\w*|resign\w*|leav(e|es|ing)|attrition|churn\w*)"
LIKELIHOOD = (r"(likel\w*|unlikel\w*|probab\w*|predict\w*|rank\w*|scor\w*|risk|chance|odds|going to|about to|"
              r"planning to|thinking (of|about)|might|may|will|could|would|next)")
RETENTION_RANK = (rf"\b(flight risk|attrition risk|retention risk|resignation risk|risk of {QUIT_WORDS}|"
                  rf"{LIKELIHOOD}\W+(\w+\W+){{0,3}}?{QUIT_WORDS}|{QUIT_WORDS}\W+(\w+\W+){{0,3}}?"
                  rf"(risk|likel\w*|probab\w*|scor\w*|rank\w*|predict\w*))")
PRIVATE_MESSAGES = (r"\b(slack|slag|whats ?app|dms?|direct messages?|private messages?|chat logs?|chats?|"
                    r"(their|his|her|staff|employees'?|everyone'?s|people'?s|team'?s) (messages?|texts?))\b")
CONSENT = (r"\b(says? (it'?s|it is) (fine|ok|okay)|said (it'?s|it is|it was) (fine|ok|okay)|approved|consent\w*|"
           r"signed off|gave (the )?(ok|go-ahead|permission)|is fine with|ok'?d|permission)\b")
# The alternative T6c offers: an aggregate view of continuity, with no one scored.
CONTINUITY = (r"\b(workforce continuity|continuity|vacanc\w*|open (roles|requisitions|reqs|positions)|"
              r"requisitions?|succession|departures?|attrition|who (has )?left)\b")
# T6d: a reported (or hypothetical) departure and what it does to the work. Answered from records only.
DEPARTURE = (r"\b(resign\w*|quit|quits|quitting|leav(es|ing)|left the company|notice period|handed in (her|his|their) "
             r"notice|last (working )?day)\b")
VERSION = r"\b(version (three|3)|v ?3)\b"

# An on-call question is answered from the on-call rota only (DECISIONS.md 30).
ON_CALL_Q = r"\b(on[- ]call|oncall|rota|pager|standby|stand-by)\b"
# "Who ran payroll?" asks who did the work, not what anyone was paid. It goes to the records
# search, but only when no pay-amount word is present, so the pay rules are not weakened.
PAYROLL_RUN = (r"\bwho\b.{0,30}\b(ran|run|runs|running|process(ed|es|ing)?|handl(ed|es|ing)|prepar(ed|es|ing)|"
               r"approv(ed|es|ing)|sign(ed|s)? off|did|does|do)\b.{0,15}\bpayroll\b")
PAY_AMOUNT = (r"\b(salary|salaries|pay|paid|earn\w*|ctc|compensation|wages?|take[- ]home|amount|how much|gross|net|"
              r"total|totals|cost|bonus\w*)\b")

# Git commit records (DECISIONS.md 30). A commit time shows only when a commit was recorded. Commits
# are never used for a question about a person, on-call, hours, activity, workload, productivity or
# performance. They stay usable for repository history ("What was committed to atlas-engine in August?").
COMMIT_SYSTEM = "GitHub"
PEOPLE_ACTIVITY = (r"\b(who|whom|whose|on[- ]call|oncall|rota|pager|standby|stand-by|shifts?|available|availability|"
                   r"active|activity|activities|busy|workload|productiv\w*|performance|perform\w*|output|effort|"
                   r"work|works|worked|working|doing|online|awake|late|night|nights|weekends?|hours?|overtime|"
                   r"midnight|overnight|evenings?|mornings?|pattern|patterns|time of day|habits?|schedules?|"
                   r"authors?|authored|committers?|contribut\w*|individual|individually|per person|each person|"
                   r"engineers?|developers?|people|person|staff|employees?|team members?)\b")


def commit_records_barred(question: str, ents: Entities) -> bool:
    """True when Git commit records must not be used to answer this question (decision 30): it names a
    person, or asks about on-call, hours, activity, workload, productivity, performance or who did
    something. This is checked by the fallback search, by statements() and again by the engine."""
    return bool(ents.persons or ents.unknown_names) or _has(PEOPLE_ACTIVITY, question) or _has(WORK_HOURS, question)


def classify(question: str, ents: Entities) -> Intent:
    q = question
    person = bool(ents.persons or ents.unknown_names)

    ranking = _has(r"\b(rank\w*|list\w*|everyone|every one|all|who|whom|which|top|most|score\w*|team|staff|people|"
                   r"anyone|engineers?)\b", q)
    if _has(RETENTION_RANK, q) and ranking:
        return Intent("refusal", refusal="retention_ranking")   # decisions 11, 23, 34; with or without names
    if person and _has(SPECULATION, q):
        return Intent("refusal", refusal="speculation")         # one named person's intentions (decisions 11, 23)
    if _has(RETENTION_RANK, q):
        return Intent("refusal", refusal="retention_ranking")   # decisions 11, 23, 34; with or without names
    if _has(PRIVATE_MESSAGES, q):
        return Intent("refusal", refusal="private_messages")    # decision 34
    if _has(COMMIT, q) and _has(COMMIT_TIME, q):
        return Intent("refusal", refusal="performance_assessment")
    if _has(WORK_HOURS, q) and person and not _has(ON_CALL, q):
        return Intent("refusal", refusal="performance_assessment")  # decision 23, however it is phrased
    if _has(WORK_HOURS, q) and _has(r"\bwho\b", q) and not _has(ON_CALL, q):
        # "Who works late?" asks the cockpit to pick people out by their hours (decision 23).
        return Intent("refusal", refusal="performance_assessment")
    if _has(PERFORMANCE, q) or (_has(r"\bperformance\b", q) and person):
        return Intent("refusal", refusal="performance_assessment")
    if _has(SPECULATION, q) and (person or _has(r"\b(who|whom|which|anyone|everyone|people|staff)\b", q)):
        return Intent("refusal", refusal="speculation")
    if _has(NOT_COMPUTABLE, q):
        return Intent("refusal", refusal="not_computable")
    if _has(PAY, q) and _has(PAYROLL_RUN, q) and not _has(PAY_AMOUNT, q):
        return Intent("search")   # who did the payroll run: a records question, not pay
    if _has(PAY, q):
        return Intent("payroll")
    if _has(DISAGREE, q):
        return Intent("disagreement")
    if _has(DEPARTURE, q) and (person or _has(VERSION, q)):
        return Intent("departure_impact")       # T6d: reported or hypothetical, never applied (decision 33)
    if _has(CONTINUITY, q):
        return Intent("workforce_continuity")   # the aggregate view offered instead of a ranking (decision 34)
    if _has(ON_CALL_Q, q):
        return Intent("on_call")
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
