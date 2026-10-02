# Tech debt

## Bugs

- Mobile viewport is zoomed in after login. The login screen is fine; the
  authenticated layout renders wider than the screen until you pinch out.

## Security

- Rate limiting: done (2026-10-02). Login 5 and sign-up 3 attempts per minute
  per IP, plus API Gateway stage throttling at 50 rps, burst 100. IPv6 is
  handled (bare, bracketed and IPv4-mapped addresses; counted per /64). Still
  open: the per-IP limits are per Lambda container, not shared.
- Confirm from two different networks that the login rate limit is per user:
  six bad logins from one, then one from another should give 401, not 429.
  `CloudFront-Viewer-Address` is in the `/api/*` origin request policy
  (deployed 2026-10-02), but a single network can't tell per-user from
  per-edge.
- Block direct calls to the public `execute-api` endpoint: done (2026-10-02).
  CloudFront sends a secret `X-Origin-Verify` header and the backend answers
  403 without it. Verified on dev and prod: direct calls get 403, the site
  works.
- Gitleaks in CI: done (2026-10-02). The `secrets-scan` job in `ci.yml` scans
  the full history on every PR and push and gates the dev deploy; reviewed
  false positives are in `.gitleaksignore`.
- Account and project caps per user.
- Cap password length on `/auth/login`. Registration caps at 256 characters,
  login does not, and argon2 is slow by design.
- Decide what to do about the writable demo account. Retiring it means
  removing that environment's entry from `demo_passwords` and re-applying.
- Observability: done for the backend. Metrics, traces and an alert exist in dev.
  Frontend error reporting is still missing.

## Migrations

- Move to Alembic. `create_all()` creates missing tables but cannot alter
  existing ones.

## Testing

- End-to-end tests with Playwright: done (`frontend/tests/`, run against the
  local uvicorn backend). Still to do: run them against Docker Compose and in CI.
- Integration tests that run against Docker Compose and real Postgres.
  Current backend tests use in-memory SQLite.
- Makefile for the common commands.

## Observability

- Prod SERVICE_VERSION SemVer versioning: done. `promote.yml` runs
  `service-version.sh` against the promoted image's commit.

## Deferred features

- Attachments. Needs an upload-mechanism decision (direct-to-S3 presigned vs
  proxied) first.
- PWA installability. No manifest or service worker.

## Open questions

- Logout-on-any-failure may be too aggressive. The app routes to login
  whenever the backend is unreachable, not only on a real 401. Neon sleeps
  after five minutes, so the first request after idle is slow. Not yet
  root-caused; also entangled with an environment quirk seen in the automated
  browser tab.

## Project requirements

- Root `README.md`: done.
- `product-spec.md` at the repo root. The spec currently lives at `docs/specs.md`.
- Separate unit and integration tests with markers or subdirectories, and
  document the command for each.
- `ops/` directory.
- `security/` directory, containing:
  - PR audit output
  - deterministic security scan output (checkov or tfsec over `infra/`,
    pip-audit over backend deps, trivy over the image)
  - agent and extension security notes
  - operational diagnosis output
  - AI tool and data policy
- `agent-capabilities/`, `agent-hooks/`, `mcp-server/`, and either `plugins/`
  or `custom-agent/`, plus `docs/agent-extension-pack.md` and
  `docs/permissions.md`. Needs a reusable workflow, a subagent, an MCP tool or
  server, and a hook or guardrail.
- Promote to prod so `hub.dnls.dev` is live: done.
- Make the repo public before peer review: done (https://github.com/rdanielsstat/hub-platform).
- Do not destroy the stack until peer review is finished.
