# Hub API

FastAPI backend for Hub. Implements auth, project, and note endpoints
against a real database via SQLAlchemy: it uses SQLite locally, Neon
Postgres when deployed (database-agnostic, so the same code runs on
both). Attachments aren't built yet. See `../docs/specs.md` and
`../openapi.yaml` for the full intended contract.

## Setup

Requires Python 3.12 (see `.python-version`) and
[uv](https://docs.astral.sh/uv/getting-started/installation/), e.g.
`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`.
uv installs Python 3.12 for you if it's missing.

```
uv sync
```

For a local full-stack run (the Vite frontend against this API on port
8000), also copy `frontend/.env.example` to `frontend/.env`. Without it
the frontend calls same-origin `/api`, which only exists behind
CloudFront, so every request fails locally.

To run against real Postgres instead of SQLite (prod parity), use
Docker Compose from the repo root instead of the `uv run` steps below:

```
docker compose up --build
```

See "Postgres and the database bootstrap" below for what it starts.

For deploying to AWS (one-time OpenTofu state bucket, GitHub OIDC
trust, Neon and Cloudflare setup), see `../infra/BOOTSTRAP.md`.

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

Everything is in `app/core/config.py`, the single settings source, all
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
| `OTEL_ENABLED` | off | No. On exports traces and metrics via OpenTelemetry (`observability/`). Set for the dev Lambda by OpenTofu, which exports to Grafana Cloud. Dev only: the prod Lambda leaves it off and emits no telemetry. See `observability/README.md` for local use. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | No. OTLP/HTTP base URL (Grafana Cloud's, in dev). Unset with `OTEL_ENABLED` on means a local collector at `http://localhost:4318`. Only read when `OTEL_ENABLED` is on. Set for the dev Lambda only, by OpenTofu. |
| `OTEL_EXPORTER_OTLP_HEADERS` | unset | No. Comma-separated `key=value` pairs, values URL-encoded (carries the Grafana Cloud `Authorization` token). Only read when `OTEL_ENABLED` is on. Set for the dev Lambda only, by OpenTofu. |
| `OTEL_SDK_DISABLED` | unset | No. `true` turns observability off entirely, even with `OTEL_ENABLED` on. |
| `SERVICE_VERSION` | unset (falls back to `LAMBDA_IMAGE_TAG`, then `local-dev`) | No. The `service.version` on telemetry. Set by OpenTofu on the dev Lambda from git tags; see "Releases and SERVICE_VERSION". |
| `API_BASE_PATH` | `/` | Lambda only (`app/lambda_handler.py`): the path prefix Mangum strips before routing. The deployment sets `/api`, since CloudFront forwards `/api/*` with the prefix intact. Unused by uvicorn. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | No. Comma-separated. Only matters locally; CloudFront makes the deployed site same-origin. |
| `DB_URL_PARAM_NAME` | unset | Only used when `USE_SSM` is on: the SSM parameter name holding the full database URL. |
| `JWT_PARAM_NAME` | unset | Only used when `USE_SSM` is on: the SSM parameter name holding the raw JWT secret. |
| `DEMO_PASSWORD_PARAM_NAME` | unset | Only read by the bootstrap, only in cloud mode: the SSM parameter holding this environment's demo account password. Absent means no demo account. See "Seeded demo account". |
| `MASTER_DB_PARAM_NAME` | unset | Unused. `app/bootstrap_db.py` would read master credentials from this SSM parameter with `USE_SSM` on, but cloud mode never asks for master credentials (Neon provides the role and database), and nothing sets it. |
| `MASTER_DB_HOST` / `MASTER_DB_PORT` / `MASTER_DB_USER` / `MASTER_DB_PASSWORD` | unset | Only used by the bootstrap command (below), only in local mode (`USE_SSM` off). Never read by the app itself. |

### JWT secret guard

`app/core/config.py`'s `require_safe_jwt_secret()` runs once at startup
(`app/main.py`, before the app is even constructed) against whatever
`get_jwt_secret()` resolved. Outside a local environment, or whenever
`USE_SSM` is on (even if `ENVIRONMENT` says `local`), it raises
`RuntimeError` and refuses to start if the secret is unset or still
equal to the built-in dev default, so it's impossible to accidentally run
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

Uses SQLite locally, Neon Postgres when deployed. Locally that's a
SQLite file by default (`hub.db`, gitignored). Accepts a
Postgres URL (e.g. `postgresql+psycopg://user:pass@host/db`) via
`DATABASE_URL` with no code change, or from SSM when `USE_SSM` is on
(see above). `psycopg[binary]` is already a dependency.

Importing the app does no database work. Tables are created by a
separate step: `init_local` (`python -m app.db.init_local`) locally, or
`bootstrap_db.py` (`python -m app.bootstrap_db`, run as its own Lambda
on every deploy) when deployed. Docker Compose runs both. Tests skip
both and create tables on each test's in-memory database directly (see
`tests/conftest.py`). All of these only create missing
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
It then seeds the demo account if the environment has one (see "Seeded
demo account").

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

One user, `demo@hub.dev`, with ten varied projects and their notes
(`app/db/seed.py`), so there's something to log in to and look at.

**Locally**, with `SEED_DEMO_DATA=true`, `python -m app.db.init_local`
seeds it into a database with no users yet, with the password
`demo1234`. An existing database is never re-seeded, duplicated, or
overwritten. With `USE_SSM` on, init_local refuses to run and the app
refuses to start if `SEED_DEMO_DATA` is on.

**Deployed**, the bootstrap seeds it when the environment has a demo
account, which is when its Lambda has `DEMO_PASSWORD_PARAM_NAME` set.
The password comes from that SSM parameter, one per environment, and
only the bootstrap's role can read it. `demo1234` is never used; a
missing or empty parameter fails the bootstrap instead. Every deploy
creates the account only if it doesn't exist yet and otherwise leaves it
exactly as it is, password included.

It is a real, writable account: anyone with the password can edit or
delete its projects, and those changes persist across deploys. To put it
back to the seed data, run the **Reset demo data** workflow from the
Actions tab, pick the environment, and type `reset` to confirm. That
invokes the bootstrap with `{"reset_demo": true}`, which deletes the
demo user and everything it owns (its notes, projects, and login), then
seeds it again with the current SSM password. No other account's data
is touched. In an environment without a demo account it refuses and
deletes nothing.

## Releases and SERVICE_VERSION

Every merge to `main` deploys dev; no tag is needed. The dev Lambda
reports a SemVer `SERVICE_VERSION` (the `service.version` on its
telemetry), derived from the nearest `vX.Y.Z` git tag by
`.github/scripts/service-version.sh`:

| HEAD | SERVICE_VERSION |
|---|---|
| no release tag yet | `0.0.0+<sha>` |
| tagged `v1.2.0` | `1.2.0` |
| 2 commits after `v1.2.0` | `1.2.0+2.g<sha>` |

To mark a release, tag the commit on `main` and push the tag:

```
git tag -a v1.2.0 -m "v1.2.0"
git push origin v1.2.0
```

Pushing a tag doesn't deploy anything by itself; the version shows up on
the next deploy of that commit or a later one. Image tags are unaffected:
they stay `<timestamp>-<sha>`, unique per build.

## Run the tests

```
uv run pytest
```

Each test runs against its own fresh, isolated in-memory SQLite database
(see `tests/conftest.py`), never the dev `hub.db` file, never shared
across tests, never a real database.

## Auth

Roll-your-own: passwords hashed with argon2 (via argon2-cffi), JWT bearer
tokens (via PyJWT), OAuth2 password flow. `POST /auth/login` takes
`application/x-www-form-urlencoded` with `username` (the email) and
`password`, matching openapi.yaml and FastAPI's built-in OAuth2 tooling.

All of the JWT secret/algorithm/expiry live in `app/core/config.py` (see
Config above); nothing security-relevant is hardcoded in
`app/auth/security.py` itself.
