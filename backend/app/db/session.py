"""SQLAlchemy engine and session setup.

Database-agnostic: app/core/config.py's get_database_url() decides
SQLite vs Postgres, and nothing here (or in orm.py) assumes
SQLite-only behavior except the one guarded exception below (enabling
FK enforcement, which Postgres already does natively).
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_database_url
from app.db.orm import Base


def enable_sqlite_foreign_keys(target_engine: Engine, database_url: str) -> None:
    """SQLite doesn't enforce foreign keys by default; Postgres always
    does. Attach this to any SQLite engine (the app's, or a test's own)
    so behavior stays consistent with prod instead of silently allowing
    orphaned rows. No-op for a non-SQLite URL.

    A plain module-level engine listener isn't enough here: tests build
    their own separate engine per test (see tests/conftest.py) rather
    than reusing this module's `engine`, so this has to be callable
    per-engine, not just attached once at import time.
    """
    if not database_url.startswith("sqlite"):
        return

    @event.listens_for(target_engine, "connect")
    def _enable(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Built lazily on first use, not at import: get_database_url() may hit
# AWS SSM, and resolving it eagerly at module import would turn a
# transient SSM/DB outage into an import-time crash, and importing the
# app must do no database work at all (see app/main.py). Cached after the
# first build, same as config.py's own get_database_url()/
# get_jwt_secret() caches.
_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        database_url = get_database_url()
        # SQLite needs this so a connection can be used from a
        # different thread than the one that created it (FastAPI runs
        # sync routes in a threadpool); Postgres connections don't
        # have this restriction.
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        # pool_pre_ping: test each pooled connection on checkout and
        # replace it if the server dropped it, instead of failing the
        # request. Neon's pooler closes idle connections and its compute
        # scales to zero, so a warm Lambda routinely holds dead ones.
        # A pool-level option, valid for every dialect, SQLite included.
        engine = create_engine(
            database_url, connect_args=connect_args, pool_pre_ping=True
        )
        enable_sqlite_foreign_keys(engine, database_url)
        _engine = engine
    return _engine


def _get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=_get_engine(), autoflush=False, expire_on_commit=False
        )
    return _session_factory


def SessionLocal() -> Session:
    """A new Session, bound to the lazily-built engine. Kept as a
    zero-arg callable (`SessionLocal()`) so existing call sites don't
    need to know the engine behind it is built lazily."""
    return _get_session_factory()()


def create_tables() -> None:
    """v1 migration story: create tables if they don't exist. Called by
    the local init step (app/db/init_local.py), never at app import.
    No Alembic yet — the schema is still moving pre-launch. Once it
    stabilizes, swap this for real Alembic migrations so future schema
    changes are tracked and reversible instead of implicit."""
    Base.metadata.create_all(bind=_get_engine())


def get_db_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
