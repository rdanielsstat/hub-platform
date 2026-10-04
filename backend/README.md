# Hub API

FastAPI backend for Hub. Implements auth, project, and note endpoints
against a real database via SQLAlchemy: it uses SQLite locally, Neon
Postgres when deployed (database-agnostic, so the same code runs on
both). Attachments aren't built yet. See `../product-spec.md` and
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
SEED_DEMO_DATA=true uv run python -m app.db.init_local   # schema + demo account
uv run uvicorn app.main:app --reload
```

Importing the app does no database work: the schema and the demo account
come from `app/db/init_local.py`, a separate idempotent step (safe to
re-run; it applies any pending migrations and never re-seeds). Re-run it
after pulling a change that adds a migration. It refuses
to run with `USE_SSM` on. Docker Compose runs it for you.

Then visit:

- `http://localhost:8000/health`
- `http://localhost:8000/docs` (auto-generated OpenAPI docs, includes a
  working "Authorize" button for the bearer token). Local runs only: once
  deployed (`is_deployed()`, dev included) `/docs`, `/redoc` and
  `/openapi.json` return 404.

CORS allows `CORS_ORIGINS` (default: the Vite dev server at `http://localhost:5173` and `http://127.0.0.1:5173`).

## Config

Everything is in `app/core/config.py`, the single settings source, all
read from environment variables with defaults safe for local dev. Copy
`.env.example` to `.env` to override any of them; local dev needs none
of it.

| Var | Default | Required in prod? |
|---|---|---|
| `ENVIRONMENT` | `local` | No. `local`/`development`/`dev` (case-insensitive) all count as local; anything else (`production`, `staging`, ...) is treated as non-local and turns on the JWT secret guard below. A run counts as deployed (`is_deployed()` in `app/core/config.py`) when `USE_SSM` is on or `ENVIRONMENT` isn't local, so the dev Lambda (`ENVIRONMENT=dev`, `USE_SSM=true`) gets the deployed defaults: Secure cookie, login rate limit on, API docs hidden. |
| `USE_SSM` | off | No. When on, `DATABASE_URL`/`HUB_JWT_SECRET` below are ignored and the real settings come from AWS SSM Parameter Store instead (see "AWS SSM" below). Off by default so local dev and Docker Compose never need AWS access. |
| `DATABASE_URL` | `sqlite:///./hub.db` | No if `USE_SSM` is off, but you'll want a real database URL outside dev. Ignored if `USE_SSM` is on. |
| `HUB_JWT_SECRET` | a known dev-only string | **Yes, if `USE_SSM` is off.** See below. Ignored if `USE_SSM` is on. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | No. |
| `AUTH_COOKIE_SECURE` | on when deployed (`is_deployed()`), off locally | No. Whether the `hub_token` session cookie gets the `Secure` flag (HTTPS only). Off locally because the dev servers are plain `http://localhost`. See "Auth". |
| `LOGIN_RATE_LIMIT_PER_MINUTE` | `5` when deployed (`is_deployed()`, dev Lambda included), `0` (off) locally | No. Login attempts allowed per client IP per minute on `POST /auth/login`; `0` turns the limit off. Off locally because the Playwright suite logs in many times from 127.0.0.1. See "Rate limits". |
| `REGISTER_RATE_LIMIT_PER_MINUTE` | `3` when deployed (`is_deployed()`), `0` (off) locally | No. Sign-up attempts allowed per client IP per minute on `POST /auth/register`, counted separately from logins; `0` turns the limit off. Off locally because the E2E suite registers a user per test. See "Rate limits". |
| `CLIENT_IP_HEADER` | unset (use the TCP peer address) | No. Request header holding the real client IP, for the login rate limit. The Lambdas set `CloudFront-Viewer-Address`. Only set it when every request comes through the proxy that writes it, since a client can send any header. |
| `SEED_DEMO_DATA` | off | No. Local only: lets `python -m app.db.init_local` seed the demo account. Must be off with `USE_SSM` on; the app refuses to start otherwise. |
| `OTEL_ENABLED` | off | No. On exports traces and metrics via OpenTelemetry (`observability/`). Set for the dev and prod Lambdas by OpenTofu, which export to Grafana Cloud. Prod sends OTEL data to Grafana via OTLP endpoint. See `observability/README.md` for local use. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | No. OTLP/HTTP base URL (Grafana Cloud's, in dev and prod). Unset with `OTEL_ENABLED` on means a local collector at `http://localhost:4318`. Only read when `OTEL_ENABLED` is on. Set for the dev and prod Lambdas by OpenTofu. |
| `OTEL_EXPORTER_OTLP_HEADERS` | unset | No. Comma-separated `key=value` pairs, values URL-encoded (carries the Grafana Cloud `Authorization` token). Only read when `OTEL_ENABLED` is on. Set for the dev and prod Lambdas by OpenTofu. |
| `OTEL_SDK_DISABLED` | unset | No. `true` turns observability off entirely, even with `OTEL_ENABLED` on. |
| `SERVICE_VERSION` | unset (falls back to `LAMBDA_IMAGE_TAG`, then `local-dev`) | No. The `service.version` on telemetry. Set by OpenTofu on the dev and prod Lambdas from git tags; see "Releases and SERVICE_VERSION". |
| `API_BASE_PATH` | `/` | Lambda only (`app/lambda_handler.py`): the path prefix Mangum strips before routing. The deployment sets `/api`, since CloudFront forwards `/api/*` with the prefix intact. Unused by uvicorn. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | No. Comma-separated. Only matters locally; CloudFront makes the deployed site same-origin. |
| `DB_URL_PARAM_NAME` | unset | Only used when `USE_SSM` is on: the SSM parameter name holding the full database URL. |
| `JWT_PARAM_NAME` | unset | Only used when `USE_SSM` is on: the SSM parameter name holding the raw JWT secret. |
| `ORIGIN_VERIFY_PARAM_NAME` | unset | **Required when `USE_SSM` is on**, ignored otherwise: the SSM parameter holding the `X-Origin-Verify` secret CloudFront sends. With `USE_SSM` on, the app refuses to start if it's unset, unreadable or empty. See "Origin verification". |
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

Importing the app does no database work. The schema comes from Alembic
migrations, applied by a separate step: `init_local`
(`python -m app.db.init_local`) locally, or `bootstrap_db.py`
(`python -m app.bootstrap_db`, run as its own Lambda on every deploy)
when deployed. Docker Compose runs both. Unit tests skip both and create
tables on each test's in-memory database directly (see
`tests/conftest.py`); `tests/test_migrations.py` covers the migrations
themselves, and the integration tests run them against real Postgres.

