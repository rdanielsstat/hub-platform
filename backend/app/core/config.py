"""Application settings, sourced from environment variables and,
when USE_SSM is on, AWS SSM Parameter Store.

The single settings source: the database URL and everything
security-relevant (JWT secret, algorithm, token expiry) live here, not
scattered across session.py/security.py. Local dev and Docker Compose
need zero env vars and no AWS access at all: USE_SSM is off by default,
so DATABASE_URL and HUB_JWT_SECRET are read straight from the
environment, exactly as before. With USE_SSM on (the AWS/Lambda
deployments), get_database_url() and get_jwt_secret() instead fetch
their values from SSM, lazily and cached after the first successful
read, so a transient SSM/DB outage at Lambda cold start (see
app/main.py's startup try/except) never turns into an import-time
crash. Anywhere USE_SSM is on, or ENVIRONMENT isn't local/dev,
app/main.py calls `require_safe_jwt_secret()` against the resolved
secret and refuses to run on a missing or default value.
"""

import os
from typing import Any

ENVIRONMENT = os.environ.get("ENVIRONMENT", "local")

# On: DATABASE_URL and the JWT secret come from AWS SSM Parameter Store
# (DB_URL_PARAM_NAME / JWT_PARAM_NAME, both SecureString) instead of plain
# env vars. Off by default so local dev and Docker Compose never need
# AWS credentials or network access.
USE_SSM = os.environ.get("USE_SSM", "").strip().lower() in {"1", "true", "yes"}

# Only a fallback for local dev — never a real secret. See
# require_safe_jwt_secret() below: with USE_SSM on, or anywhere
# ENVIRONMENT isn't local/dev, running with this value (or an unset or
# unfetchable secret) is a hard startup failure.
DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

_LOCAL_ENVIRONMENTS = {"local", "development", "dev"}

# Lazy caches: populated on first successful call, never at import and
# never per-request. A failed fetch leaves these as None so the next
# call retries rather than sticking with a bad cached value.
_ssm_client: Any = None
_database_url: str | None = None
_jwt_secret: str | None = None


def is_local_environment(environment: str = ENVIRONMENT) -> bool:
    return environment.lower() in _LOCAL_ENVIRONMENTS


def _get_ssm_client() -> Any:
    """Built on first use only. A local/Compose run never calls this
    (USE_SSM is off), so it needs no AWS credentials, network access,
    or even a configured region. boto3 resolves the region itself from
    the Lambda execution environment."""
    global _ssm_client
    if _ssm_client is None:
        import boto3

        _ssm_client = boto3.client("ssm")
    return _ssm_client


def _fetch_ssm_parameter(name: str) -> str:
    client = _get_ssm_client()
    response = client.get_parameter(Name=name, WithDecryption=True)
    return response["Parameter"]["Value"]


def normalize_database_url(url: str) -> str:
    """Point a plain postgresql:// URL (the form Neon hands out) at the
    psycopg 3 driver SQLAlchemy needs. Only the leading scheme changes;
    everything after it, query string included (Neon requires
    sslmode=require and may add channel_binding=require), is kept
    byte-for-byte. postgresql+psycopg:// and sqlite:// pass through."""
    prefix = "postgresql://"
    if url.startswith(prefix):
        return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def get_database_url() -> str:
    """The SQLAlchemy database URL: from AWS SSM (DB_URL_PARAM_NAME,
    whose value is the full connection URL) when USE_SSM is on,
    otherwise from DATABASE_URL exactly as before. Resolved at most
    once per process."""
    global _database_url
    if _database_url is None:
        if USE_SSM:
            raw_url = _fetch_ssm_parameter(os.environ["DB_URL_PARAM_NAME"])
        else:
            raw_url = os.environ.get("DATABASE_URL", "sqlite:///./hub.db")
        _database_url = normalize_database_url(raw_url)
    return _database_url


def get_jwt_secret() -> str:
    """The JWT signing secret: from AWS SSM when USE_SSM is on,
    otherwise from HUB_JWT_SECRET exactly as before. Resolved at most
    once per process."""
    global _jwt_secret
    if _jwt_secret is None:
        if USE_SSM:
            param_name = os.environ["JWT_PARAM_NAME"]
            _jwt_secret = _fetch_ssm_parameter(param_name)
        else:
            _jwt_secret = os.environ.get("HUB_JWT_SECRET", DEV_JWT_SECRET)
    return _jwt_secret


def require_safe_jwt_secret(
    environment: str = ENVIRONMENT,
    secret: str = DEV_JWT_SECRET,
    dev_default: str = DEV_JWT_SECRET,
    use_ssm: bool = USE_SSM,
) -> None:
    """Refuse to start with a missing or default JWT secret, except on
    a genuinely local run. Called once at app startup (see
    app/main.py), against whichever value get_jwt_secret() resolved.

    use_ssm forces the strict check even when environment's label is
    local/dev: a run that's actually pulling its secret from SSM is
    never a bare laptop run, whatever ENVIRONMENT says.

    Pure function — reads nothing from os.environ or module state
    directly, only its arguments (which default to this module's
    already-resolved settings) — so it's directly testable without
    reloading this module or touching real env vars.
    """
    if is_local_environment(environment) and not use_ssm:
        if secret == dev_default:
            # flush=True: stdout is block-buffered once it's not a TTY
            # (e.g. redirected to a log file, which is the normal case
            # for a running server) — without it this warning can sit
            # unflushed indefinitely instead of actually being visible.
            print(
                "WARNING: using the default dev JWT secret. Fine for local "
                "development; set HUB_JWT_SECRET before this runs anywhere else.",
                flush=True,
            )
        return

    if not secret or secret == dev_default:
        raise RuntimeError(
            f"JWT secret is unset or still the insecure dev default, and "
            f"ENVIRONMENT={environment!r} (USE_SSM={use_ssm}) is not a bare "
            "local run. Refusing to start. Set HUB_JWT_SECRET (or the SSM "
            "parameter named by JWT_PARAM_NAME) to a strong, unique secret."
        )
