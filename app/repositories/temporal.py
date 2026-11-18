"""Point-in-time filters, applied in SQL so later records cannot leak (ARCHITECTURE.md 11)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, and_, or_

from app.temporal import Mode, TimeContext


def visible(stmt: Select, model, ctx: TimeContext) -> Select:
    """Restrict a query on a TemporalMixin model to what the time frame allows.

    KNOWN:    released_on <= as_of
    RECORDED: released_on <= knowledge cutoff AND exported_on <= as_of.
              Records with no exported_on (transcripts) are excluded, because
              when the company recorded them is unknown.
    """
    if ctx.mode is Mode.KNOWN:
        return stmt.where(model.released_on <= ctx.as_of)
    return stmt.where(
        model.released_on <= ctx.release_cutoff,
        model.exported_on.is_not(None),
        model.exported_on <= ctx.as_of,
    )


def released_by(stmt: Select, model, cutoff: datetime) -> Select:
    return stmt.where(model.released_on <= cutoff)


def valid_at(stmt: Select, model, at: datetime, *, release_cutoff: datetime,
             include_announced: bool = False) -> Select:
    """Effective-dated rows (ValidityMixin) that hold at `at` and were known by the cutoff."""
    statuses = ("confirmed", "announced") if include_announced else ("confirmed",)
    return stmt.where(
        model.released_on <= release_cutoff,
        model.status.in_(statuses),
        model.valid_from.is_not(None),
        model.valid_from <= at,
        or_(model.valid_to.is_(None), model.valid_to > at),
    )


def pending(stmt: Select, model, *, release_cutoff: datetime) -> Select:
    """Announced changes known by the cutoff (DECISIONS.md 18)."""
    return stmt.where(and_(model.released_on <= release_cutoff, model.status == "announced"))
