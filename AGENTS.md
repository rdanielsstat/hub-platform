# AGENTS.md

Standing instructions for AI coding agents working in this repo.

## Project

Hub: a personal platform to capture, organize, and triage project ideas, from
small sparks to standalone builds. See `product-spec.md` (repo root) for the product spec
and data model. That document is the source of truth; don't duplicate it
here and don't let this file drift from it.

## Structure

- `frontend/`: the app. Vite 6 + React 19 SPA, self-contained (its own
  `package.json`, `src/`, config).
- `backend/`: the API. FastAPI app, self-contained (its own `pyproject.toml`,
  `app/`, `tests/`). See "Backend" below.
- `docs/`: specs, planning notes, tech debt, and session logs. Reference 
  material, not code.
- `openapi.yaml` (repo root): the API contract frontend and backend are both
  built against.
- `infra/`: OpenTofu infrastructure as code (bootstrap and hub workspaces for
  dev and prod). See `infra/BOOTSTRAP.md` for deployment setup.
- `.github/workflows/`: CI/CD pipelines (ci, promote, observability
  alert handling).
- `docker-compose.yml` (repo root): local Postgres 17, bootstrap, and app for
  prod-parity testing.
- `Makefile` (repo root): common commands (`make help`), including the test
  layers (`test-unit`, `test-integration`, `test-e2e`, `test-e2e-docker`),
  `docker-up`/`docker-down`, and `check` (every local gate below).
- `backend/alembic/`: Alembic migration scripts (`versions/`); run by
  `backend/app/db/migrations.py`.
- `ops/`: runbooks: deployment, health checks, troubleshooting, monitoring.
- `security/`: rate limiting, agent security, gitleaks, dependencies, image
  and IaC scan results (`IAC_SCANS.md`), data policy, and the security
  checklist (what's checked and what's open).
- `backend/observability/`: OpenTelemetry setup, local Grafana/Tempo/Prometheus
  stack.
- `backend/oncall/`: on-call agent (OpenAI diagnostic for dev alerts).
- `.claude/`: agent configuration, skills, and subagent definitions.

## Frontend

Stack: Vite 6.4, React 19.2, TypeScript 5.7, Tailwind 4.3 via @tailwindcss/vite,
shadcn/ui with base-nova style (`components.json`), @base-ui/react 1.5 for
accessible primitives (dialogs, etc.), pnpm 12.3. State management: React Context
(no external library), with per-user store and auth contexts.

All commands run from inside `frontend/`:

```
pnpm install
pnpm dev            # start the dev server
pnpm build          # tsc -b && vite build, must be clean before calling a task done
pnpm lint           # eslint ., must stay 0 errors / 0 warnings
pnpm format         # prettier --write .
pnpm format:check   # prettier --check .
```

- The `@/` import alias resolves to `frontend/src` (set in both
  `tsconfig.json` and `vite.config.ts`).
- All data access goes through `frontend/src/services/api/`. Never call
  `fetch` directly from a component. That layer is real HTTP against the
  FastAPI backend (`services/api/real.ts`, via `http.ts`); it's the seam
  that would let a future consumer (native iOS, agents) swap in without
  touching components, so keep components talking to `api`/the store, not
  to the HTTP internals.

## Backend

FastAPI 0.141 app in `backend/`, Python 3.12, dependencies managed with `uv`.

```
uv sync                              # install, from inside backend/
SEED_DEMO_DATA=true uv run python -m app.db.init_local  # migrations + demo data
uv run uvicorn app.main:app --reload # start the dev server (http://localhost:8000)
uv run pytest                        # run the unit tests
uv run ruff check . && uv run ruff format --check .  # lint and format check
```

- Storage: SQLAlchemy 2.0 (`app/db/`), database-agnostic. SQLite locally and in tests
  (default), Neon Postgres when deployed (via `DATABASE_URL`), Postgres 17 in
  Docker Compose for local prod-parity. Schema changes are Alembic migrations
  (`backend/alembic/versions/`, run by `app/db/migrations.py`). A change to
  `app/db/orm.py` needs a reviewed `alembic revision --autogenerate`; the
  `test_migrations_match_the_orm_models` test fails until it has one.
