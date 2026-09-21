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
| `USE_SSM` | off | No. When on, `DATABASE_URL`/`HUB_JWT_SECRET` below are ignored and the real settings come from AWS SSM Parameter Store instead (see "AWS SSM" below). Off by default so local dev and Docker Compose never need AWS access. |
| `DATABASE_URL` | `sqlite:///./hub.db` | No if `USE_SSM` is off, but you'll want a real database URL outside dev. Ignored if `USE_SSM` is on. |
| `HUB_JWT_SECRET` | a known dev-only string | **Yes, if `USE_SSM` is off.** See below. Ignored if `USE_SSM` is on. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | No. |
| `DB_PARAM_NAME` | — | Only used when `USE_SSM` is on: the SSM parameter name holding the DB credentials JSON. |
| `JWT_PARAM_NAME` | — | Only used when `USE_SSM` is on: the SSM parameter name holding the raw JWT secret. |

### JWT secret guard

`app/core/config.py`'s `require_safe_jwt_secret()` runs once at startup
(`app/main.py`, before the app is even constructed) against whatever
`get_jwt_secret()` resolved. Outside a local environment, or whenever
`USE_SSM` is on (even if `ENVIRONMENT` says `local`), it raises
`RuntimeError` and refuses to start if the secret is unset or still
equal to the built-in dev default — it's impossible to accidentally run
in production on the insecure fallback. On a bare local run, an unset/
default secret just prints a warning and the app starts anyway, so a
fresh clone runs with zero setup. Generate a real one with:

```
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### AWS SSM (`USE_SSM=true`)

Used by the Lambda deployment, running inside a VPC with an SSM
interface endpoint. `app/core/config.py`'s `get_database_url()` and
`get_jwt_secret()` fetch two `SecureString` parameters via boto3
(`WithDecryption=True`), lazily and cached after the first successful
read per process — never called eagerly at import, and never more than
once per warm Lambda container:

- `DB_PARAM_NAME` — a JSON string: `{"username", "password", "host",
  "port", "dbname"}`. Built into a
  `postgresql+psycopg://user:pass@host:port/dbname` URL (`psycopg` is
  already a dependency).
- `JWT_PARAM_NAME` — the raw JWT secret string, used as-is.

boto3 resolves its own region and credentials from the Lambda execution
environment; nothing else needs configuring. The SSM client itself is
only ever built when `USE_SSM` is on, so a local/Compose run never
touches boto3 or needs AWS credentials at all.

A fetch that fails because SSM/the DB is transiently unreachable (e.g.
during Lambda cold start) logs a warning and lets startup continue,
matching `app/main.py`'s existing DB-creation try/except — later calls
retry rather than sticking with a bad cached value. A fetch that
*succeeds* but returns a missing/default JWT secret still hard-fails via
the guard above, since that's a real misconfiguration, not an outage.

## Database

SQLite by default, via a local file (`hub.db`, gitignored). Accepts a
Postgres URL (e.g. `postgresql+psycopg://user:pass@host/db`) via
`DATABASE_URL` with no code change, or built automatically from SSM
when `USE_SSM` is on (see above). `psycopg[binary]` is already a
dependency.

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
