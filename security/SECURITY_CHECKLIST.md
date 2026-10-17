# Security checklist

Pre-launch security validation: what's been checked, with evidence, and
what's still open. Update the date and the status column whenever an
item changes. Last reviewed: 2026-10-13.

Legend: **Done** (implemented, and tested or configured in code),
**Verified** (also confirmed by hand on a deployed environment),
**Open** (not done), **Accepted** (known, deliberately left). Most
"Done" items could become "Verified" with a quick check on dev.

## Authentication and sessions

| Item | Status | Evidence |
|---|---|---|
| Passwords hashed with argon2id, parameters pinned | Done | `backend/app/auth/security.py`, `tests/test_password_hashing.py` |
| Constant-cost login for unknown emails (no timing oracle) | Done | `DUMMY_PASSWORD_HASH`, `tests/test_auth.py` |
| Password length 8 to 256 at sign-up; 256 cap at login, before hashing | Done | `RegisterInput`, `routers/auth.py`, `tests/test_auth.py` |
| Session is a JWT in an httpOnly, SameSite=Strict cookie, Secure when deployed | Done | `app/auth/cookies.py`, `tests/test_auth_cookie.py`, E2E cookie tests |
| Invalid or expired cookie is cleared on the 401 | Done | `app/auth/dependencies.py` |
| JWT secret from SSM; refuses to start with a missing or default secret when deployed | Done | `require_safe_jwt_secret()`, `tests/test_startup.py` |
| Login CSRF: sign-in and sign-up refuse a foreign `Origin` | Done | `app/auth/csrf.py` (allowlist `CORS_ORIGINS`), `tests/test_login_csrf.py`; 2026-10-13 sweep, `security/REMEDIATION_LOG.md` M4 |
| Sign-up doesn't reveal whether an email is registered | Accepted | 409 "Email already registered" kept: a uniform response needs email verification, which Hub doesn't have. Bounded by the 3/min/IP sign-up limit; login doesn't leak it. `security/RATE_LIMITING.md`, "Email enumeration through sign-up" |
| Logout revokes tokens server side | Accepted | Stateless JWTs, 60-minute expiry; logout clears the cookie only |
| Backend unreachable doesn't sign the user out | Done | `frontend/src/auth.tsx` retry and "can't reach" state, `ops/TROUBLESHOOTING.md` |

## Authorization and data isolation

| Item | Status | Evidence |
|---|---|---|
| Every project and note query is scoped to the owner | Done | `app/db/store.py`, `tests/test_projects.py`, `tests/test_notes.py`, integration tests |
| Another user's resource is a 404, indistinguishable from missing | Done | Same; `openapi.yaml` `NotFound` |
| MCP server limited to one account's data, with no delete tools | Done | `mcp-server/hub_mcp/server.py`; `tests/test_server.py` (tool list), `tests/test_contract.py` (no DELETE in the client), `tests/test_live_api.py` (404 for another id) |
| MCP server: destructive updates guarded, ids can't reach other endpoints, password kept from the agent | Done | 2026-10-13 sweep (`security/REMEDIATION_LOG.md` H1, H2, M1, L4, L5): `update_project` marked destructive with `allow_clear`/`confirm_bulk`; project ids must be UUIDs; password from the macOS keychain via `run-with-keychain.sh`, never over remote http; `mcp-server/tests/test_hardening.py`, `tests/test_keychain_wrapper.py` |
| MCP server has no scoped or read-only token | Accepted | The API issues one kind of token; the server holds the configured account's full non-delete access. Mitigated by no delete tools and per-call confirmation in Claude Code (`security/AGENT_SECURITY.md`) |
| Link URLs restricted to http(s) (no `javascript:`) | Done | `Link` validator, tests |

## Abuse and resource limits