- Auth: argon2-cffi (password hashing) + PyJWT (HS256), OAuth2 password flow.
  The web app's session is the JWT in an httpOnly, SameSite=Strict `hub_token`
  cookie; the API also accepts `Authorization: Bearer`, so the same API serves
  future iOS apps and agents. `/auth/login` (5/min), `/auth/register`
  (3/min) and `/client-errors` (30/min) are rate limited per client IP when
  deployed. Usage caps (`app/core/quotas.py`: accounts, projects per user,
  notes per project) answer 403. See `security/RATE_LIMITING.md`.
- Database outages: an `OperationalError` is a 503 with `Retry-After`
  (`app/main.py`), and the web app only treats a 401 as signed out
  (`frontend/src/auth.tsx`). Keep both true; see `ops/TROUBLESHOOTING.md`.
- Frontend errors: `POST /client-errors` (`app/routers/errors.py`) logs
  reports sent by `frontend/src/lib/error-reporting.ts`; the `app.client_errors`,
  `app.db` and `app.security` loggers are also exported to Grafana (Loki) as
  OTLP logs (`backend/observability/`).
- Security headers: CloudFront sends a strict CSP (no inline scripts; Google
  Fonts allowed) and HSTS (`infra/hub/frontend.tf`). Anything the frontend
  loads from a new origin must be added to `local.content_security_policy`.
- Deployed vs local: `is_deployed()` in `app/core/config.py` (true when `USE_SSM`
  is on or `ENVIRONMENT` isn't local/development/dev, so the dev Lambda counts)
  switches on the Secure cookie, the login rate limit, and hidden API docs. Use
  it, not `is_local_environment()`, for anything that should differ once deployed.
- Origin verification: deployed, every request must carry CloudFront's
  `X-Origin-Verify` secret or gets 403 (`app/auth/origin_verify.py`), which blocks
  direct calls to the public `execute-api` URL. A new request header the API
  needs must be added to the `/api/*` origin request policy in
  `infra/hub/frontend.tf`, or CloudFront drops it.
- Multi-user with per-user data isolation.
- `app/core/config.py` is the single settings source, read from environment
  variables with dev-safe defaults. Its `require_safe_jwt_secret()` runs at
  startup and refuses to start, outside a local `ENVIRONMENT` or whenever
  `USE_SSM` is on, if the JWT secret is unset or still the built-in dev default.
- Database initialization: Importing the app does no database work. The schema
  comes from Alembic migrations, applied by `init_local` locally (or with
  SEED_DEMO_DATA=true) and `bootstrap_db.py` (separate Lambda, run on every
  deploy) when deployed. Unit tests use `create_all` directly. Docker Compose
  runs both init_local and bootstrap. Pre-Alembic databases are stamped at the
  baseline revision automatically.

See `backend/README.md` for the full setup, config table, and details.

## Testing

Frontend: Vitest 5.0, React Testing Library 16, jsdom. `pnpm test`
(from inside `frontend/`) runs `vitest run`; 202 tests in 22 files as of
October 2026.

- Vitest runs with `test.globals` off (tests import from vitest explicitly);
  RTL auto-cleanup is wired by hand in `src/test-setup.ts`, which must stay.
- `base-ui`'s Dialog keeps its content mounted (hidden) while closed; scope
  queries to a landmark rather than the whole document to avoid matching hidden content.

Backend: pytest 9.1, two layers told apart by the `integration` marker.
`uv run pytest` (from inside `backend/`) runs the unit tests only: 435 tests in
27 files as of October 2026, each with its own in-memory SQLite database.
`uv run pytest -m integration` runs `tests/integration/` (38 tests in 4 files)
against the Docker Compose Postgres (`docker compose up -d --wait postgres`, or
`make test-integration`), in a throwaway database built by the real
migrations. `tests/test_startup.py` imports the app in a subprocess to check
startup behaviour (secret guards, deployed defaults, origin verification).

E2E: Playwright, 201 tests in `frontend/tests/`, in two projects. `chromium`:
`app.spec.ts` (89 browser tests) and `api.spec.ts` (104 API tests) cover signup,
login, the session cookie, dashboard, projects, filters, sorts, edits, deletes,
and API endpoints, against any backend on :8000. `docker-compose`:
`integration.spec.ts` (8 tests) covers the Compose stack, error reporting, and
backend and database outages; its outage tests stop and pause the Compose
Postgres and only run with `E2E_DOCKER=1` and `--workers=1`. Playwright starts
the Vite dev server itself (or reuses one); the backend must already be running
(`make docker-up`, or uvicorn; the `e2e-testing` skill starts one if needed).
Against a local or Compose backend, origin verification and the rate limits
are off. See `frontend/README.md`.

**All tests must pass before a task is considered done.** This includes:
- Frontend unit tests (`pnpm test` from `frontend/`)
- Backend unit tests (`uv run pytest` from `backend/`)
- Backend integration tests (`uv run pytest -m integration`) when a change
  touches the database layer or migrations, and Docker is available
- Lint checks must be 0 errors / 0 warnings (`pnpm lint` from `frontend/`, and
  `uv run ruff check .` from `backend/`)
- Backend formatting must pass (`uv run ruff format --check .` from `backend/`;
  `make fmt` fixes it)
- TypeScript build must be clean (`pnpm build` from `frontend/`)
- Format must pass (`pnpm format:check` from `frontend/`)

Note: CI runs the unit tests, a dependency scan (pip-audit and pnpm audit,
failing on HIGH and CRITICAL), a gitleaks secret scan of the full git
history, the backend integration tests and the Playwright suite (against
the Compose stack) on every PR and push; all five must pass before the
dev deploy runs. Actions in `.github/workflows/` are pinned to commit SHAs
(version in a trailing comment); keep it that way when adding or bumping one.
CI also runs the backend's Ruff lint and format check (in the `test` job);
the frontend's lint, format, and build checks are enforced locally before
committing (`make check`) and don't run in CI. Reviewed gitleaks false positives go in `.gitleaksignore` (by
fingerprint); never add a real secret there.

