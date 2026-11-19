"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app import __version__
from app.api import agents, answers, evidence, health, worries
from app.api.errors import register_error_handlers
from app.config import Settings, get_settings
from app.database import init_db, make_engine, make_session_factory
from app.logging_config import setup_logging

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    settings.data_path.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(engine)
        log.info("Veloxa CXO Cockpit %s started; database at %s",
                 __version__, settings.database_path)
        yield
        engine.dispose()

    app = FastAPI(title="Veloxa CXO Cockpit", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(evidence.router)
    app.include_router(answers.router)
    app.include_router(agents.router)
    app.include_router(worries.router)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """The CEO page: the worry list first, the question box below (DECISIONS.md 12)."""
        return FileResponse(Path(__file__).parent / "web" / "index.html", media_type="text/html")

    return app
