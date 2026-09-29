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


NEON_POOLED_URL = (
    "postgresql://hub_app:p%40ss@ep-cool-name-123456-pooler.us-east-2.aws.neon.tech"
    "/hub?sslmode=require&channel_binding=require"
)


def test_get_database_url_returns_ssm_value_verbatim(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", True)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setenv("DB_URL_PARAM_NAME", "/hub-prod/db-url")
    ssm_value = "postgresql+psycopg://hub_app:p%40ss@db.example.com/hub?sslmode=require"
    fake_client = _FakeSSMClient({"/hub-prod/db-url": ssm_value})
    monkeypatch.setattr(config, "_get_ssm_client", lambda: fake_client)

    assert config.get_database_url() == ssm_value


def test_get_database_url_normalizes_neon_url_from_ssm(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", True)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setenv("DB_URL_PARAM_NAME", "/hub-prod/db-url")
    fake_client = _FakeSSMClient({"/hub-prod/db-url": NEON_POOLED_URL})
    monkeypatch.setattr(config, "_get_ssm_client", lambda: fake_client)

    assert config.get_database_url() == (
        "postgresql+psycopg://hub_app:p%40ss@ep-cool-name-123456-pooler.us-east-2.aws.neon.tech"
        "/hub?sslmode=require&channel_binding=require"
    )


def test_get_database_url_from_ssm_is_cached_after_first_fetch(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", True)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setenv("DB_URL_PARAM_NAME", "/hub-prod/db-url")
    fake_client = _FakeSSMClient({"/hub-prod/db-url": NEON_POOLED_URL})
    monkeypatch.setattr(config, "_get_ssm_client", lambda: fake_client)

    config.get_database_url()
    config.get_database_url()

    assert fake_client.calls == ["/hub-prod/db-url"]


def test_get_database_url_ignores_legacy_db_param_name(monkeypatch):
    """DB_PARAM_NAME (the old JSON credentials parameter) no longer
    exists in AWS; only DB_URL_PARAM_NAME is read."""
    monkeypatch.setattr(config, "USE_SSM", True)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.delenv("DB_URL_PARAM_NAME", raising=False)
    monkeypatch.setenv("DB_PARAM_NAME", "/hub/prod/db")
    fake_client = _FakeSSMClient({"/hub/prod/db": "{}"})
    monkeypatch.setattr(config, "_get_ssm_client", lambda: fake_client)

    with pytest.raises(KeyError, match="DB_URL_PARAM_NAME"):
        config.get_database_url()
    assert fake_client.calls == []


# ---- normalize_database_url() ----


def test_normalize_rewrites_plain_postgresql_scheme_to_psycopg():
    assert (
        config.normalize_database_url("postgresql://u:p@host/db")
        == "postgresql+psycopg://u:p@host/db"
    )


def test_normalize_leaves_psycopg_url_alone():
    url = "postgresql+psycopg://u:p@host:5432/db"
    assert config.normalize_database_url(url) == url


def test_normalize_leaves_sqlite_url_alone():
    assert config.normalize_database_url("sqlite:///./hub.db") == "sqlite:///./hub.db"
    assert config.normalize_database_url("sqlite:///:memory:") == "sqlite:///:memory:"


def test_normalize_preserves_query_string_with_multiple_params():
    url = (
        "postgresql://u:p%40ss@host/db"
        "?sslmode=require&channel_binding=require&options=endpoint%3Dep-abc"
    )
    assert config.normalize_database_url(url) == (
        "postgresql+psycopg://u:p%40ss@host/db"
        "?sslmode=require&channel_binding=require&options=endpoint%3Dep-abc"
    )


def test_normalize_only_rewrites_the_leading_scheme():
    """A 'postgresql://' appearing later in the URL (here inside a
    query value) must not be touched."""
    url = "postgresql+psycopg://u:p@host/db?application_name=postgresql://x"
    assert config.normalize_database_url(url) == url


def test_get_database_url_normalizes_database_url_env_var(monkeypatch):
    monkeypatch.setattr(config, "USE_SSM", False)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setenv("DATABASE_URL", NEON_POOLED_URL)

    assert config.get_database_url() == (
        "postgresql+psycopg://hub_app:p%40ss@ep-cool-name-123456-pooler.us-east-2.aws.neon.tech"
        "/hub?sslmode=require&channel_binding=require"
    )


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