## Working Conventions

- Keep changes small and scoped to what was asked.
- Run lint, typecheck, build, and both test suites, and confirm they're
  clean before considering a task done.
- Match the existing code style. ESLint + Prettier are configured in
  `frontend/`, Ruff (lint and format) in `backend/`; lint must stay at
  0 errors / 0 warnings on both.
- No em dashes in any prose you write here, in commit messages, in code
  comments, or in chat responses. Use a period, comma, or colon instead; or 
  rephrase.
- Frontend requires Node 22 (CI uses Node 22; no .nvmrc pins the version locally,
  so your Node version may differ). pnpm 12.3 is pinned in `package.json`.

## Agent Permissions and Security Boundaries

**Agents must follow these rules:**

- **Never commit code.** Make the changes you're asked to make, write a summary of what changed, provide a suggested commit message (use conventional commit format: `feat:`, `fix:`, `refactor:`, etc.; no capital first letter; use semicolons to separate clauses, not periods). The human reviews and commits.
- **Never deploy.** All deployment is manual or via CI/CD gates. Agents can verify that deployment would work, but cannot trigger it.
- **Never modify real `.env` files or any secrets.** Files named `.env` (no `.example` suffix, e.g. `backend/.env`, `frontend/.env`) hold local configuration and possibly secrets: never read them into output, edit them, or commit them (they are gitignored). The tracked templates `backend/.env.example` and `frontend/.env.example` are different: they hold no secrets, and you CAN and SHOULD update them whenever a task adds, removes, or changes a setting, documenting what it does and its default. If a task needs a real value set somewhere, flag it and document what's needed.
- **Never make destructive changes to data.** Do not delete user data, reset the database, or modify production state without explicit approval.
- **Never restructure or refactor working code** unless explicitly asked. Stick to the task scope.
- **Never add dependencies casually.** Only add what a task actually requires. Justify each addition.
- **Never reproduce or edit files under `docs/`.** Those are planning and reference material, not code.

