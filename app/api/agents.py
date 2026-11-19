"""Agent profile endpoints. Read-only; no purpose or privacy parameter (extra parameters are
ignored), so a profile cannot be used to reach restricted or purpose-limited records."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.agents.profiles import agent_profile, all_profiles, find_agent, to_dict
from app.api.deps import get_db
from app.temporal import TimeContext

router = APIRouter(prefix="/api", tags=["agents"])


def _ctx(as_of: str | None, mode: str) -> TimeContext:
    try:
        return TimeContext.recorded_by(as_of) if mode == "recorded" else TimeContext.known_at(as_of)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"as_of is not a date or time: {as_of!r}") from exc


@router.get("/agents")
def list_agents(as_of: str | None = None, mode: str = Query("known", pattern="^(known|recorded)$"),
                db: Session = Depends(get_db)):
    return [{"agent": p.agent, "name": p.name, "agent_group": p.agent_group, "status": p.status,
             "emp_id": p.emp_id} for p in all_profiles(db, _ctx(as_of, mode))]


@router.get("/agents/{agent}")
def get_agent(agent: str, as_of: str | None = None, mode: str = Query("known", pattern="^(known|recorded)$"),
              db: Session = Depends(get_db)):
    spec = find_agent(agent)
    if spec is None:
        raise HTTPException(status_code=404, detail="No agent by that name. There are 14 agents (ARCHITECTURE.md 8).")
    return to_dict(agent_profile(db, spec, _ctx(as_of, mode)))
