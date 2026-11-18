"""Shared fixtures. Every test gets its own temporary database."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import init_db, make_engine, make_session_factory
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, db_filename="test.db", log_level="WARNING")


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as c:  # runs the lifespan, so init_db happens
        yield c


@pytest.fixture
def engine(settings):
    eng = make_engine(settings.database_url)
    init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        session.close()
