# hub-platform repo inventory

> Point-in-time snapshot, not a live description. Figures below were checked against the repo, test runs, and OpenTofu state on the date shown; re-run the commands in each section before relying on them later.

Snapshot of `main` at `6bd192a` (2026-10-02), plus the commit that adds this version of the file (which also touches `AGENTS.md`, `backend/.env.example`, `backend/app/core/config.py`, `docs/tech-debt.md`, and `openapi.yaml`). Secret values are redacted throughout. Replaces the earlier snapshot of `d514520` (2026-09-29), which predated CI/CD, the move from Aurora to Neon, the E2E suite, observability, and the prod deployment.

## 1. Tree (depth 3, generated/vendor dirs excluded)

```
.                       root: AGENTS.md README.md LICENSE openapi.yaml docker-compose.yml
                              .gitignore .prettierignore .pre-commit-config.yaml
.claude/                CLAUDE.md, launch.json, agents/qa-engineer.md,
                        skills/{design-review,e2e-testing,release,security-scanning}/SKILL.md
.github/                workflows/{ci,promote,observability-alert-handler}.yml
                        scripts/service-version.sh
docs/                   8 files: agent-extension-pack permissions design-notes prompts
                        repo-inventory results specs tech-debt (.md)
backend/                68 tracked files
  app/  main.py lambda_handler.py bootstrap_db.py
        auth/ core/ db/ models/ routers/
  observability/  OTel setup, metrics registry, local Grafana/Tempo/Prometheus/Loki stack
  oncall/         diagnose.py (on-call diagnostic agent)
  tests/          20 test files
  Dockerfile pyproject.toml uv.lock .python-version .env.example README.md
frontend/               86 tracked files
  src/  App.tsx main.tsx auth*.ts(x) store*.ts(x) use-*.ts test-setup.ts
        components/ lib/ pages/ services/
  tests/  api.spec.ts app.spec.ts helpers.ts (Playwright)
  package.json pnpm-lock.yaml vite.config.ts playwright.config.ts tsconfig*.json
  eslint.config.js components.json .env.example
infra/                  20 tracked files
  bootstrap/  backend main providers .tf, .terraform.lock.hcl (GitHub OIDC trust, run once by hand)
  hub/        apigateway backend bootstrap certs database dns ecr frontend lambda main
              outputs providers .tf, .terraform.lock.hcl, terraform.tfvars.example
  BOOTSTRAP.md PLACEMENT.md
custom-agent/           on-call-diagnostic/README.md
```

203 tracked files in total. Gitignored and present on disk: `backend/.env`, `frontend/.env`, `backend/hub.db`, `infra/hub/terraform.tfvars`, `.secrets/`, `.vscode/`. `infra/shared/` (Aurora, VPC) no longer exists.

## 2. Backend

- FastAPI 0.141.1 on Python 3.12 (`.python-version`; `requires-python >=3.12`). App object: `app` in `backend/app/main.py`.
- Local: `uv run uvicorn app.main:app --reload`, after `python -m app.db.init_local` once. Lambda: `app/lambda_handler.py` wraps the app in Mangum with `api_gateway_base_path` from `API_BASE_PATH` (`/api` when deployed). Prod image CMD is `app.lambda_handler.handler`.
- Import does no database work. At import `app.main` resolves the JWT secret and runs `require_safe_jwt_secret()` (refuses to start with a missing or dev-default secret outside a local run, or whenever `USE_SSM` is on) and `require_safe_seed_setting()`. Tables come from `init_local` locally and the bootstrap Lambda when deployed.
- CORS origins from `CORS_ORIGINS` (default the Vite dev server); deployed, CloudFront makes the site same-origin. `/docs`, `/redoc`, `/openapi.json` are served only for a local run (not `is_deployed()`: `USE_SSM` off and `ENVIRONMENT` local/development/dev). At the snapshot commit they keyed on `ENVIRONMENT` alone, which left them public on the dev Lambda; fixed since.

