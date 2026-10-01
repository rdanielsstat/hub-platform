# hub-platform repo inventory

> Historical snapshot, not a description of the current repo. Paths and details reflect `main` at the commit below (for example, `_docs/` was later renamed `docs/`).

Snapshot of `main` at `d514520` (2026-09-29). Secret values are redacted throughout.

## 1. Tree (depth 3, generated/vendor dirs excluded)

```
.                       root files: 5 (.gitignore, AGENTS.md, docker-compose.yml, openapi.yaml, .DS_Store)
_docs/                  5 files: design-notes.md prompts.md results.md specs.md tech-debt.md
backend/                39 files
  app/  __init__ main.py lambda_handler.py bootstrap_db.py
        auth/ core/ db/ models/ routers/
  tests/ conftest.py test_auth.py test_bootstrap_db.py test_config.py test_notes.py test_projects.py
  Dockerfile pyproject.toml uv.lock .python-version .env.example .dockerignore README.md
frontend/               84 files
  src/  App.tsx main.tsx auth*.ts(x) store*.ts(x) use-*.ts test-setup.ts
        components/ lib/ pages/ services/
  public/ package.json pnpm-lock.yaml vite.config.ts tsconfig.json eslint.config.js components.json .env.example
infra/                  28 files (on disk; 20 tracked)
  hub/     apigateway backend bootstrap certs database dns ecr frontend lambda main outputs providers shared .tf, terraform.tfvars(.example)
  shared/  aurora backend outputs providers variables vpc .tf, .terraform.lock.hcl (untracked)
  BOOTSTRAP.md PLACEMENT.md .env (gitignored)
```

No root README. No `.github/`.

## 2. Backend

- FastAPI 0.141.1 on Python 3.12 (`.python-version`; `requires-python >=3.12`). App object: `app` in `backend/app/main.py`.
- Local: `uv run uvicorn app.main:app --reload`, or Compose `dev` image running the same. Lambda: `app/lambda_handler.py` does `handler = Mangum(app)` (default options); prod image CMD is `app.lambda_handler.handler`. Both paths import `app.main`, which at import time fetches the JWT secret, then calls `create_tables()` and seeds if empty, each wrapped in try/except that logs and continues.
- CORS origins are hardcoded to `http://localhost:5173` and `http://127.0.0.1:5173`. `/docs`, `/redoc`, `/openapi.json` served only when `ENVIRONMENT` is local/development/dev.

Modules:
- `core/config.py`: settings; env + SSM resolution, JWT secret guard.
- `db/session.py`: lazy engine, session factory, `create_tables()`, `get_db_session` dependency.
- `db/orm.py`: SQLAlchemy declarative tables.
- `db/store.py`: `Store` class (all queries), record dataclasses, `get_store` dependency.
- `db/seed.py`: seeds one demo user, 10 projects, notes.
- `auth/security.py`: argon2 hashing (passlib), JWT encode/decode (PyJWT, HS256).
- `auth/dependencies.py`: `OAuth2PasswordBearer`, `get_current_user`.
- `models/base.py|project.py|note.py|user.py`: Pydantic camelCase schemas.
- `routers/health.py|auth.py|projects.py|notes.py`: endpoints.
- `bootstrap_db.py`: Postgres role/database bootstrap (section 3).
- `lambda_handler.py`: Mangum wrapper.