| Item | Status | Evidence |
|---|---|---|
| Login rate limit, 5/min per IP | Verified | `tests/test_rate_limit.py`; on dev, 429 on the 6th attempt |
| Sign-up rate limit, 3/min per IP | Done | same |
| Error-report rate limit, 30/min per IP | Done | `tests/test_client_errors.py` |
| API Gateway stage throttle, 50 rps, burst 100 | Done | `infra/hub/apigateway.tf` |
| Caps: 1000 accounts, 500 projects per user, 500 notes per project | Done | `app/core/quotas.py`, `tests/test_quotas.py` |
| Per-IP limits shared across Lambda containers | Accepted | Per container; see `security/RATE_LIMITING.md` for the bound and the fixes |
| Rate limits key on the real client IP behind Cloudflare and CloudFront | Verified | `TRUSTED_PROXY_IPS` + `X-Forwarded-For` (`app/auth/rate_limit.py`, `tests/test_rate_limit.py`); Cloudflare's ranges set on dev and prod; two-network test passed 2026-10-04 (second network got 401, not 429) |
| Text field length limits: project name 256, pitch 2000, description 5000, next action 1000, note body 10000 characters | Verified | API 422 (`app/models/project.py`, `app/models/note.py`) and CHECK constraints (migration `0002`); `tests/test_text_limits.py`, integration and E2E tests; constraints present on prod (2026-10-04) |
| Length limits on tags, links and display name | Verified | 50 tags of up to 64 characters, 50 links (URL 2048, label 200), display name 100. API 422 (`app/models/`), CHECK constraints for the counts and the display name (migration `0003`, on dev and prod since 2026-10-03); per-element lengths are API-only |

## Infrastructure and transport

| Item | Status | Evidence |
|---|---|---|
| HTTPS only, ACM certificate, CloudFront | Verified | `infra/hub/certs.tf`, `frontend.tf`; HSTS on every response |
| Direct `execute-api` calls refused (origin verification) | Verified | `app/auth/origin_verify.py`, `tests/test_origin_verify.py`; checked on dev and prod |
| S3 bucket private, served only through CloudFront (OAC) | Done | `infra/hub/frontend.tf` |
| API docs (`/docs`, `/openapi.json`) hidden when deployed | Verified | `app/main.py`, `tests/test_startup.py`; `/api/docs` 404 on dev and prod (2026-10-04) |
| Secrets in SSM SecureStrings, read only by the Lambdas | Done | `infra/hub/database.tf`, `lambda.tf` |
| CORS limited to the local dev origins (same-origin when deployed) | Done | `tests/test_cors.py` |
| Security headers (CSP, HSTS, X-Frame-Options, nosniff, Referrer-Policy) | Verified | `aws_cloudfront_response_headers_policy.security` (`infra/hub/frontend.tf`) on the SPA and `/api/*`; strict CSP (`script-src 'self'` plus the Cloudflare Web Analytics beacon, no inline scripts). All five headers present on dev and prod, and no CSP violations in a browser (2026-10-04) |
| IaC scan (checkov and tfsec) | Done | 2026-10-03, every finding fixed or accepted with a reason: `security/IAC_SCANS.md` |

## Database

| Item | Status | Evidence |
|---|---|---|
| App connects as a least-privilege role (locally); Neon role per env | Done | `app/bootstrap_db.py`, integration test `test_local_bootstrap_migrates_as_the_least_privilege_role` |
| Schema changes are reviewed, versioned migrations | Done | Alembic, `tests/test_migrations.py`, drift test |
| Migrations run before the new API code goes live | Verified | `ci.yml` and `promote.yml`: targeted bootstrap apply, bootstrap, then full apply (`ops/DEPLOYMENT.md`); prod applied 0003 at 23:34:03 UTC before the API switched (2026-10-03) |
| No raw SQL built from user input | Done | SQLAlchemy throughout; the bootstrap's dynamic identifiers are validated and quoted |
| Unique email enforced by the database, not just the app | Done | Unique index; `test_unique_index_catches_a_duplicate_the_precheck_missed` |
| Backups / restore tested | Verified | 2026-10-04: prod restored to a point 4 minutes before migration 0003 on a test branch; schema and data matched that moment. 6-hour window on the free plan. `ops/DEPLOYMENT.md`, "Backup Testing" |

## Supply chain and secrets

