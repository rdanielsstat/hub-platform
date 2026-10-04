"""Integration tests: the real app and Store against real Postgres.

Needs the Docker Compose Postgres (Postgres 17, matching Neon). From the
repo root: `make test-integration`, or by hand:

    docker compose up -d --wait postgres
    cd backend && uv run pytest -m integration

Deselected from a plain `uv run pytest` (see pyproject.toml).

Each session creates a throwaway database (hub_it_<random>) with the
Compose superuser, builds its schema with the real Alembic migrations
(so the migrations themselves are exercised on Postgres), and drops it
at the end. The Compose app's own hub_dev database is never touched.
Between tests every table is truncated, so tests stay independent.

INTEGRATION_ADMIN_URL overrides where that superuser connection goes
(default: the Compose service's published port on localhost).

The fixtures here override tests/conftest.py's `store` with a
Postgres-backed one, so its `client` and `register_and_login` fixtures
work unchanged against Postgres.
"""

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.db.migrations import upgrade_to_head
from app.db.store import Store

# The Compose superuser (docker-compose.yml). Local-only dev defaults.
ADMIN_URL = os.environ.get(
    "INTEGRATION_ADMIN_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
)

APP_TABLES = "users, auth_identities, projects, notes"


def admin_engine() -> Engine:
    return create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")


@contextmanager
def throwaway_database() -> Iterator[str]:
    """A brand-new, empty database; yields its URL, drops it afterwards."""
    name = f"hub_it_{uuid.uuid4().hex[:12]}"
    admin = admin_engine()
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except OperationalError as exc:
        admin.dispose()
        where = make_url(ADMIN_URL).render_as_string(hide_password=True)
        pytest.fail(
            f"Can't reach Postgres at {where}. Start it with `make docker-up` "
            "(or `docker compose up -d --wait postgres`) from the repo root, "
            f"or set INTEGRATION_ADMIN_URL.\n{exc}",
            pytrace=False,
        )
    try:
        yield (
            make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
        )
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """One migrated database for the whole session."""
    with throwaway_database() as url:
        upgrade_to_head(url)
        yield url


@pytest.fixture(scope="session")
def pg_engine(pg_url: str) -> Iterator[Engine]:
    engine = create_engine(pg_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def store(pg_engine: Engine) -> Iterator[Store]:
    """Overrides tests/conftest.py's SQLite store. Starts from empty
    tables every test."""
    with pg_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {APP_TABLES} CASCADE"))
    db = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)()
    try:
        yield Store(db)
    finally:
        db.close()


@pytest.fixture()
def fresh_database() -> Iterator[str]:
    """An empty, unmigrated database of its own, for migration tests."""
    with throwaway_database() as url:
        yield url
