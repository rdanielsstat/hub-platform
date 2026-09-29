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
    result = _import_app(
        {"USE_SSM": "true", "JWT_PARAM_NAME": "/hub-prod/jwt-secret"}
    )

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


def test_real_jwt_secret_with_use_ssm_starts(tmp_path):
    result = _import_app(
        {
            "USE_SSM": "true",
            "JWT_PARAM_NAME": "/hub-prod/jwt-secret",
            "FAKE_SSM_hub_prod_jwt_secret": "a-real-looking-unique-secret",
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
