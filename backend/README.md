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

## Config

Everything in `app/core/config.py` — the single settings source, all
read from environment variables with defaults safe for local dev. Copy
`.env.example` to `.env` to override any of them; local dev needs none
of it.

| Var | Default | Required in prod? |
|---|---|---|
| `ENVIRONMENT` | `local` | No. `local`/`development`/`dev` (case-insensitive) all count as local; anything else (`production`, `staging`, ...) is treated as non-local and turns on the JWT secret guard below. |
| `DATABASE_URL` | `sqlite:///./hub.db` | No, but you'll want a real database URL outside dev. |
| `HUB_JWT_SECRET` | a known dev-only string | **Yes.** See below. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | No. |

### JWT secret guard

`app/core/config.py`'s `require_safe_jwt_secret()` runs once at startup
(`app/main.py`, before the app is even constructed). Outside a local
environment, it raises `RuntimeError` and refuses to start if
`HUB_JWT_SECRET` is unset or still equal to the built-in dev default —
it's impossible to accidentally run in production on the insecure
fallback. Locally, an unset/default secret just prints a warning and
the app starts anyway, so a fresh clone runs with zero setup. Generate a
real one with:

```
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## Database

SQLite by default, via a local file (`hub.db`, gitignored). Accepts a
Postgres URL (e.g. `postgresql+psycopg://user:pass@host/db`) via
`DATABASE_URL` with no code change; you'd need to `uv add psycopg[binary]`
(or another Postgres driver) at that point, since SQLite's driver ships
with Python and Postgres's doesn't.

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

All of the JWT secret/algorithm/expiry live in `app/core/config.py` (see
Config above) — nothing security-relevant is hardcoded in
`app/auth/security.py` itself.
