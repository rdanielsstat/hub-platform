"""The app's engine (app/db/session.py) recovering from connections that
die underneath its pool: Neon's pooler closes idle connections and its
compute scales to zero, so a warm Lambda routinely holds dead ones."""

import pytest
from sqlalchemy import text

from app.core import config
from app.db import session


@pytest.fixture()
def app_engine(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """The real _get_engine(), pointed at a throwaway SQLite file."""
    monkeypatch.setattr(config, "_database_url", f"sqlite:///{tmp_path / 'pool.db'}")
    monkeypatch.setattr(session, "_engine", None)
    monkeypatch.setattr(session, "_session_factory", None)
    engine = session._get_engine()
    yield engine
    engine.dispose()


def _kill_pooled_connection(engine) -> object:
    """Check a connection out, close its DBAPI connection behind the
    pool's back (as a server-side drop would), and return it to the
    pool. Returns the dead DBAPI connection."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        dead = conn.connection.dbapi_connection
    dead.close()
    return dead


def test_dead_pooled_connection_is_replaced_not_surfaced(app_engine):
    dead = _kill_pooled_connection(app_engine)

    with session.SessionLocal() as db:
        assert db.execute(text("SELECT 1")).scalar() == 1
        assert db.connection().connection.dbapi_connection is not dead


def test_dead_pooled_connection_is_replaced_on_repeated_drops(app_engine):
    for _ in range(3):
        _kill_pooled_connection(app_engine)

        with session.SessionLocal() as db:
            assert db.execute(text("SELECT 1")).scalar() == 1