Modules:
- `core/config.py`: the single settings source; env + SSM resolution, JWT secret and seed guards, cookie and rate-limit settings.
- `db/session.py`: lazy engine (`pool_pre_ping=True`), session factory, `get_db_session` dependency.
- `db/orm.py`: SQLAlchemy declarative tables.
- `db/store.py`: `Store` class (all queries), record dataclasses, `get_store` dependency.
- `db/seed.py`: demo user, 10 projects, notes. `db/init_local.py`: local table creation and optional seeding (refuses to run with `USE_SSM` on).
- `auth/security.py`: argon2 hashing (argon2-cffi directly; passlib removed), JWT encode/decode (PyJWT, HS256).
- `auth/dependencies.py`: `get_current_user`, reading `Authorization: Bearer` or the `hub_token` cookie.
- `auth/cookies.py`: set/clear the session cookie. `auth/rate_limit.py`: per-IP login limiter.
- `models/base.py|project.py|note.py|user.py`: Pydantic camelCase schemas; project links must be http(s).
- `routers/health.py|auth.py|projects.py|notes.py`: endpoints.
- `bootstrap_db.py`: schema bootstrap and demo seeding in AWS; local role/database creation (section 3).
- `observability/`: OpenTelemetry tracing and metrics (FastAPI and SQLAlchemy instrumentation), `ENDPOINT_METRICS` registry covering every API operation.
- `oncall/diagnose.py`: on-call diagnostic agent (OpenAI), run by `observability-alert-handler.yml`.

Config (`app/core/config.py`), all from env with local-safe defaults: `ENVIRONMENT` (default `local`), `USE_SSM`, `DATABASE_URL` (default `sqlite:///./hub.db`), `HUB_JWT_SECRET`, `ACCESS_TOKEN_EXPIRE_MINUTES` (60), `SEED_DEMO_DATA`, `CORS_ORIGINS`, `AUTH_COOKIE_SECURE`, `LOGIN_RATE_LIMIT_PER_MINUTE` (5 deployed, 0 locally), `CLIENT_IP_HEADER`, `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_SDK_DISABLED`, `SERVICE_VERSION`, `LAMBDA_IMAGE_TAG`, `API_BASE_PATH`. With `USE_SSM` on, the database URL and JWT secret come from SSM SecureStrings named by `DB_URL_PARAM_NAME` (the full connection URL) and `JWT_PARAM_NAME`, cached per process. Bootstrap only: `DEMO_PASSWORD_PARAM_NAME`, `MASTER_DB_PARAM_NAME`, `MASTER_DB_HOST|PORT|USER|PASSWORD`. Parameter names come from OpenTofu. `backend/.env.example` documents all of these except the bootstrap-only `DEMO_PASSWORD_PARAM_NAME`/`MASTER_DB_PARAM_NAME` and the Lambda-set `SERVICE_VERSION`/`LAMBDA_IMAGE_TAG`/`OTEL_SDK_DISABLED`.

Dependencies (source of truth `backend/uv.lock`): argon2-cffi 25.1.0, boto3 1.43.98, email-validator 2.3.0, fastapi 0.141.1, mangum 0.22.0, opentelemetry-sdk 1.45.0 (plus OTLP HTTP exporter and FastAPI/SQLAlchemy instrumentation), psycopg[binary] 3.3.6, pyjwt 2.15.1, python-dotenv 1.2.3, python-multipart 0.0.32, sqlalchemy 2.0.54, uvicorn[standard] 0.53.0. Transitive: pydantic 2.13.5, starlette 1.6.0. Dev: httpx 0.28.1, pytest 9.1.1, pyyaml 6.0.3. No rate-limit library: the login limiter is in-house.

## 3. Database layer

