import pytest
from sqlalchemy import inspect

from app.core import config
from app.db import init_local, session
from app.db.seed import SEED_USER_EMAIL
from app.db.store import Store


@pytest.fixture()
def local_sqlite(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Point the app's lazily-built engine at a throwaway SQLite file,
    and put it back afterwards."""
    monkeypatch.setattr(config, "USE_SSM", False)
    monkeypatch.setattr(config, "_database_url", f"sqlite:///{tmp_path / 'hub.db'}")
    monkeypatch.setattr(session, "_engine", None)
    monkeypatch.setattr(session, "_session_factory", None)
    yield
    if session._engine is not None:
        session._engine.dispose()


def _has_users() -> bool:
    with session.SessionLocal() as db:
        return Store(db).has_users()


def test_init_local_refuses_to_run_with_use_ssm(monkeypatch):
    """Refuses before any database work, whatever SEED_DEMO_DATA says."""

    def _boom() -> None:
        raise AssertionError("create_tables must not run with USE_SSM on")

    monkeypatch.setattr(init_local, "create_tables", _boom)

    with pytest.raises(RuntimeError, match="USE_SSM"):
        init_local.init_local(use_ssm=True, seed_demo_data=False)


def test_init_local_creates_tables_without_seeding_by_default(local_sqlite):
    init_local.init_local(use_ssm=False, seed_demo_data=False)

    tables = set(inspect(session._get_engine()).get_table_names())
    assert {"users", "projects"} <= tables
    assert not _has_users()


def test_init_local_seeds_when_seed_demo_data_is_on(local_sqlite):
    init_local.init_local(use_ssm=False, seed_demo_data=True)

    with session.SessionLocal() as db:
        assert Store(db).get_user_by_email(SEED_USER_EMAIL) is not None


def test_init_local_never_reseeds_an_existing_database(local_sqlite):
    init_local.init_local(use_ssm=False, seed_demo_data=True)
    with session.SessionLocal() as db:
        first = Store(db).list_projects(Store(db).get_user_by_email(SEED_USER_EMAIL).id)

    init_local.init_local(use_ssm=False, seed_demo_data=True)
    with session.SessionLocal() as db:
        second = Store(db).list_projects(Store(db).get_user_by_email(SEED_USER_EMAIL).id)

    assert len(second) == len(first)