## Reusable Skills

Skills are discoverable workflows that agents load automatically. They live in `.claude/skills/<NAME>/SKILL.md` with frontmatter. When a task matches a skill, the agent loads and follows it without needing an explicit "use this file" instruction.

Current skills:

- **release**: Document and execute the release workflow: tag a version, push the tag and code to main, verify dev deployment, and document what was released. Based on the current workflow (tag only affects next dev deploy; no automated package registry publishing yet).
- **e2e-testing**: Run Playwright E2E tests, validate test fixtures, report results and edge cases. For local runs and feature validation; CI runs the same suites on every push.
- **security-scanning**: Run static security checks (dependencies, secrets, code patterns). CI already runs the dependency scan and gitleaks on every push; the skill adds bandit, trivy and the IaC scans, run by hand before releases (results in `security/`).
- **design-review**: Audit current UI/UX against best practices; review component library, layout efficiency, and data presentation; research emerging design tools and frameworks; report improvements, new affordances (buttons, controls), layout reorganization, and tool swap recommendations. Run on demand or periodically (quarterly suggested).

## Subagents

A subagent runs in a fresh context with a specialized role. It reads the role definition and operates independently, preventing context bias.

### QA Engineer Subagent

Role: Review a feature, change, or fix in a fresh context without implementation bias.

- Runs E2E tests (loads the `e2e-testing` skill)
- Validates against acceptance criteria
- Checks for edge cases and error paths
- Reports pass/fail with evidence (test output, screenshots, notes)
- Does NOT implement fixes; flags issues for the human to address

Invoked as: "Launch QA subagent to review [feature/change]"

Definition: `.claude/agents/qa-engineer.md`

## Deployment Architecture

**Infrastructure**: OpenTofu 1.12 (`infra/`), two roots: bootstrap (GitHub OIDC trust,
run once by hand) and hub (dev/prod workspaces). Region: us-east-1.

**Backend**: Lambda container image (ECR), Python 3.12. API Gateway HTTP API v2.
Requests routed via Mangum, which strips `/api` prefix. A separate bootstrap Lambda
(same image) applies the Alembic migrations and seeds the demo account on every
deploy, before the API Lambda switches to the new image. The image applies OS
security updates at build and ships without pip; ECR tags are immutable.

**Frontend**: React SPA built with Vite, served from S3 with Origin Access Control,
behind CloudFront. CloudFront Function routes SPA paths; forwards `/api/*` to API
Gateway through a custom origin request policy (allowlisted headers plus
`CloudFront-Viewer-Address` for the per-IP login limit, never `Host`) and adds a
secret `X-Origin-Verify` header the backend requires. A response headers policy
adds CSP, HSTS, X-Frame-Options, nosniff and Referrer-Policy to every response.
API Gateway's stage throttles at 50 rps, burst 100. Same-origin setup (no CORS
needed). DNS in Cloudflare, proxied, so the rate limiter reads the client from
`X-Forwarded-For` when the hop is in `TRUSTED_PROXY_IPS` (Cloudflare's ranges,
a GitHub environment variable). ACM validation records in Cloudflare.

**Database**: Neon Postgres (deployed). Connection via `DATABASE_URL` read from SSM
when `USE_SSM=true`. The app uses the pooled URL, bootstrap uses the direct URL.
Local dev uses SQLite or Postgres 17 via Docker Compose. Backups: Neon point-in-time
restore (6-hour window on the current plan), tested 2026-10-04.

**Secrets**: The JWT secret, database URLs, and origin-verify secret are stored in
SSM SecureStrings and read at startup with `USE_SSM=true` in Lambda, via boto3. OTEL tokens are passed from
GitHub secrets to the dev and prod Lambdas' environments (`TF_VAR_otel_headers_dev`
in `ci.yml`, `TF_VAR_otel_headers_prod` in `promote.yml`); they are not stored in SSM.

