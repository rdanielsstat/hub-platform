from pathlib import Path

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

    def _boom(database_url: str) -> None:
        raise AssertionError("migrations must not run with USE_SSM on")

    monkeypatch.setattr(init_local, "upgrade_to_head", _boom)

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
        second = Store(db).list_projects(
            Store(db).get_user_by_email(SEED_USER_EMAIL).id
        )

    assert len(second) == len(first)


# ---- `python -m app.db.init_local` reads backend/.env ------------------


@pytest.fixture()
def env_file(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Point main() at a throwaway .env instead of the developer's real
    one, and make sure anything it loads is undone afterwards."""
    for var in ("SEED_DEMO_DATA", "USE_SSM"):
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / ".env"
    monkeypatch.setattr(init_local, "ENV_FILE", path)
    return path


def test_main_reads_seed_demo_data_from_env_file(local_sqlite, env_file):
    env_file.write_text("SEED_DEMO_DATA=true\n")

    init_local.main()

    assert _has_users()


def test_main_shell_env_wins_over_env_file(local_sqlite, env_file, monkeypatch):
    env_file.write_text("SEED_DEMO_DATA=true\n")
    monkeypatch.setenv("SEED_DEMO_DATA", "false")

    init_local.main()

    assert not _has_users()


def test_main_refuses_use_ssm_from_env_file(local_sqlite, env_file):
    env_file.write_text("USE_SSM=true\nSEED_DEMO_DATA=true\n")

    with pytest.raises(SystemExit):
        init_local.main()


def test_main_without_env_file_does_not_seed(local_sqlite, env_file):
    assert not env_file.exists()

    init_local.main()

    assert not _has_users()


def test_env_file_is_backend_dotenv():
    assert init_local.ENV_FILE == Path(__file__).resolve().parent.parent / ".env"
