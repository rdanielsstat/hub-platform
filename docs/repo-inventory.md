# hub-platform repo inventory

> Point-in-time snapshot, not a live description. Figures below were checked against the repo, test runs, and OpenTofu state on the date shown; re-run the commands in each section before relying on them later.

Snapshot of `main` at `8ac75ae` (2026-10-04). Secret values are redacted throughout. Replaces the snapshot of `6bd192a` (2026-10-02), which predated Alembic, the integration tests, `ops/` and `security/`, the security headers, the length limits and usage caps, OTLP log export, and the dependency scan in CI.

## 1. Tree (depth 3, generated/vendor dirs excluded)

```
.                       root: AGENTS.md README.md product-spec.md LICENSE Makefile
                              openapi.yaml docker-compose.yml .gitignore .gitleaksignore
                              .prettierignore .pre-commit-config.yaml
.claude/                CLAUDE.md, launch.json, agents/qa-engineer.md,
                        skills/{design-review,e2e-testing,release,security-scanning}/SKILL.md
.github/                workflows/{ci,promote,observability-alert-handler}.yml
                        scripts/service-version.sh, scripts/pip_audit_gate.py
docs/                   7 files: agent-extension-pack design-notes permissions prompts
                        repo-inventory results tech-debt (.md)
ops/                    DEPLOYMENT HEALTH_CHECKS MONITORING TROUBLESHOOTING (.md)
security/               AGENT_SECURITY DATA_POLICY DEPENDENCIES GITLEAKS_CONFIG IAC_SCANS
                        OPERATIONAL_DIAGNOSIS PR_AUDIT RATE_LIMITING SECURITY_CHECKLIST (.md)
backend/                90 tracked files
  app/  main.py lambda_handler.py bootstrap_db.py
        auth/ core/ db/ models/ routers/
  alembic/        env.py, versions/0001..0003 (migrations); alembic.ini
  observability/  OTel setup (traces, metrics, logs), metrics registry, local stack
  oncall/         diagnose.py (on-call diagnostic agent)
  tests/          26 unit test files, integration/ (4 files, real Postgres)
  Dockerfile pyproject.toml uv.lock .python-version .env.example README.md
frontend/               93 tracked files
  src/  App.tsx main.tsx auth*.ts(x) store*.ts(x) use-*.ts test-setup.ts
        components/ lib/ pages/ services/
  public/ favicon.svg theme-init.js
  tests/  api.spec.ts app.spec.ts integration.spec.ts helpers.ts (Playwright)
  package.json pnpm-lock.yaml vite.config.ts playwright.config.ts tsconfig*.json
  eslint.config.js components.json .env.example README.md
infra/                  20 tracked files
  bootstrap/  GitHub OIDC trust, run once by hand
  hub/        apigateway backend bootstrap certs database dns ecr frontend lambda main
              outputs providers .tf, .terraform.lock.hcl, terraform.tfvars.example
  BOOTSTRAP.md PLACEMENT.md
custom-agent/           on-call-diagnostic/README.md
```

247 tracked files in total. Gitignored and present on disk: `backend/.env`, `frontend/.env`, `backend/hub.db`, `infra/hub/terraform.tfvars`.

## 2. Backend

