"""Application settings, sourced from environment variables.

The single settings source: the database URL and everything
security-relevant (JWT secret, algorithm, token expiry) live here, not
scattered across session.py/security.py. Local dev needs zero env vars —
everything has a safe-for-a-laptop default. Anywhere ENVIRONMENT isn't
local/development, app/main.py calls `require_safe_jwt_secret()` at
startup and refuses to run on a missing or default JWT secret.
"""

import os

ENVIRONMENT = os.environ.get("ENVIRONMENT", "local")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./hub.db")

# Only a fallback for local dev — never a real secret. See
# require_safe_jwt_secret() below: outside local/dev, running with this
# value (or with HUB_JWT_SECRET unset) is a hard startup failure.
DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"
JWT_SECRET = os.environ.get("HUB_JWT_SECRET", DEV_JWT_SECRET)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

_LOCAL_ENVIRONMENTS = {"local", "development", "dev"}


def is_local_environment(environment: str = ENVIRONMENT) -> bool:
    return environment.lower() in _LOCAL_ENVIRONMENTS


def require_safe_jwt_secret(
    environment: str = ENVIRONMENT,
    secret: str = JWT_SECRET,
    dev_default: str = DEV_JWT_SECRET,
) -> None:
    """Refuse to start outside local/dev on a missing or default JWT
    secret. Called once at app startup (see app/main.py).

    Pure function — reads nothing from os.environ or module state
    directly, only its arguments (which default to this module's
    already-resolved settings) — so it's directly testable without
    reloading this module or touching real env vars.
    """
    if is_local_environment(environment):
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
            f"HUB_JWT_SECRET is unset or still the insecure dev default, "
            f"and ENVIRONMENT={environment!r} is not local. Refusing to "
            "start. Set HUB_JWT_SECRET to a strong, unique secret."
        )
