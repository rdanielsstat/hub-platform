# Data policy

What data Hub collects, why, where it goes, and how long it stays. Also
covers what AI tools see. Kept in step with the code: if a change adds a
field, a log line with user data, or a third party, update this file in
the same change.

Hub is a personal idea tracker run as a portfolio project. There's no
advertising, no analytics SDK in the app, no tracking cookies, and no
data is sold or shared beyond the processors listed below. The one form
of analytics is Cloudflare Web Analytics (below), which Cloudflare's
proxy adds to the pages itself.

## What's stored (Neon Postgres)

| Data | Table | Why | Notes |
|---|---|---|---|
| Email address | `users`, `auth_identities` | Sign-in identifier | Stored lowercased |
| Display name (optional) | `users` | Shown in the header | |
| Password hash | `auth_identities` | Sign-in | argon2id; the password itself is never stored or logged |
| Projects: name, pitch, description, status, tags, scores, next action, target date, links | `projects` | The product | Whatever the user types |
| Notes | `notes` | The product | Whatever the user types |
| Created and updated timestamps | all tables | Sorting, display | |

Nothing else about the user is stored: no IP addresses, no device data,
no location.

## What's processed but not stored

- **Client IP address**: used in memory for the per-IP rate limits
  (`backend/app/auth/rate_limit.py`), kept at most a minute per address,
  in the Lambda container's memory only, never written anywhere.
- **Session token**: a signed JWT holding only the user id and expiry,
  in an httpOnly cookie (or a bearer header for API clients). Not stored
  server side.

## Logs and telemetry

| Where | What user-related data | Retention |
|---|---|---|
| CloudWatch Logs (API Lambda) | Frontend error reports: user id (when signed in), browser user agent, page path (no query string), error message and stack trace. Origin-verification rejections: the source IP of the rejected request (a caller that bypassed CloudFront, not a site user). Project creations: outcome, status code, duration, trace and span ids only (no body, email, token or user id; `backend/tests/test_journey_log.py`). Unhandled exception tracebacks. | 14 days |
| CloudWatch Logs (bootstrap Lambda) | The demo account's email when it's seeded; no user data otherwise | 14 days |
| Grafana Cloud (logs) | The same frontend error reports, database-outage lines and origin-verification rejections as CloudWatch (user id, user agent, page path, error message and stack; source IP of a rejected direct call), exported from the `app.client_errors`, `app.db` and `app.security` loggers, plus the project creation lines (outcome, status, duration, trace and span ids) from `app.projects`. Nothing else is exported as logs. | Per the Grafana Cloud stack's plan |
| Grafana Cloud (traces, metrics) | Traces: request method, route, status, timing, SQL statements as parameterized text (bound values aren't recorded), and whatever HTTP attributes the OpenTelemetry FastAPI instrumentation adds (which can include the client address and user agent). Metrics: counts and latencies only, labeled with route, status code and environment, no user data; latency points can carry a trace id as an exemplar. | Per the Grafana Cloud stack's plan |
| API Gateway, CloudFront, Cloudflare | Standard request handling. API Gateway access logging is off. | Per each provider |

Error messages and stacks from the browser can contain fragments of
what's on screen (for example a project name in an exception message).
They're kept 14 days and only the account owner and maintainers can see
CloudWatch.

## Processors (third parties that handle user data)

| Provider | Role | Data |
|---|---|---|
| AWS (us-east-1) | Hosting: Lambda, API Gateway, CloudFront, S3, SSM, CloudWatch | All of the above in transit; logs at rest |
| Neon | Postgres database | Everything in "What's stored" |
| Cloudflare | DNS, and proxy for the site hostname (`proxied = true`) | All requests in transit (Cloudflare terminates TLS) |
| Cloudflare Web Analytics | Page-view and performance analytics, injected into pages by Cloudflare's proxy (found 2026-10-03) | Cookieless: page URL, referrer, browser and device type, country, page timing. No account data. Allowed by the CSP (`infra/hub/frontend.tf`); to stop it, turn off Web Analytics for the hostname in Cloudflare and remove the two CSP entries |
| Grafana Cloud | Traces and metrics | As in the table above |
| GitHub | Code, CI, the on-call agent's tracking issues | No user data. Grafana's alert reaches GitHub (`repository_dispatch`) carrying only the rule name, labels, summary and counts, and the issues hold the alert summary and the diagnosis |

## Retention and deletion

- Account data stays until the account is deleted. **There's no
  self-service account deletion yet.** A deletion request is handled by
  hand by a maintainer: deleting the `users` row cascades to the user's
  identities, projects and notes (foreign keys with `ON DELETE CASCADE`).
- Deleting a project deletes its notes (cascade).
- Logs age out after 14 days. Neon keeps its own point-in-time-restore
  history for the plan's restore window, so deleted rows survive there
  until it expires.

Gaps worth closing: self-service account deletion and data export.

## Privacy law (GDPR and similar)

This hasn't had a formal GDPR assessment, and it isn't claimed to be
compliant. Where it stands against the main principles:

- **Data minimisation**: only email, an optional display name, a password
  hash and what users type into projects and notes. No tracking cookies,
  no ad or behavioural analytics; Cloudflare Web Analytics is cookieless.
- **Purpose and retention**: stored data is used only to run the app.
  Logs are kept 14 days in CloudWatch; Grafana Cloud per its plan; Neon
  restore history 6 hours.
- **Processors**: listed above (AWS, Neon, Cloudflare, Grafana Cloud).
  No data processing agreements are recorded here.
- **Data subject rights**: access, export and deletion are possible, but
  only by request, handled by a maintainer by hand (deleting the user row
  cascades to everything they own). No self-service yet.
- **Security of processing**: `security/SECURITY_CHECKLIST.md`.
- **Not in place**: a user-facing privacy notice in the app, a contact
  for data requests, records of processing, breach-notification
  procedure.

For a deployment with real users beyond reviewers, those gaps (above all
the privacy notice and self-service deletion and export) come first.

## Caps on what's stored

Usage caps bound how much one account can store: 500 projects per user,
500 notes per project, 1000 accounts per deployment
(`security/RATE_LIMITING.md`).

## AI tools

- **Coding agents** (Claude Code and others) work on the code in a
  developer checkout. They never have production database credentials,
  production logs, or real `.env` files (`AGENTS.md`), so no user data
  reaches them. Local development uses the seeded demo data or test
  accounts.
- **On-call agent** (`backend/oncall/diagnose.py`): sends OpenAI the
  alert's summary (from the rule's annotation on the automatic path, or
  the text a human pastes into the manual one), plus a fixed description
  of the stack. Never logs, traces, database content or user data. Don't
  paste user data into a manual alert summary.
- **Hub MCP server** (`mcp-server/`): when a user connects an AI client
  (Claude Code, Claude Desktop) to it, the tools return that user's own
  projects and notes, which become part of the agent's context and so go
  to the model provider behind the client they chose. It only ever
  covers the account the user configured it with, nothing runs unless
  they connect a client, and Hub itself sends nothing anywhere: the
  user's AI provider is their choice and under their own terms, not a
  Hub processor. Use the demo account to try it without real data.
- **Otherwise, no AI processing of user content.** Hub never sends
  projects or notes to an AI service on its own, and the on-call
  diagnostic sees only alert text.

See `security/AGENT_SECURITY.md` for how the agents themselves are
contained.
