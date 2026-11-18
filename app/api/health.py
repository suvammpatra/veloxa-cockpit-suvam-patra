from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.database import check_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> JSONResponse:
    db_ok = check_db(request.app.state.engine)
    body = {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "unavailable",
        "version": __version__,
        "llm_enabled": request.app.state.settings.llm_enabled,
    }
    return JSONResponse(body, status_code=200 if db_ok else 503)
