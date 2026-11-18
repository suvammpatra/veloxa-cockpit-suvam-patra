"""SQLite FTS5 index over Evidence.

The index is an external-content FTS5 table: it stores no text of its own and
points at evidence.id, so nothing can be found that is not an ingested Evidence
row. Triggers keep it in step with every insert, update and delete.

Tokenizer: porter stemming over unicode61, so "delays" finds "delay". Distinct
names stay distinct tokens: "sneha" never matches "snehal".
"""

from __future__ import annotations

import re

from sqlalchemy import Engine, text

DDL = [
    """CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
           content, locator, content='evidence', content_rowid='id',
           tokenize='porter unicode61 remove_diacritics 2')""",
    """CREATE TRIGGER IF NOT EXISTS evidence_fts_ai AFTER INSERT ON evidence BEGIN
           INSERT INTO evidence_fts(rowid, content, locator) VALUES (new.id, new.content, new.locator);
       END""",
    """CREATE TRIGGER IF NOT EXISTS evidence_fts_ad AFTER DELETE ON evidence BEGIN
           INSERT INTO evidence_fts(evidence_fts, rowid, content, locator)
           VALUES ('delete', old.id, old.content, old.locator);
       END""",
    """CREATE TRIGGER IF NOT EXISTS evidence_fts_au AFTER UPDATE OF content, locator ON evidence BEGIN
           INSERT INTO evidence_fts(evidence_fts, rowid, content, locator)
           VALUES ('delete', old.id, old.content, old.locator);
           INSERT INTO evidence_fts(rowid, content, locator) VALUES (new.id, new.content, new.locator);
       END""",
]


def ensure_fts(engine: Engine) -> None:
    """Create the index and triggers if missing; rebuild it if it is out of step."""
    with engine.begin() as conn:
        for stmt in DDL:
            conn.execute(text(stmt))
        n_ev = conn.execute(text("SELECT COUNT(*) FROM evidence")).scalar()
        n_fts = conn.execute(text("SELECT COUNT(*) FROM evidence_fts_docsize")).scalar()
        if n_ev != n_fts:
            conn.execute(text("INSERT INTO evidence_fts(evidence_fts) VALUES ('rebuild')"))


# Words that carry no meaning for retrieval. Kept short on purpose: names and
# figures are never dropped.
STOPWORDS = frozenset("""
a an and are as at be by did do does for from had has have how i in is it its me my of on or our
so than that the their them then there these they this to was we were what when where which who
whom why will with you your
""".split())

_TERM = re.compile(r"[^\s\"]+")


def terms(query: str) -> list[str]:
    """Search terms from free text. Punctuation at the edges is dropped; terms
    with no letters or digits are ignored; stopwords are removed."""
    out = []
    for raw in _TERM.findall(query):
        t = raw.strip("()[]{}.,;:!?'*^+-~<>=|\\/`")
        if not t or not re.search(r"\w", t) or t.casefold() in STOPWORDS:
            continue
        if t.casefold() not in (x.casefold() for x in out):
            out.append(t)
    return out


def quote(term: str) -> str:
    """One FTS5 string. Quoting makes every operator character literal, so user
    text can never become FTS5 syntax (NEAR, AND, column filters, '*')."""
    return '"' + term.replace('"', '""') + '"'


def match_expression(query_terms: list[str], *, all_terms: bool = False) -> str:
    return (" AND " if all_terms else " OR ").join(quote(t) for t in query_terms)
