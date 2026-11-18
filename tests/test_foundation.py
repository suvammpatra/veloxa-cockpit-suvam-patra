"""Phase 1: the app starts, the database initialises, health and errors behave."""

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.config import Settings
from app.database import SCHEMA_VERSION, init_db
from app.main import create_app


def test_health_reports_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["llm_enabled"] is False


def test_startup_creates_database_file(client, settings):
    assert settings.database_path.exists()


def test_init_db_records_schema_version_and_is_idempotent(engine):
    init_db(engine)  # second call must not fail or duplicate
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT key, value FROM app_meta")).all()
    assert rows == [("schema_version", SCHEMA_VERSION)]
    assert "app_meta" in inspect(engine).get_table_names()


def test_sqlite_foreign_keys_enabled(engine):
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_defaults_need_no_env_or_api_key(monkeypatch):
    for var in ("VELOXA_LLM_ENABLED", "VELOXA_DATA_DIR"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.llm_enabled is False
    assert s.database_url.startswith("sqlite:///")
    assert s.database_path.name == "cockpit.db"


def test_unknown_route_returns_json_404(client):
    resp = client.get("/no-such-page")
    assert resp.status_code == 404
    assert resp.json()["error"] == "http_error"


def test_unhandled_error_is_hidden_and_returns_500(settings):
    app = create_app(settings)

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/boom")
    assert resp.status_code == 500
    assert resp.json() == {"error": "internal_error",
                           "detail": "An unexpected error occurred."}
    assert "secret" not in resp.text