- Engine: `backend/app/db/session.py` `_get_engine()`, built lazily and cached in a module global, `pool_pre_ping=True` (Neon closes idle connections). SQLite gets `check_same_thread=False` and an FK pragma listener.
- Session: `sessionmaker(autoflush=False, expire_on_commit=False)`; `get_db_session()` generator dependency (yield, close in finally); `get_store` wraps it. No middleware.
- URL: `config.get_database_url()`. SQLite by default; Postgres via `DATABASE_URL` or, with `USE_SSM`, the SSM parameter. A plain `postgresql://` URL (Neon's form) is rewritten to `postgresql+psycopg://`, query string kept.
- Sync SQLAlchemy 2.0 (`select`, `Mapped`). All routes are sync `def`.
- Transactions: each `Store` write method commits itself. Note add/delete then calls `update_project` in a separate commit (two transactions per request); if the project vanishes in between, the route returns 404.
- Migrations: none. No Alembic. `Base.metadata.create_all` from `init_local` (local) or the bootstrap Lambda (deployed), never at app import.
- Schema: `String(36)` IDs with Python-side `uuid4`; `tags` and `links` as `sqlalchemy.JSON`; `status` as `SAEnum`; `DateTime(timezone=True)`; FKs with `ondelete="CASCADE"`; unique index on `users.email`, lookups via `func.lower`.
- `bootstrap_db.py`: CLI `python -m app.bootstrap_db` and Lambda `app.bootstrap_db.lambda_handler`, run by CI on every deploy. Cloud mode (`USE_SSM`): creates missing tables using the direct (non-pooled) Neon URL and seeds the demo account from SSM if absent, never modifying an existing one. Local mode: also creates the database and a least-privilege login role using `MASTER_DB_*` (identifiers validated and quoted).
- Hosting: Neon Postgres for dev and prod, reached over the public internet with TLS (no VPC). The app uses the pooled URL, the bootstrap the direct URL. Local: SQLite, or Postgres 17 via Docker Compose.

## 4. API contract

- `openapi.yaml` (OpenAPI 3.1.0, 669 lines) is the contract. `backend/tests/test_openapi_contract.py` fails if the spec's and the app's path+method sets differ, and checks the prod server URL is declared.
- Security schemes: `bearerAuth` (HTTP bearer JWT) and `cookieAuth` (`hub_token` cookie).
- Endpoints: public `GET /health`, `POST /auth/register`, `POST /auth/login` (429 over the rate limit), `POST /auth/logout`; authenticated `GET /auth/me`, `GET|POST /projects`, `GET|PATCH|DELETE /projects/{project_id}`, `GET|POST /projects/{project_id}/notes`, `DELETE /notes/{note_id}`. Attachments are no longer in the spec (deferred feature).
- Servers: `https://hub.dnls.dev/api` (prod), `https://hub-dev.dnls.dev/api` (dev), `http://localhost:8000`.

## 5. Frontend

- React 19.2.4, Vite 6.4.3, TypeScript 5.7.3, Tailwind 4.3.3, shadcn/ui, `@base-ui/react` 1.5.0, react-router-dom 7.18.4. pnpm 12.3.4 (`packageManager`). Node not pinned (no `.nvmrc`/`engines`); CI uses Node 22, local is v22.23.3.
- Centralized client: `frontend/src/services/api/` (`index.ts` exports `api`/`authApi`; HTTP in `http.ts`; endpoints in `real.ts`, `auth.ts`). Components never call `fetch`.
- Base URL: `VITE_API_BASE_URL` (`src/lib/config.ts`). Unset means same-origin `/api` (every deployed build); `.env.example` sets `http://localhost:8000` for local dev.
- Auth: the web app's session is the `hub_token` cookie (HttpOnly, SameSite=Strict, Secure when deployed), set by `POST /auth/login` and `POST /auth/register`. Frontend code never sees or stores the token; `http.ts` sends `credentials: 'include'`, and on load the app calls `GET /auth/me` to find out whether it is signed in. `POST /auth/logout` clears the cookie (JavaScript can't remove an httpOnly cookie). The API still returns the token in the response body and accepts `Authorization: Bearer`, for future iOS and agent clients; the header wins when both are sent. No refresh token; a 401 mid-session triggers a logout handler.
- Project links render as anchors only for http(s) URLs (`isSafeLinkUrl`); anything else shows as plain text.
- localStorage holds only the theme choice (`hub.theme`).

## 6. Tests

| Suite | Runner | Count | Command |
|---|---|---|---|
| Backend unit/integration | pytest 9.1.1 | 332 tests, 21 files | `cd backend && uv run pytest` |
| Frontend unit | Vitest 5.0.1 + RTL 16 + jsdom | 173 tests, 20 files | `cd frontend && pnpm test` |
| E2E | Playwright 1.63.0 (Chromium) | 189 tests: `api.spec.ts` 100, `app.spec.ts` 89 | `cd frontend && pnpm exec playwright test` with uvicorn on :8000 and Vite on :5173 |

- Backend per file: test_auth 12, test_auth_cookie 8, test_bootstrap_db 28, test_config 54, test_cors 7, test_demo_seed 18, test_init_local 9, test_lambda_handler 2, test_notes 12, test_observability 20, test_observability_config 6, test_observability_stack 20, test_oncall 12, test_openapi_contract 2, test_origin_verify 10, test_password_hashing 24, test_projects 22, test_rate_limit 34, test_service_version 8, test_session 2, test_startup 22.
- Backend count history on 2026-10-02: 283 at the snapshot commit, 299 after the dev-vs-deployed fix (`is_deployed()`, 16 tests), 317 after origin verification (18 tests), 339 after the sign-up rate limit and IPv6 client-IP handling (22 tests), 332 after removing the demo reset (its 12 tests replaced by 5 no-reset safety cases).
- Backend API tests go through `TestClient`, so they are integration tests in practice. No markers or subdirectories separate unit from integration.
- Real DB: backend tests use in-memory SQLite (`conftest.py` forces `DATABASE_URL=sqlite:///:memory:`, per-test `StaticPool` engine). `test_bootstrap_db.py` uses a fake psycopg connection. Nothing touches Postgres. E2E runs against the local SQLite `hub.db`.
- CI runs the backend and frontend unit suites on every PR and push to main. E2E, lint, format, and build are run locally, not in CI.

