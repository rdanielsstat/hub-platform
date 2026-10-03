import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.auth.origin_verify import OriginVerifyMiddleware
from app.core.config import (
    CORS_ORIGINS,
    OTEL_ENABLED,
    get_jwt_secret,
    get_origin_verify_secret,
    is_deployed,
    require_safe_jwt_secret,
    require_safe_seed_setting,
)
from app.routers import auth, errors, health, notes, projects
from observability import initialize_observability

# First thing at startup, and deliberately not wrapped in try/except:
# a JWT secret that can't be loaded (SSM unreachable, parameter
# missing), or that's missing or the dev default outside a bare local
# run, must kill the process rather than leave a running app signing
# tokens with a known key or failing every request.
require_safe_jwt_secret(secret=get_jwt_secret())
require_safe_seed_setting()
# Same rule for the CloudFront origin-verify secret: with USE_SSM on, not
# being able to load it is fatal (None locally, where the check is off).
_origin_verify_secret = get_origin_verify_secret()

# No database work here. Importing the app (a Lambda cold start, or
# uvicorn locally) never creates tables or seeds: that's the job of a
# separate, run-once step (app/db/init_local.py locally, the bootstrap
# in AWS), so a broken database fails that step loudly instead of
# producing an app that starts and then fails every request.

# /docs, /redoc, and the raw schema are only served locally: once
# deployed (is_deployed(), so the dev Lambda too, not just prod) they'd
# hand an anonymous visitor a full map of the API surface for no
# benefit, since nothing consumes them there.
_docs_enabled = not is_deployed()

app = FastAPI(
    title="Hub API",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# Traces and metrics to Grafana Cloud (or a local collector), only with
# OTEL_ENABLED on. Never raises: a broken telemetry setup is logged and
# the app runs without it.
initialize_observability(app, enabled=OTEL_ENABLED)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Added last, so it's the outermost layer and runs first: a request that
# didn't come through CloudFront is refused before CORS, routing, auth or
# the login rate limit see it. A no-op when the secret is None (local).
app.add_middleware(OriginVerifyMiddleware, secret=_origin_verify_secret)


db_logger = logging.getLogger("app.db")


@app.exception_handler(OperationalError)
async def database_unavailable(request: Request, exc: OperationalError) -> JSONResponse:
    """The database couldn't be reached (Neon still resuming, Postgres
    down, connection dropped): 503 with Retry-After, not an unhandled 500.
    Clients treat it as "try again", and the web app never takes it for a
    signed-out session (frontend/src/auth.tsx). Handled here, inside the
    CORS middleware, so the response keeps its CORS headers; an unhandled
    500 comes from the outermost layer without them, and a cross-origin
    browser then sees only a network error. The message is logged, not
    returned: it can name the database host."""
    db_logger.warning(
        "database_unavailable method=%s path=%s error=%s",
        request.method,
        request.url.path,
        type(exc.orig).__name__ if exc.orig is not None else type(exc).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The database is temporarily unavailable. Try again in a moment."
        },
        headers={"Retry-After": "2"},
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(notes.router)
app.include_router(errors.router)