### Migrations (Alembic)

Scripts live in `alembic/versions/`; `app/db/migrations.py` runs them.
`0001` is the baseline: exactly the schema the old `create_all()` built.

```
uv run alembic upgrade head                            # apply pending migrations
uv run alembic current                                 # show the database's revision
uv run alembic revision --autogenerate -m "add x to y" # new migration from orm.py
uv run alembic check                                   # fail if orm.py has unmigrated changes
uv run alembic upgrade head --sql                      # print the SQL, run nothing
```

The CLI targets the same database the app would: `alembic/env.py` loads
`.env` and resolves the URL through `app/core/config.py`.

To change the schema: edit `app/db/orm.py`, generate a revision, read
it (autogenerate misses renames and data moves, and can't tell a rename
from a drop plus an add), then run the tests.
`tests/test_migrations.py::test_migrations_match_the_orm_models` fails
whenever `orm.py` and the migrations disagree. The next deploy's
bootstrap applies it.

Databases created before Alembic (the deployed Neon databases, existing
local `hub.db` files and Compose volumes) have the baseline tables but
no `alembic_version` table. The first migration run stamps them at
`0001` instead of re-running it, then upgrades normally; no data is
touched and nothing needs doing by hand. A database with only some of
the baseline tables is refused rather than guessed at.

The stamp and every migration run in one transaction, so a failed
migration rolls back completely (and fails the deploy's bootstrap
step). That holds on SQLite too: `app/db/migrations.py` turns off the
`sqlite3` driver's own transaction handling, which would otherwise
commit DDL early and leave half a run behind. SQLite migrations use
Alembic's batch mode (copy the table, drop the original, rename), since
SQLite can't `ALTER` most things in place; foreign keys stay off while
they run, or dropping `projects` would cascade-delete every note.

Migrations so far: `0001` baseline schema; `0002` CHECK constraints for
the text length limits; `0003` limits on display names and on the number
of tags and links. `0002` and `0003` refuse to run if existing rows
already exceed them (see "Usage caps").

## Postgres and the database bootstrap

Two ways to run this app locally:

- **Plain `uv run`, no Docker**: stays on the SQLite default above. Zero
  AWS; run `python -m app.db.init_local` once for the schema, and
  again after pulling a new migration (see "Run the dev server").