**CI/CD** (`.github/workflows/`):
- `ci.yml`: on PR, run unit tests, the dependency scan, integration tests,
  Playwright E2E against Docker Compose, and the gitleaks history scan; on push to main, run them,
  then (only if all of them pass) deploy to dev (build
  image, update and run the bootstrap Lambda (migrations), apply infra, build
  frontend, sync to S3, invalidate CloudFront, smoke-test `/api/health`).
- `promote.yml`: manual promotion of exact image tag from dev to prod (no rebuild).
- `observability-alert-handler.yml`: manual on-call diagnostic (started manually after a Grafana alert).

**Observability**: Grafana Cloud over OTLP/HTTP (dev and prod Lambdas). Traces and
metrics exported via OpenTelemetry SDK + FastAPI and SQLAlchemy instrumentation, plus
OTLP logs from `app.client_errors`, `app.db` and `app.security` (Loki). `SERVICE_VERSION` is set for both dev and
prod Lambdas from git tags.
Local dev: off by default; optional local Grafana/Tempo/Prometheus/Loki stack in `backend/observability/`.

**Versioning**: SemVer `SERVICE_VERSION` from git tags (latest release v1.0.0) via
`.github/scripts/service-version.sh`.

## Deployment and Release Gates

**Per-commit CI/CD (runs on every push to main):**
- Unit tests (frontend + backend) and the backend's Ruff lint and format check
  (frontend lint, format, and build are enforced locally, not in CI)
- Dependency scan (pip-audit and pnpm audit; HIGH and CRITICAL fail it)
- Backend integration tests against Postgres and Playwright E2E against Docker Compose
- Gitleaks scan of the full history (`secrets-scan` job)
- The deploy waits on all of the above
- Build and push backend image to dev ECR (timestamp-sha tag, e.g., 20260930-123456-abc123)
- Deploy to dev Lambda (runs migrations via the bootstrap Lambda first, then applies infra, rebuilds frontend, smoke-tests /api/health)

**Tagging a release (manual, semantic versioning):**
- From main at the commit you want to release: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
- Push the tag: `git push origin vX.Y.Z`
- Tags do not trigger CI. The tag takes effect on the next push to main, when `service-version.sh`
  extracts it and sets `SERVICE_VERSION` (reported in telemetry on dev Lambda). Prod gets
  the version of the promoted image's commit when `promote.yml` runs.
- If HEAD is exactly the tagged commit, dev reports `SERVICE_VERSION=X.Y.Z`; otherwise
  `SERVICE_VERSION=X.Y.Z+N.g<sha>`.

**Promoting to prod (manual, workflow_dispatch):**
- Copies the current backend image from dev ECR to prod ECR (no rebuild, exact bytes; skipped if prod already has the tag)
- Runs the prod migrations (bootstrap) before applying prod infra
- Rebuilds and deploys frontend from current main checkout
- Smoke-tests prod /api/health
- Requires typing "promote" to confirm, then approval through the GitHub `prod`
  environment (required reviewers plus a wait timer). Prod is live at
  https://hub.dnls.dev.

**Not yet wired:**
- bandit, trivy and the IaC scans still run by hand (`security-scanning` skill); CI runs
  the dependency scan and gitleaks
- Version sync: `pyproject.toml` and `package.json` are hardcoded (1.0.0, bumped by hand for v1.0.0); should sync with git tags
- Package registry publishing (PyPI, npm) is not set up
- Full backlog: `docs/tech-debt.md`

## Do Not

- Don't restructure or refactor working code unless asked.
- Don't add dependencies casually; only add what a task actually needs.
- Don't reproduce or edit files under `docs/` as if they were code; they're
  planning/reference material.
- Don't commit code; summarize instead.
- Don't deploy or modify real `.env` files (`.env.example` templates are fine; keep them current).
- Don't make decisions about architecture or data model changes; ask first.
