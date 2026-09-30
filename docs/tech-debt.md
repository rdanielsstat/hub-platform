# Tech debt

## Bugs

- Mobile viewport is zoomed in after login. The login screen is fine; the
  authenticated layout renders wider than the screen until you pinch out.

## Security

- Rate-limiting on signup and login.
- Account and project caps per user.
- Cap password length on `/auth/login`. Registration caps at 256 characters,
  login does not, and argon2 is slow by design.
- Decide what to do about the writable demo account. Retiring it means
  removing that environment's entry from `demo_passwords` and re-applying.
- Wire up observability. Nothing reports errors, frontend or backend.

## Migrations

- Move to Alembic. `create_all()` creates missing tables but cannot alter
  existing ones.

## Testing

- End-to-end tests with Playwright, run against Docker Compose.
- Integration tests that run against Docker Compose and real Postgres.
  Current backend tests use in-memory SQLite.
- Makefile for the common commands.

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

- Root `README.md`.
- `product-spec.md` at the repo root. Currently `docs/specs.md`.
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
- Promote to prod so `hub.dnls.dev` is live.
- Make the repo public before peer review.
- Do not destroy the stack until peer review is finished.

## Housekeeping

- `AGENTS.md` says storage "can move to Postgres later via DATABASE_URL".
  Postgres is already in use, locally and deployed.
