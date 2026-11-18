"""SQLite engine, session factory and schema initialisation."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

log = logging.getLogger(__name__)

SCHEMA_VERSION = "4"


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db(engine: Engine) -> None:
    """Create all tables. Safe to call on every start."""
    from app import models  # noqa: F401  (registers every model on Base)
    from app.models.meta import AppMeta

    _guard_schema_version(engine)
    Base.metadata.create_all(engine)
    from app.retrieval.fts import ensure_fts
    ensure_fts(engine)
    with Session(engine) as session:
        row = session.get(AppMeta, "schema_version")
        if row is None:
            session.add(AppMeta(key="schema_version", value=SCHEMA_VERSION))
        else:
            row.value = SCHEMA_VERSION
        session.commit()
    log.info("Database ready (schema version %s)", SCHEMA_VERSION)


class SchemaMismatch(RuntimeError):
    pass


def _guard_schema_version(engine: Engine) -> None:
    """There are no migrations. An older schema with no sources in it is rebuilt;
    one that holds ingested sources is never dropped, and the app stops instead."""
    insp = inspect(engine)
    if "app_meta" not in insp.get_table_names():
        return
    with engine.connect() as conn:
        found = conn.execute(text("SELECT value FROM app_meta WHERE key='schema_version'")).scalar()
        if found in (None, SCHEMA_VERSION):
            return
        has_sources = ("source_record" in insp.get_table_names() and
                       conn.execute(text("SELECT COUNT(*) FROM source_record")).scalar())
    if has_sources:
        raise SchemaMismatch(
            f"Database schema {found} is older than {SCHEMA_VERSION} and holds ingested sources. "
            "Move the database file aside and ingest again.")
    log.warning("Rebuilding empty database from schema %s to %s", found, SCHEMA_VERSION)
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        for t in inspect(engine).get_table_names():
            conn.execute(text(f'DROP TABLE IF EXISTS "{t}"'))


def check_db(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - health check reports, never raises
        log.exception("Database health check failed")
        return False


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
