"""The worry list endpoint (Phase 7; DECISIONS.md 11-16; ARCHITECTURE.md 16.16).

Read-only. It takes a time frame and nothing else: no purpose, no privacy switch and no
weights, so a caller cannot widen what is read or change the order.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.temporal import TimeContext
from app.worries.engine import evaluate, to_dict

router = APIRouter(prefix="/api", tags=["worries"])


@router.get("/worries")
def worries(as_of: str | None = None, mode: str = Query("known", pattern="^(known|recorded)$"),
            db: Session = Depends(get_db)):
    try:
        ctx = TimeContext.recorded_by(as_of) if mode == "recorded" else TimeContext.known_at(as_of)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"as_of is not a date or time: {as_of!r}") from exc
    return to_dict(evaluate(db, ctx))
