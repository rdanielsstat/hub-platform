"""SQLAlchemy engine and session setup.

Database-agnostic: app/core/config.py's DATABASE_URL decides SQLite vs
Postgres, and nothing here (or in orm.py) assumes SQLite-only behavior
except the one guarded exception below (enabling FK enforcement, which
Postgres already does natively).
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DATABASE_URL
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


# SQLite needs this so a connection can be used from a different thread
# than the one that created it (FastAPI runs sync routes in a
# threadpool); Postgres connections don't have this restriction.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
enable_sqlite_foreign_keys(engine, DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_tables() -> None:
    """v1 migration story: create tables on startup if they don't exist.
    No Alembic yet — the schema is still moving pre-launch. Once it
    stabilizes, swap this for real Alembic migrations so future schema
    changes are tracked and reversible instead of implicit."""
    Base.metadata.create_all(bind=engine)


def get_db_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
