# Hub — System Spec

A personal platform to capture, organize, and triage project ideas, where ANY idea can graduate into a real, standalone build but there's a place for ALL of them. Central place for everything; the good ideas spin off. The platform exists to stop the scatter, not to become a thing that is endlessly polished instead of shipping actual projects.

Multi-user: anyone can self-register and track their own project ideas. Each account is isolated (users don't interact or share); every query is scoped to the authenticated user.

This document describes the system as built. Roadmap, deferred work, and known issues live in `_docs/tech-debt.md`, not here.

---

## 1. Guiding principles

- **Ship small, ship working.** No broken half-states.
- **Beautiful, sleek, minimalist.** Simple by default.
- **Layer discipline, not layer sprawl.** A clean seam between data, API, and UI, so agents or a native client can plug in later without a rewrite.
- **GTD, loosely.** Inbox capture, clarify into a project with a single next action, statuses including a "someday/parked" resting place. No rigid GTD machinery.
- **Responsive.** Works on desktop and mobile browsers alike.

---

## 2. Architecture

- **Backend:** FastAPI, in `backend/`. Serves the web app now; the same API is meant to serve a future native client and, eventually, agents. Gives OpenAPI docs for free at `/docs`.
- **Frontend:** React (Vite) SPA, in `frontend/`, responsive.
- **API layer (frontend):** all data access goes through `frontend/src/services/api/`; components never call `fetch` directly. This is the seam a future consumer (native iOS, agents) would plug into.
- **Storage:** SQLite via SQLAlchemy (`backend/app/db/`), built database-agnostic (UUIDs as strings, generic JSON for tags/links, a portable status enum, timezone-aware timestamps) so it can move to Postgres later with a config change, not a rewrite. See `backend/README.md` for the specific portability notes.
- **Auth:** roll-your-own in FastAPI, not a managed provider. Hashed passwords + JWT bearer tokens, token-based rather than cookie/session so the same API can serve a web client and a future native client identically. Identity is split into its own table (`auth_identities`) so other sign-in methods can attach later.
- **Multi-user, per-user isolation:** every project and note is scoped to its owner. The backend fetches by ID *and* owner, never by ID alone; authentication proves who you are, scoping enforces what you can access.
- **Agents:** absent. No agent layer exists yet.
- **Observability:** a frontend error boundary (`components/error-boundary.tsx`) catches render crashes and shows a fallback instead of a white screen. Nothing reports errors anywhere (frontend or backend); there is no Sentry or equivalent wired up.

---

## 3. Data model

### `users`
| field | type | notes |
|---|---|---|
| id | string (uuid) / pk | |
| email | text, unique | login identity |
| display_name | text, nullable | shown in UI |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### `auth_identities`
| field | type | notes |
|---|---|---|
| id | string (uuid) / pk | |
| user_id | fk → users | |
| provider | text | `"password"` is the only provider wired today |
| provider_subject | text | email, for the password provider |
| password_hash | text, nullable | set when provider = password; argon2 |
| created_at | timestamptz | |

> Auth is split from the profile so one user can have multiple sign-in methods over time without reshaping the `users` table.

### `projects`
| field | type | notes |
|---|---|---|
| id | string (uuid) / pk | |
| owner_id | fk → users | every query filters on this |
| name | text | |
| pitch | text | one-line, scannable, separate from description |
| description | text | the full brain-dump |
| status | enum | `Inbox`, `Exploring`, `Active`, `Parked`, `Graduated`, `Killed` |
| tags | JSON list of text | freeform |
| excitement | int 1–5 | |
| effort | int 1–5 | |
| potential | int 1–5 | |
| next_action | text | the single next concrete step (GTD core) |
| target_date | date, nullable | |
| links | JSON list of `{ label, url }` | label is optional |
| created_at | timestamptz | |
| updated_at | timestamptz | |

> Status set encodes the GTD backbone. "Killed" is a feature: dead ideas you can see and stop reconsidering. "Parked" is someday/maybe.

### `notes`
| field | type | notes |
|---|---|---|
| id | string (uuid) / pk | |
| project_id | fk → projects | ownership reached via the project |
| body | text | |
| created_at | timestamptz | timestamped log entry, not one blob |

### Attachments: not built

No `attachments` table exists, and there is no attachment UI on project detail. `openapi.yaml` still documents attachment endpoints, but the backend has no attachments router and the frontend has no corresponding type or screen. See `_docs/tech-debt.md`.

> **Isolation:** every read and write is scoped to the authenticated user, enforced at the store layer (fetch by ID and owner together).

---

## 4. Screens

1. **Login.** Email/password, against `POST /auth/login` (OAuth2 password flow).
2. **Sign up.** Open self-registration: email + password + optional display name. Email uniqueness enforced (`409` on a duplicate).
3. **Dashboard.** The logged-in user's projects. Filter by status and tag, free-text search across name/pitch/description/tags, sort by update time, opportunity (excitement + potential − effort, computed client-side), excitement, effort, name, or target date. Cards show **stale** (Active/Exploring, untouched 30+ days) and **quick-win** (Inbox/Exploring/Active, excitement ≥ 4, effort ≤ 2) badges. Loading, error, and empty states (including a distinct "no matches" state when filters exclude everything). Prominent quick-capture entry point. Responsive.
4. **Project detail.** All fields editable: status, scores, next action, tags, links; notes log (add/delete); next action shown prominently.
5. **Quick capture.** Minimal add form: name (required), one-line pitch, optional description. Fast entry point, available from the header on every authenticated screen.

**Auth gating:** the app shows a loading state while checking for a stored token, the login/signup routes when unauthenticated, and the full app (with its own routes) once authenticated. A `401` from any authenticated request logs the user out.

---

## 5. Auth (as built)

- Passwords hashed with argon2 (via passlib).
- JWT bearer tokens (via PyJWT), issued on register/login, verified on every authenticated request.
- OAuth2 password flow: `POST /auth/login` takes `application/x-www-form-urlencoded` (`username` = email, `password`), matching FastAPI's built-in OAuth2 tooling and `openapi.yaml`.
- `backend/app/core/config.py` is the single settings source (database URL, JWT secret, algorithm, token expiry), read from environment variables with dev-safe defaults so local dev needs no setup.
- Startup guard: `require_safe_jwt_secret()` runs before the app is constructed (`backend/app/main.py`). Outside a local `ENVIRONMENT`, it refuses to start if `HUB_JWT_SECRET` is unset or still the built-in dev default.
- Seed-when-empty: the database seeds one demo account (`demo@hub.dev` / `demo1234`) with a curated set of sample projects and notes the first time it's ever empty. An existing database is never re-seeded, duplicated, or overwritten on restart.

---

## 6. Testing

- **Backend:** pytest (`uv run pytest`, from `backend/`). Each test runs against its own fresh, isolated in-memory SQLite database, never the dev `hub.db` file.
- **Frontend:** Vitest + React Testing Library, jsdom environment (`pnpm test`, from `frontend/`).
- Both suites must stay green as part of calling a task done, alongside lint and build. See `AGENTS.md` for commands and the two test-authoring gotchas (manual RTL cleanup, base-ui's Dialog staying mounted while closed).

---

## Intended direction (not built)

Hub is shaped, deliberately, for a few things it doesn't do yet:

- **Native iOS app.** Talking to the same FastAPI backend is why token auth (not cookie/session) and the frontend's API-layer seam exist now, not added later.
- **Agents layer.** No agent code exists. The API seam is kept clean so an agent service could plug in later without reshaping what's already built.
- **Attachments.** Screenshots/files per project; needs an upload-mechanism decision (direct-to-storage presigned vs. proxied) before building.
- **PWA installability.** Responsive today; no manifest or service worker yet.
- **Sign in with Apple/Google.** The `auth_identities` table already supports multiple providers per user; only the password provider is wired.
- **Deploy target:** Vercel (frontend) + Neon Postgres (backend), which is also what drives the database-agnostic storage layer.
- **Incubate-then-spin-off:** a graduated project eventually getting its own subdomain and, if it gets serious, its own independent deploy.

This is high-level intent, not a build plan. Tracked detail, sequencing, and known gaps live in `_docs/tech-debt.md`.
