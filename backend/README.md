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
| `DB_URL_PARAM_NAME` | — | Only used when `USE_SSM` is on: the SSM parameter name holding the full database URL. |
| `JWT_PARAM_NAME` | — | Only used when `USE_SSM` is on: the SSM parameter name holding the raw JWT secret. |
| `MASTER_DB_HOST` / `MASTER_DB_PORT` / `MASTER_DB_USER` / `MASTER_DB_PASSWORD` | — | Only used by the bootstrap command (below), only in local mode (`USE_SSM` off). Never read by the app itself. |

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

Used by the Lambda deployment. `app/core/config.py`'s
`get_database_url()` and `get_jwt_secret()` fetch two `SecureString`
parameters via boto3 (`WithDecryption=True`), cached after the first
successful read per process:

- `DB_URL_PARAM_NAME`: the full connection URL (Neon's, e.g.
  `postgresql://user:pass@host/db?sslmode=require&channel_binding=require`).
  A leading `postgresql://` is rewritten to `postgresql+psycopg://`; the
  rest, query string included, is kept exactly. The app points this at
  the pooled URL (`/hub-<env>/db-url`), the bootstrap at the direct one
  (`/hub-<env>/db-url-direct`).
- `JWT_PARAM_NAME`: the raw JWT secret string, used as-is.

boto3 resolves its own region and credentials from the Lambda execution
environment; nothing else needs configuring. The SSM client itself is
only ever built when `USE_SSM` is on, so a local/Compose run never
touches boto3 or needs AWS credentials at all.

The JWT secret is resolved when the app is imported, and any failure is
fatal: a secret that can't be fetched, or is missing or the dev default,
stops the process instead of starting an app that signs tokens with a
known key. The database URL is resolved lazily, on first use.

## Database

SQLite by default, via a local file (`hub.db`, gitignored). Accepts a
Postgres URL (e.g. `postgresql+psycopg://user:pass@host/db`) via
`DATABASE_URL` with no code change, or from SSM when `USE_SSM` is on
(see above). `psycopg[binary]` is already a dependency.

Importing the app does no database work. Tables are created by a
separate step: `python -m app.db.init_local` for plain local dev, or
the bootstrap below for Compose and AWS. Both only create missing
tables (`Base.metadata.create_all`); there's no Alembic yet, which is
fine while the schema is still moving pre-launch. Once it stabilizes,
that should become real Alembic migrations so future schema changes are
tracked and reversible instead of implicit.

## Postgres and the database bootstrap

Two ways to run this app locally:

- **Plain `uv run`, no Docker**: stays on the SQLite default above. Zero
  AWS; run `python -m app.db.init_local` once for tables (see "Run the
  dev server").
- **Docker Compose, prod-parity**: runs the full stack against real
  Postgres. `docker compose up --build` from the repo root starts, in
  order: a `postgres` service (Postgres 17, matching Neon), a
  `bootstrap` service, an `init_local` service that seeds the demo
  account, then the `app` service, which connects as a limited role.
  Compose sets all the env vars for you.

`app/bootstrap_db.py`, run via `python -m app.bootstrap_db` (or its
`lambda_handler` in AWS), owns table creation and has two modes:

**Cloud (`USE_SSM` on).** Neon already provides the role and database,
so the bootstrap only creates tables, connecting with the URL in
`DB_URL_PARAM_NAME`. The deployment points that at the direct
(non-pooled) endpoint, since PgBouncer's transaction mode is a poor fit
for DDL. No master credentials, no `CREATE ROLE`, no `CREATE DATABASE`.

**Local (`USE_SSM` off).** Against the Compose Postgres, it:

1. Connects with **master/superuser** credentials from
   `MASTER_DB_HOST`/`PORT`/`USER`/`PASSWORD` (Compose passes the local
   image's `postgres` superuser).
2. Creates the per-environment database and a `LOGIN` role, with
   `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION`, using the
   *same* name and password the app will connect with (parsed from
   `DATABASE_URL`). Skips creation if the role/database already exists;
   never updates an existing role's password.
3. Grants that role exactly `CONNECT` on the database plus `USAGE,
   CREATE` on the `public` schema. Nothing broader: no superuser, no
   `CREATEDB`/`CREATEROLE`, no ownership of the database itself.
4. Creates the tables, connected as that role, so the role owns them.

Every step is idempotent, so re-running is always safe. A failure in
either mode propagates: the CLI exits 1 and `lambda_handler` fails the
invocation, rather than reporting success.

The app's own runtime (`app/main.py`, `app/db/session.py`) never reads
the `MASTER_DB_*` vars and never holds master credentials.

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
