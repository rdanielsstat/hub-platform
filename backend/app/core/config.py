"""Application settings, sourced from environment variables and,
when USE_SSM is on, AWS SSM Parameter Store.

The single settings source: the database URL and everything
security-relevant (JWT secret, algorithm, token expiry) live here, not
scattered across session.py/security.py. Local dev and Docker Compose
need zero env vars and no AWS access at all: USE_SSM is off by default,
so DATABASE_URL and HUB_JWT_SECRET are read straight from the
environment, exactly as before. With USE_SSM on (the AWS/Lambda
deployments), get_database_url() and get_jwt_secret() instead fetch
their values from SSM, cached after the first successful read. The
JWT secret is resolved at import (app/main.py) and any failure there
is fatal: a Lambda that can't load its signing key must not start.
The database URL stays lazy; nothing touches the database at import.
Anywhere USE_SSM is on, or ENVIRONMENT isn't local/dev, app/main.py
calls `require_safe_jwt_secret()` against the resolved secret and
refuses to run on a missing or default value.
"""

import os
from typing import Any

ENVIRONMENT = os.environ.get("ENVIRONMENT", "local")


def env_flag(name: str) -> bool:
    """A boolean env var: 1/true/yes (any case, surrounding whitespace
    ignored) is on; anything else, including unset, is off."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


# On: DATABASE_URL and the JWT secret come from AWS SSM Parameter Store
# (DB_URL_PARAM_NAME / JWT_PARAM_NAME, both SecureString) instead of plain
# env vars. Off by default so local dev and Docker Compose never need
# AWS credentials or network access.
USE_SSM = env_flag("USE_SSM")

# On: `python -m app.db.init_local` seeds the demo account (with its
# hardcoded, publicly-known password; see app/db/seed.py) into an empty
# database. Local only: require_safe_seed_setting() refuses to start
# with this on while USE_SSM is on, so demo credentials can never reach
# a deployed database.
SEED_DEMO_DATA = env_flag("SEED_DEMO_DATA")

# On: export traces and metrics via OpenTelemetry (observability/, set
# up in app/main.py). Off by default, so local runs and tests never
# export unless asked, even with OTEL_EXPORTER_OTLP_ENDPOINT set in a
# .env. Where it goes is observability/config.py's concern.
OTEL_ENABLED = env_flag("OTEL_ENABLED")

_DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def parse_cors_origins(raw: str | None) -> list[str]:
    """Comma-separated origins, whitespace around each entry ignored.
    Unset or empty falls back to the local Vite dev server. In AWS,
    CloudFront serves the frontend and API from one origin, so CORS
    only matters for local development."""
    origins = [entry.strip() for entry in (raw or "").split(",") if entry.strip()]
    return origins or list(_DEFAULT_CORS_ORIGINS)


CORS_ORIGINS = parse_cors_origins(os.environ.get("CORS_ORIGINS"))

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
_origin_verify_secret: str | None = None


def is_local_environment(environment: str = ENVIRONMENT) -> bool:
    """Whether ENVIRONMENT is labelled local/development/dev. A label
    only: the deployed dev Lambda is also "dev". To ask "is this a real
    deployment?", use is_deployed()."""
    return environment.lower() in _LOCAL_ENVIRONMENTS


def is_deployed(environment: str = ENVIRONMENT, use_ssm: bool = USE_SSM) -> bool:
    """A real deployment rather than a laptop or Docker Compose run: true
    when secrets come from SSM (every Lambda sets USE_SSM, local runs
    never do), or when ENVIRONMENT isn't a local label. The dev Lambda
    has ENVIRONMENT=dev, so the label alone would wrongly treat it as
    local; USE_SSM settles it, the same override require_safe_jwt_secret()
    applies.

    Gates the deployment-only defaults: Secure session cookie, login rate
    limit on, API docs hidden. Pure function of its arguments, like the
    guards below, so it's testable without reloading this module."""
    return use_ssm or not is_local_environment(environment)


# The browser session: /auth/login and /auth/register set the JWT in this
# httpOnly cookie (JavaScript can't read it, so an XSS bug can't steal
# it), SameSite=Strict (never sent on a cross-site request, which is the
# CSRF defence). Non-browser clients keep using the Authorization header.
AUTH_COOKIE_NAME = "hub_token"

