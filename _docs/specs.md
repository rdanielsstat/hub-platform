# Project Incubator — v1 Build Spec

A personal platform to capture, organize, and triage project ideas, where ANY idea can graduate into a real, standalone build but there's a place for ALL of them. Central place for everything; the good ideas spin off. The platform exists to stop the scatter — not to become a thing that is endlessly polished instead of shipping actual projects. **Keep v1 manageable.**

Multi-user: anyone can self-register and track their own project ideas. Each account is isolated (users don't interact or share); every query is scoped to the authenticated user.

---

## 1. Guiding principles

- **Ship small, ship working.** Every milestone is a usable app, never a broken half-state.
- **Beautiful, sleek, minimalist.** Simple by default.
- **Layer discipline, not layer sprawl.** Clean seam between data, API, and UI so agents/mobile can plug in later without a rewrite. Do not build those layers now.
- **GTD, loosely.** Inbox capture → clarify into a project with a single next action → statuses including a "someday/parked" resting place. No rigid GTD machinery.
- **Mobile and desktop from day one.** Responsive web, installable as a PWA. Native iOS deferred but the API must be ready for it.
- **Cost-guarded AWS.** Serverless / scale-to-zero only; no always-on resources; budget alarm before anything deploys.

---

## 2. Architecture (layers)

- **Data layer:** Postgres. Tables: `users`, `auth_identities`, `projects`, `notes`, `attachments`.
- **API layer:** FastAPI. The clean seam. Serves web now, native iOS later, agents eventually. Gives OpenAPI docs for free at `/docs` (useful later for generating the iOS client).
- **App layer:** React (Vite) SPA, responsive, installable as a PWA.
- **Auth:** roll your own in FastAPI — hashed passwords (bcrypt/argon2) + token-based auth (JWT bearer). Token-based, not cookie/session, so the same API serves the web app and the future iOS app identically. Identity is split into its own table so additional sign-in methods (Sign in with Apple/Google) can attach later. See stack note.
- **Agent layer:** ABSENT in v1. Leave the API seam clean so it slots in later as its own service. (This is the pay-per-token API-cost path — add only when the value justifies it.)
- **Observability:** cross-cutting. v1 = error tracking (Sentry free tier) + platform dashboards. Grows into the future "agentic dashboard" when agents exist.

---

## 3. Data model

### \`users\`
| field | type | notes |
|---|---|---|
| id | uuid / pk | |
| email | text, unique | login identity |
| display_name | text, nullable | shown in UI |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### \`auth_identities\`
| field | type | notes |
|---|---|---|
| id | uuid / pk | |
| user_id | fk → users | |
| provider | enum | `password` now; `apple`, `google` later |
| provider_subject | text | email for password; provider's stable subject id later |
| password_hash | text, nullable | set only when provider = password (bcrypt/argon2) |
| created_at | timestamptz | |

> Auth is split from the profile so one user can have multiple sign-in methods over time (password now, Sign in with Apple for the iOS app later) without reshaping the users table.

### \`projects\`
| field | type | notes |
|---|---|---|
| id | uuid / pk | |
| user_id | fk → users | owner; every query filters on this |
| name | text | |
| pitch | text | one-line, scannable — separate from description |
| description | text | the full brain-dump |
| status | enum | Inbox, Exploring, Active, Parked, Graduated, Killed |
| tags | text[] | interests: stats, healthcare, chess, dogs, spanish, etc. |
| excitement | int 1–5 | |
| effort | int 1–5 | |
| potential | int 1–5 | |
| next_action | text | the single next concrete step (GTD core) |
| target_date | date, nullable | milestone/target |
| links | jsonb / text[] | repo, live demo, references |
| created_at | timestamptz | |
| updated_at | timestamptz | |

> Status set encodes the GTD backbone. "Killed" is a feature — dead ideas you can
> see and stop reconsidering. "Parked" = someday/maybe.

### \`notes\`
| field | type | notes |
|---|---|---|
| id | uuid / pk | |
| project_id | fk → projects | ownership reached via the project |
| body | text | |
| created_at | timestamptz | timestamped log entry, not one blob |

### \`attachments\`
| field | type | notes |
|---|---|---|
| id | uuid / pk | |
| project_id | fk → projects | ownership reached via the project |
| file_path | text | storage key/URL |
| caption | text | |
| created_at | timestamptz | |

**Domain stays at three tables (projects, notes, attachments); `users` + `auth_identities` are the auth backbone. Resist further domain tables in v1.**

> **Isolation:** every read and write is scoped to the authenticated user. The backend fetches by ID *and* owner, never by ID alone — authentication proves who you are, scoping enforces what you can access.

---

## 4. Screens

1. **Login.** Email/password.
2. **Sign up.** Open self-registration: email + password + optional display name. Email uniqueness enforced.
3. **Dashboard / operations view.** The logged-in user's projects; filter by status + tag; sort by scores and dates; surface what's active, what's gone stale (longest untouched), high-excitement/low-effort picks, upcoming dates. Prominent quick-capture. Responsive — genuinely usable on a phone. This is the GTD weekly-review surface.
4. **Project detail.** All fields editable; status changes; scores; notes log; attachments; links; **next action shown at top.**
5. **Quick capture.** Minimal add (name + pitch, optional description). The GTD inbox front door. Fast on mobile.

---

## 5. Stack

- **Frontend:** React (Vite), responsive, PWA-installable. Lives in `frontend/`. Scaffolded in v0 or Lovable first for design, then exported to a GitHub repo to build out. Host on **Vercel free tier** (keeps AWS learning surface small; every git branch gets a preview URL = free dev/prod).
- **Backend:** FastAPI in `backend/`, on **AWS Lambda** (via Mangum adapter) behind a Lambda Function URL or API Gateway. Serverless = near-zero at this scale.
- **Database:** **Neon** (or Supabase) serverless Postgres — real free tier, scales to zero. Avoids the always-on RDS cost trap while learning AWS.
- **Auth:** roll your own in FastAPI — passlib (bcrypt/argon2) for hashing, JWT bearer tokens, OAuth2 password flow. Token-based so the same API serves web and the future iOS app. `auth_identities` keeps the door open for "Sign in with Apple/Google" later. (Managed providers like Clerk/Supabase Auth remain a fallback if roll-your-own becomes a burden.)
- **File storage:** S3 (screenshots/attachments), or the storage bundled with Supabase if used.
- **IaC:** Terraform or AWS SAM/CDK — define it once so future spinoffs are reproducible/stampable.
- **Observability:** Sentry (React + FastAPI) from day one; platform dashboards otherwise.

---

## 6. Environments (dev / prod)

- Two environments, each with its **own separate database** (never mix dev and prod data).
- Vercel gives per-branch preview URLs automatically; \`main\` → production, attached to a custom domain (\`app.yourname.com\` for prod, \`dev.yourname.com\` for staging).
- Domain bought from Cloudflare (\`dnls.dev\`).
- **Per-spinoff pattern (later):** each graduated project can start as a subdomain under the parent (\`stocks.yourname.com\`, \`dev-stocks.yourname.com\`) and get promoted to its own independent deploy if it becomes serious. Infra mirrors the incubate-then-spin-off concept.

---

## 7. Cost guardrails (do these first)

- **Set an AWS Budgets alert at ~\$5 and ~\$15 the moment the account is created, before deploying anything.**
- Serverless / scale-to-zero only. **No always-on RDS, load balancers, or NAT gateways.**
- Keep Postgres on a free-tier serverless provider (Neon/Supabase), not RDS, while learning.
- Use IaC so you can tear everything down cleanly and nothing lingers billingwise.

---

## 8. Milestone sequence

Each step ships a usable thing. Build one per session; commit after each.

1. **Foundation.** Postgres (Neon), roll-your-own auth, FastAPI wired up, tables with user ownership, signup + login working end to end.
2. **Dashboard read/create.** Responsive React app: list projects + quick-capture, scoped to the logged-in user. **Dump every idea from the brainstorm in here.** First real win.
3. **Project detail + edit.** Full editing: status, scores, next action, links.
4. **Notes log.** Add/view timestamped notes per project.
5. **Attachments.** Upload + view screenshots/files (S3 or Supabase storage).
6. **PWA polish.** Installable on phone; responsive pass; offline-friendly capture if easy.

Steps 1–2 = working, hosted, logged-in tool reachable from any browser. Everything after is additive.

---

## 9. Deferred (captured, not built)

- Embedded / autonomous agents (pay-per-token API cost path).
- Agentic dashboard (really the observability surface for agent runs — Langfuse etc.).
- Multi-agent projects.
- Native iOS app (talks to the same FastAPI — that's why the API seam, token auth, and multi-user matter now).
- Sign in with Apple/Google (schema is ready via `auth_identities`; not wired in v1).
- Deeper "app + Claude Code share a filesystem" project-folder idea.
- Apple Notes import (no clean public API; bulk export/paste when it comes).
- Migrate to AWS Cloud Run / heavier AWS services as a *graduated project* in its own right.

---

## 10. Build / usage notes

- Whatever tool builds it (v0, Lovable, Claude Code, by hand): v1 is standard CRUD + auth wiring. If a tool lets you choose a model, a mid-tier one is plenty here — no need for a top-tier reasoning model for this scope.
- Hand the building tool this doc up front each session so it isn't rediscovering context.
- One milestone per session; commit after each.
- If building via Claude Code on a Pro plan: don't set \`ANTHROPIC_API_KEY\` in your environment — that would bill you per-token API charges instead of using your Pro plan, and prefer Sonnet over Opus (Opus burns quota faster).

---

## 11. Seed projects (populate the dashboard on first run)

From the brainstorm — drop these in as \`Inbox\`/\`Parked\` with tags so the dashboard isn't empty:

- **This incubator** (status: Active) — the platform itself.
- **Stock analytics/TA platform** — tags: stats, stocks. High effort.
- **CMS hospital quality benchmarking** — tags: healthcare, stats. Strong expertise moat.
- **Personal health-data analytics hub** — tags: healthcare, stats, fitness.
- **Hiking/outdoor analytics** — tags: outdoors, fitness, california.
- **Chess improvement analytics** — tags: chess, stats.
- **German Shepherd health/activity tracker** — tags: dogs.
- **Job-search + application tracker** — tags: career.
- **Spanish learning helper** — tags: spanish, learning.
- **Consulting client site/portal** — tags: consulting, healthcare.
