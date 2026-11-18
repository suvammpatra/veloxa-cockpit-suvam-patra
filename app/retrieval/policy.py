"""Which evidence a retrieval may return (privacy and use limits).

  * Restricted sources (the payroll register) are never returned by search
    unless the caller asks for them explicitly. Their evidence rows hold no
    amounts, but they are per-person pay records (DECISIONS.md 3, 4).
  * Purpose-limited sources are returned only for the purpose they are
    allowed for. 09.eml may be used only for a question directly about Atlas
    ownership, never to infer resignation, dissatisfaction or motive
    (DECISIONS.md 23).
  * Copies and reference files (Email_Printouts.pdf, README.txt, the brief)
    are left out by default: a copy is not a second source, and reference
    files are not evidence (ARCHITECTURE.md 2, 15.1).
"""

from __future__ import annotations

from sqlalchemy import Select, not_

from app.models import SourceRecord

PURPOSE_LIMITED: dict[str, tuple[str, ...]] = {
    "09.eml": ("atlas_ownership",),  # DECISIONS.md 23
}

DEFAULT_ROLES = ("evidence",)


def apply(stmt: Select, *, include_restricted: bool = False, purpose: str | None = None,
          roles: tuple[str, ...] = DEFAULT_ROLES) -> Select:
    """Add policy conditions to a query that already joins SourceRecord."""
    stmt = stmt.where(SourceRecord.role.in_(roles), SourceRecord.status != "failed")
    if not include_restricted:
        stmt = stmt.where(SourceRecord.access != "restricted")
    blocked = [name for name, purposes in PURPOSE_LIMITED.items() if purpose not in purposes]
    if blocked:
        stmt = stmt.where(not_(SourceRecord.filename.in_(blocked)))
    return stmt


def allowed(source: SourceRecord, *, include_restricted: bool = False, purpose: str | None = None,
            roles: tuple[str, ...] = DEFAULT_ROLES) -> str | None:
    """None if the source may be used; otherwise the reason it may not."""
    if source.status == "failed":
        return "source_failed"
    if source.access == "restricted" and not include_restricted:
        return "restricted"
    if source.filename in PURPOSE_LIMITED and purpose not in PURPOSE_LIMITED[source.filename]:
        return "purpose_limited"
    if source.role not in roles:
        return f"role_{source.role}"
    return None

