"""The question endpoint: five-field answers (ARCHITECTURE.md 6, 9).

There is no purpose or privacy parameter. Extra query parameters are ignored,
so a caller cannot unlock purpose-limited or restricted records.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.answering.engine import ask
from app.answering.model import to_dict
from app.api.deps import get_db
from app.privacy.payroll import PayrollStore
from app.temporal import TimeContext

router = APIRouter(prefix="/api", tags=["answers"])


@router.get("/ask")
def ask_question(request: Request, q: str = Query(..., max_length=500), as_of: str | None = None,
                 mode: str = Query("known", pattern="^(known|recorded)$"), db: Session = Depends(get_db)):
    try:
        ctx = None
        if as_of or mode == "recorded":
            ctx = TimeContext.recorded_by(as_of) if mode == "recorded" else TimeContext.known_at(as_of)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"as_of is not a date or time: {as_of!r}") from exc
    settings = request.app.state.settings
    store = PayrollStore(settings.payroll_path) if settings.payroll_path.exists() else None
    try:
        answer = ask(db, q, ctx, payroll=store.aggregator() if store else None,
                     llm_enabled=settings.llm_enabled)
    finally:
        if store:
            store.dispose()
    return to_dict(answer)
