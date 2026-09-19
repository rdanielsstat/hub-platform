# Hub API

FastAPI backend for Hub. Implements auth, project, and note endpoints
against a real database (SQLite via SQLAlchemy, database-agnostic so
Postgres can replace it at deploy time). Attachments aren't built yet.
See `../_docs/specs.md` and `../openapi.yaml` for the full intended
contract.

## Setup

```
uv sync
```

## Run the dev server

```
uv run uvicorn app.main:app --reload
```

Then visit:

- `http://localhost:8000/health`
- `http://localhost:8000/docs` (auto-generated OpenAPI docs, includes a
  working "Authorize" button for the bearer token)

CORS is currently open to the Vite dev server at `http://localhost:5173`.

## Database

SQLite by default, via a local file (`hub.db`, gitignored) — set with
`DATABASE_URL` (see `app/core/config.py`), which defaults to
`sqlite:///./hub.db`. Accepts a Postgres URL (e.g.
`postgresql+psycopg://user:pass@host/db`) with no code change; you'd
need to `uv add psycopg[binary]` (or another Postgres driver) at that
point, since SQLite's driver ships with Python and Postgres's doesn't.

Data persists across restarts now. Tables are created on startup if they
don't exist (`app/db/session.py`'s `create_tables()`) — there's no
Alembic yet, which is fine while the schema is still moving pre-launch.
Once it stabilizes, that should become real Alembic migrations so future
schema changes are tracked and reversible instead of implicit.

## Seeded demo account

The database seeds one user with ten varied projects (and notes) the
first time it's ever empty — a fresh database gets this; an existing one
is never re-seeded, duplicated, or overwritten on restart:

- email: `demo@hub.dev`
- password: `demo1234`

## Run the tests

```
uv run pytest
```

Each test runs against its own fresh, isolated in-memory SQLite database
(see `tests/conftest.py`) — never the dev `hub.db` file, never shared
across tests, never a real database.

## Auth

Roll-your-own: passwords hashed with argon2 (via passlib), JWT bearer
tokens (via PyJWT), OAuth2 password flow. `POST /auth/login` takes
`application/x-www-form-urlencoded` with `username` (the email) and
`password`, matching openapi.yaml and FastAPI's built-in OAuth2 tooling.

The JWT signing secret defaults to a hardcoded dev-only value
(`app/auth/security.py`). Set `HUB_JWT_SECRET` before running this
anywhere but a laptop.
