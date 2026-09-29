"""Tests for app/bootstrap_db.py. Fully mocked: a FakeConnection/
FakeCursor pair stands in for psycopg so these never touch a real
Postgres or AWS. See app/bootstrap_db.py's docstring for the design
this exercises (master vs. app credentials kept separate, idempotent
role/database creation, least-privilege grants).
"""

import json
import re

import pytest
from psycopg import errors as pg_errors

from app.bootstrap_db import (
    _quote_identifier,
    _quote_literal,
    bootstrap,
    get_app_target,
    get_master_credentials,
    lambda_handler,
)
from app.core import config

ROLE_RE = re.compile(r'^CREATE ROLE "([^"]+)"')
DATABASE_RE = re.compile(r'^CREATE DATABASE "([^"]+)"')


class FakeCursor:
    def __init__(self, state: dict) -> None:
        self.state = state
        self._last_fetch: tuple | None = None

    def execute(self, query: str, params: tuple | None = None) -> None:
        self.state["executed"].append((query, params))
        self._last_fetch = None

        if "FROM pg_roles" in query:
            self._last_fetch = (1,) if params[0] in self.state["roles"] else None
        elif "FROM pg_database" in query:
            self._last_fetch = (1,) if params[0] in self.state["databases"] else None
        elif query.startswith("CREATE ROLE"):
            role = ROLE_RE.match(query).group(1)
            if self.state.get("raise_duplicate_role"):
                raise pg_errors.DuplicateObject("role already exists")
            self.state["roles"].add(role)
        elif query.startswith("CREATE DATABASE"):
            dbname = DATABASE_RE.match(query).group(1)
            if self.state.get("raise_duplicate_database"):
                raise pg_errors.DuplicateDatabase("database already exists")
            self.state["databases"].add(dbname)

    def fetchone(self) -> tuple | None:
        return self._last_fetch

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


class FakeConnection:
    def __init__(self, state: dict, **kwargs: object) -> None:
        self.state = state
        self.state["connections"].append(dict(kwargs))

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.state)

    def close(self) -> None:
        pass


@pytest.fixture()
def fake_pg_state() -> dict:
    return {
        "roles": set(),
        "databases": set(),
        "connections": [],
        "executed": [],
    }


@pytest.fixture()
def fake_connect(monkeypatch: pytest.MonkeyPatch, fake_pg_state: dict):
    def _connect(**kwargs: object) -> FakeConnection:
        return FakeConnection(fake_pg_state, **kwargs)

    monkeypatch.setattr("app.bootstrap_db._connect", _connect)
    return _connect


@pytest.fixture()
def local_master_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "USE_SSM", False)
    monkeypatch.setenv("MASTER_DB_HOST", "postgres")
    monkeypatch.setenv("MASTER_DB_PORT", "5432")
    monkeypatch.setenv("MASTER_DB_USER", "postgres")
    monkeypatch.setenv("MASTER_DB_PASSWORD", "postgres")


@pytest.fixture()
def app_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "USE_SSM", False)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://hub_dev_user:hub_dev_password@postgres:5432/hub_dev",
    )


# ---- get_app_target() ----


def test_get_app_target_rejects_sqlite_database_url(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", False)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./hub.db")

    with pytest.raises(RuntimeError, match="not Postgres"):
        get_app_target()


def test_get_app_target_parses_postgres_url(app_database_url):
    target = get_app_target()

    assert target == {
        "role": "hub_dev_user",
        "password": "hub_dev_password",
        "dbname": "hub_dev",
    }


def test_get_app_target_decodes_special_characters_in_password(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", False)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://hub_dev_user:p%40ss%2Fword@postgres:5432/hub_dev",
    )

    target = get_app_target()

    assert target["password"] == "p@ss/word"


# ---- get_master_credentials() ----


def test_get_master_credentials_local_reads_env_vars(local_master_env):
    creds = get_master_credentials()

    assert creds == {
        "host": "postgres",
        "port": 5432,
        "user": "postgres",
        "password": "postgres",
    }


