# AGENTS.md

Standing instructions for AI coding agents working in this repo.

## Project

Hub: a personal platform to capture, organize, and triage project ideas, from
small sparks to standalone builds. See `docs/specs.md` for the product spec
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
- `.github/workflows/`: CI/CD pipelines (ci, promote, reset-demo, observability
  alert handling).
- `docker-compose.yml` (repo root): local Postgres 17, bootstrap, and app for
  prod-parity testing.
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
SEED_DEMO_DATA=true uv run python -m app.db.init_local  # tables + demo data, once
uv run uvicorn app.main:app --reload # start the dev server (http://localhost:8000)
uv run pytest                        # run the test suite
```

- Storage: SQLAlchemy 2.0 (`app/db/`), database-agnostic. SQLite locally and in tests
  (default), Neon Postgres when deployed (via `DATABASE_URL`), Postgres 17 in
  Docker Compose for local prod-parity. No Alembic; tables come from `create_all`.
- Auth: argon2-cffi (password hashing) + PyJWT (HS256), OAuth2 password flow.
  Token-based so the same API serves the web app and future iOS apps.
- Multi-user with per-user data isolation.
- `app/core/config.py` is the single settings source, read from environment
  variables with dev-safe defaults. Its `require_safe_jwt_secret()` runs at
  startup and refuses to start, outside a local `ENVIRONMENT` or whenever
  `USE_SSM` is on, if the JWT secret is unset or still the built-in dev default.
- Database initialization: Importing the app does no database work. Tables are
  created by `init_local` locally (or with SEED_DEMO_DATA=true), `bootstrap_db.py`
  (separate Lambda, run on every deploy) when deployed, and `create_all` directly
  in tests. Docker Compose runs both init_local and bootstrap.

See `backend/README.md` for the full setup, config table, and details.

## Testing

Frontend: Vitest 5.0, React Testing Library 16, jsdom. `pnpm test`
(from inside `frontend/`) runs `vitest run`.

- Vitest runs with `test.globals` off (tests import from vitest explicitly);
  RTL auto-cleanup is wired by hand in `src/test-setup.ts`, which must stay.
- `base-ui`'s Dialog keeps its content mounted (hidden) while closed; scope
  queries to a landmark rather than the whole document to avoid matching hidden content.

Backend: pytest 9.1. `uv run pytest` (from inside `backend/`). Each test gets
its own in-memory SQLite database.

E2E: Playwright is done. 187 tests in `frontend/tests/` cover signup, login,
dashboard, projects, filters, sorts, edits, deletes, and API endpoints. Run
`pnpm exec playwright test` from `frontend/` with the backend and dev server running.

**All tests must pass before a task is considered done.** This includes:
- Frontend unit tests (`pnpm test` from `frontend/`)
- Backend unit tests (`uv run pytest` from `backend/`)
- Lint checks must be 0 errors / 0 warnings (`pnpm lint` from `frontend/`)
- TypeScript build must be clean (`pnpm build` from `frontend/`)
- Format must pass (`pnpm format:check` from `frontend/`)

Note: CI runs only tests on every push. Lint, format, and build checks are
enforced locally before committing; they do not run in the GitHub Actions
workflow on PRs.

## Working Conventions

- Keep changes small and scoped to what was asked.
- Run lint, typecheck, build, and both test suites, and confirm they're
  clean before considering a task done.
- Match the existing code style. ESLint + Prettier are configured in
  `frontend/`; lint must stay at 0 errors / 0 warnings.
- No em dashes in any prose you write here, in commit messages, in code
  comments, or in chat responses. Use a period, comma, or colon instead; or 
  rephrase.
- Frontend requires Node 22 (CI uses Node 22; no .nvmrc pins the version locally,
  so your Node version may differ). pnpm 12.3 is pinned in `package.json`.

## Agent Permissions and Security Boundaries

**Agents must follow these rules:**

- **Never commit code.** Make the changes you're asked to make, write a summary of what changed, provide a suggested commit message (use conventional commit format: `feat:`, `fix:`, `refactor:`, etc.; no capital first letter; use semicolons to separate clauses, not periods). The human reviews and commits.
- **Never deploy.** All deployment is manual or via CI/CD gates. Agents can verify that deployment would work, but cannot trigger it.
- **Never modify `.env` files or any secrets.** All environment configuration is off-limits. If a task needs an env variable, flag it and document what's needed.
- **Never make destructive changes to data.** Do not delete user data, reset the database, or modify production state without explicit approval.
- **Never restructure or refactor working code** unless explicitly asked. Stick to the task scope.
- **Never add dependencies casually.** Only add what a task actually requires. Justify each addition.
- **Never reproduce or edit files under `docs/`.** Those are planning and reference material, not code.

## Reusable Skills

Skills are discoverable workflows that agents load automatically. They live in `.claude/skills/<NAME>/SKILL.md` with frontmatter. When a task matches a skill, the agent loads and follows it without needing an explicit "use this file" instruction.

Current skills (under construction):

- **release**: Document and execute the release workflow: tag a version, push the tag and code to main, verify dev deployment, and document what was released. Based on the current workflow (tag only affects next dev deploy; no automated package registry publishing yet).
- **e2e-testing**: Run Playwright E2E tests, validate test fixtures, report results and edge cases. Planned for pre-release gates and feature validation (not yet wired to CI).
- **security-scanning**: Run static security checks (dependencies, secrets, code patterns). Planned for pre-release gates (not yet wired to CI).
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
creates schema and seeds demo account on every deploy.

**Frontend**: React SPA built with Vite, served from S3 with Origin Access Control,
behind CloudFront. CloudFront Function routes SPA paths; forwards `/api/*` to API
Gateway. Same-origin setup (no CORS needed). DNS and ACM in Cloudflare.

**Database**: Neon Postgres (deployed). Connection via `DATABASE_URL` read from SSM
when `USE_SSM=true`. The app uses the pooled URL, bootstrap uses the direct URL.
Local dev uses SQLite or Postgres 17 via Docker Compose.

**Secrets**: The JWT secret and database URLs are stored in SSM SecureStrings and
read at startup with `USE_SSM=true` in Lambda, via boto3. OTEL tokens are passed from
GitHub secrets (`TF_VAR_otel_headers_dev`) to the dev Lambda's environment; they are
not stored in SSM.

**CI/CD** (`.github/workflows/`):
- `ci.yml`: on PR, run tests; on push to main, run tests, deploy to dev (build
  image, apply infra, bootstrap, build frontend, sync to S3, invalidate CloudFront,
  smoke-test `/api/health`).
- `promote.yml`: manual promotion of exact image tag from dev to prod (no rebuild).
- `reset-demo.yml`: manual reset of demo account.
- `observability-alert-handler.yml`: manual on-call diagnostic (started manually after a Grafana alert).

**Observability**: Grafana Cloud over OTLP/HTTP (dev Lambda only). Traces and metrics
exported via OpenTelemetry SDK + FastAPI and SQLAlchemy instrumentation. Prod Lambda
deliberately leaves `OTEL_ENABLED` off and emits no telemetry. Local dev: off by
default; optional local Grafana/Tempo/Prometheus/Loki stack in `backend/observability/`.

**Versioning**: SemVer `SERVICE_VERSION` from git tags (v0.1.0, etc.) via
`.github/scripts/service-version.sh`.

## Deployment and Release Gates

**Per-commit CI/CD (runs on every push to main):**
- Unit tests (frontend + backend; lint, format, and build are enforced locally, not in CI)
- Build and push backend image to dev ECR (timestamp-sha tag, e.g., 20260930-123456-abc123)
- Deploy to dev Lambda (applies infra, bootstraps, rebuilds frontend, smoke-tests /api/health)

**Tagging a release (manual, semantic versioning):**
- From main at the commit you want to release: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
- Push the tag: `git push origin vX.Y.Z`
- Tags do not trigger CI. The tag takes effect on the next push to main, when `service-version.sh`
  extracts it and sets `SERVICE_VERSION` (reported in telemetry on dev Lambda).
- If HEAD is exactly the tagged commit, dev reports `SERVICE_VERSION=X.Y.Z`; otherwise
  `SERVICE_VERSION=X.Y.Z+N.g<sha>`.

**Promoting to prod (manual, workflow_dispatch):**
- Copies the current backend image from dev ECR to prod ECR (no rebuild, exact bytes)
- Rebuilds and deploys frontend from current main checkout
- Smoke-tests prod /api/health
- Requires typing "promote" to confirm, and reviewer approval (GitHub prod environment to be created)

**Tech debt (not yet wired):**
- E2E test automation on tagged releases (planned via `e2e-testing` skill)
- Security scanning on releases (planned via `security-scanning` skill)
- Version sync: `pyproject.toml` and `package.json` are hardcoded; should sync with git tags
- Package registry publishing (PyPI, npm) is not set up
- Prod emits no telemetry (SERVICE_VERSION is dev-only)

## Do Not

- Don't restructure or refactor working code unless asked.
- Don't add dependencies casually; only add what a task actually needs.
- Don't reproduce or edit files under `docs/` as if they were code; they're
  planning/reference material.
- Don't commit code; summarize instead.
- Don't deploy or modify `.env` files.
- Don't make decisions about architecture or data model changes; ask first.
