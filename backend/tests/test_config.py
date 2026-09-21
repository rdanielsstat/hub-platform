import json

import pytest

from app.core import config
from app.core.config import DEV_JWT_SECRET, require_safe_jwt_secret

REAL_LOOKING_SECRET = "a-unique-generated-secret-that-is-not-the-dev-default"


class _FakeSSMClient:
    """Stands in for the boto3 SSM client. `values` maps a parameter
    name to the raw string SSM would return as Parameter.Value."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values
        self.calls: list[str] = []

    def get_parameter(self, Name: str, WithDecryption: bool) -> dict:
        assert WithDecryption is True
        self.calls.append(Name)
        return {"Parameter": {"Value": self._values[Name]}}


def test_local_with_dev_secret_does_not_raise():
    require_safe_jwt_secret(
        environment="local", secret=DEV_JWT_SECRET, dev_default=DEV_JWT_SECRET
    )


def test_local_with_missing_secret_does_not_raise():
    require_safe_jwt_secret(
        environment="local", secret="", dev_default=DEV_JWT_SECRET
    )


def test_development_alias_is_also_treated_as_local():
    require_safe_jwt_secret(
        environment="development", secret=DEV_JWT_SECRET, dev_default=DEV_JWT_SECRET
    )


def test_local_check_is_case_insensitive():
    require_safe_jwt_secret(
        environment="Local", secret=DEV_JWT_SECRET, dev_default=DEV_JWT_SECRET
    )


def test_production_with_dev_secret_raises():
    with pytest.raises(RuntimeError):
        require_safe_jwt_secret(
            environment="production",
            secret=DEV_JWT_SECRET,
            dev_default=DEV_JWT_SECRET,
        )


def test_production_with_missing_secret_raises():
    with pytest.raises(RuntimeError):
        require_safe_jwt_secret(
            environment="production", secret="", dev_default=DEV_JWT_SECRET
        )


def test_any_non_local_environment_with_dev_secret_raises():
    with pytest.raises(RuntimeError):
        require_safe_jwt_secret(
            environment="staging", secret=DEV_JWT_SECRET, dev_default=DEV_JWT_SECRET
        )


def test_production_with_a_real_secret_does_not_raise():
    require_safe_jwt_secret(
        environment="production",
        secret=REAL_LOOKING_SECRET,
        dev_default=DEV_JWT_SECRET,
    )


def test_use_ssm_forces_strict_check_even_when_environment_is_local():
    with pytest.raises(RuntimeError):
        require_safe_jwt_secret(
            environment="local",
            secret=DEV_JWT_SECRET,
            dev_default=DEV_JWT_SECRET,
            use_ssm=True,
        )


def test_use_ssm_with_a_real_secret_and_local_environment_does_not_raise():
    require_safe_jwt_secret(
        environment="local",
        secret=REAL_LOOKING_SECRET,
        dev_default=DEV_JWT_SECRET,
        use_ssm=True,
    )


# ---- get_database_url() / get_jwt_secret(): local path (USE_SSM off) ----
#
# app.main is already imported by the time these run (tests/conftest.py
# imports it before any test module), which means get_database_url()/
# get_jwt_secret() were already called once and cached. Each test below
# resets the module's private cache to None first so it's exercising a
# fresh resolution, not conftest's leftover cached value.


def test_get_database_url_reads_env_var_when_use_ssm_is_off(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", False)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./somewhere.db")

    assert config.get_database_url() == "sqlite:///./somewhere.db"


def test_get_database_url_defaults_to_local_sqlite_file(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", False)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert config.get_database_url() == "sqlite:///./hub.db"


def test_get_jwt_secret_reads_env_var_when_use_ssm_is_off(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", False)
    monkeypatch.setattr(config, "_jwt_secret", None)
    monkeypatch.setenv("HUB_JWT_SECRET", REAL_LOOKING_SECRET)

    assert config.get_jwt_secret() == REAL_LOOKING_SECRET


def test_get_jwt_secret_defaults_to_dev_secret_when_use_ssm_is_off(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", False)
    monkeypatch.setattr(config, "_jwt_secret", None)
    monkeypatch.delenv("HUB_JWT_SECRET", raising=False)

    assert config.get_jwt_secret() == DEV_JWT_SECRET


def test_local_path_never_builds_an_ssm_client(monkeypatch):
    """Docker Compose runs with zero AWS access: with USE_SSM off,
    resolving settings must never even try to build an SSM client."""
    monkeypatch.setattr(config, "USE_SSM", False)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setattr(config, "_jwt_secret", None)

    def _boom() -> None:
        raise AssertionError("SSM client should not be built when USE_SSM is off")

    monkeypatch.setattr(config, "_get_ssm_client", _boom)

    config.get_database_url()
    config.get_jwt_secret()


# ---- get_database_url() / get_jwt_secret(): AWS SSM path (mocked) ----


def test_get_database_url_builds_postgres_url_from_ssm_json(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", True)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setenv("DB_PARAM_NAME", "/hub/prod/db")
    fake_client = _FakeSSMClient(
        {
            "/hub/prod/db": json.dumps(
                {
                    "username": "hub_app",
                    "password": "p@ss/word",
                    "host": "db.internal",
                    "port": 5432,
                    "dbname": "hub",
                }
            )
        }
    )
    monkeypatch.setattr(config, "_get_ssm_client", lambda: fake_client)

    url = config.get_database_url()

    assert url == "postgresql+psycopg://hub_app:p%40ss%2Fword@db.internal:5432/hub"


def test_get_database_url_from_ssm_is_cached_after_first_fetch(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", True)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setenv("DB_PARAM_NAME", "/hub/prod/db")
    fake_client = _FakeSSMClient(
        {
            "/hub/prod/db": json.dumps(
                {
                    "username": "u",
                    "password": "p",
                    "host": "h",
                    "port": 5432,
                    "dbname": "d",
                }
            )
        }
    )
    monkeypatch.setattr(config, "_get_ssm_client", lambda: fake_client)

    config.get_database_url()
    config.get_database_url()

    assert fake_client.calls == ["/hub/prod/db"]


def test_get_jwt_secret_reads_raw_value_from_ssm(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", True)
    monkeypatch.setattr(config, "_jwt_secret", None)
    monkeypatch.setenv("JWT_PARAM_NAME", "/hub/prod/jwt")
    fake_client = _FakeSSMClient({"/hub/prod/jwt": REAL_LOOKING_SECRET})
    monkeypatch.setattr(config, "_get_ssm_client", lambda: fake_client)

    assert config.get_jwt_secret() == REAL_LOOKING_SECRET


def test_get_jwt_secret_from_ssm_is_cached_after_first_fetch(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", True)
    monkeypatch.setattr(config, "_jwt_secret", None)
    monkeypatch.setenv("JWT_PARAM_NAME", "/hub/prod/jwt")
    fake_client = _FakeSSMClient({"/hub/prod/jwt": REAL_LOOKING_SECRET})
    monkeypatch.setattr(config, "_get_ssm_client", lambda: fake_client)

    config.get_jwt_secret()
    config.get_jwt_secret()

    assert fake_client.calls == ["/hub/prod/jwt"]


def test_ssm_client_is_built_lazily_via_boto3_and_cached(monkeypatch):
    monkeypatch.setattr(config, "_ssm_client", None)
    created: list[str] = []

    class _FakeBotoClient:
        def get_parameter(self, Name: str, WithDecryption: bool) -> dict:
            return {"Parameter": {"Value": "unused"}}

    def _fake_boto3_client(service_name: str) -> _FakeBotoClient:
        created.append(service_name)
        return _FakeBotoClient()

    monkeypatch.setattr("boto3.client", _fake_boto3_client)

    client = config._get_ssm_client()

    assert created == ["ssm"]
    assert config._get_ssm_client() is client
