from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import (
    CORS_ORIGINS,
    OTEL_ENABLED,
    get_jwt_secret,
    is_local_environment,
    require_safe_jwt_secret,
    require_safe_seed_setting,
)
from app.routers import auth, health, notes, projects
from observability import initialize_observability

# First thing at startup, and deliberately not wrapped in try/except:
# a JWT secret that can't be loaded (SSM unreachable, parameter
# missing), or that's missing or the dev default outside a bare local
# run, must kill the process rather than leave a running app signing
# tokens with a known key or failing every request.
require_safe_jwt_secret(secret=get_jwt_secret())
require_safe_seed_setting()

# No database work here. Importing the app (a Lambda cold start, or
# uvicorn locally) never creates tables or seeds: that's the job of a
# separate, run-once step (app/db/init_local.py locally, the bootstrap
# in AWS), so a broken database fails that step loudly instead of
# producing an app that starts and then fails every request.

# /docs, /redoc, and the raw schema are only served locally: outside
# local/dev they'd hand an anonymous visitor a full map of the API
# surface for no benefit, since nothing consumes them once deployed.
_docs_enabled = is_local_environment()

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

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(notes.router)
