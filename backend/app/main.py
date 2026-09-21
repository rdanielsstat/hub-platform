from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_jwt_secret, is_local_environment, require_safe_jwt_secret
from app.db.seed import seed
from app.db.session import SessionLocal, create_tables
from app.db.store import Store
from app.routers import auth, health, notes, projects

# First thing at startup: refuse to run outside local/dev on a missing
# or default JWT secret, before the app does anything else. Fetching
# the secret (from SSM, once USE_SSM is on) is kept separate from
# checking it: a transient SSM outage should warn and let startup
# continue (mirroring the DB try/except below), but a secret that *was*
# fetched and is missing or the dev default is a real misconfiguration
# and must still hard-fail.
try:
    _jwt_secret = get_jwt_secret()
except Exception as _jwt_fetch_error:
    print(
        f"WARNING: could not fetch the JWT secret at startup, will retry "
        f"per-request: {_jwt_fetch_error!r}",
        flush=True,
    )
else:
    require_safe_jwt_secret(secret=_jwt_secret)

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(notes.router)

try:
    create_tables()

    # Seed only a genuinely empty database, so restarting against an
    # existing one (dev's hub.db, or later a real deployment) never
    # re-seeds, duplicates, or overwrites real data.
    with SessionLocal() as _startup_db:
        _startup_store = Store(_startup_db)
        if not _startup_store.has_users():
            seed(_startup_store)
except Exception as _startup_db_error:
    # Import time is Lambda cold-start init: if the database isn't
    # reachable yet (VPC ENI still attaching, Secrets Manager-backed
    # credentials not resolved, RDS still warming up), failing here
    # would fail the whole init phase and the function would never
    # come up. Log and continue; routes that touch the database will
    # surface a normal per-request error until it's reachable.
    print(
        f"WARNING: startup table creation/seed skipped, database "
        f"unreachable: {_startup_db_error!r}",
        flush=True,
    )
