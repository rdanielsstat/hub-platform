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
- [openapi.yaml](openapi.yaml) - API contract (backend-generated)

---

## What is Hub-Platform?

Hub-Platform is a personal hub for capturing ideas, scoring them, and tracking them through a lifecycle. Sign up, quickly capture an idea with a one-line pitch, brain-dump description, and scoring (excitement, potential, effort). Track ideas through statuses (inbox, exploring, active, parked, graduated, killed), add notes, set target dates, and filter your dashboard by tags, status, or score.

### Key features

- **Quick capture**: One-screen form to capture an idea with minimal friction
- **Lifecycle tracking**: Move ideas from inbox through exploring, active, parked, graduated, or killed
- **Scoring system**: Rate excitement, potential, and effort; opportunity score calculated automatically
- **Dashboard filtering**: Filter by tags, status, and sort by recently updated, scores, target date, or name
- **Notes and links**: Add notes to ideas and link to external resources
- **Personal workspace**: Individual signup and login; your ideas, your rules
- **Production-ready**: Deployed to AWS with full observability, alerting, and AI-assisted incident response
- **AI-native development**: Built with Claude Code using spec-driven development, AI skills, and specialized subagents

### Typical workflow

1. Sign up with email and password
2. Land on dashboard showing all your ideas with tiles displaying name, pitch, scores, and status
3. Click "quick capture" to add a new idea
4. Enter project name, one-line pitch, brain-dump description, status, and scores (excitement, potential, effort)
5. See the new idea tile on your dashboard immediately
6. Click a tile to open the full project page
7. Add notes, links, update target date, refine scores
8. Filter dashboard by tags, status, or sort by recently updated, scores, target date, or name

---

## Quick Start

### Prerequisites

- Python 3.12 (via `uv`)
- Node.js 22+ (via `pnpm`)
- Docker and Docker Compose
- Git

### Run locally

```bash
# Clone the repository
git clone https://github.com/yourusername/hub-platform.git
cd hub-platform

# Install backend dependencies
uv sync

# Install frontend dependencies
cd frontend
pnpm install
cd ..

# Seed demo data and start the backend
SEED_DEMO_DATA=true uv run python -m app.db.init_local
uv run uvicorn app.main:app --reload --port 8000
# Or if Makefile is available: make run

# In a separate terminal, start the frontend
cd frontend
pnpm dev
```

Visit `http://localhost:5173` (frontend) and `http://localhost:8000/api/docs` (backend OpenAPI docs).

### Run with Docker Compose (production parity)

```bash
# Start all services (app, database, observability stack)
docker compose up --build

# Visit http://localhost:8100
```

This starts:
- FastAPI backend + React frontend (one container)
- Postgres 17
- OpenTelemetry Collector
- Prometheus, Loki, Tempo
- Grafana dashboards

---

## Architecture

### System design

[**ARCHITECTURE DIAGRAM PLACEHOLDER**]

Visual description: A user accesses Hub-Platform through a web browser. The frontend (React) is compiled and served by the FastAPI backend. The backend is containerized and deployed to AWS Lambda via ECR. Lambda connects to Postgres on Neon for persistent storage. CloudFront caches the frontend and provides HTTPS. OpenTelemetry instruments the backend and exports metrics to Prometheus, logs to Loki, and traces to Tempo via an OTel Collector. Grafana displays dashboards and handles alerting.

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
- Authentication: JWT + argon2 password hashing
- Testing: pytest 9.1
- RESTful API for CRUD operations on ideas and notes

**Database**
- SQLite for local development and testing
- Postgres 17 for production (via Neon)
- SQLAlchemy 2.0 (no migrations; creates schema on startup)
- Schema: users, auth_identities (auth), projects (ideas), notes

**Infrastructure**
- AWS Lambda (compute)
- AWS ECR (container registry)
- Neon Postgres (managed database)
- CloudFront (CDN + HTTPS)
- S3 (frontend static assets)
- OpenTofu 1.12.6 (IaC)
- GitHub Actions (CI/CD)

**Observability**
- OpenTelemetry SDK (Python)
- Prometheus (metrics)
- Loki (logs)
- Tempo (traces)
- Grafana (dashboards and alerting)
- Grafana Cloud (production observability)

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

**Using `uv` for Python:**

```bash
# Install dependencies (creates virtual environment)
uv sync

# Add a package
uv add package-name

# Run a Python file
uv run python script.py

# Run pytest
uv run pytest
```

**Using `pnpm` for Node:**

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

**Backend:**

```bash
make run
# Or manually:
uv run uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/api/docs` for interactive OpenAPI documentation.

**Frontend:**

```bash
cd frontend
pnpm dev
```

Visit `http://localhost:5173`.

### Running Tests Locally