- **Docker Compose, prod-parity**: runs the full stack against real
  Postgres. `docker compose up --build` from the repo root starts, in
  order: a `postgres` service (Postgres 17, matching Neon), a
  `bootstrap` service, an `init_local` service that seeds the demo
  account, then the `app` service, which connects as a limited role.
  Compose sets all the env vars for you.

`app/bootstrap_db.py`, run via `python -m app.bootstrap_db` (or its
`lambda_handler` in AWS), owns the schema and has two modes:

**Cloud (`USE_SSM` on).** Neon already provides the role and database,
so the bootstrap only runs the migrations, connecting with the URL in
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
4. Runs the migrations, connected as that role, so the role owns the
   tables (and can `ALTER` them in later migrations).

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
delete its projects, and those changes persist across deploys. There is
no reset: the bootstrap never deletes or re-seeds an existing demo
account, whatever event it's invoked with.

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
the next deploy of that commit or a later one. Prod reports the same
version dev did for the image it promotes. Image tags are unaffected:
they stay `<timestamp>-<sha>`, unique per build.

## Run the tests

Two kinds, told apart by the `integration` pytest marker (registered in
`pyproject.toml`) and the `tests/integration/` directory:

```
uv run pytest                  # unit tests (the default)
uv run pytest -m integration   # integration tests, needs Postgres (below)
```

Or from the repo root: `make test-backend` and `make test-integration`.

**Unit tests** (`tests/*.py`, the default run; integration tests are
deselected by `addopts`). Each test runs against its own fresh, isolated
in-memory SQLite database (see `tests/conftest.py`), never the dev
`hub.db` file, never shared across tests, never a real database. No
services needed. This is what CI's `test` job runs.

**Integration tests** (`tests/integration/`, every module marked
`pytestmark = pytest.mark.integration`). The same app and `Store`, but
against real Postgres 17: the Docker Compose `postgres` service. Start
it from the repo root with `docker compose up -d --wait postgres` (or
let `make test-integration` do it). Each run:

- creates a throwaway database (`hub_it_<random>`) as the Compose
  superuser, builds its schema with the real Alembic migrations, and
  drops it at the end, so the Compose app's own `hub_dev` data is never
  touched;
- truncates every table between tests;
- runs the local bootstrap end to end once, against its own throwaway
  role and database, to prove the least-privilege grants are enough for
  the migrations.

They cover what SQLite can't: the native `status` enum, case-insensitive
email lookups on case-sensitive text, the unique email index under a
racing insert, timezone-aware timestamps, foreign-key cascades, and the
migrations' stamp, upgrade and downgrade paths on Postgres.
`INTEGRATION_ADMIN_URL` points them at another Postgres (default
`postgresql+psycopg://postgres:postgres@localhost:5432/postgres`, the
Compose service). Without a reachable Postgres they fail with a message
saying how to start it, rather than skipping silently. CI's
`integration` job runs them.

## Auth

Roll-your-own: passwords hashed with argon2 (via argon2-cffi), JWT bearer
tokens (via PyJWT), OAuth2 password flow. `POST /auth/login` takes
`application/x-www-form-urlencoded` with `username` (the email) and
`password`, matching openapi.yaml and FastAPI's built-in OAuth2 tooling.

All of the JWT secret/algorithm/expiry live in `app/core/config.py` (see
Config above); nothing security-relevant is hardcoded in
`app/auth/security.py` itself.

The web app never sees the token. `POST /auth/login` and
`POST /auth/register` return it in the body (for API clients such as a
future iOS app or scripts, which send it back as
`Authorization: Bearer <token>`) and also set it as the `hub_token`
cookie: `HttpOnly` (JavaScript can't read it, so an XSS bug can't steal
it), `SameSite=Strict` (the browser never sends it on a cross-site
request, which is the CSRF defence), `Path=/`, `Max-Age` matching
`ACCESS_TOKEN_EXPIRE_MINUTES`, and `Secure` when deployed
(`is_deployed()`, so dev as well as prod).
Protected routes accept either; the header wins when both are sent
(`app/auth/dependencies.py`). `POST /auth/logout` clears the cookie, and
a cookie that fails validation is cleared on the 401 that rejects it.
Tokens are still stateless JWTs: logout doesn't revoke a copy held
elsewhere, it expires on its own.

Locally the frontend (`:5173`) and API (`:8000`) are different origins
but the same site, so the cookie still flows; the frontend sends
`credentials: 'include'` and CORS allows credentials for
`CORS_ORIGINS`.

## Rate limits

Two layers. The full picture, including what each layer does and doesn't
protect against, is in `security/RATE_LIMITING.md`.

