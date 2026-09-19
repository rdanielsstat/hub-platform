from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import require_safe_jwt_secret
from app.db.seed import seed
from app.db.session import SessionLocal, create_tables
from app.db.store import Store
from app.routers import auth, health, notes, projects

# First thing at startup: refuse to run outside local/dev on a missing
# or default JWT secret, before the app does anything else.
require_safe_jwt_secret()

app = FastAPI(title="Hub API")

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

create_tables()

# Seed only a genuinely empty database, so restarting against an existing
# one (dev's hub.db, or later a real deployment) never re-seeds,
# duplicates, or overwrites real data.
with SessionLocal() as _startup_db:
    _startup_store = Store(_startup_db)
    if not _startup_store.has_users():
        seed(_startup_store)