# Secure (HTTPS-only) whenever is_deployed(), dev Lambda included; off
# for a local run, where the Vite dev server and uvicorn are plain
# http://localhost. AUTH_COOKIE_SECURE overrides it either way.
AUTH_COOKIE_SECURE = (
    env_flag("AUTH_COOKIE_SECURE")
    if os.environ.get("AUTH_COOKIE_SECURE", "").strip()
    else is_deployed()
)

# Failed-or-not login attempts allowed per client IP per minute on
# /auth/login; over it, 429. 0 turns the limit off. Defaults to 5
# whenever is_deployed() (dev Lambda included) and off for a local run,
# where the Playwright suite logs in far more often than that from
# 127.0.0.1. See app/auth/rate_limit.py.
# Blank counts as unset, so a .env copied from .env.example works.
LOGIN_RATE_LIMIT_PER_MINUTE = int(
    os.environ.get("LOGIN_RATE_LIMIT_PER_MINUTE", "").strip()
    or ("5" if is_deployed() else "0")
)

# Same for POST /auth/register, per client IP per minute: 3 when deployed,
# off locally (the E2E suite registers a fresh user per test). Keeps one
# client from mass-creating accounts or burning Lambda CPU on argon2
# hashing. Successful and rejected (409, 422) attempts all count.
REGISTER_RATE_LIMIT_PER_MINUTE = int(
    os.environ.get("REGISTER_RATE_LIMIT_PER_MINUTE", "").strip()
    or ("3" if is_deployed() else "0")
)

# Request header that carries the real client IP, set by a proxy in front
# of the app (in AWS: CloudFront-Viewer-Address, "ip:port"). Unset means
# use the TCP peer address. Only set this when every request comes
# through that proxy: a client can send any header it likes.
CLIENT_IP_HEADER = os.environ.get("CLIENT_IP_HEADER", "").strip()


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


# Header CloudFront adds to every /api/* request it forwards, carrying a
# shared secret (infra/hub: frontend.tf, database.tf). See
# app/auth/origin_verify.py.
ORIGIN_VERIFY_HEADER = "X-Origin-Verify"


def get_origin_verify_secret() -> str | None:
    """The value every request must carry in X-Origin-Verify, from the
    SSM parameter named by ORIGIN_VERIFY_PARAM_NAME. Only with USE_SSM
    on: a local or Compose run has no CloudFront in front of it, so it
    returns None and the check is off. Resolved at most once per process.

    With USE_SSM on, a missing parameter name, an unreadable parameter or
    an empty value raises: app/main.py calls this at import, so a deployed
    Lambda that can't load the secret fails to start rather than running
    with the check silently off."""
    global _origin_verify_secret
    if not USE_SSM:
        return None
    if _origin_verify_secret is None:
        param_name = os.environ.get("ORIGIN_VERIFY_PARAM_NAME", "").strip()
        if not param_name:
            raise RuntimeError(
                "USE_SSM is on but ORIGIN_VERIFY_PARAM_NAME is not set. Refusing "
                "to start without origin verification."
            )
        secret = _fetch_ssm_parameter(param_name).strip()
        if not secret:
            raise RuntimeError(
                f"SSM parameter {param_name!r} (ORIGIN_VERIFY_PARAM_NAME) is "
                "empty. Refusing to start without origin verification."
            )
        _origin_verify_secret = secret
    return _origin_verify_secret


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


def require_safe_seed_setting(
    seed_demo_data: bool = SEED_DEMO_DATA,
    use_ssm: bool = USE_SSM,
) -> None:
    """Refuse to run with SEED_DEMO_DATA on anywhere USE_SSM is on: the
    demo account's password is hardcoded in the repo. Pure function,
    like require_safe_jwt_secret()."""
    if seed_demo_data and use_ssm:
        raise RuntimeError(
            "SEED_DEMO_DATA is on while USE_SSM is on. Demo data (with its "
            "publicly-known password) is for local development only. "
            "Refusing to start."
        )
