"""Read-only evidence endpoints over the retrieval layer.

Restricted and purpose-limited evidence is never returned here: these
endpoints take no switch for it (app.retrieval.policy). The question-answering
layer decides purpose; a raw search cannot.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.retrieval.search import Filters, SearchError, get_evidence, search
from app.temporal import TimeContext

router = APIRouter(prefix="/api", tags=["evidence"])


def _ctx(as_of: str | None, mode: str) -> TimeContext:
    try:
        if mode == "recorded":
            return TimeContext.recorded_by(as_of, knowledge_cutoff=None)
        return TimeContext.known_at(as_of)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"as_of is not a date or time: {as_of!r}") from exc


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


@router.get("/search")
def search_evidence(
    q: str | None = None,
    as_of: str | None = None,
    mode: str = Query("known", pattern="^(known|recorded)$"),
    person: str | None = None,
    department: str | None = None,
    source: list[str] = Query(default=[]),
    system: list[str] = Query(default=[]),
    file_type: list[str] = Query(default=[]),
    max_trust_rung: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 10,
    all_terms: bool = False,
    db: Session = Depends(get_db),
):
    ctx = _ctx(as_of, mode)
    filters = Filters(person=person, department=department, source_keys=tuple(source), systems=tuple(system),
                      file_types=tuple(file_type), max_trust_rung=max_trust_rung, date_from=date_from,
                      date_to=date_to)
    try:
        result = search(db, q, ctx, filters, limit=limit, all_terms=all_terms)
    except SearchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _jsonable(asdict(result))


@router.get("/evidence/{key}")
def evidence_by_key(key: str, as_of: str | None = None, mode: str = Query("known", pattern="^(known|recorded)$"),
                    db: Session = Depends(get_db)):
    ctx = _ctx(as_of, mode)
    try:
        hit = get_evidence(db, key, ctx)
    except SearchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if hit is None:
        raise HTTPException(status_code=404, detail=f"No usable evidence {key} at this date.")
    return _jsonable(asdict(hit))
