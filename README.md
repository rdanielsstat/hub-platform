# Hub-Platform

A personal idea management system for capturing, triaging, and tracking ideas from spark to graduation. Built with AI assistance, containerized infrastructure, and production-grade observability.

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/downloads/)
[![FastAPI 0.141](https://img.shields.io/badge/FastAPI-0.141-009688.svg)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev)
[![TypeScript 5.7](https://img.shields.io/badge/TypeScript-5.7-3178c6.svg)](https://www.typescriptlang.org/)
[![Postgres 17](https://img.shields.io/badge/Postgres-17-336791.svg)](https://www.postgresql.org/)
[![Neon](https://img.shields.io/badge/Neon-Postgres-00e599.svg)](https://neon.tech/)
[![AWS Lambda](https://img.shields.io/badge/AWS-Lambda-FF9900.svg)](https://aws.amazon.com/lambda/)
[![Grafana](https://img.shields.io/badge/Grafana-Observability-F2CC0C.svg)](https://grafana.com/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ed.svg)](https://www.docker.com/)

**Live environments:**
- Development: https://hub-dev.dnls.dev
- Production: https://hub.dnls.dev

**Documentation:**
- [AGENTS.md](AGENTS.md) - Project instructions for AI agents and developers
- [docs/agent-extension-pack.md](docs/agent-extension-pack.md) - AI skills and subagent workflows
- [docs/permissions.md](docs/permissions.md) - Agent security boundaries and permissions
- [openapi.yaml](openapi.yaml) - API contract (hand-written; a backend test checks the app matches it)

## Demo Account

Reviewers can explore the live app without signing up:

1. Open https://hub.dnls.dev
2. Log in with:
   - Email: `demo@hub.dev`
   - Password: `demo-hub-2026`

The account comes with seeded sample ideas and notes to explore. It is read/write and shared by all reviewers, so its data may change during the review, and it may be reset to the original sample data at any time. It is temporary and valid through the end of the review period. Login is limited to 5 attempts per minute per IP; if you see "Too many login attempts", wait a minute and try again. To keep your own data private, sign up with any email instead.

---

## What is Hub-Platform?

Hub-Platform is a personal hub for capturing ideas, scoring them, and tracking them through a lifecycle. Sign up, quickly capture an idea with a one-line pitch, brain-dump description, and scoring (excitement, potential, effort). Track ideas through statuses (inbox, exploring, active, parked, graduated, killed), add notes, set target dates, and filter your dashboard by status, tag, or search text, sorted by score, date, or name.

### Key features

- **Quick capture**: One-screen form to capture an idea with minimal friction
- **Lifecycle tracking**: Move ideas from inbox through exploring, active, parked, graduated, or killed
- **Scoring system**: Rate excitement, potential, and effort; opportunity score calculated automatically
- **Dashboard filtering**: Filter by status or tag, search by text, and sort by recently updated, scores, target date, or name
- **Notes and links**: Add notes to ideas and link to external resources
- **Personal workspace**: Individual signup and login; your ideas, your rules
- **Deployed**: Runs on AWS, with separate dev and prod environments, both live, OpenTelemetry tracing and metrics in dev and prod, and a manual AI-assisted alert diagnostic
- **AI-native development**: Built with Claude Code using spec-driven development, AI skills, and specialized subagents

### Typical workflow

1. Sign up with email and password
2. Land on dashboard showing all your ideas with tiles displaying name, pitch, scores, and status
3. Click "quick capture" to add a new idea
4. Enter project name, one-line pitch, brain-dump description, status, and scores (excitement, potential, effort)
5. See the new idea tile on your dashboard immediately
6. Click a tile to open the full project page
7. Add notes, links, update target date, refine scores
8. Filter the dashboard by status or tag, search it, or sort by recently updated, scores, target date, or name

---

## Quick Start

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs and manages Python 3.12 for the backend)
- Node.js 22 (install with a version manager such as nvm or fnm)
- pnpm 12.3 (the version is pinned in `frontend/package.json`)
- Git
- Docker, only for the optional Postgres and observability stacks

### Run locally

Locally the backend uses a SQLite file (`backend/hub.db`), so no database server is needed.

**Terminal 1: backend**

```bash
git clone https://github.com/rdanielsstat/hub-platform.git
cd hub-platform/backend

# Install dependencies
uv sync

# Create the tables and the demo account (once)
SEED_DEMO_DATA=true uv run python -m app.db.init_local

# Start the API on http://localhost:8000
uv run uvicorn app.main:app --reload
```

**Terminal 2: frontend** (from the `hub-platform` folder)

```bash
cd frontend

# Point the frontend at the local backend (once)
cp .env.example .env

pnpm install
pnpm dev
```

Visit `http://localhost:5173` and log in as `demo@hub.dev` / `demo1234`, or sign up. Interactive API docs are at `http://localhost:8000/docs`.

### Run with Docker Compose (Postgres)

To run the backend against Postgres 17 instead of SQLite, from the repo root:

```bash
docker compose up --build
```

This starts:
- Postgres 17
- `bootstrap`: creates the database and a least-privilege login role
- `init_local`: creates the tables and seeds the demo account
- `app`: the FastAPI backend on `http://localhost:8000`

It doesn't include the frontend (run `pnpm dev` as above) or the observability stack, which is a separate compose file (see [Observability](#observability)).

---

## Architecture

### System design

[**ARCHITECTURE DIAGRAM PLACEHOLDER**]

Visual description: A user opens Hub-Platform in a web browser at CloudFront (HTTPS). CloudFront serves the built React app from a private S3 bucket and forwards `/api/*` requests to an API Gateway HTTP API, so the frontend and API share one origin. API Gateway invokes the backend Lambda, a container image from ECR running FastAPI through Mangum, which strips the `/api` prefix. The Lambda stores data in Neon Postgres. A separate bootstrap Lambda creates the schema and seeds the demo account on every deploy. In both dev and prod, OpenTelemetry sends traces and metrics from the backend to Grafana Cloud.

Locally, the frontend runs on the Vite dev server (`http://localhost:5173`) and calls the backend directly on `http://localhost:8000`, which uses SQLite.

### Component overview

**Frontend (React 19)**
- TypeScript 5.7 with strict mode
- Vite 6.4 for bundling
- Tailwind CSS 4.3 + shadcn/ui (base-nova neutral)
- Component library: @base-ui/react 1.5 (headless), lucide-react for icons
- State management: React Context (no external library)
- Testing: Vitest 5.0 + React Testing Library 16
- Dashboard with filtering and sorting
- Quick capture form and detailed project view

**Backend (FastAPI)**
- Python 3.12 with Pydantic 2.13 for validation
- SQLAlchemy 2.0 ORM (database-agnostic)
- OpenTelemetry instrumentation
- Authentication: JWT + argon2 password hashing; the web app's session is an httpOnly, SameSite=Strict cookie, and the API also accepts bearer tokens
- Testing: pytest 9.1
- RESTful API for CRUD operations on ideas and notes

**Database**
- SQLite for local development and testing
- Postgres 17 for production (via Neon)
- SQLAlchemy 2.0, no migrations: tables are created by `init_local` locally and by the bootstrap Lambda on each deploy. The app itself does no database work at startup.
- Schema: users, auth_identities (auth), projects (ideas), notes

**Infrastructure**
- AWS Lambda (compute)
- API Gateway HTTP API (routes `/api/*` to Lambda)
- AWS ECR (container registry)
- Neon Postgres (managed database)
- CloudFront (CDN + HTTPS)
- S3 (frontend static assets)
- OpenTofu 1.12.6 (IaC)
- GitHub Actions (CI/CD)

**Security controls (deployed)**
- Session cookie `hub_token`: HttpOnly, SameSite=Strict, Secure
- Login rate limit: 5 attempts per minute per client IP (429 over it); API Gateway throttles at 50 rps, burst 100
- CloudFront forwards the viewer's IP (`CloudFront-Viewer-Address`) through a custom origin request policy, so the login limit is per user, not per CloudFront edge
- Origin verification: CloudFront adds a per-environment secret `X-Origin-Verify` header; the API answers 403 without it, so the public `execute-api` URL can't bypass CloudFront
- Dev and prod both count as deployed (`USE_SSM` on), so both get these controls and hide the API docs
- Gitleaks pre-commit hook; GitHub secret scanning with push protection
- Details: `backend/README.md` ("Auth", "Rate limits", "Origin verification")

**Observability**
- OpenTelemetry SDK (Python): traces and metrics, with FastAPI and SQLAlchemy instrumentation
- Grafana Cloud (dev and prod environments)
- Optional local stack: OTel Collector, Prometheus, Tempo, Loki, Grafana

---

## Technology Stack

### Frontend Stack

```
React 19.2                      Component framework
TypeScript 5.7                  Type safety
Vite 6.4                        Bundler and dev server
Tailwind CSS 4.3                Utility-first styling
shadcn/ui (base-nova)           Component library
@base-ui/react 1.5              Headless components
lucide-react                    Icon library
react-router-dom 7.18           Client-side routing
pnpm 12.3                       Package manager
Vitest 5.0                      Unit test runner
@testing-library/react 16       Component testing
Prettier 3                      Code formatter
ESLint 10                       Linter
```

### Backend Stack

```
FastAPI 0.141                   Web framework
Uvicorn 0.53                    ASGI server
Pydantic 2.13                   Data validation
SQLAlchemy 2.0                  ORM
psycopg 3.3.6                   Postgres driver
argon2-cffi 25.1                Password hashing
PyJWT 2.14                      JWT tokens
python-multipart                Form parsing
Mangum 0.22                     ASGI to Lambda adapter
boto3                           AWS SDK
OTel Python SDK                 Observability
pytest 9.1                      Testing
```

### Infrastructure Stack

```
AWS Lambda                      Compute
AWS API Gateway (HTTP API)      Routes /api/* to Lambda
AWS ECR                         Container registry
AWS CloudFront                  CDN / HTTPS
AWS S3                          Static asset storage
Neon Postgres                   Managed database
OpenTofu 1.12.6                 Infrastructure as code
GitHub Actions                  CI/CD
Docker                          Containerization
```

---

## Local Development

### Installation

**Using `uv` for Python** (from `backend/`):

```bash
cd backend

# Install dependencies (creates virtual environment)
uv sync

# Add a package
uv add package-name

# Run a Python file
uv run python script.py

# Run pytest
uv run pytest
```

**Using `pnpm` for Node** (from the repo root):

```bash
cd frontend

# Install dependencies
pnpm install

# Add a package
pnpm add package-name

# Run dev server
pnpm dev

# Run tests
pnpm test

# Build for production
pnpm build
```

### Development Server

**Backend** (from `backend/`):

```bash
uv run uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/redoc` for interactive API documentation.

**Frontend** (from `frontend/`, with `.env` copied from `.env.example`):

```bash
pnpm dev
```

Visit `http://localhost:5173`.

### Running Tests Locally

```bash
# Backend tests (from backend/)
uv run pytest

# Frontend tests, lint, typecheck and format (from frontend/)
pnpm test
pnpm lint
pnpm build
pnpm format:check
```

### Database Management

**Create tables and seed demo data** (from `backend/`):

```bash
SEED_DEMO_DATA=true uv run python -m app.db.init_local
```

This creates the tables in the local SQLite file `backend/hub.db`, and, if the database has no users yet, one demo account (`demo@hub.dev` / `demo1234`) with ten sample projects and their notes. It's safe to run again: an existing database is never re-seeded.

**Reset the database:**

```bash
# SQLite (from backend/), then run init_local again
rm hub.db

# Docker Compose Postgres (from the repo root): deletes the data volume
docker compose down -v
```

### Local Docker Compose (Production Parity)

To run the backend against Postgres, as it does when deployed (from the repo root):

```bash
docker compose up --build
```

This starts Postgres 17 (with a persistent volume), creates the database, role, tables and demo account, then serves the API on `http://localhost:8000`. The frontend isn't part of it: start it with `pnpm dev` from `frontend/` and open `http://localhost:5173`. Stop the API from Terminal 1 first if it's running, since both use port 8000.

**Test the workflow:**
1. Sign up with an email and password
2. Create a new project using quick capture
3. Fill in name, pitch, description, and scores
4. View the dashboard with your new project tile
5. Click the tile to open the project page
6. Add notes and links
7. Update scores or change status
8. Return to dashboard and filter by status or tag

---

## Deployment Architecture

### CI/CD Pipeline

[**CI/CD DIAGRAM PLACEHOLDER**]

Visual description: A developer pushes code to main. GitHub Actions runs the backend tests, then the frontend tests, in a single job (pull requests run only this step). If they pass, CI builds a Docker image, tags it with a timestamp and short SHA (e.g., 20261001-163457-83242da), and pushes it to the dev ECR repository. It then applies the dev infrastructure with OpenTofu, runs the bootstrap Lambda, builds the frontend and uploads it to S3, and smoke-tests `/api/health`. After testing in dev, a release owner manually runs the promote workflow, which copies the same image from dev ECR to prod ECR (no rebuild), deploys it to the production Lambda, and builds and uploads the frontend.

### Environments

**Development**
- Automatic deployment on every push to main
- Latest code always running
- Internal testing and validation

**Production**
- Manual promotion from development
- Tested release selected by release owner
- Live at https://hub.dnls.dev

### Release Process

**Creating a release:**

```bash
# On main branch, verify clean state
git status

# Determine next version (using git describe)
git describe --tags --long --match 'v[0-9]*.[0-9]*.[0-9]*'

# Tag the release
git tag -a v0.2.0 -m "Release v0.2.0"

# Push tag and code to main
git push origin v0.2.0
git push origin main
```

After pushing:
1. CI builds and deploys to dev (tag doesn't trigger CI; next push to main does)
2. SERVICE_VERSION updates to the semantic version on dev Lambda
3. Verify the release at https://hub-dev.dnls.dev
4. Manually promote to production via GitHub Actions workflow

For detailed release workflow, see `.claude/skills/release/SKILL.md`.

### Scaling and Infrastructure

The current setup deploys to a single Lambda with Neon Postgres:
- Lambda scales concurrency automatically
- Neon scales compute automatically, but suspends after 5 minutes idle, so the first request after an idle period is slow
- CloudFront caches static assets

---

## Observability

### What we monitor

The backend is instrumented with OpenTelemetry (`backend/observability/`):

- **Traces** for every API request (FastAPI) and database query (SQLAlchemy)
- **Per-endpoint metrics**: request count, error count, and latency for each API route (for example `projects_create_total`, `projects_create_errors_total`, `projects_create_latency_ms`)
- **Account and activity counters**: logins and signups (with their errors), accounts created, projects created, notes created

Every metric and trace is tagged with the deployed version (`SERVICE_VERSION`, from git tags).

### Where telemetry goes

- **Dev** (`hub-dev.dnls.dev`): the dev Lambda exports traces and metrics to Grafana Cloud over OTLP/HTTP.
- **Production** (`hub.dnls.dev`): the prod Lambda exports traces and metrics to Grafana Cloud over OTLP/HTTP.
- **Local**: off by default. Turn it on to send to the optional local stack below.

### Local Observability (optional)

A separate stack, `backend/observability/docker-compose.yml`, runs an OpenTelemetry Collector, Prometheus, Tempo, Loki, and Grafana for checking instrumentation changes. From `backend/`:

```bash
# Start the stack
docker compose -f observability/docker-compose.yml up -d

# Start the backend with telemetry on (sends to the local collector)
OTEL_ENABLED=true uv run uvicorn app.main:app --reload
```

| Service        | URL                     |
| -------------- | ----------------------- |
| Grafana        | http://localhost:3000 (login `admin` / `admin`) |
| OTel Collector | http://localhost:4318 (OTLP/HTTP in) |
| Prometheus     | http://localhost:9090   |
| Tempo          | http://localhost:3200   |
| Loki           | http://localhost:3100   |

There are no prebuilt dashboards: use Grafana's **Explore** view to query metrics (Prometheus) and traces (Tempo, service name `hub-platform`). The backend doesn't export logs, so Loki stays empty. See `backend/observability/README.md` for details.

---

## On-Call Diagnostic

A Grafana Cloud alert rule, "Registration Error Rate > 10%", fires when more than 10% of registration requests in the dev environment return an error (4xx or 5xx) for 5 minutes. That includes 409 (email already registered) and 422 (invalid input), not only server errors. Its webhook notifies the on-call person, who then runs the diagnostic workflow, `.github/workflows/observability-alert-handler.yml`:

1. The on-call person starts the workflow by hand in GitHub Actions, pasting in the alert summary.
2. The job waits for a reviewer's approval (the `observability-oncall` environment).
3. `backend/oncall/diagnose.py` estimates the monthly cost and skips the call, with a warning, if it would exceed $5/month.
4. Otherwise it makes one OpenAI API call (GPT-4o-mini by default) for a short diagnosis of the alert text.
5. The diagnosis is written to the run log and the job summary.

---

## API

The backend exposes a REST API. Locally it's at `http://localhost:8000` with no prefix. When deployed, the same routes are under `/api` on the site (for example `https://hub-dev.dnls.dev/api/projects`), because CloudFront forwards `/api/*` to the backend.

### Interactive documentation

Locally only: `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/redoc` (ReDoc). The deployed API doesn't serve them.

### Main endpoints

**Health:**
```
GET    /health                    Liveness check (no login needed)
```

**Authentication:**
```
POST   /auth/register             Create an account; returns a token
POST   /auth/login                Log in (form fields); returns a token
GET    /auth/me                   The logged-in user
```

There's no logout endpoint. Logging out in the app just discards the token in the browser, and tokens expire on their own (after 60 minutes by default).

**Projects (ideas):**
```
GET    /projects                  List your projects
POST   /projects                  Create a project
GET    /projects/{id}             Get one project
PATCH  /projects/{id}             Update some fields (name, pitch, status, scores, etc.)
DELETE /projects/{id}             Delete a project and its notes
```

**Notes:**
```
GET    /projects/{id}/notes       List a project's notes
POST   /projects/{id}/notes       Add a note
DELETE /notes/{id}                Delete a note
```

Notes can be added and deleted, not edited.

### Authentication

The API uses JWT bearer tokens. Every endpoint except `/health`, `/auth/register`, and `/auth/login` needs one.

```bash
# Sign up (JSON)
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "secure-password",
    "displayName": "Your Name"
  }'

# Log in (form fields named username and password, not JSON)
curl -X POST http://localhost:8000/auth/login \
  -d "username=user@example.com" \
  -d "password=secure-password"

# Use the access_token from either response
curl http://localhost:8000/projects \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Field limits

- **Password:** 8 to 256 characters, enforced by the API.
- **Email:** must be a valid address.
- **Text fields:** no length limits. Display names, project names, pitches, descriptions, next actions, tags, and notes accept any length. The API also accepts empty or whitespace-only project names and notes; the UI is what stops you from saving those.
- **Scores** (`excitement`, `effort`, `potential`): whole numbers from 1 to 5.
- **Links:** URLs must start with `http://` or `https://`.
- **Rate limiting:** none yet.

### Error responses

Most errors return a single message in `detail`:

```json
{"detail": "Incorrect email or password"}
```

Validation errors (`422`) return `detail` as a list, one entry per invalid field, with its location and a message:

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "password"],
      "msg": "String should have at least 8 characters",
      "input": "short",
      "ctx": {"min_length": 8}
    }
  ]
}
```

Status codes: `401` for a missing, invalid, or expired token (or a wrong login), `404` for a project or note that doesn't exist or belongs to another user (the two look the same on purpose), `409` for an email that's already registered, and `422` for invalid input.

For the full API contract, see `openapi.yaml`. It's written by hand, and `backend/tests/test_openapi_contract.py` fails if its endpoints and the app's drift apart.

---

## Testing

### Test structure

```
backend/
  tests/
    test_auth.py              Signup, login, tokens
    test_projects.py          Project CRUD, validation, per-user isolation
    test_notes.py             Notes
    test_openapi_contract.py  App and openapi.yaml declare the same endpoints
    test_*.py                 Config, startup, database setup, observability,
                              on-call agent, service versioning, and more

frontend/
  src/
    **/*.test.ts(x)           Unit and component tests, next to the code
                              they cover (pages, components, store, API client)
  tests/
    app.spec.ts               Playwright: browser flows
    api.spec.ts               Playwright: live API tests
    helpers.ts                Shared setup for both
```

Backend tests each get their own in-memory SQLite database, so they don't need a running server. The Playwright tests do (see below).

### Running tests

**Backend:**

```bash
cd backend

# All tests
uv run pytest

# Specific test file
uv run pytest tests/test_projects.py

# Verbose output
uv run pytest -v
```

**Frontend:**

```bash
cd frontend

# All unit tests, once
pnpm test

# Watch mode
pnpm exec vitest

# One file
pnpm test src/pages/dashboard.test.tsx
```

### End-to-end tests (Playwright)

Hub-Platform has a full end-to-end test suite built with Playwright. These tests use the app the way a person would, and they talk to the real local backend rather than a stand-in, so a passing run means the whole system works together.

The suite covers two areas:

- **The app in the browser:** signing up, logging in and out, the dashboard, creating and editing projects, filtering and sorting, adding and deleting notes, and deleting projects. It also checks how the app behaves on phones and tablets, and what users see when something goes wrong.
- **The API on its own:** every sign-up, login and project endpoint, including what happens with missing or invalid input, expired or bad logins, and attempts to reach data that belongs to someone else.

Together they cover everyday use, error cases, unusual input such as very long text or emoji, and making sure each user only ever sees their own data.

To run them, start the backend (port 8000) and the frontend dev server (port 5173) as described in Quick Start, then:

```bash
cd frontend
pnpm exec playwright test
```

Two optional environment variables (read in `frontend/tests/helpers.ts`) point the tests elsewhere:

- `E2E_API_URL`: the backend the tests call directly (default `http://localhost:8000`)
- `E2E_JWT_SECRET`: the JWT secret the backend signs tokens with, used by the expired- and forged-token tests (default: the backend's built-in dev secret). If it doesn't match the server, those tests skip themselves.

---

## AI-Native Development Workflow

Hub-Platform was built using AI-native development practices: spec-driven development, context engineering, and AI agent teams.

### How it was built

1. **Specification**: Brainstormed with Claude to define the problem, users, features, and workflows (saved in `docs/specs.md`)
2. **Frontend first**: Created a React prototype with mocked backend calls using Claude Code
3. **API contract**: Defined OpenAPI specification for frontend-backend communication
4. **Backend from spec**: Built FastAPI backend from the OpenAPI contract
5. **Database**: Added Postgres persistence via SQLAlchemy
6. **Deployment**: Containerized, deployed to AWS, and set up CI/CD
7. **Observability**: Instrumented with OpenTelemetry and added a manual on-call diagnostic workflow
8. **Agent extension pack**: Created reusable skills and autonomous agents

### Reusable Skills

Skills are discoverable workflows for repeatable tasks. Located in `.claude/skills/`:

**Release** (.claude/skills/release/SKILL.md)
- Tag a new semantic version
- Push to main
- Verify dev deployment
- Document the release

**Security Scanning** (.claude/skills/security-scanning/SKILL.md)
- Audit dependencies (pip-audit, pnpm audit)
- Scan for secrets (truffleHog)
- Static analysis (bandit, ESLint)
- Configuration review
- License audit
- Deep threat analysis with Claude Fable 5.1 (most capable security model)

**End-to-End Testing** (.claude/skills/e2e-testing/SKILL.md)
- Run Playwright test suite
- Verify test fixtures and isolation
- Generate reports

**Design Review** (.claude/skills/design-review/SKILL.md)
- Audit UI/UX against best practices
- Evaluate component library
- Research emerging tools
- Recommend improvements

### Specialized Subagents

Subagents are AI agents in fresh contexts with specific roles:

**QA Engineer** (.claude/agents/qa-engineer.md)
- Independent feature validation without implementation bias
- Tests happy path and edge cases
- Reports findings with severity levels
- Outputs PASS or FAIL verdict

**On-Call Diagnostic** (.github/workflows/observability-alert-handler.yml)
- Run by hand, with reviewer approval, for a given alert summary
- Makes one OpenAI call (GPT-4o-mini) for a short diagnosis
- Writes the result to the GitHub Actions run log; changes nothing
- See [On-Call Diagnostic](#on-call-diagnostic)

### Example workflow

**Developing a feature:**

1. Write a feature spec with acceptance criteria
2. Request QA subagent to review the spec
3. Develop the feature with Claude Code
4. Request QA subagent to validate independently
5. If QA says FAIL, fix and retest
6. When QA says PASS, commit and push
7. Request security-scanning skill before release

**Releasing to production:**

1. Use release skill to tag version
2. Use security-scanning skill to audit dependencies
3. Use e2e-testing skill to run tests
4. Manually promote to production via GitHub Actions

For more details, see:
- `AGENTS.md` - Project instructions for AI agents
- `docs/agent-extension-pack.md` - Skills and subagent architecture
- `docs/permissions.md` - Agent security boundaries

---

## Contributing

### Development process

Hub-Platform uses an AI-native development workflow with reusable skills and specialized agents. New contributors should:

1. Read `AGENTS.md` for project instructions
2. Read `docs/agent-extension-pack.md` to understand the skill and subagent system
3. Read `docs/permissions.md` to understand what agents can and cannot do

### Making changes

**Before implementing:**

1. Create a GitHub issue or discussion with acceptance criteria
2. Clarify requirements and acceptance criteria before starting
3. Commit to the issue what needs to be done

**During implementation:**

The project owner pushes directly to `main`; contributors use a branch and pull request:

1. Create a feature branch
2. Implement the changes
3. Run tests locally: `uv run pytest` (backend), `pnpm test` (frontend)
4. Commit with conventional message format: `feat:`, `fix:`, `refactor:`, etc.
5. Push to your branch

**Before merge:**

1. Open a pull request
2. GitHub Actions runs tests automatically
3. Request QA subagent to validate the feature
4. Address QA findings
5. Merge when QA approves

### Code style

**Backend:**
- No formatter or linter is configured yet; match the style of the surrounding code

**Frontend:**
- Run `prettier` for formatting (`pnpm format`)
- Run `eslint` for linting (`pnpm lint`)
- TypeScript strict mode required

---

## Troubleshooting

### Backend not responding

If the frontend can't connect to the backend, check:

1. Backend is running: `http://localhost:8000/health` should return `{"status":"ok"}`
2. `frontend/.env` exists (copied from `.env.example`) so the frontend calls `http://localhost:8000`; restart `pnpm dev` after creating it
3. CORS allows your frontend's origin: `http://localhost:5173` by default, or set `CORS_ORIGINS`

### Database connection issues

**Local SQLite** (from `backend/`):
```bash
# Reinitialize database
rm hub.db
SEED_DEMO_DATA=true uv run python -m app.db.init_local
```

**Docker Compose Postgres** (from the repo root):
```bash
# Check logs
docker compose logs postgres

# Restart services
docker compose down
docker compose up --build
```

### Tests failing locally

```bash
# From backend/: run with verbose output
uv run pytest -vv

# Run specific test
uv run pytest tests/test_projects.py::test_patch_empty_body_is_a_no_op -vv
```

### Frontend build issues

If issues persist, try `pnpm install` to reinstall from the locked versions.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

Hub-Platform was developed as part of the [AI Dev Tools Zoomcamp](https://github.com/DataTalksClub/ai-dev-tools-zoomcamp), a free course by [DataTalks.Club](https://github.com/DataTalksClub) instructed by [Alexey Grigorev](https://github.com/alexeygrigorev).

The course teaches AI-native development practices including spec-driven development, context engineering, loop engineering, and multi-agent orchestration. This project demonstrates end-to-end application development from specification through deployment, observability, and autonomous incident response.

**Course resources:**
- [AI Dev Tools Zoomcamp](https://github.com/DataTalksClub/ai-dev-tools-zoomcamp)
- [Alexey Grigorev on GitHub](https://github.com/alexeygrigorev)
- [DataTalks.Club](https://github.com/DataTalksClub)

**Related articles:**
- [Part 1: AI-Native Development: Specifications, Loop and Graph Engineering](https://aishippingblog.com/p/ai-native-development-specifications)
- [Part 2: Build and Ship a Full-Stack App with AI Coding Assistants](https://aishippingblog.com/p/build-and-ship-a-full-stack-app-with)
- [Part 3: Deploy a Full-Stack App with AI Coding Assistants](https://aishippingblog.com/p/deploy-a-full-stack-app-with-ai-coding)
- [Part 4: DevOps and Observability for an AI-Built App](https://aishippingblog.com/p/devops-and-observability-for-an-ai)
- [Part 5: Coding Agent Building Blocks: Reusable Skills and Specialized Subagents](https://aishippingblog.com/p/coding-agent-building-blocks-reusable)