Last lines of the backend run (re-run after the post-snapshot fixes below):
```
.venv/.../fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
.venv/.../starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
.venv/.../mangum/adapter.py:65: DeprecationWarning: There is no current event loop
332 passed, 3 warnings in 17.21s
```
Frontend: `Test Files 20 passed (20)`, `Tests 173 passed (173)`. Playwright: `189 passed (24.4s)`.

## 7. Containers

- `backend/Dockerfile`: `deps` (`ghcr.io/astral-sh/uv:0.9-alpine`, `uv export --frozen --no-dev`); `prod` (`public.ecr.aws/lambda/python:3.12`, CMD `app.lambda_handler.handler`); `dev` (`python:3.12-slim`, uvicorn with `--reload`, EXPOSE 8000). The bootstrap Lambda reuses the prod image with command override `app.bootstrap_db.lambda_handler`.
- `docker-compose.yml`: `postgres` (postgres:17-alpine, 5432, volume `postgres_data`, healthcheck); `bootstrap` (runs `python -m app.bootstrap_db`); `init_local` (runs `python -m app.db.init_local`); `app` (dev target, 8000). All `ENVIRONMENT=local`. Local-only Postgres credentials are inline.
- `backend/observability/docker-compose.yml`: optional local collector, Tempo, Prometheus, Loki, and Grafana.
- Image size: not measured.

## 8. Infrastructure and CI/CD

- OpenTofu, region us-east-1, state in S3 bucket `dnls-hub-tofu-state` with lockfile locking. Two roots:
  - `infra/bootstrap`: 4 resources (GitHub OIDC provider, CI role, its policy attachment and inline policy), applied once by hand.
  - `infra/hub`: 36 resource blocks, workspaces `dev` and `prod`. OpenTofu state on the snapshot date holds 34 managed resources in each workspace: 29 AWS, 2 Cloudflare DNS records (frontend alias and ACM validation), 1 `random_password` (JWT secret), and 2 `terraform_data` input guards. Earlier notes cited 33; the state shows 34.
- AWS per environment: Lambda (backend, container image) and a bootstrap Lambda, each with IAM role, policies, and log group; ECR repository (MUTABLE tags; untagged images expire 7 days after push, and only the 10 newest images are kept) with lifecycle policy; API Gateway HTTP API (stage throttling 50 rps, burst 100); S3 bucket with OAC; CloudFront distribution with an SPA-routing function, forwarding `/api/*` to API Gateway; ACM certificate; SSM SecureStrings for the pooled and direct database URLs, JWT secret, and demo password.
- Environments: dev at `https://hub-dev.dnls.dev`, prod live at `https://hub.dnls.dev`.
- Workflows (`.github/workflows/`):
  - `ci.yml`: on PR, run tests; on push to main, run tests then deploy dev (build and push the image with a timestamp-sha tag, `tofu apply`, run the bootstrap Lambda, build the frontend, sync to S3, invalidate CloudFront, smoke-test `/api/health`).
  - `promote.yml`: manual (type "promote"); copies the dev image to prod ECR without rebuilding, applies prod, rebuilds and deploys the frontend, smoke-tests prod.
  - `observability-alert-handler.yml`: manual on-call diagnostic after a Grafana alert.