```bash
# Backend tests (from project root)
uv run pytest

# Frontend tests
cd frontend
pnpm test

# Lint and format
cd frontend
pnpm lint
pnpm format
```

### Database Management

**Seed demo data:**

```bash
SEED_DEMO_DATA=true uv run python -m app.db.init_local
```

This creates demo users and sample interview sessions.

**Reset database:**

```bash
rm data/sdip.db  # For SQLite
# Or drop/recreate schema for Postgres
```

### Local Docker Compose (Production Parity)

To test the application exactly as it runs in production:

```bash
docker compose up --build
```

This starts:
- Containerized app + frontend (compiled)
- Postgres 17 with persistent volume
- Full observability stack (OTel Collector, Prometheus, Loki, Tempo, Grafana)

Access the app at `http://localhost:8100` and Grafana at `http://localhost:3000`.

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

Visual description: A developer pushes code to main. GitHub Actions runs backend and frontend tests in parallel. If tests pass, CI builds a Docker image, tags it with a timestamp and short SHA (e.g., 20261001-163457-83242da), and pushes it to AWS ECR. The deploy step pulls the image and deploys to the development Lambda. After testing in dev, a release owner manually triggers a prod release workflow, which promotes the same image from dev ECR to prod ECR (no rebuild) and deploys to production Lambda.

### Environments

**Development**
- Automatic deployment on every push to main
- Latest code always running
- Internal testing and validation
- Shorter retention (logs, backups)

**Production**
- Manual promotion from development
- Tested release selected by release owner
- Serves real users
- Full retention and compliance

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

The current setup deploys to a single Lambda with Neon Postgres. For production scale:
- Lambda auto-scales concurrency
- Neon auto-scales compute
- CloudFront caches static assets
- No request queuing; scale up or down instantly

---

## Observability

### What we monitor

Hub-Platform instruments application-level metrics relevant to the system design interview experience:

