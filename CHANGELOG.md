# Changelog

All notable changes to Hub are recorded here. Versions follow
[Semantic Versioning](https://semver.org/); the deployed `SERVICE_VERSION`
comes from the git tag (`.github/scripts/service-version.sh`).

## [Unreleased]

### Added
- On-call agent wakes on its own: a Grafana alert reaches
  `observability-alert-handler.yml` through `repository_dispatch`
  (`grafana-alert`); it triages the payload, opens a tracking issue, posts
  an OpenAI diagnosis, and on dev rolls back to the previous image
  (`rollback-dev.yml`) with a health check
- Alerting as code (`infra/hub/grafana.tf`): project creation 5xx rate above
  2% over 5 minutes (at least 10 requests), dev and prod, with the webhook
  contact point and notification policy
- Project creation journey log (`app.projects`): one JSON line per
  `POST /projects` with outcome, status, duration and `trace_id`; endpoint
  metrics carry `hub_environment`
- `FAULT_INJECT_5XX`, the drill's switch (dev only)
- `make test-all`, the single test command
- Dashboard shows how many projects match the filters (#13)
- `AGENT_TEAM.md`; GitHub Issues as the task tracker
- MCP server (`mcp-server/`): five tools over the Hub API for AI agents
  (list, get, create, update, add note; no deletes), registered for
  Claude Code in `.mcp.json`
- Guard hook (`agent-hooks/guard.py`, `.claude/settings.json`): Claude Code
  can't commit, deploy or read real `.env` files and secrets, and asks
  before pushes and commands that delete data
- `agent-capabilities/README.md`: every agent capability in one table
- Docker Compose runs the whole system: a `frontend` service (nginx on
  :8080) serves the production build with CloudFront's security headers
  and SPA routing, and proxies `/api/*` to the backend

### Fixed
- Mobile: the page no longer stays zoomed in after logging in. Form fields
  are 16px on phones (iOS Safari zooms in on focusing anything smaller) and
  14px from the `md` breakpoint up, as before
- Project detail: the link label field is wide enough to show its
  "Label (optional)" placeholder

### Changed
- The API refuses blank (empty or whitespace-only) project names and note
  bodies with 422 (#12)
- `lambda_image_tag`, `service_version` and `trusted_proxy_ips` are
  required OpenTofu variables with no default; an empty proxy list is
  refused; OpenTofu runs in CI only, with `tofu fmt` and `tofu validate`
  on every pull request
- CI runs the frontend's lint, format check and build in the `test` job
- CI also lints and tests the MCP server and the guard hook, runs the MCP
  server against the Compose stack, and audits `mcp-server/uv.lock`
- The `security-scanning` skill runs trivy (backend and frontend images,
  the frontend Dockerfile) and the IaC scans, and audits the MCP server
- `make docker-up` waits for the web app as well as the API; new targets
  `test-mcp`, `test-mcp-live`, `test-hooks`, `lint-mcp`, `lint-hooks`
- `pnpm lint` fails on any ESLint warning (`--max-warnings 0`)

### Security
- Fixes from the 2026-10-13 security sweep, one entry each in
  `security/REMEDIATION_LOG.md`:
  - MCP server: the password comes from the macOS keychain through
    `mcp-server/run-with-keychain.sh`, never Claude Code's environment;
    `update_project` is marked destructive and won't blank text without
    `allow_clear` or make more than three status changes in ten minutes
    without `confirm_bulk`; project ids must be UUIDs (no path
    injection); error text is capped; no password over plain http to a
    remote host; the server tells the model user text is untrusted; the
    live test refuses non-local backends
  - Guard hook: denies environment dumps, AWS secret reads, every git
    command that creates a commit, git aliases, tofu state changes and
    `-chdir=` forms, workflow dispatches through `gh api`, S3 uploads
    whatever the option order, and package publishing; checks `bash -c`,
    `eval` and wrapped commands; splits command lines outside quotes only;
    fails closed (`agent-hooks/run-guard.sh`)
  - Login CSRF: `/auth/login` and `/auth/register` refuse a foreign
    `Origin` (403); Docker Compose allows its `:8080` web app
  - Backend prod image: the unused Lambda emulator removed (3 HIGH, 5
    MEDIUM gone; 0 findings); the local dev image runs as a non-root user
    with a healthcheck
  - `source-map-js` pinned to 1.2.2 (GHSA-68fv-2mgg-jv7q)
  - CI: `id-token: write` only on `deploy-dev`; deploy scripts pass
    actionlint (checked locally; CI runs neither actionlint nor
    shellcheck)
  - The `dev` and `prod` GitHub environments accept deployments from
    `main` only
  - Sign-up's 409 for a registered email kept, with the reasoning
    recorded (`security/RATE_LIMITING.md`)
- Compose frontend image: OS packages upgraded at build (fixes a MEDIUM
  zlib CVE), non-root, healthcheck, no nginx version in responses
- Data policy states that the opt-in MCP server returns a user's own data
  to the AI client they connect

### Documentation
- Rubric scorecard (`docs/rubric-scorecard.md`): each of the 12 criteria
  scored from evidence, with what a reviewer could still dock
- Drill runbook in `security/OPERATIONAL_DIAGNOSIS.md` rewritten as a
  reusable procedure; the one-time setup steps that are done are gone,
  and the run log entries are unchanged
- `product-spec.md`: acceptance criteria for each shipped feature, dated
  2026-10-18 and labeled as written after the work, linked to issues and
  PRs where they exist
- `AGENTS.md`: issues #12 and #13 named as the issue-first evidence; the
  CI role's trust (`environment:dev` and `environment:prod` only), the
  hand-applied `infra/bootstrap` root, actionlint in `infra-check`, and the
  backend unit count (600 tests, 37 files)
- `README.md`, `AGENT_TEAM.md`, `infra/BOOTSTRAP.md`, `ops/DEPLOYMENT.md`:
  the same CI role trust, OpenTofu in CI only for dev and prod with
  `infra/bootstrap` applied by hand, and actionlint on pull requests;
  `promote.yml` refuses any tag that isn't a CI build tag
- `security/SECURITY_CHECKLIST.md`: the drill marked passed (run
  39069607931), the jobs that hold `id-token: write`, and the narrowed
  trust (PR #34)
- `ops/MONITORING.md` and `docs/tech-debt.md`: prod alert email routing
  recorded as an open decision; the old registration rule's cleanup no
  longer points at a removed runbook step
- `docs/permissions.md`: the webhook-triggered on-call agent and the dev
  rollback marked done; `docs/repo-inventory.md` test counts and checks
- README lists every `make` target (new "Make Targets" section)
- README's AI workflow section documents the tools and their roles, the
  prompt log, context files, and manual review and verification; Mermaid
  architecture and CI/CD diagrams replace the placeholders

### Testing
- 204 Playwright E2E tests (a phone-width check that every form field is
  16px or larger; the Compose frontend container's headers, routing,
  proxy and a browser journey)
- 459 backend unit tests (login CSRF, Dockerfile, workflow permissions)
- 74 MCP server unit tests and a live test; 36 guard hook tests

## [1.0.0] - 2026-10-03

### Added
- User authentication (login/signup with cookie-based sessions)
- Projects and notes (multi-user, per-user data isolation)
- Rate limiting per client IP (login 5/min, register 3/min, client error reports 30/min), plus usage quotas
- Cloudflare integration (DDoS protection, WAF, Web Analytics)
- Frontend error reporting to Grafana Cloud Loki
- Data length limits: display name (100), tags (50 @ 64 chars), links (50 @ 2048 URL + 200 label)

### Security
- Content Security Policy (CSP) with HSTS, X-Frame-Options, nosniff, Referrer-Policy
- Backend Docker image hardened (Trivy scan clean)
- Infrastructure scanning (tfsec/checkov)
- Dependency scanning (pip-audit, pnpm audit) gated in CI
- GitHub branch protection (blocks force-push and deletion of main)

### Infrastructure
- PostgreSQL with Alembic migrations (0003)
- Lambda backend, CloudFront + S3 frontend
- Docker Compose for local development
- CI/CD pipeline: test → integration → e2e → dependency-scan → deploy-dev; separate promotion to prod with migrations-before-code
- Grafana Cloud observability (logs, error reporting)

### Testing
- 435 backend unit tests, 38 backend integration tests
- 202 frontend unit tests, 201 Playwright E2E tests

### Documentation
- Product specification
- API specification (OpenAPI)
- Architecture and design notes
- Deployment and troubleshooting guides
- Security audit and hardening documentation

### Design Notes
- Tags field caps total input length (comma-separated), not per-tag
- Link URLs auto-prepend `https://` if missing
- Form fields use HTML `maxLength` attributes to enforce API limits

[1.0.0]: https://github.com/rdanielsstat/hub-platform/releases/tag/v1.0.0