Config (`app/core/config.py`): `USE_SSM` truthy on `1/true/yes`. Off: `DATABASE_URL` (default `sqlite:///./hub.db`) and `HUB_JWT_SECRET` (dev default) from env. On: fetches SSM SecureString named by `DB_PARAM_NAME` (JSON with `username,password,host,port,dbname`) and `JWT_PARAM_NAME`, cached per process. Other env vars: `ENVIRONMENT` (default `local`), `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60). `bootstrap_db.py` also reads `MASTER_DB_PARAM_NAME`, `MASTER_DB_HOST`, `MASTER_DB_PORT`, `MASTER_DB_USER`, `MASTER_DB_PASSWORD`. SSM parameter names are not hardcoded in Python; Terraform supplies them (`aws_ssm_parameter.app_db`, `.jwt`, `local.aurora_master_param_name`). `backend/.env.example` keys: all twelve names above.

Dependencies (source of truth `backend/uv.lock`; `pyproject.toml` has `>=` floors equal to the lock): argon2-cffi 25.1.0, boto3 1.43.98, email-validator 2.3.0, fastapi 0.141.1, mangum 0.22.0, passlib 1.7.4, psycopg[binary] 3.3.6, pyjwt 2.14.0, python-multipart 0.0.32, sqlalchemy 2.0.54, uvicorn[standard] 0.53.0. Transitive: pydantic 2.13.5, starlette 1.6.0. Dev: httpx 0.28.1, pytest 9.1.1.

## 3. Database layer

- Engine: `backend/app/db/session.py:50-62` (`_get_engine`, `create_engine` at line 59), built lazily and cached in module global `_engine`. `connect_args={"check_same_thread": False}` only for SQLite. No pool options set: default `QueuePool` for Postgres. SQLite FK pragma listener at lines 19-37.
- Session: `sessionmaker(autoflush=False, expire_on_commit=False)` at `session.py:65-71`; `SessionLocal()` at 74-78; `get_db_session()` generator dependency at 89-94 (yield, close in finally). `get_store` (`store.py:290`) wraps it. No middleware.
- URL switch: `config.get_database_url()` (`config.py:85-95`). SQLite from env default; Postgres either via `DATABASE_URL` env or built from SSM JSON as `postgresql+psycopg://user:pass@host:port/dbname` (`config.py:74-82`, `quote_plus` on user/password).
- Sync SQLAlchemy 2.0.54 (2.0-style `select`, `Mapped`). All routes are sync `def`.
- Transactions: each `Store` write method calls `commit()` itself. `create_user` uses `flush()` then commit, rollback on `IntegrityError`. Note add/delete then calls `update_project` in a separate commit (two transactions per request).
- Migrations: none. No Alembic. `create_tables()` = `Base.metadata.create_all` at startup (`session.py:81-86`).
- Beyond plain columns: IDs are `String(36)` with Python-side `uuid4` (no DB UUID type); `tags` and `links` are generic `sqlalchemy.JSON` (JSON on Postgres, not JSONB); `status` is `SAEnum` (native enum type on Postgres); `DateTime(timezone=True)`; FKs with `ondelete="CASCADE"`; unique index on `users.email`. No server-side defaults, no `RETURNING`, no raw SQL in app code except the SQLite `PRAGMA foreign_keys=ON`. Email lookup uses `func.lower`.
- `bootstrap_db.py`: CLI `python -m app.bootstrap_db` (`main()`, exits 1 on error); Lambda `app.bootstrap_db.lambda_handler` (no exception catching). Credentials: master from SSM `MASTER_DB_PARAM_NAME` JSON when `USE_SSM`, else `MASTER_DB_*` env; app role/password/db parsed from `config.get_database_url()`. Connects with psycopg (autocommit) to `postgres` DB and runs: `SELECT 1 FROM pg_roles WHERE rolname = %s`; `CREATE ROLE "<role>" WITH LOGIN PASSWORD '<literal>' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION`; `SELECT 1 FROM pg_database WHERE datname = %s`; `CREATE DATABASE "<db>"`. Then connects to the target DB: `GRANT CONNECT ON DATABASE "<db>" TO "<role>"`; `GRANT USAGE, CREATE ON SCHEMA public TO "<role>"`. Identifiers validated by regex; password literal escaped by quote doubling.
- Persistence assumptions: module-global engine/pool and cached URL/secret reused across warm Lambda invocations; import-time `create_tables()` + seed on every cold start; no per-request transaction spanning requests found.
- Infra: Aurora PostgreSQL 16.8, provisioned mode with Serverless v2 (min 0, max 2 ACU), `enable_http_endpoint = true` (Data API). No RDS Proxy found. Lambda runs in VPC.

## 4. API contract

- `openapi.yaml` (OpenAPI 3.1.0, 694 lines) is hand-written; its description says it was derived from the frontend client and specs, and "the backend implements this contract." The YAML is the stated authority.
- No automated check that spec and code agree was found.
- Endpoints (spec): `POST /auth/register` (no auth), `POST /auth/login` (no auth), `GET /auth/me`, `GET|POST /projects`, `GET|PATCH|DELETE /projects/{projectId}`, `GET|POST /projects/{projectId}/notes`, `DELETE /notes/{noteId}` (all auth). Spec-only, not implemented: `GET|POST /projects/{projectId}/attachments`, `DELETE /attachments/{attachmentId}`. Code-only: `GET /health` (no auth).

## 5. Frontend

- React 19, Vite 6, TypeScript 5.7.3, Tailwind v4, shadcn/ui, `@base-ui/react`, react-router-dom 7. pnpm 12.3.4 (`packageManager`). Node version not pinned (no `.nvmrc`/`engines`); local is v26.8.1.
- Centralized client: `frontend/src/services/api/` (`index.ts` exports `api`/`authApi`; HTTP in `http.ts`; endpoints in `real.ts`, `auth.ts`).
- Base URL: `VITE_API_BASE_URL` in `src/lib/config.ts`, fallback `http://localhost:8000`. `.env.example` sets the same. No per-environment files beyond that.
- Auth: bearer token in `localStorage` key `hub.token` (`token.ts`). No refresh token; a 401 on an authenticated request triggers a logout handler.
- Tests: Vitest 5 + RTL + jsdom, setup `src/test-setup.ts`, co-located `*.test.ts(x)`. 20 files, 157 tests: pages, components, store, auth, http/token client.

