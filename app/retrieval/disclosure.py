"""Sentence-level disclosure rules for user-facing output (DECISIONS.md 28, 29; ARCHITECTURE.md 16.14).

Stored evidence is never changed. These rules decide only what text may leave the system in a
search hit, a snippet, an evidence-detail response, a citation quote, a conflict quote or an
answer. Two kinds of sentence are withheld:

  working_hours          a working-hours phrase ("late nights", "weekends", "working late" ...)
                         in the same sentence as a name (a linked person, an alias, or any
                         capitalised name) (decision 28, extending decision 23)
  personal_circumstance  any row of a leave record, whatever its leave type (decisions 11, 29);
                         a family event or a health matter ("wedding", "marriage", "funeral",
                         "maternity", "hospital", "sick" ...) (decision 29)

The unit is the sentence: text split at full stops, question and exclamation marks and line
breaks. A sentence is withheld whole; it is not cut into clauses, so a sentence that mixes a
personal remark with business detail is withheld rather than partly disclosed. Other sentences
of the same record stay visible. The marker that replaces withheld text is the same for both
rules, so it does not reveal which rule applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.temporal import TimeContext

WORK_HOURS = (r"\b(late nights?|late hours|working late|works? late|worked late|weekends?|overtime|hours worked|"
              r"long hours|after hours|night shifts?|all[- ]nighters?|stay(s|ed|ing)? late|"
              r"work(s|ed|ing)? (at )?nights?|how many hours|working (pattern|hours|schedule)s?|"
              r"work (pattern|schedule)s?)\b")
# Operational wording: a sentence about on-call, the rota, incidents, deploys or releases is a work
# record, not a remark about someone's hours, and is never withheld by the working-hours rule.
OPERATIONAL = (r"\b(on[- ]call|rota|incidents?|pager(duty)?|sev ?[1-4]|outages?|deploy\w*|releases?|"
               r"maintenance window|change freeze)\b")
PERSONAL = (r"\b(weddings?|married|marriage|honeymoon|divorce[ds]?|funerals?|bereave\w*|pregnan\w*|maternity|"
            r"paternity|illness|medical|hospital\w*|surgery|sick)\b")
MARKER = "[text withheld under disclosure rules 28 and 29]"

# Capitalised words that start such sentences but are not names ("Says ...", "Weekend deploys ...").
_NOT_A_NAME = (r"says?|said|mentions?|notes?|weekends?|nights?|late|overtime|hours?|working|works?|long|after|"
               r"team|everyone|someone|nobody|people|staff|the|this|that|deploys?|releases?")


@dataclass
class Redaction:
    text: str                                         # the content with withheld sentences replaced
    reasons: list[str] = field(default_factory=list)  # one per withheld sentence

    @property
    def withheld(self) -> bool:
        return bool(self.reasons)

    @property
    def fully_withheld(self) -> bool:
        """Nothing disclosable is left once the markers are removed."""
        return self.withheld and not re.sub(r"[\W_]+", "", self.text.replace(MARKER, ""))


def _names_in(session: Session, sentence: str, ctx: TimeContext) -> bool:
    from app.answering.parse import find_entities   # here, to keep the retrieval layer import-light
    ents = find_entities(session, sentence, ctx)
    names = [n for n in ents.unknown_names if not re.fullmatch(_NOT_A_NAME, n, re.I)]
    return bool(ents.persons or names)


# A row of a leave record (it has a leave-type field) says why one named person was absent. Whatever the
# type, that is a personal circumstance (decisions 11 and 29; ARCHITECTURE.md 16.19). The test is the
# field, not the value, so a leave type not on any word list is withheld too.
LEAVE_RECORD = re.compile(r"(?:^|;)\s*(?:leave[ _-]?type|type of leave|leave reason|reason for leave)\s*:", re.I)


def sentence_reason(session: Session, sentence: str, ctx: TimeContext) -> str | None:
    if re.search(PERSONAL, sentence, re.I) or (_ROW.fullmatch(sentence.strip()) and LEAVE_RECORD.search(sentence)):
        return "personal_circumstance"
    if (re.search(WORK_HOURS, sentence, re.I) and not re.search(OPERATIONAL, sentence, re.I)
            and _names_in(session, sentence, ctx)):
        return "working_hours"
    return None


# A table row as ingestion stores it: "Header: value; Header: value". A row is one unit, so a
# withheld cell takes the whole row with it (an employee name must not stay beside a withheld leave type).
_ROW = re.compile(r"[^;:\n]{1,60}: [^;\n]*(?:; [^;:\n]{1,60}: [^;\n]*)+")
def _units(content: str) -> list[tuple[int, int]]:
    if _ROW.fullmatch(content.strip()):
        return [(0, len(content))]
    spans, start = [], 0
    for m in re.finditer(r"[.!?](?=\s|$)|\n", content):
        prev = content[m.start() - 1] if m.start() else ""
        before = content[max(0, m.start() - 2):m.start()]
        if m.group(0) != "\n" and prev.isupper() and (len(before) < 2 or not before[0].isalpha()):
            continue   # "F." in "F. Shah" is an initial, not a sentence end
        end = m.end()
        if content[start:end].strip():
            spans.append((start, end))
        start = end
    if content[start:].strip():
        spans.append((start, len(content)))
    return spans


def redact(session: Session, content: str, ctx: TimeContext) -> Redaction:
    out, reasons, last = [], [], 0
    content = content or ""
    for s, e in _units(content):
        reason = sentence_reason(session, content[s:e], ctx)
        if reason:
            lead = len(content[s:e]) - len(content[s:e].lstrip())
            out.append(content[last:s + lead])
            out.append(MARKER)
            last = e
            reasons.append(reason)
    if not reasons:
        return Redaction(content or "")
    out.append(content[last:])
    return Redaction("".join(out), reasons)


def mentions_any(text: str, terms) -> bool:
    """Whether visible (not withheld) text still holds a search term or its word form."""
    visible_text = (text or "").replace(MARKER, " ")
    for t in terms:
        stem = t if len(t) <= 4 else t[:max(4, len(t) - 2)]
        if re.search(rf"\b{re.escape(stem)}", visible_text, re.I):
            return True
    return False


def snippet(text: str, terms, width: int = 90) -> str | None:
    """A short excerpt of visible text around the first term, with the term marked like FTS5 does."""
    visible_text = (text or "").replace(MARKER, " ... ")
    for t in terms:
        stem = t if len(t) <= 4 else t[:max(4, len(t) - 2)]
        m = re.search(rf"\b{re.escape(stem)}\w*", visible_text, re.I)
        if m:
            start, end = max(0, m.start() - width), min(len(visible_text), m.end() + width)
            return (("... " if start else "") + visible_text[start:m.start()] + "[" + m.group(0) + "]"
                    + visible_text[m.end():end] + (" ..." if end < len(visible_text) else ""))
    return None