| Item | Status | Evidence |
|---|---|---|
| Secret scan of full history on every PR and push, gating deploys | Done | `security/GITLEAKS_CONFIG.md` |
| Dependency audit (pip-audit, pnpm audit) | Verified | Runs in CI on every push (`dependency-scan`), over the backend, MCP server and frontend locks; clean on run 37164319484 (2026-10-04); MCP server lock clean locally with the same gate (2026-10-13); `security/DEPENDENCIES.md` |
| Container image scan (trivy) | Done | Backend, 2026-10-03: 8 HIGH in the base image fixed in the Dockerfile; patched build has no CRITICAL/HIGH/MEDIUM/LOW. Rescan 2026-10-13: 3 HIGH, 5 MEDIUM in the bundled Lambda emulator, unreachable in Lambda; the binary is now removed, 0 findings, handler verified; absence confirmed on the deployed prod image (digest `sha256:9bcd0e4c...6cec1b42`, `ls` exit 2, run by the owner, 2026-10-13), no Go binary scan of that image run; `trivy config` clean (dev stage non-root). ECR also scans on push. Local Compose frontend (nginx), 2026-10-13: 1 MEDIUM (zlib) fixed by an OS upgrade at build; no findings after, and `trivy config` clean on its Dockerfile. `security/IAC_SCANS.md` |
| GitHub Actions pinned to commit SHAs | Verified | Every `uses:` in `.github/workflows/` since 2026-10-03; CI has run green on the pins |
| Every CI check gates the dev deploy | Verified | `deploy-dev` needs `test`, `dependency-scan`, `secrets-scan`, `integration`, `e2e`; run timings show the deploy starting only after the last check |
| ECR image tags immutable | Verified | `infra/hub/ecr.tf`; `imageTagMutability: IMMUTABLE` on the prod repository; `promote.yml` skips re-copying an existing tag |
| Dependency scans in CI | Verified | `dependency-scan` job, gates the deploy on HIGH and CRITICAL; gate tested against known HIGH, MODERATE-only and unknown-severity cases (`security/DEPENDENCIES.md`) |
| PR audit | Done | `security/PR_AUDIT.md` (PR #5, ec830d6, f34d327) |
| Agent guardrail: no commits, deploys or secret access by a coding agent | Done | `agent-hooks/guard.py` (Claude Code `PreToolUse`, `.claude/settings.json`); `agent-hooks/tests/test_guard.py`; confirmed live 2026-10-13 (a `git commit --dry-run` was denied) |
| Operational diagnosis run | Done | `security/OPERATIONAL_DIAGNOSIS.md` (drill, run 37164038288) |
| Branch protection on `main` (no force-push or deletion) | Verified | Repository ruleset `protect-main` (id 24435773), active since 2026-10-04; GitHub reports `deletion` and `non_fast_forward` applying to `main`; direct pushes still allowed |
| Deploy environments limited to `main`; OIDC only for deploy jobs | Verified | `dev` and `prod` GitHub environments accept deployments from `main` only (set and read back via the GitHub API, 2026-10-13; `prod` keeps its reviewer and wait timer); `id-token: write` only on `deploy-dev` in `ci.yml` (`backend/tests/test_workflow_permissions.py`); the role trusts only jobs in those environments (`infra/bootstrap/main.tf`). `security/REMEDIATION_LOG.md` L2, L3, N4 |

## Monitoring and response

| Item | Status | Evidence |
|---|---|---|
| Traces and metrics in Grafana Cloud for dev and prod | Done | `ops/MONITORING.md` |
| Frontend errors reported | Verified | `POST /client-errors`; a report to dev returned 204 and was logged (2026-10-03) |
| Frontend errors visible in Grafana | Verified | Exported as OTLP logs; the dev report was found in Grafana Cloud Loki with its labels and trace id (2026-10-03); `ops/MONITORING.md` |
| Alerting on user impact, as code | Done | Project creation 5xx rate, dev and prod (`infra/hub/grafana.tf`); end-to-end drill pending (`security/OPERATIONAL_DIAGNOSIS.md`) |
| On-call agent's deploy scope (dev rollback only) | Done | `rollback-dev.yml`; scope checked by `backend/tests/test_workflow_permissions.py` |
| Alerts beyond project creation (all-endpoint 5xx, latency, client errors) | **Open** | Suggestions in `ops/MONITORING.md` |
| Deploy and rollback runbook | Done | `ops/DEPLOYMENT.md`, "Rolling back" (automatic for dev) |
| Key journey log carries no user data | Done | `backend/tests/test_journey_log.py` |

## Privacy

| Item | Status | Evidence |
|---|---|---|
| Data inventory and processors documented | Done | `security/DATA_POLICY.md` |
| Self-service account deletion and export | **Open** | Manual today |
| No user data sent to AI services by Hub | Done | Hub sends none; the opt-in MCP server returns a user's own data to the AI client that user connects (`security/DATA_POLICY.md`, "AI tools"; `security/AGENT_SECURITY.md`) |

## Highest-priority open items

1. Alerts beyond project creation (`ops/MONITORING.md`), and the
   end-to-end drill of the automatic on-call path on dev.
2. Self-service account deletion and data export.
3. Optionally, require the CI checks before merging into `main` (would
   mean moving to pull requests for every change).