- Secrets reach OpenTofu as `TF_VAR_*` from GitHub Environment secrets (`NEON_URLS`, `DEMO_PASSWORDS`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID`, OTEL headers). AWS auth is GitHub OIDC, no static keys.
- Versioning: `.github/scripts/service-version.sh` derives `SERVICE_VERSION` from git tags for both Lambdas.
- Observability: dev and prod export OTLP traces and metrics to Grafana Cloud.

## 9. Docs and project meta

- Root `README.md` (what Hub is, quick start, architecture, stack, local development, deployment, observability, on-call, API, testing, AI-native workflow, contributing, troubleshooting, license) and `LICENSE`.
- `backend/README.md` sections: Setup, Run the dev server, Config, Database, Postgres and the database bootstrap, Seeded demo account, Releases and SERVICE_VERSION, Run the tests, Auth, Rate limits. `backend/observability/README.md` covers local telemetry.
- `AGENTS.md` (agent instructions); `.claude/` holds `CLAUDE.md`, the QA engineer subagent, and four skills (release, e2e-testing, security-scanning, design-review). `.pre-commit-config.yaml` runs gitleaks on staged changes (opt-in per clone with `pre-commit install`).
- `docs/`: specs (source of truth for product and data model), design-notes, tech-debt, prompts, results, agent-extension-pack, permissions, and this file. No formal ADRs. No `security/`, `ops/`, `agent-capabilities/`, or `mcp-server/` directories yet.

## 10. Git state

- Branch `main`, HEAD `6bd192a`, remote `origin` (GitHub `rdanielsstat/hub-platform`, public), tracking `origin/main`. No stashes. Other branches, local and on origin: `observability-oncall-agent`, `otel-enabled-dev-lambda`, `semver-service-version`, `service-version-dev-lambda`.
- Recent: 6bd192a security improvements (gitleaks hook, dependency bumps, login rate limit, API Gateway throttling, link URL check, cookie sessions); 1afb349 Cloudflare token for prod deploy; ad2c8d9 JWT secret rotation; 8ebc8ae prod OTel and promote workflow.

## Changes since the snapshot

Security work on top of `6bd192a`, from the follow-up scans on 2026-10-02. Test counts in section 6 include all of it; the rest of this file still describes `6bd192a`.

Committed in `9af9e53`, deployed to dev and promoted to prod, and verified live on both (health 200, `/api/docs` 404, direct `execute-api` 403 with or without a guessed header, `Secure` session cookie, dev login limit returning 429 on the 6th attempt):

- Client IP for the login rate limit: `/api/*` uses a custom origin request policy (`<env>-forward-viewer-address`, `infra/hub/frontend.tf`) that forwards an allowlist of headers plus `CloudFront-Viewer-Address`, replacing the managed `AllViewerExceptHostHeader`, which didn't forward it.
- Dev vs deployed: `is_deployed()` (`USE_SSM` on, or a non-local `ENVIRONMENT`) drives the Secure cookie, the rate limits, and the API docs gate. Before, the dev Lambda (`ENVIRONMENT=dev`) got local defaults: no rate limit, no Secure flag, public `/docs`.
- Origin verification: a per-environment `random_password` in SSM, sent by CloudFront as `X-Origin-Verify` (origin `custom_header`); `app/auth/origin_verify.py` answers 403 without it when `USE_SSM` is on.
- Infra: 37 managed resources per workspace in OpenTofu state (was 34): the origin request policy, `random_password.origin_verify`, and its SSM parameter.

After `9af9e53` (backlog remediation):

- Sign-up rate limit: 3 per minute per client IP on `POST /auth/register` when deployed (`REGISTER_RATE_LIMIT_PER_MINUTE`), counted separately from logins.
- Client IP parsing: bare, bracketed and IPv4-mapped IPv6 handled; malformed headers fall back to the peer address; IPv6 counted per `/64`.
- Demo reset removed: `reset-demo.yml`, the bootstrap's `{"reset_demo": true}` path, and `Store.delete_user_and_owned_data` are gone. The demo account stays as seeded for the review period; the bootstrap never deletes or re-seeds it.
- CI: `secrets-scan` job runs gitleaks over the full history on every PR and push and gates the dev deploy; reviewed false positives in `.gitleaksignore`.

## Risks

- `infra/hub/tfplan` and `infra/hub/tfplan-prod`, committed in `8ebc8ae` and removed in `1f59439`, contained Neon connection strings and other sensitive values and remain in public history. Credentials in them must be treated as exposed until rotated; `tfplan*` is now gitignored. The JWT secret was rotated in `ad2c8d9`.
- The login rate limit is per Lambda container, and relies on CloudFront forwarding `CloudFront-Viewer-Address` (in a custom `/api/*` origin request policy since `9af9e53`; per-user behaviour still to confirm from two networks). The API Gateway default endpoint is public and bypasses CloudFront (origin verification since `9af9e53` rejects such calls with 403, verified on dev and prod).
- A writable demo account with a known local password (`app/db/seed.py`) exists locally; deployed environments seed it from SSM.
- `docker-compose.yml` commits local-only Postgres credentials.
- No migrations tool: schema changes beyond new tables need manual handling.