def test_get_master_credentials_ssm_reads_from_master_param(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", True)
    monkeypatch.setenv("MASTER_DB_PARAM_NAME", "/dnls-shared/aurora-master")
    fetched: list[str] = []

    def fake_fetch(name: str) -> str:
        fetched.append(name)
        return json.dumps(
            {"username": "master", "password": "s3cret", "host": "db.internal", "port": 5432}
        )

    monkeypatch.setattr(config, "_fetch_ssm_parameter", fake_fetch)

    creds = get_master_credentials()

    assert creds == {
        "host": "db.internal",
        "port": 5432,
        "user": "master",
        "password": "s3cret",
    }
    assert fetched == ["/dnls-shared/aurora-master"]


def test_master_credentials_are_a_separate_source_from_app_credentials(
    local_master_env, app_database_url
):
    """The app's own DB_PARAM_NAME/DATABASE_URL must never be read for
    master credentials, and vice versa."""
    master = get_master_credentials()
    target = get_app_target()

    assert master["user"] != target["role"]
    assert master["password"] != target["password"]


# ---- _quote_identifier() ----


def test_quote_identifier_accepts_normal_names():
    assert _quote_identifier("hub_dev_user") == '"hub_dev_user"'


def test_quote_identifier_rejects_unsafe_names():
    with pytest.raises(ValueError):
        _quote_identifier('hub"; DROP TABLE users; --')


def test_quote_literal_escapes_embedded_quotes():
    assert _quote_literal("p@ss'; DROP TABLE users; --") == "'p@ss''; DROP TABLE users; --'"


# ---- bootstrap() ----


def test_bootstrap_creates_role_and_database(
    local_master_env, app_database_url, fake_connect, fake_pg_state
):
    bootstrap()

    assert fake_pg_state["roles"] == {"hub_dev_user"}
    assert fake_pg_state["databases"] == {"hub_dev"}


def test_bootstrap_created_role_is_not_superuser(
    local_master_env, app_database_url, fake_connect, fake_pg_state
):
    bootstrap()

    create_role_statements = [
        query for query, _ in fake_pg_state["executed"] if query.startswith("CREATE ROLE")
    ]
    assert len(create_role_statements) == 1
    statement = create_role_statements[0]
    assert "NOSUPERUSER" in statement
    assert "NOCREATEDB" in statement
    assert "NOCREATEROLE" in statement
    assert "SUPERUSER" not in statement.replace("NOSUPERUSER", "")
    assert "CREATEDB" not in statement.replace("NOCREATEDB", "")
    assert "CREATEROLE" not in statement.replace("NOCREATEROLE", "")


def test_bootstrap_role_password_matches_app_database_url(
    local_master_env, app_database_url, fake_connect, fake_pg_state
):
    bootstrap()

    create_role_statements = [
        query for query, _ in fake_pg_state["executed"] if query.startswith("CREATE ROLE")
    ]
    assert create_role_statements == [
        "CREATE ROLE \"hub_dev_user\" WITH LOGIN PASSWORD 'hub_dev_password' "
        "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION"
    ]


def test_bootstrap_grants_only_connect_usage_and_create(
    local_master_env, app_database_url, fake_connect, fake_pg_state
):
    bootstrap()

    grants = [query for query, _ in fake_pg_state["executed"] if query.startswith("GRANT")]

    assert grants == [
        'GRANT CONNECT ON DATABASE "hub_dev" TO "hub_dev_user"',
        'GRANT USAGE, CREATE ON SCHEMA public TO "hub_dev_user"',
    ]


def test_bootstrap_never_grants_superuser_or_all_privileges(
    local_master_env, app_database_url, fake_connect, fake_pg_state
):
    bootstrap()

    for query, _ in fake_pg_state["executed"]:
        assert "SUPERUSER" not in query.replace("NOSUPERUSER", "")
        assert "ALL PRIVILEGES" not in query
        assert "ALTER ROLE" not in query


def test_bootstrap_uses_admin_database_then_target_database(
    local_master_env, app_database_url, fake_connect, fake_pg_state
):
    bootstrap()

    dbnames_connected = [conn["dbname"] for conn in fake_pg_state["connections"]]
    assert dbnames_connected == ["postgres", "hub_dev"]


def test_bootstrap_is_idempotent_running_twice(
    local_master_env, app_database_url, fake_connect, fake_pg_state
):
    bootstrap()
    bootstrap()

    create_role_statements = [
        q for q, _ in fake_pg_state["executed"] if q.startswith("CREATE ROLE")
    ]
    create_database_statements = [
        q for q, _ in fake_pg_state["executed"] if q.startswith("CREATE DATABASE")
    ]

    assert len(create_role_statements) == 1
    assert len(create_database_statements) == 1
    # GRANTs re-run every time (idempotent on the Postgres side).
    grants = [q for q, _ in fake_pg_state["executed"] if q.startswith("GRANT")]
    assert len(grants) == 4


def test_bootstrap_handles_role_created_concurrently(
    local_master_env, app_database_url, fake_connect, fake_pg_state
):
    fake_pg_state["raise_duplicate_role"] = True
    fake_pg_state["raise_duplicate_database"] = True

    bootstrap()  # must not raise despite the pre-check racing with creation


def test_bootstrap_does_not_recreate_existing_role_or_database(
    local_master_env, app_database_url, fake_connect, fake_pg_state
):
    fake_pg_state["roles"].add("hub_dev_user")
    fake_pg_state["databases"].add("hub_dev")

    bootstrap()

    create_statements = [
        q
        for q, _ in fake_pg_state["executed"]
        if q.startswith("CREATE ROLE") or q.startswith("CREATE DATABASE")
    ]
    assert create_statements == []


def test_bootstrap_import_has_no_side_effects():
    """Importing the module must not touch any credentials or open a
    connection — only calling bootstrap()/main() should."""
    import importlib

    import app.bootstrap_db as bootstrap_db

    importlib.reload(bootstrap_db)


# ---- lambda_handler() ----


def test_lambda_handler_runs_bootstrap_and_returns_success(
    local_master_env, app_database_url, fake_connect, fake_pg_state
):
    result = lambda_handler({}, None)

    assert result == {"status": "ok", "message": "Bootstrap complete."}
    assert fake_pg_state["roles"] == {"hub_dev_user"}
    assert fake_pg_state["databases"] == {"hub_dev"}


def test_lambda_handler_reads_same_env_vars_as_cli_via_ssm(monkeypatch, fake_connect, fake_pg_state):
    """The Lambda path uses MASTER_DB_PARAM_NAME/DB_URL_PARAM_NAME (USE_SSM
    on) — the same resolution the CLI uses, not a separate source."""
    monkeypatch.setattr(config, "USE_SSM", True)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setenv("MASTER_DB_PARAM_NAME", "/dnls-shared/aurora-master")
    monkeypatch.setenv("DB_URL_PARAM_NAME", "/hub-dev/db-url-direct")

    def fake_fetch(name: str) -> str:
        if name == "/dnls-shared/aurora-master":
            return json.dumps(
                {"username": "master", "password": "s3cret", "host": "db.internal", "port": 5432}
            )
        if name == "/hub-dev/db-url-direct":
            return (
                "postgresql://hub_dev_user:hub_dev_password@db.internal:5432"
                "/hub_dev?sslmode=require"
            )
        raise AssertionError(f"unexpected SSM parameter: {name}")

    monkeypatch.setattr(config, "_fetch_ssm_parameter", fake_fetch)

    result = lambda_handler({}, None)

    assert result == {"status": "ok", "message": "Bootstrap complete."}
    assert fake_pg_state["roles"] == {"hub_dev_user"}
    assert fake_pg_state["databases"] == {"hub_dev"}


def test_lambda_handler_propagates_exceptions(monkeypatch):
    """A failed bootstrap must surface as a failed Lambda invocation,
    not a caught/swallowed error — unlike main(), which catches and
    exits(1) for a CLI-friendly message instead."""
    monkeypatch.setattr(config, "USE_SSM", False)
    monkeypatch.delenv("MASTER_DB_HOST", raising=False)

    with pytest.raises(KeyError):
        lambda_handler({}, None)
