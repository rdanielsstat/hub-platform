"""Import-time behaviour of app.main, and the startup safety checks.

Each import test runs `import app.main` in a fresh subprocess: the test
process already imported app.main via conftest, and re-importing it
in-process would leave a half-initialised module behind whenever the
import is expected to raise.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.core.config import DEV_JWT_SECRET

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Settings env vars scrubbed from every subprocess so a developer's own
# shell can't leak into these tests.
_SETTINGS_VARS = {
    "ENVIRONMENT",
    "USE_SSM",
    "DATABASE_URL",
    "DB_URL_PARAM_NAME",
    "HUB_JWT_SECRET",
    "JWT_PARAM_NAME",
    "SEED_DEMO_DATA",
    "CORS_ORIGINS",
    "AUTH_COOKIE_SECURE",
    "LOGIN_RATE_LIMIT_PER_MINUTE",
    "REGISTER_RATE_LIMIT_PER_MINUTE",
    "CLIENT_IP_HEADER",
    "ORIGIN_VERIFY_PARAM_NAME",
}

# Replaces boto3 inside the subprocess: `client("ssm")` returns a fake
# whose parameters come from the FAKE_SSM_* env vars below.
_FAKE_BOTO3 = textwrap.dedent(
    """
    import os, sys, types

    class _FakeSSM:
        def get_parameter(self, Name, WithDecryption):
            key = "FAKE_SSM_" + Name.strip("/").replace("/", "_").replace("-", "_")
            return {"Parameter": {"Value": os.environ[key]}}

    _boto3 = types.ModuleType("boto3")
    _boto3.client = lambda *args, **kwargs: _FakeSSM()
    sys.modules["boto3"] = _boto3
    """
)


def _run(code: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if k not in _SETTINGS_VARS}
    return subprocess.run(
        [sys.executable, "-c", _FAKE_BOTO3 + textwrap.dedent(code)],
        cwd=BACKEND_DIR,
        env={**base, **env},
        capture_output=True,
        text=True,
        timeout=60,
    )


def _import_app(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return _run("import app.main\n", env)


# ---- no database work at import ----


def test_importing_the_app_performs_no_ddl_and_no_seeding(tmp_path):
    """Even with SEED_DEMO_DATA on, importing app.main must not touch
    the database at all: no connection means no file for SQLite."""
    db_file = tmp_path / "import-check.db"

    result = _import_app(
        {"DATABASE_URL": f"sqlite:///{db_file}", "SEED_DEMO_DATA": "true"}
    )

    assert result.returncode == 0, result.stderr
    assert not db_file.exists()


def test_local_defaults_still_import_cleanly(tmp_path):
    """No settings env vars at all (a bare `uv run uvicorn`), apart from
    pointing the default SQLite file somewhere disposable."""
    result = _import_app({"DATABASE_URL": f"sqlite:///{tmp_path / 'hub.db'}"})

    assert result.returncode == 0, result.stderr
    assert "WARNING: using the default dev JWT secret" in result.stdout


# ---- fail loudly on unsafe settings ----


def test_seed_demo_data_with_use_ssm_refuses_to_start():
    result = _import_app(
        {
            "USE_SSM": "true",
            "SEED_DEMO_DATA": "true",
            "JWT_PARAM_NAME": "/hub-prod/jwt-secret",
            "FAKE_SSM_hub_prod_jwt_secret": "a-real-looking-unique-secret",
        }
    )

    assert result.returncode != 0
    assert "SEED_DEMO_DATA" in result.stderr


def test_missing_jwt_secret_with_use_ssm_refuses_to_start():
    """JWT_PARAM_NAME unset: the secret can't be loaded at all. Must be
    a startup failure, not a warning followed by a running app."""
    result = _import_app({"USE_SSM": "true"})

    assert result.returncode != 0
    assert "JWT_PARAM_NAME" in result.stderr


def test_unfetchable_jwt_secret_with_use_ssm_refuses_to_start():
    """The parameter is named but the fetch fails (here: the fake SSM has
    no such parameter, raising like a real outage would)."""
    result = _import_app({"USE_SSM": "true", "JWT_PARAM_NAME": "/hub-prod/jwt-secret"})

    assert result.returncode != 0
    assert "FAKE_SSM_hub_prod_jwt_secret" in result.stderr


def test_empty_jwt_secret_with_use_ssm_refuses_to_start():
    result = _import_app(
        {
            "USE_SSM": "true",
            "JWT_PARAM_NAME": "/hub-prod/jwt-secret",
            "FAKE_SSM_hub_prod_jwt_secret": "",
        }
    )

    assert result.returncode != 0
    assert "Refusing to start" in result.stderr


def test_dev_default_jwt_secret_with_use_ssm_refuses_to_start():
    result = _import_app(
        {
            "USE_SSM": "true",
            "JWT_PARAM_NAME": "/hub-prod/jwt-secret",
            "FAKE_SSM_hub_prod_jwt_secret": DEV_JWT_SECRET,
        }
    )

    assert result.returncode != 0
    assert "Refusing to start" in result.stderr


# Origin-verify parameter every USE_SSM run needs (see the last section).
_ORIGIN_VERIFY_SECRET = "test-origin-verify-secret"
_ORIGIN_VERIFY_ENV = {
    "ORIGIN_VERIFY_PARAM_NAME": "/hub-test/origin-verify-secret",
    "FAKE_SSM_hub_test_origin_verify_secret": _ORIGIN_VERIFY_SECRET,
}


def test_real_jwt_secret_with_use_ssm_starts(tmp_path):
    result = _import_app(
        {
            "USE_SSM": "true",
            "JWT_PARAM_NAME": "/hub-prod/jwt-secret",
            "FAKE_SSM_hub_prod_jwt_secret": "a-real-looking-unique-secret",
            **_ORIGIN_VERIFY_ENV,
        }
    )

    assert result.returncode == 0, result.stderr


# ---- CORS_ORIGINS reaches the running app ----


@pytest.mark.parametrize(
    ("origin", "allowed"),
    [
        ("https://a.example", True),
        ("https://b.example", True),
        ("http://localhost:5173", False),
    ],
)
def test_cors_origins_env_var_configures_the_app(tmp_path, origin, allowed):
    result = _run(
        f"""
        from fastapi.testclient import TestClient
        import app.main

        res = TestClient(app.main.app).options(
            "/health",
            headers={{
                "Origin": {origin!r},
                "Access-Control-Request-Method": "GET",
            }},
        )
        print("ALLOW=" + str(res.headers.get("access-control-allow-origin")))
        """,
        {
            "DATABASE_URL": f"sqlite:///{tmp_path / 'hub.db'}",
            "CORS_ORIGINS": " https://a.example , https://b.example ",
        },
    )

    assert result.returncode == 0, result.stderr
    expected = f"ALLOW={origin}" if allowed else "ALLOW=None"
    assert expected in result.stdout


# ---- deployment-only defaults follow is_deployed() ----

_STRONG_SECRET = "a-strong-test-secret-that-is-not-the-dev-default"


@pytest.mark.parametrize(
    ("environment", "use_ssm", "deployed"),
    [
        ("local", False, False),  # bare laptop run
        ("dev", False, False),  # laptop run labelled dev
        ("dev", True, True),  # the deployed dev Lambda
        ("local", True, True),  # SSM always means deployed
        ("prod", False, True),  # non-local label
        ("prod", True, True),  # the deployed prod Lambda
    ],
)
def test_deployment_defaults_follow_is_deployed(
    tmp_path, environment, use_ssm, deployed
):
    """Secure cookie, login rate limit and hidden API docs come on exactly
    when is_deployed(): any USE_SSM run, or a non-local ENVIRONMENT. The
    deployed dev Lambda (ENVIRONMENT=dev, USE_SSM=true) is the case the
    ENVIRONMENT label alone used to get wrong."""
    env = {
        "ENVIRONMENT": environment,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'hub.db'}",
    }
    if use_ssm:
        env |= {
            "USE_SSM": "true",
            "JWT_PARAM_NAME": "/hub-test/jwt-secret",
            "FAKE_SSM_hub_test_jwt_secret": _STRONG_SECRET,
            **_ORIGIN_VERIFY_ENV,
        }
    else:
        env["HUB_JWT_SECRET"] = _STRONG_SECRET

    result = _run(
        """
        import app.main
        from app.core import config
        print(config.is_deployed(), config.AUTH_COOKIE_SECURE,
              config.LOGIN_RATE_LIMIT_PER_MINUTE,
              config.REGISTER_RATE_LIMIT_PER_MINUTE, app.main.app.docs_url)
        """,
        env,
    )

    assert result.returncode == 0, result.stderr
    expected = "True True 5 3 None" if deployed else "False False 0 0 /docs"
    assert result.stdout.strip().splitlines()[-1] == expected


def test_explicit_settings_override_the_deployment_defaults(tmp_path):
    result = _run(
        """
        from app.core import config
        print(config.AUTH_COOKIE_SECURE, config.LOGIN_RATE_LIMIT_PER_MINUTE,
              config.REGISTER_RATE_LIMIT_PER_MINUTE)
        """,
        {
            "ENVIRONMENT": "prod",
            "HUB_JWT_SECRET": _STRONG_SECRET,
            "AUTH_COOKIE_SECURE": "false",
            "LOGIN_RATE_LIMIT_PER_MINUTE": "20",
            "REGISTER_RATE_LIMIT_PER_MINUTE": "0",
            "DATABASE_URL": f"sqlite:///{tmp_path / 'hub.db'}",
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False 20 0"


# ---- origin verification: requests must come through CloudFront ----

_SSM_ENV = {
    "USE_SSM": "true",
    "JWT_PARAM_NAME": "/hub-test/jwt-secret",
    "FAKE_SSM_hub_test_jwt_secret": _STRONG_SECRET,
}

_PROBE_HEALTH = """
    from fastapi.testclient import TestClient
    import app.main

    client = TestClient(app.main.app)
    for headers in ({}, {"X-Origin-Verify": "wrong"},
                    {"X-Origin-Verify": "test-origin-verify-secret"}):
        print("status", client.get("/health", headers=headers).status_code)
    """


def _statuses(stdout: str) -> list[str]:
    # Only the probe's lines: startup can print to stdout too.
    lines = stdout.splitlines()
    return [line.split()[1] for line in lines if line.startswith("status ")]


def test_deployed_app_rejects_requests_without_the_origin_verify_header(tmp_path):
    """USE_SSM on: a direct execute-api call (no header, or a wrong one)
    gets 403; a request through CloudFront, which adds the right value,
    gets through."""
    result = _run(
        _PROBE_HEALTH,
        {
            **_SSM_ENV,
            **_ORIGIN_VERIFY_ENV,
            "DATABASE_URL": f"sqlite:///{tmp_path / 'hub.db'}",
        },
    )

    assert result.returncode == 0, result.stderr
    assert _statuses(result.stdout) == ["403", "403", "200"]
    assert "origin_verify_rejected" in result.stderr
    assert _ORIGIN_VERIFY_SECRET not in result.stderr


def test_local_run_skips_the_origin_verify_check(tmp_path):
    """USE_SSM off (laptop, Docker Compose): no CloudFront in front, so
    every request gets through with or without the header."""
    result = _run(
        _PROBE_HEALTH,
        {
            "ENVIRONMENT": "prod",
            "HUB_JWT_SECRET": _STRONG_SECRET,
            "DATABASE_URL": f"sqlite:///{tmp_path / 'hub.db'}",
        },
    )

    assert result.returncode == 0, result.stderr
    assert _statuses(result.stdout) == ["200", "200", "200"]


def test_missing_origin_verify_param_with_use_ssm_refuses_to_start():
    result = _import_app(_SSM_ENV)

    assert result.returncode != 0
    assert "ORIGIN_VERIFY_PARAM_NAME is not set" in result.stderr


def test_empty_origin_verify_secret_with_use_ssm_refuses_to_start():
    result = _import_app(
        {
            **_SSM_ENV,
            **_ORIGIN_VERIFY_ENV,
            "FAKE_SSM_hub_test_origin_verify_secret": "  ",
        }
    )

    assert result.returncode != 0
    assert "is empty" in result.stderr