| Layer | Threshold | Scope | Where |
|---|---|---|---|
| Login attempts | 5 per minute (sliding window) | Per client IP, `POST /auth/login` only, successful and failed attempts alike | `app/auth/rate_limit.py`, `LOGIN_RATE_LIMIT_PER_MINUTE` |
| Sign-up attempts | 3 per minute (sliding window) | Per client IP, `POST /auth/register` only, counted separately from logins; successful, duplicate (409) and invalid (422) attempts alike | `app/auth/rate_limit.py`, `REGISTER_RATE_LIMIT_PER_MINUTE` |
| Error reports | 30 per minute (sliding window) | Per client IP, `POST /client-errors` only, counted separately | `app/auth/rate_limit.py`, `CLIENT_ERROR_RATE_LIMIT_PER_MINUTE` |
| API Gateway stage throttle | 50 requests/second steady, bursts up to 100 | All clients and routes together | `infra/hub/apigateway.tf` (`default_route_settings`) |

How the client is identified: the address in `CLIENT_IP_HEADER`
(`CloudFront-Viewer-Address` when deployed), else the TCP peer. If that
address is in `TRUSTED_PROXY_IPS` (Cloudflare's ranges when deployed;
empty, so off, by default), the client is taken from `X-Forwarded-For`
instead, read from the right past trusted proxies; see
`security/RATE_LIMITING.md` for why that can't be spoofed. The
header may be `ip:port` (CloudFront's form, IPv6 unbracketed), a bare
address, or `[ipv6]:port`; a suffix only counts as a port if it's
numeric and at most 65535. A malformed value falls back to the peer
address instead of becoming a bucket of its own. IPv4-mapped IPv6
(`::ffff:203.0.113.7`) counts as the IPv4 address, and IPv6 is counted
per `/64` network, since one subscriber usually controls a whole `/64`
and could otherwise rotate addresses to reset the count.

Over any limit the response is `429 Too Many Requests`. The per-IP
limits add a `Retry-After` header (seconds) and don't count the
rejected attempt, so a client that keeps retrying is let back in once
its oldest attempt is a minute old. Both are off locally and on in dev
and prod (`is_deployed()`).

Known gaps:

- The per-IP limits are in-memory per process. Each warm Lambda container
  counts separately, so with several running a client can get a few
  times the limit through. The API Gateway throttle is the global
  backstop. A shared counter (e.g. a database table) would close this
  if it ever matters.
- Behind CloudFront the client IP comes from `CloudFront-Viewer-Address`
  (`CLIENT_IP_HEADER`). CloudFront only adds that header when the
  origin request policy lists it, so `/api/*` uses a custom allowlist
  policy (`aws_cloudfront_origin_request_policy.api` in
  `infra/hub/frontend.tf`) instead of the managed
  `AllViewerExceptHostHeader`, which didn't. If the header were missing,
  the app would fall back to the peer address, which is CloudFront's,
  and the limit would apply per CloudFront edge: one user's five
  attempts would lock out everyone on that edge. The allowlist also
  means a request header the API starts to rely on must be added to
  that policy, or CloudFront drops it.
- API Gateway's default `execute-api` endpoint is public, so a request
  sent there directly could set `CloudFront-Viewer-Address` to anything.
  Closed by origin verification (below): without CloudFront's secret
  header, such a request gets 403 before the rate limit runs.

## Usage caps

`app/core/quotas.py`, configured in `app/core/config.py`. Over a cap the
API answers `403` with a message the frontend shows as-is; `0` turns a
cap off.

| Cap | Default | Checked on |
|---|---|---|
| `MAX_ACCOUNTS` (total accounts) | 1000 when deployed, off locally | `POST /auth/register` |
| `MAX_PROJECTS_PER_USER` | 500 | `POST /projects` |
| `MAX_NOTES_PER_PROJECT` | 500 | `POST /projects/{project_id}/notes` |

They're soft: the check counts, then inserts, with no lock between, so
two requests racing at the boundary can both get through. Fine for what
they're for, bounding how much one account (or a burst of sign-ups) can
make the database hold. Accounts created outside sign-up (the
bootstrap's demo account) count toward `MAX_ACCOUNTS` but are never
blocked by it. Updates and deletes are never capped.

Text fields are length-limited, in characters: project `name` 256,
`pitch` 2000, `description` 5000, `nextAction` 1000, note `body`
10000. Longer input is a `422` from the input models
(`app/models/project.py`, `app/models/note.py`, where the limits are
defined once), and the database backs it up with CHECK constraints
(`app/db/orm.py`, migration `0002`), so nothing writing to the tables
directly can exceed them either. Migration `0002` refuses to run over a
database that already holds longer values, rather than truncating them;
see `ops/TROUBLESHOOTING.md`.

Lists and short fields are limited too: at most 50 tags per project,
each up to 64 characters; at most 50 links, each URL up to 2048
characters and label up to 200; display names up to 100. All are 422s
from the input models; the database backs up the display name length and
the tag and link counts (migration `0003`). A CHECK constraint can't
portably look inside each JSON array element, so the per-tag and
per-link lengths are enforced by the API only.

`POST /auth/login` also caps the password at 256 characters, the same
maximum sign-up enforces: anything longer is a `422` before any argon2
work, so one request can't burn seconds of Lambda CPU hashing a huge
input. Those attempts still count toward the login rate limit.

## Frontend error reports

`POST /client-errors` (`app/routers/errors.py`) takes reports from the
web app (`frontend/src/lib/error-reporting.ts`): uncaught errors,
unhandled promise rejections, React render crashes, and API calls that
got no response or a 5xx. Each is written as one JSON line on the
`app.client_errors` logger, so CloudWatch Logs when deployed and the
console locally, plus Grafana Cloud (Loki) as OTLP log records wherever
`OTEL_ENABLED` is on; nothing goes in the database. The request itself
shows up in the per-endpoint metrics as `client_errors_post_*`.

```
WARNING:app.client_errors:client_error {"endpoint": null, "kind": "error", "message": "TypeError: ...", "method": null, "stack": "...", "status": null, "url": "https://hub.dnls.dev/project/...", "user_agent": "...", "user_id": "..."}
```

Unauthenticated, because errors happen while signed out too; rate
limited per IP (above) and length-capped per field instead. A valid
session attaches the user id (never the email). URLs lose their query
string and fragment. The browser side sends at most 20 reports per page
load and each distinct one once. Querying them in Grafana:
`ops/MONITORING.md`.

## Origin verification

Deployed, every request must come through CloudFront. API Gateway's
default `execute-api` URL is public, and a request sent there skips
CloudFront entirely: it could claim any `CloudFront-Viewer-Address` and
so dodge the per-IP login limit, and it skips anything else CloudFront
does. To close that:

- OpenTofu generates a random secret per environment
  (`random_password.origin_verify`) and stores it in SSM
  (`/hub-<env>/origin-verify-secret`, `infra/hub/database.tf`).
- CloudFront adds it as an `X-Origin-Verify` header to every request it
  forwards to the API (`custom_header` on the API Gateway origin,
  `infra/hub/frontend.tf`). CloudFront replaces any `X-Origin-Verify` a
  viewer sends, so a client can't supply its own.
- The Lambda loads the same value at startup from the parameter named by
  `ORIGIN_VERIFY_PARAM_NAME`, and `OriginVerifyMiddleware`
  (`app/auth/origin_verify.py`), the app's outermost layer, answers
  `403 {"detail": "Forbidden"}` to any request whose header is missing
  or wrong, compared in constant time. That happens before CORS,
  routing, auth or the rate limit.
- Each rejection is logged as a warning on the `app.security` logger
  (`origin_verify_rejected method=... path=... source_ip=... reason=missing|mismatch`),
  which lands in the Lambda's CloudWatch log group. The header value is
  never logged.

Only with `USE_SSM` on. Local and Docker Compose runs have no CloudFront
in front of them, so the check is off and the setting is ignored. With
`USE_SSM` on, a Lambda that can't load the secret refuses to start
rather than run unprotected.

On deploy, OpenTofu updates the CloudFront distribution and waits for it
to finish deploying before it updates the Lambda (`depends_on` in
`infra/hub/lambda.tf`), so CloudFront is already sending the header when
a Lambda that checks for it goes live. To rotate the secret:
`tofu apply -replace=random_password.origin_verify` in each workspace.
The new value bumps the SSM parameter's version, which the Lambda
carries as `ORIGIN_VERIFY_VERSION`, so the apply also updates the
function and replaces warm containers holding the old cached value. The
app accepts one value at a time, though, so between CloudFront switching
to the new secret and the Lambda update finishing (a few minutes),
requests get 403. Rotate in a quiet moment.

The CI and promote smoke tests call `/api/health` through the site URL,
so they pass through CloudFront and are unaffected. Anything that needs
to call the API directly (a script, a load test) must go through the
site URL too.
