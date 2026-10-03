# Tech debt

## Bugs

- Mobile viewport is zoomed in after login. The login screen is fine; the
  authenticated layout renders wider than the screen until you pinch out.

## Security

- Rate limiting: done (2026-10-02). Login 5 and sign-up 3 attempts per minute
  per IP, plus API Gateway stage throttling at 50 rps, burst 100. IPv6 is
  handled (bare, bracketed and IPv4-mapped addresses; counted per /64). The
  per-IP limits are per Lambda container, not shared: accepted, with the bound
  and the options in `security/RATE_LIMITING.md`.
- Rate limits keyed on the real client behind Cloudflare: done (2026-10-02).
  `TRUSTED_PROXY_IPS` (Cloudflare's ranges, set on the dev and prod GitHub
  environments) lets the limiter read the client from `X-Forwarded-For`.
  Still open: confirm from two different networks that six bad logins from
  one, then one from another, give 401 for the second, not 429.
- Block direct calls to the public `execute-api` endpoint: done (2026-10-02).
  CloudFront sends a secret `X-Origin-Verify` header and the backend answers
  403 without it. Verified on dev and prod: direct calls get 403, the site
  works.
- Gitleaks in CI: done (2026-10-02). The `secrets-scan` job in `ci.yml` scans
  the full history on every PR and push and gates the dev deploy; reviewed
  false positives are in `.gitleaksignore`.
- Account and project caps per user: done (2026-10-02). 1000 accounts
  (deployed), 500 projects per user, 500 notes per project
  (`backend/app/core/quotas.py`).
- Cap password length on `/auth/login`: done (2026-10-02). 256 characters,
  checked before argon2.
- Text field length limits: done (2026-10-02). Project name 256, pitch 2000,
  description 5000, next action 1000, note body 10000 characters; API 422s
  and Postgres CHECK constraints (migration `0002`).
- Length limits on tags, links and display name: done (2026-10-03). 50 tags
  of up to 64 characters, 50 links (URL 2048, label 200), display name 100;
  API 422s, CHECK constraints for the counts and the display name (migration
  `0003`).
- Security headers: done (2026-10-03). CloudFront response headers policy
  with a strict CSP (no inline scripts), HSTS (one year, includeSubDomains,
  preload), `X-Frame-Options: DENY`, nosniff and Referrer-Policy.
- Container image scan: done (2026-10-03). trivy found 8 HIGH in the Lambda
  base image's OS packages and an old bundled pip; the Dockerfile now applies
  OS security updates and removes pip. Patched build: no CRITICAL, HIGH,
  MEDIUM or LOW findings (`security/IAC_SCANS.md`).
- IaC scans: done (2026-10-03). tfsec and checkov over `infra/hub`; S3
  encryption made explicit and ECR tags made immutable, the rest accepted
  with reasons (`security/IAC_SCANS.md`).
- GitHub Actions on Node.js 24: done (2026-10-03). Every action updated; no
  Node 20 deprecation warnings in CI.
- GitHub Actions pinned to commit SHAs: done (2026-10-03), in every workflow.
- Decide what to do about the writable demo account. Retiring it means
  removing that environment's entry from `demo_passwords` and re-applying.
- Observability: done. Metrics, traces and an alert in dev and prod.
  Frontend error reporting: done (2026-10-02, `POST /client-errors`), and
  exported to Grafana Cloud (Loki) as OTLP logs since 2026-10-03.
- Still open: test a restore from Neon's point-in-time history; run the
  dependency scans in CI; alerts beyond the registration error rate;
  self-service account deletion and export (`security/SECURITY_CHECKLIST.md`).

## Migrations

- Move to Alembic: done (2026-10-02). Baseline `0001` matches the old
  `create_all()` schema; existing databases are stamped automatically.
- Run migrations before the new API code goes live: done (2026-10-02). CI and
  promote update and run the bootstrap function, then apply everything else.

## Testing

- End-to-end tests with Playwright: done, run against Docker Compose and in
  CI (2026-10-02).
- Integration tests against Docker Compose and real Postgres: done
  (2026-10-02, `backend/tests/integration/`).
- Makefile for the common commands: done (2026-10-02).
- Integration and E2E jobs gate the dev deploy: done (2026-10-03).
- Deprecation warnings in the test run (httpx, anyio, Mangum): done
  (2026-10-02). `httpx2`, Starlette 1.7.0; Mangum's one warning filtered with
  the reason, since 0.22.0 is the latest release.

## Observability

- Prod SERVICE_VERSION SemVer versioning: done. `promote.yml` runs
  `service-version.sh` against the promoted image's commit.

## Deferred features

- Attachments. Needs an upload-mechanism decision (direct-to-S3 presigned vs
  proxied) first.
- PWA installability. No manifest or service worker.

## Open questions

- Logout-on-any-failure: resolved (2026-10-02). Root cause: the on-load
  session check treated any failure as signed out. Now only a 401 does; other
  failures retry once, then show a "Can't reach the server" screen, and a
  database outage is a 503 (`ops/TROUBLESHOOTING.md`).

## Completed work, by session

**2026-10-02, security hardening (P3a to P3d) and follow-ups**

- Alembic migrations, and the bootstrap running them on every deploy.
- Login password cap; account, project and note caps; `POST /client-errors`
  with frontend error reporting; `security/RATE_LIMITING.md` and
  `security/AGENT_SECURITY.md`.
- Integration tests on Postgres, Playwright against Docker Compose and in
  CI, the Makefile, and the `ops/` and `security/` directories.
- The logout-on-any-failure fix.
- Text length limits (migration `0002`); migrations moved before the code
  switch in CI and promote; rate limits keyed on the real client behind
  Cloudflare (`TRUSTED_PROXY_IPS`).
- Test-run deprecation warnings cleared; GitHub Actions on Node.js 24.

**2026-10-03, remaining hardening**

- CloudFront security headers (CSP, HSTS and related).
- trivy scan of the prod image, and the Dockerfile fixes for its findings.
- tfsec and checkov over `infra/hub`, with S3 encryption and immutable ECR
  tags.
- GitHub Actions pinned to commit SHAs.
- Frontend error reports (and database-outage and origin-verification logs)
  exported to Grafana Cloud as OTLP logs.
- Length limits on tags, links and display name (migration `0003`).
- Integration and E2E jobs gating the dev deploy.
- This file.

## Project requirements

- Root `README.md`: done.
- `product-spec.md` at the repo root. The spec currently lives at `docs/specs.md`.
- Separate unit and integration tests with markers or subdirectories, and
  document the command for each: done (2026-10-02, the `integration` pytest
  marker; `backend/README.md`, `frontend/README.md`).
- `ops/` directory: done (2026-10-02).
- `security/` directory: done (2026-10-02), containing:
  - agent and extension security notes (`AGENT_SECURITY.md`): done
  - AI tool and data policy (`DATA_POLICY.md`): done
  - deterministic security scan output (checkov and tfsec over `infra/`,
    pip-audit over backend deps, trivy over the image): done (2026-10-03,
    `IAC_SCANS.md`, `DEPENDENCIES.md`)
  - PR audit output: still to do
  - operational diagnosis output: still to do
- `agent-capabilities/`, `agent-hooks/`, `mcp-server/`, and either `plugins/`
  or `custom-agent/`, plus `docs/agent-extension-pack.md` and
  `docs/permissions.md`. Needs a reusable workflow, a subagent, an MCP tool or
  server, and a hook or guardrail.
- Promote to prod so `hub.dnls.dev` is live: done.
- Make the repo public before peer review: done (https://github.com/rdanielsstat/hub-platform).
- Do not destroy the stack until peer review is finished.