## 6. Tests

- Backend: pytest, config in `pyproject.toml` (`testpaths = ["tests"]`). Frontend: Vitest via `vite.config.ts`.
- No unit/integration/e2e separation: no markers, no subdirectories. Backend API tests are effectively integration tests through `TestClient`. No e2e suite.
- Backend 73: test_auth 12, test_bootstrap_db 22, test_config 20, test_notes 10, test_projects 9. Frontend 157.
- Real DB: backend uses in-memory SQLite (`conftest.py` forces `DATABASE_URL=sqlite:///:memory:`, per-test `StaticPool` engine). `test_bootstrap_db.py` uses a fake psycopg connection. Nothing touches Postgres.
- Commands: `cd backend && uv run pytest`; `cd frontend && pnpm test`.

Last 15 lines of backend run:
```
.venv/lib/python3.12/site-packages/starlette/testclient.py:53
  .../starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

.venv/lib/python3.12/site-packages/passlib/utils/__init__.py:854
  .../passlib/utils/__init__.py:854: DeprecationWarning: 'crypt' is deprecated and slated for removal in Python 3.13
    from crypt import crypt as _crypt

.venv/lib/python3.12/site-packages/passlib/handlers/argon2.py:716
  .../passlib/handlers/argon2.py:716: DeprecationWarning: Accessing argon2.__version__ is deprecated ...
    _argon2_cffi.__version__, max_version)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 73 passed, 4 warnings in 3.23s ========================
```
Frontend: `Test Files 20 passed (20)`, `Tests 157 passed (157)`, 3.86s.

## 7. Containers

- `backend/Dockerfile`: `deps` (`ghcr.io/astral-sh/uv:0.9-alpine`, `uv export --frozen --no-dev` to requirements.txt); `prod` (`public.ecr.aws/lambda/python:3.12`, CMD `app.lambda_handler.handler`); `dev` (`python:3.12-slim`, CMD `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`, EXPOSE 8000). Bootstrap Lambda reuses the prod image with command override `app.bootstrap_db.lambda_handler`.
- `docker-compose.yml`: `postgres` (postgres:16-alpine, 5432:5432, volume `postgres_data`, healthcheck); `bootstrap` (dev target, runs `python -m app.bootstrap_db`, env `ENVIRONMENT`, `DATABASE_URL`, `MASTER_DB_*`); `app` (dev target, 8000:8000, bind mount `./backend/app:/app/app`, env `ENVIRONMENT`, `DATABASE_URL`). Credentials are local dev defaults inline (redacted here).
- Image size: unclear.

## 8. CI/CD

- No `.github/workflows`. Nothing deploys automatically. Deployment is manual OpenTofu (`infra/shared`, `infra/hub`, S3 state per `BOOTSTRAP.md`). AWS auth for that is unclear (ambient CLI credentials implied); `infra/.env` holds a Cloudflare API token export.
- Tagging: ECR repo `MUTABLE`, Lambda `image_uri` uses `var.lambda_image_tag` default `latest` ("set by CI"; no CI exists). Untagged images expire after 7 days.

## 9. Docs and project meta

- No root README. `backend/README.md` sections: Setup, Run the dev server, Config (JWT secret guard, AWS SSM), Database, Postgres and the database bootstrap, Seeded demo account, Run the tests, Auth.
- `AGENTS.md` exists (agent instructions). No `CLAUDE.md`, no `product-spec.md` (spec is `_docs/specs.md`: architecture, data model, screens, auth, testing). No `docs/` (before this file), `security/`, `ops/`, `agent-capabilities/`, or `mcp-server/`.
- `_docs/design-notes.md` is the closest to decision records (storage, auth, api seam, write convention, testing). `_docs/tech-debt.md` covers security, migrations, deferred features. No formal ADRs.

## 10. Git state

- Branch `main`, HEAD `d514520791c3fbb024e72d89dd24bfe57efcfe29`, remote `origin` (GitHub `rdanielsstat/hub-platform`), tracking `origin/main`. No stashes, no other local branches.
- Uncommitted: modified `infra/shared/aurora.tf`, `outputs.tf`, `vpc.tf` (+94/-103); untracked `infra/shared/.terraform.lock.hcl`.
- Recent: d514520 Postgres bootstrap + AWS infra; b0e0033 Lambda + SSM; 8876b16 security hardening; 59d4f9a tech-debt trim.

## Risks

- No committed real secrets found. `infra/.env` (Cloudflare token) and `infra/hub/terraform.tfvars` exist on disk but are gitignored.
- A demo account with a hardcoded password (`app/db/seed.py`) is seeded into any empty database, including a deployed one.
- `docker-compose.yml` commits local-only Postgres credentials.
