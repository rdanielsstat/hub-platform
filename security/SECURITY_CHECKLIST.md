# Security checklist

Pre-launch security validation: what's been checked, with evidence, and
what's still open. Update the date and the status column whenever an
item changes. Last reviewed: 2026-10-02.

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
| Logout revokes tokens server side | Accepted | Stateless JWTs, 60-minute expiry; logout clears the cookie only |
| Backend unreachable doesn't sign the user out | Done | `frontend/src/auth.tsx` retry and "can't reach" state, `ops/TROUBLESHOOTING.md` |

## Authorization and data isolation

| Item | Status | Evidence |
|---|---|---|
| Every project and note query is scoped to the owner | Done | `app/db/store.py`, `tests/test_projects.py`, `tests/test_notes.py`, integration tests |
| Another user's resource is a 404, indistinguishable from missing | Done | Same; `openapi.yaml` `NotFound` |
| Link URLs restricted to http(s) (no `javascript:`) | Done | `Link` validator, tests |

## Abuse and resource limits

| Item | Status | Evidence |
|---|---|---|
| Login rate limit, 5/min per IP | Done | `tests/test_rate_limit.py` |
| Sign-up rate limit, 3/min per IP | Done | same |
| Error-report rate limit, 30/min per IP | Done | `tests/test_client_errors.py` |
| API Gateway stage throttle, 50 rps, burst 100 | Done | `infra/hub/apigateway.tf` |
| Caps: 1000 accounts, 500 projects per user, 500 notes per project | Done | `app/core/quotas.py`, `tests/test_quotas.py` |
| Per-IP limits shared across Lambda containers | Accepted | Per container; see `security/RATE_LIMITING.md` for the bound and the fixes |
| Rate limits key on the real client IP behind Cloudflare and CloudFront | Done, **not yet enabled** | `TRUSTED_PROXY_IPS` + `X-Forwarded-For` (`app/auth/rate_limit.py`, `tests/test_rate_limit.py`). Takes effect once the GitHub environment variable `TRUSTED_PROXY_IPS` is set to Cloudflare's ranges on dev and prod (`ops/DEPLOYMENT.md`), then verify from two networks |
| Text field length limits: project name 256, pitch 2000, description 5000, next action 1000, note body 10000 characters | Done | API 422 (`app/models/project.py`, `app/models/note.py`) and Postgres CHECK constraints (migration `0002`); `tests/test_text_limits.py`, `tests/test_migrations.py`, integration tests |
| Length limits on tags, links and display name | **Open** | Not capped yet; same approach as the text fields would work |

## Infrastructure and transport

| Item | Status | Evidence |
|---|---|---|
| HTTPS only, ACM certificate, CloudFront | Done | `infra/hub/certs.tf`, `frontend.tf` |
| Direct `execute-api` calls refused (origin verification) | Verified | `app/auth/origin_verify.py`, `tests/test_origin_verify.py`; checked on dev and prod |
| S3 bucket private, served only through CloudFront (OAC) | Done | `infra/hub/frontend.tf` |
| API docs (`/docs`, `/openapi.json`) hidden when deployed | Done | `app/main.py`, `tests/test_startup.py` |
| Secrets in SSM SecureStrings, read only by the Lambdas | Done | `infra/hub/database.tf`, `lambda.tf` |
| CORS limited to the local dev origins (same-origin when deployed) | Done | `tests/test_cors.py` |
| Security headers on the SPA (CSP, HSTS, X-Frame-Options) | **Open** | Not checked in this review. A CloudFront response headers policy would add them. |
| IaC scan (checkov or tfsec) | **Open** | Not run; `security/DEPENDENCIES.md` |

## Database

| Item | Status | Evidence |
|---|---|---|
| App connects as a least-privilege role (locally); Neon role per env | Done | `app/bootstrap_db.py`, integration test `test_local_bootstrap_migrates_as_the_least_privilege_role` |
| Schema changes are reviewed, versioned migrations | Done | Alembic, `tests/test_migrations.py`, drift test |
| Migrations run before the new API code goes live | Done | `ci.yml` and `promote.yml`: targeted bootstrap apply, bootstrap, then full apply (`ops/DEPLOYMENT.md`) |
| No raw SQL built from user input | Done | SQLAlchemy throughout; the bootstrap's dynamic identifiers are validated and quoted |
| Unique email enforced by the database, not just the app | Done | Unique index; `test_unique_index_catches_a_duplicate_the_precheck_missed` |
| Backups / restore tested | **Open** | Relies on Neon's point-in-time restore; never exercised |

## Supply chain and secrets

| Item | Status | Evidence |
|---|---|---|
| Secret scan of full history on every PR and push, gating deploys | Done | `security/GITLEAKS_CONFIG.md` |
| Dependency audit (pip-audit, pnpm audit) | Done | Clean on 2026-10-02, `security/DEPENDENCIES.md` |
| Container image scan (trivy) | **Open** | `security/DEPENDENCIES.md` |
| Third-party GitHub Actions pinned to commit SHAs | **Open** | Pinned to tags today |
| Dependency scans in CI | **Open** | Run by hand only |

## Monitoring and response

| Item | Status | Evidence |
|---|---|---|
| Traces and metrics in Grafana Cloud for dev and prod | Done | `ops/MONITORING.md` |
| Frontend errors reported | Done | `POST /client-errors`, logged to CloudWatch |
| Frontend errors visible in Grafana | **Open** | Manual setup; `ops/MONITORING.md`, "Frontend errors to Grafana" |
| Alerting beyond the registration error rate | **Open** | Suggestions in `ops/MONITORING.md` |
| Deploy and rollback runbook | Done | `ops/DEPLOYMENT.md` |

## Privacy

| Item | Status | Evidence |
|---|---|---|
| Data inventory and processors documented | Done | `security/DATA_POLICY.md` |
| Self-service account deletion and export | **Open** | Manual today |
| No user data sent to AI services | Done | `security/DATA_POLICY.md`, `security/AGENT_SECURITY.md` |

## Highest-priority open items

1. Set `TRUSTED_PROXY_IPS` to Cloudflare's ranges on the dev and prod
   GitHub environments, deploy, and check the login limit from two
   networks (`ops/DEPLOYMENT.md`).
2. Security headers on the CloudFront distribution.
3. Run trivy on the image and checkov or tfsec on `infra/`.
4. Pin third-party GitHub Actions to SHAs.
5. Length caps on tags, links and display name.
