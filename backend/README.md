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
SEED_DEMO_DATA=true uv run python -m app.db.init_local   # once: tables + demo account
uv run uvicorn app.main:app --reload
```

Importing the app does no database work: tables and the demo account
come from `app/db/init_local.py`, a separate idempotent step (safe to
re-run; it only creates what's missing and never re-seeds). It refuses
to run with `USE_SSM` on. Docker Compose runs it for you.

Then visit:

- `http://localhost:8000/health`
- `http://localhost:8000/docs` (auto-generated OpenAPI docs, includes a
  working "Authorize" button for the bearer token)

CORS allows `CORS_ORIGINS` (default: the Vite dev server at `http://localhost:5173` and `http://127.0.0.1:5173`).

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
| `SEED_DEMO_DATA` | off | No. Local only: lets `python -m app.db.init_local` seed the demo account. Must be off with `USE_SSM` on; the app refuses to start otherwise. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | No. Comma-separated. Only matters locally; CloudFront makes the deployed site same-origin. |
| `DB_PARAM_NAME` | — | Only used when `USE_SSM` is on: the SSM parameter name holding the DB credentials JSON. |
| `JWT_PARAM_NAME` | — | Only used when `USE_SSM` is on: the SSM parameter name holding the raw JWT secret. |
| `MASTER_DB_HOST` / `MASTER_DB_PORT` / `MASTER_DB_USER` / `MASTER_DB_PASSWORD` | — | Only used by the bootstrap command (below), only when `USE_SSM` is off. Never read by the app itself. |
| `MASTER_DB_PARAM_NAME` | — | Only used by the bootstrap command, only when `USE_SSM` is on: the SSM parameter name holding master/superuser credentials JSON. Never read by the app itself. |

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

## Postgres and the database bootstrap

Two ways to run this app locally:

- **Plain `uv run`, no Docker**: stays on the SQLite default above. Zero
  setup, zero AWS.
- **Docker Compose, prod-parity**: runs the full stack against real
  Postgres. `docker compose up --build` from the repo root starts, in
  order: a `postgres` service (Postgres 16, matching the deployed
  Aurora major version), a `bootstrap` service that creates this
  environment's database and a least-privilege login role, then the
  `app` service, which connects as that limited role. Compose sets all
  the env vars below for you.

In both AWS deployment and Compose, the app itself connects as a
per-environment, least-privilege Postgres role (e.g. `hub_dev_user`),
never as a superuser. Something has to create that role and its
database first: `app/bootstrap_db.py`, run standalone via
`python -m app.bootstrap_db`. It:

1. Connects with **master/superuser** credentials, resolved separately
   from the app's own: from `MASTER_DB_PARAM_NAME` over SSM when
   `USE_SSM` is on, otherwise from `MASTER_DB_HOST`/`PORT`/`USER`/
   `PASSWORD` env vars. The deploy pipeline calls this with the shared
   Aurora cluster's master credentials (`/dnls-shared/aurora-master` in
   SSM); Compose calls it with the local Postgres image's `postgres`
   superuser.
2. Creates the per-environment database and a `LOGIN` role — with
   `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION` — using the
   *same* name and password the app itself will connect with (parsed
   from `DATABASE_URL`/`DB_PARAM_NAME`, the app's normal credential
   source). Skips creation if the role/database already exists; never
   updates an existing role's password.
3. Grants that role exactly `CONNECT` on the database plus `USAGE,
   CREATE` on the `public` schema — enough for `create_tables()` and
   normal CRUD (the role owns whatever tables it creates, so it already
   has full DML on its own data). Nothing broader: no superuser, no
   `CREATEDB`/`CREATEROLE`, no ownership of the database itself. GRANTs
   always re-run (idempotent on the Postgres side), so re-running this
   command is always safe — the deploy pipeline calls it on every
   deploy.

The app's own runtime (`app/main.py`, `app/db/session.py`) never reads
the `MASTER_DB_*`/`MASTER_DB_PARAM_NAME` vars and never holds master
credentials; only `app/bootstrap_db.py` does, and only for the duration
of that one command.

## Seeded demo account

With `SEED_DEMO_DATA=true`, `python -m app.db.init_local` seeds one
user with ten varied projects (and notes) into a database with no users
yet; an existing one is never re-seeded, duplicated, or overwritten.
Local only: with `USE_SSM` on, init_local refuses to run and the app
refuses to start if `SEED_DEMO_DATA` is on.

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