- FastAPI 0.141.1 (Starlette 1.7.0) on Python 3.12. App object: `app` in `backend/app/main.py`.
- Local: `uv run uvicorn app.main:app --reload`, after `python -m app.db.init_local` (applies migrations, optionally seeds). Lambda: `app/lambda_handler.py` wraps the app in Mangum with `api_gateway_base_path` from `API_BASE_PATH` (`/api` when deployed).
- Import does no database work. At import `app.main` resolves the JWT secret and runs `require_safe_jwt_secret()` and `require_safe_seed_setting()`, and loads the origin-verify secret when `USE_SSM` is on (fatal if it can't).
- A database `OperationalError` becomes `503` with `Retry-After` (handler in `app/main.py`), inside the CORS layer.
- `/docs`, `/redoc`, `/openapi.json` only for a local run (not `is_deployed()`).

Modules:
- `core/config.py`: the single settings source; env and SSM resolution; secret guards; cookie, rate-limit, trusted-proxy and cap settings.
- `core/quotas.py`: account, project-per-user and note-per-project caps (403).
- `db/session.py`: lazy engine (`pool_pre_ping=True`), session factory. `db/migrations.py`: runs Alembic (`upgrade_to_head`), stamps pre-Alembic databases, transactional on SQLite and Postgres.
- `db/orm.py`: tables, with CHECK constraints for the length and count limits. `db/store.py`: all queries.
- `db/seed.py`, `db/init_local.py`: local demo data and setup.
- `auth/`: argon2 hashing and JWTs (`security.py`), current user from bearer or cookie (`dependencies.py`), cookies, per-IP rate limiting with trusted-proxy `X-Forwarded-For` handling (`rate_limit.py`), origin verification middleware (`origin_verify.py`).
- `models/`: Pydantic camelCase schemas, with every length and count limit (`project.py`, `note.py`, `user.py`).
- `routers/`: `health`, `auth`, `projects`, `notes`, `errors` (`POST /client-errors`).
- `bootstrap_db.py`: deploy-time migrations and demo seeding; local role/database creation.
- `observability/`: OpenTelemetry traces and metrics, plus OTLP log export of `app.client_errors`, `app.db` and `app.security`.
- `oncall/diagnose.py`: on-call diagnostic agent (OpenAI).

Config: `backend/.env.example` documents every setting, including `TRUSTED_PROXY_IPS`, `CLIENT_ERROR_RATE_LIMIT_PER_MINUTE`, `MAX_ACCOUNTS`, `MAX_PROJECTS_PER_USER` and `MAX_NOTES_PER_PROJECT`.

Dependencies (`backend/uv.lock`): alembic 1.20.0, argon2-cffi 25.1.0, boto3 1.43.98, email-validator, fastapi 0.141.1, mangum 0.22.0, opentelemetry-sdk 1.45.0 (plus the OTLP HTTP exporter and the FastAPI, SQLAlchemy and logging instrumentation), psycopg[binary] 3.3.6, pyjwt 2.15.1, python-dotenv, python-multipart 0.0.32, sqlalchemy 2.0.54, uvicorn[standard] 0.53.0. Transitive: pydantic 2.13.5, starlette 1.7.0. Dev: httpx2 2.13.1, pytest 9.1.1, pyyaml.

## 3. Database layer

- Engine: lazy, cached, `pool_pre_ping=True` (Neon closes idle connections). Sync SQLAlchemy 2.0; each `Store` write commits itself.
- Migrations: Alembic, `backend/alembic/versions/`: `0001` baseline (the old `create_all()` schema), `0002` CHECK constraints for text lengths, `0003` display-name length and tag/link counts. Applied by `init_local` locally and by the bootstrap Lambda on every deploy, before the API code switches. Pre-Alembic databases are stamped at `0001`. `tests/test_migrations.py` fails if `orm.py` and the migrations drift.
- Schema: `String(36)` UUID ids; `tags` and `links` as JSON; `status` as an enum (native on Postgres); `DateTime(timezone=True)`; FKs with `ON DELETE CASCADE`; unique index on `users.email`.
- Hosting: Neon Postgres 17 for dev and prod (projects `hub-dev`, `hub-prod`, us-east-1), public internet with TLS. The app uses the pooled URL, the bootstrap the direct URL. Point-in-time restore window: 6 hours (free plan); restore tested 2026-10-04.

## 4. API contract

- `openapi.yaml` (OpenAPI 3.1.0, 807 lines). `backend/tests/test_openapi_contract.py` fails if the spec's and app's path+method sets differ; `tests/test_observability.py` keeps the metrics registry in step with it.
- Public: `GET /health`, `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `POST /client-errors`. Authenticated: `GET /auth/me`, `GET|POST /projects`, `GET|PATCH|DELETE /projects/{project_id}`, `GET|POST /projects/{project_id}/notes`, `DELETE /notes/{note_id}`.
- Documented limits: `maxLength` and `maxItems` on every input field; 403 for caps, 429 for rate limits, 503 for database outages.

## 5. Frontend

- React 19.2, Vite 6.4, TypeScript 5.7.3, Tailwind 4.3, shadcn/ui, `@base-ui/react` 1.5, react-router-dom 7.18. pnpm 12.3.4. CI uses Node 22.
- Centralized client: `src/services/api/`. Components never call `fetch`.
- Auth: the `hub_token` httpOnly cookie; on load `GET /auth/me`. Only a 401 means signed out; other failures retry once after 500 ms, then show "Can't reach the server" (`src/auth.tsx`).
- Error reporting: `src/lib/error-reporting.ts` (installed in `main.tsx`) and the error boundary report to `POST /client-errors` through `services/api/client-errors.ts`.
- `public/theme-init.js` sets the theme before first paint (no inline scripts, for the CSP).

## 6. Tests

| Suite | Runner | Count | Command |
|---|---|---|---|
| Backend unit | pytest 9.1.1 | 432 tests, 26 files | `cd backend && uv run pytest` |
| Backend integration | pytest, real Postgres 17 | 38 tests, 4 files | `make test-integration` |
| Frontend unit | Vitest 5.0.1 + RTL 16 + jsdom | 197 tests, 22 files | `cd frontend && pnpm test` |
| E2E | Playwright 1.63.0 (Chromium) | 201 tests: `api.spec.ts` 104, `app.spec.ts` 89, `integration.spec.ts` 8 | `make test-e2e`, `make test-e2e-docker` |

- CI (`ci.yml`) runs all four suites, plus the dependency scan and gitleaks, on every PR and push; all gate the dev deploy. Lint, format and build run locally (`make check`).
- The backend unit run is warning-free (Mangum's one known warning is filtered, with the reason, in `pyproject.toml`).

## 7. Containers

- `backend/Dockerfile`: `deps` (uv export of the lock); `prod` (`public.ecr.aws/lambda/python:3.12`, OS security updates applied at build, pip removed after installing, CMD `app.lambda_handler.handler`); `dev` (`python:3.12-slim`, uvicorn). The bootstrap Lambda reuses the prod image.
- `docker-compose.yml`: `postgres`, `bootstrap`, `init_local`, `app`. `backend/observability/docker-compose.yml`: optional local collector, Tempo, Prometheus, Loki, Grafana.
- trivy on the patched prod image (2026-10-03): no CRITICAL, HIGH, MEDIUM or LOW findings.

## 8. Infrastructure and CI/CD

- OpenTofu 1.12.6, us-east-1, state in S3. `infra/bootstrap` (OIDC trust, by hand); `infra/hub` (41 resource blocks; 39 managed resources in each of the `dev` and `prod` workspaces on 2026-10-04).
- Per environment: API and bootstrap Lambdas (container image), ECR (immutable tags, scan on push, lifecycle policy), API Gateway HTTP API (50 rps, burst 100), S3 with OAC and explicit SSE-S3, CloudFront (SPA router function, `/api/*` origin request policy, response headers policy with CSP and HSTS, `X-Origin-Verify` custom header), ACM, Cloudflare DNS (proxied), SSM SecureStrings.
- Environments: dev `https://hub-dev.dnls.dev`, prod `https://hub.dnls.dev`, both live.
- Workflows (every action pinned to a commit SHA):
  - `ci.yml`: `test`, `dependency-scan` (after `test`), `secrets-scan`, `integration`, `e2e`; on push to main, `deploy-dev` after all five (bootstrap function updated and run before the full apply).
  - `promote.yml`: manual, typed confirmation plus reviewer approval; copies the dev image (skipped if prod has the tag), migrates, applies prod, deploys the frontend, smoke-tests.
  - `observability-alert-handler.yml`: manual on-call diagnostic, reviewer approval.
- Repository: public; ruleset `protect-main` blocks force-pushes and deletion of `main`.
- Observability: dev and prod export traces, metrics and logs to Grafana Cloud.

## 9. Docs and project meta

- Root `README.md`, `product-spec.md` (product and data model, the source of truth), `AGENTS.md` (agent instructions), `openapi.yaml`, `Makefile`, `LICENSE`.
- `ops/`: deployment (including backup testing), health checks, monitoring, troubleshooting. `security/`: checklist, rate limiting, IaC and image scans, dependencies, data policy, gitleaks, agent security, PR audit, operational diagnosis.
- `docs/`: tech-debt, design-notes, agent-extension-pack, permissions, this file; `prompts.md` and `results.md` are historical session logs.

## 10. Git state

- Branch `main`, HEAD `8ac75ae`, remote `origin` (GitHub `rdanielsstat/hub-platform`, public). Other branches, local and on origin: `chore/update-github-actions-node24` (merged as PR #5), `observability-oncall-agent`, `otel-enabled-dev-lambda`, `semver-service-version`, `service-version-dev-lambda`.

## Risks

- `infra/hub/tfplan*` files committed in `8ebc8ae` (removed in `1f59439`) remain in public history with sensitive values; treat those credentials as exposed until rotated (the JWT secret was rotated in `ad2c8d9`).
- The per-IP rate limits are per Lambda container, not shared (bounded and documented in `security/RATE_LIMITING.md`).
- `docker-compose.yml` commits local-only Postgres credentials.
- Remaining backlog: `docs/tech-debt.md`.