- **Interview sessions**: Rooms created, active rooms, active participants
- **Canvas**: Elements created, total elements across all rooms
- **Performance**: Change propagation latency (how long before candidate sees interviewer's update)
- **Errors**: Component creation failures, connection failures

### Observability Stack

[**OBSERVABILITY DIAGRAM PLACEHOLDER**]

Visual description: The FastAPI backend instruments with OpenTelemetry SDK, exporting metrics, logs, and traces via OTLP protocol. An OpenTelemetry Collector receives all telemetry and routes it: metrics to Prometheus, logs to Loki, traces to Tempo. Grafana scrapes all three backends and displays dashboards, alerts, and trace analysis.

### Local Observability (Docker Compose)

When you run `docker compose up`, you get:

- **Prometheus**: Scrapes metrics from the app (port 9090)
- **Loki**: Ingests logs from the app (port 3100)
- **Tempo**: Ingests traces from the app (port 4317)
- **Grafana**: Unified dashboards and alerts (port 3000, login: admin/admin)

**Access Grafana dashboards locally:**

1. Open http://localhost:3000
2. Navigate to Dashboards
3. Select "Hub-Platform Metrics"

[**GRAFANA DASHBOARD SCREENSHOT PLACEHOLDER**]

Visual: Shows panels for interview rooms created (time series), active participants (gauge), canvas elements (counter), component failures (bar chart), all filterable by environment and deployed version.

### Production Observability (Grafana Cloud)

Development and production both export telemetry to Grafana Cloud:

- Metrics stored in Prometheus-compatible backend
- Logs stored and indexed for fast search
- Traces stored in Tempo for distributed tracing
- Real-time dashboards and alerts
- Data retention: 30 days for logs, 30 days for traces

---

## Production Alerting and On-Call Agents

### Alert workflow

When application metrics deviate from normal, Grafana fires an alert.

[**ON-CALL AGENT DIAGRAM PLACEHOLDER**]

Visual description: A Grafana alert fires and sends a notification to AWS SNS. SNS triggers an AWS Lambda. Lambda starts a container job running Claude (powered by OpenAI GPT-4o-mini). The agent has access to the GitHub repository code, CloudWatch logs, and Grafana metrics. The agent analyzes the logs, identifies the root cause, and either creates a fix (if it's a real bug) or explains why the alert is a false positive. The session log is saved after the run.

### Current alerting

Canvas component creation failures above 5% error rate for 5 minutes trigger an alert.

### On-Call Agent

The on-call diagnostic agent is an autonomous service that responds to production alerts without human intervention:

1. Alert fires in Grafana
2. SNS sends notification to Lambda
3. Lambda starts a container with Claude (GPT-4o-mini)
4. Agent receives alert details + code context
5. Agent queries CloudWatch logs
6. Agent analyzes error patterns
7. Agent recommends action or creates fix
8. Session log is saved

**Agent access:**
- GitHub repository (read-only)
- CloudWatch logs (read-only, last 100 entries)
- Grafana metrics (read-only)
- Cannot deploy, modify code without human approval, or access production data

For details, see `custom-agent/on-call-diagnostic/README.md`.

---

## API

The backend exposes a RESTful API documented in OpenAPI format.

### Interactive documentation

Visit `http://localhost:8000/api/docs` (Swagger UI) or `http://localhost:8000/api/redoc` (ReDoc).

### Main endpoints

**Authentication:**
```
POST   /api/auth/register         Create a new account
POST   /api/auth/login            Get JWT token
POST   /api/auth/refresh          Refresh token
```

**Projects (ideas):**
```
GET    /api/projects              List all your projects
POST   /api/projects              Create a new project
GET    /api/projects/{id}         Get project details
PUT    /api/projects/{id}         Update project (name, pitch, status, scores, etc.)
DELETE /api/projects/{id}         Delete project
```

**Notes:**
```
GET    /api/projects/{id}/notes   List notes for a project
POST   /api/projects/{id}/notes   Add a note
PUT    /api/notes/{id}            Update note
DELETE /api/notes/{id}            Delete note
```

### Authentication

The API uses JWT bearer tokens. Endpoints requiring authentication:

```bash
# Sign up
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "secure-password",
    "display_name": "Your Name"
  }'

# Log in
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secure-password"}'

# Use token to list projects
curl http://localhost:8000/api/projects \
  -H "Authorization: Bearer YOUR_TOKEN"
```

For full API contract, see `openapi.yaml` (auto-generated from FastAPI).

---

## Testing

### Test structure

```
backend/
  tests/
    test_auth.py              Authentication, signup, login
    test_projects.py          Project CRUD operations
    test_notes.py             Note management
    test_filtering.py         Dashboard filtering and sorting

frontend/
  src/
    __tests__/
      components/             Component unit tests (dashboard, forms, filters)
      hooks/                  Custom hook tests
      services/               API client tests
```

### Running tests

**Backend:**

```bash
# All tests
uv run pytest

# Specific test file
uv run pytest tests/test_projects.py

# With coverage
uv run pytest --cov=app

# Verbose output
uv run pytest -v
```

**Frontend:**

```bash
cd frontend

# All tests
pnpm test

# Watch mode
pnpm test --watch

# Coverage
pnpm test --coverage
```

### End-to-end tests (Playwright, planned)

End-to-end tests with Playwright will verify the full application flow: sign up, create projects, filter, update scores. Implementation in progress.

```bash
# Run E2E tests (requires app + postgres running)
make e2e

# Or from project root
docker compose up --build
# In another terminal
uv run pytest e2e/
```

---

## AI-Native Development Workflow

Hub-Platform was built using AI-native development practices: spec-driven development, context engineering, and AI agent teams.

### How it was built

1. **Specification**: Brainstormed with Claude to define the problem, users, features, and workflows (saved in `docs/spec.md`)
2. **Frontend first**: Created a React prototype with mocked backend calls using Claude Code
3. **API contract**: Defined OpenAPI specification for frontend-backend communication
4. **Backend from spec**: Built FastAPI backend from the OpenAPI contract
5. **Database**: Added Postgres persistence via SQLAlchemy
6. **Deployment**: Containerized, deployed to AWS, and set up CI/CD
7. **Observability**: Instrumented with OpenTelemetry and added alerting
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

**On-Call Agent** (custom-agent/on-call-diagnostic/)
- Autonomous production alert responder
- Queries logs and analyzes patterns
- Recommends remediation
- Can commit fixes for real bugs

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
2. Request QA subagent to groom the task (clarify requirements)
3. Commit to the issue what needs to be done

**During implementation:**

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
- Run `black` for formatting (included in `uv sync`)
- Run `ruff` for linting
- Type hints required

**Frontend:**
- Run `prettier` for formatting (`pnpm format`)
- Run `eslint` for linting (`pnpm lint`)
- TypeScript strict mode required

---

## Troubleshooting

### Backend not responding

If the frontend can't connect to the backend, check:

1. Backend is running: `http://localhost:8000/api/health`
2. CORS is configured (if on different host)
3. Firewall allows HTTP (port 8000)

### Database connection issues

**Local SQLite:**
```bash
# Reinitialize database
rm data/sdip.db
SEED_DEMO_DATA=true uv run python -m app.db.init_local
```

**Docker Compose Postgres:**
```bash
# Check logs
docker compose logs db

# Restart services
docker compose down
docker compose up --build
```

### Tests failing locally

```bash
# Run with verbose output
uv run pytest -vv

# Run specific test
uv run pytest tests/test_sessions.py::test_create_session -vv

# Check for environment variables
echo $DATABASE_URL
```

### Frontend build issues

```bash
# Clear cache and reinstall
cd frontend
rm -rf node_modules pnpm-lock.yaml .vite
pnpm install
pnpm dev
```

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
