# Hub

Hub is a personal platform for capturing, organizing, and triaging project ideas, from small sparks to standalone builds. Each project has a status that reflects where it stands, from an initial inbox capture through active work to a parked, graduated, or killed end state.

Hub is multi-user. Anyone can register an account. Each account's projects and notes are isolated from every other account.

## Architecture

- Backend: a FastAPI application in `backend/`.
- Frontend: a React (Vite) single-page application in `frontend/`, responsive on desktop and mobile.
- All frontend data access goes through `frontend/src/services/api/`; components do not call `fetch` directly.
- Storage: SQLAlchemy, database-agnostic. SQLite locally and in tests, Postgres 17 in Docker Compose, and Neon Postgres when deployed (dev and production are both live). Column types are chosen to be portable across databases: string UUIDs, JSON for tags and links, a portable status enum, and timezone-aware timestamps. The schema is managed with Alembic migrations, applied on every deploy before the new code goes live.
- Authentication is token-based: hashed passwords and JWTs. The web app holds its JWT in an httpOnly, SameSite=Strict cookie (JavaScript never sees it); API clients send the same JWT as a bearer header. There is no server-side session store.
- Every project and note is scoped to its owning user. The backend looks up records by ID and owner together, never by ID alone.
- A frontend error boundary catches render errors and displays a fallback instead of a blank or crashed page. Render crashes, uncaught errors and failed API calls are reported to the backend (`POST /client-errors`), which logs them for monitoring.

## Data model

### `users`
| field | type | notes |
|---|---|---|
| id | string (uuid) / pk | |
| email | text, unique | login identity |
| display_name | text, nullable | shown in UI; up to 100 characters |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### `auth_identities`
| field | type | notes |
|---|---|---|
| id | string (uuid) / pk | |
| user_id | fk → users | |
| provider | text | `"password"` |
| provider_subject | text | email, for the password provider |
| password_hash | text, nullable | argon2 hash, set for the password provider |
| created_at | timestamptz | |

### `projects`
| field | type | notes |
|---|---|---|
| id | string (uuid) / pk | |
| owner_id | fk → users | every query filters on this |
| name | text | up to 256 characters |
| pitch | text | one-line summary, separate from description; up to 2000 characters |
| description | text | free-form detail; up to 5000 characters |
| status | enum | `Inbox`, `Exploring`, `Active`, `Parked`, `Graduated`, `Killed` |
| tags | JSON list of text | up to 50, each up to 64 characters |
| excitement | int 1-5 | |
| effort | int 1-5 | |
| potential | int 1-5 | |
| next_action | text | the single next concrete step; up to 1000 characters |
| target_date | date, nullable | |
| links | JSON list of `{ label, url }` | up to 50; label is optional (up to 200 characters); url http(s), up to 2048 characters |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### `notes`
| field | type | notes |
|---|---|---|
| id | string (uuid) / pk | |
| project_id | fk → projects | |
| body | text | up to 10000 characters |
| created_at | timestamptz | |

Every read and write is scoped to the authenticated user, enforced by fetching records by ID and owner together.

## Screens

1. **Login.** Email and password, against `POST /auth/login` (OAuth2 password flow).
2. **Sign up.** Self-registration: email, password, and optional display name. Email uniqueness is enforced (`409` on a duplicate).
3. **Dashboard.** The logged-in user's projects. Filter by status and tag, free-text search across name, pitch, description, and tags, and sort by update time, opportunity (excitement plus potential minus effort), excitement, effort, name, or target date. Cards show a **stale** badge (status Active or Exploring, untouched 30 or more days) and a **quick-win** badge (status Inbox, Exploring, or Active, with excitement 4 or higher and effort 2 or lower). The dashboard has loading, error, empty, and no-matches states, and a quick-capture entry point.
4. **Project detail.** Every field is editable: status, scores, next action, tags, links, and target date. Includes a notes log with add and delete. The next action is shown prominently.
5. **Quick capture.** A minimal add form: name (required) and one-line pitch, with optional details behind "More details": description, status, tags, next action, and excitement, potential, and effort scores. Reachable from the header on every authenticated screen.

**Validation.** A project name and a note body must contain at least one non-whitespace character. The UI won't save a blank one, and the API answers `422` to an empty or whitespace-only name (on create and update) or note body; text that isn't blank is stored exactly as sent, untrimmed. The API also validates the password (8 to 256 characters), email format, scores (1 to 5), status values, link URLs (http or https), and every length and count limit in the tables above (`422` when exceeded); the database enforces the same limits with CHECK constraints, except per-tag and per-link lengths.

**Caps.** Each user can have up to 500 projects and each project up to 500 notes; a deployment allows up to 1000 accounts. Over a cap the API answers `403`.

The app shows a loading state while it asks the backend whether the session cookie is valid (`GET /auth/me`), the login and signup routes when unauthenticated, and the full application once authenticated. Only a `401` means signed out: a `401` on any authenticated request logs the user out, while a failed session check for any other reason (backend or database unreachable) is retried once and then shows a "Can't reach the server" screen with a retry button, never the login page.

## Auth

- Passwords are hashed with argon2.
- JWTs are issued on register and login (in the response body and as the `hub_token` cookie) and verified on every authenticated request. Deployed, login is limited to 5 attempts and sign-up to 3 per minute per client IP, and login passwords over 256 characters are rejected before hashing.
- Login uses the OAuth2 password flow: `POST /auth/login` takes `application/x-www-form-urlencoded` with `username` (the email) and `password`.
- `backend/app/core/config.py` is the settings source: database URL, JWT secret, algorithm, and token expiry, read from environment variables with local-dev defaults.
- At startup, outside a local `ENVIRONMENT` or whenever `USE_SSM` is on, the app refuses to start if the JWT secret is unset or still the built-in dev default.
- One demo account with sample projects and notes can be seeded into a database that has no users yet. Locally, `init_local` seeds it when run with `SEED_DEMO_DATA=true`. When deployed, the bootstrap seeds it when the environment sets `DEMO_PASSWORD_PARAM_NAME`. An existing database is never re-seeded.

## Testing

- Backend: pytest.
- Frontend: Vitest with React Testing Library.
- Backend integration tests against real Postgres 17 (Docker Compose).
- Playwright E2E: a comprehensive suite in `frontend/tests/` covering all workflows in the browser and every API endpoint, run against a real backend (local, or the Docker Compose stack with Postgres), including backend and database outages.
- CI runs all of them, plus dependency and secret scans, on every push; all must pass before a deploy.

## Acceptance criteria for shipped features (written 2026-10-18)

Written on 2026-10-18 from the current behavior and the tests that check
it, so a reviewer can trace each feature to a check. These are a record
written after the work, not criteria the agents wrote before it. Features
built issue first have their original criteria on the issue itself
([#12](https://github.com/rdanielsstat/hub-platform/issues/12),
[#13](https://github.com/rdanielsstat/hub-platform/issues/13)); six earlier
features were backfilled as closed issues on 2026-10-17
([#6](https://github.com/rdanielsstat/hub-platform/issues/6) to
[#11](https://github.com/rdanielsstat/hub-platform/issues/11)). The core
screens were built before the tracker and pushed to `main`, so they have
no issue or PR; the Playwright suite (`frontend/tests/`) is their check.

| Feature | Accepted when | Issue or PR | Checked by |
|---|---|---|---|
| Sign up | A new email and a valid password create an account and sign in; a duplicate email is `409`; an invalid email or a password outside 8 to 256 characters is `422` | none (pre-tracker) | `frontend/tests/api.spec.ts`, `frontend/tests/app.spec.ts`, `backend/tests/test_auth.py` |
| Log in and session | The OAuth2 password form sets the `hub_token` httpOnly cookie; only a `401` signs the user out; an unreachable backend shows "Can't reach the server" | none (pre-tracker) | `frontend/tests/app.spec.ts`, `frontend/src/auth.test.tsx` |
| Dashboard | Shows only the user's projects; filters by status and tag, searches, sorts; has loading, error, empty and no-matches states; stale and quick-win badges follow the rules in "Screens" | none (pre-tracker) | `frontend/tests/app.spec.ts`, `frontend/src/pages/dashboard.test.tsx` |
| Project count on the dashboard | `N projects` with no filter, `Showing N of M projects` with one, hidden while loading, on error and with no projects, announced with `aria-live="polite"` | [#13](https://github.com/rdanielsstat/hub-platform/issues/13), [PR #19](https://github.com/rdanielsstat/hub-platform/pull/19) | `frontend/src/pages/dashboard.test.tsx`, `frontend/tests/app.spec.ts` |
| Project detail and notes | Every field is editable; notes can be added and deleted; another user's project is `404` | none (pre-tracker) | `frontend/tests/app.spec.ts`, `backend/tests/test_projects.py`, `backend/tests/test_notes.py` |
| Quick capture | Name required, pitch optional, more details behind "More details"; the new card appears without a reload | none (pre-tracker) | `frontend/tests/app.spec.ts`, `frontend/src/components/quick-capture-dialog.test.tsx` |
| Blank names and notes refused | An empty or whitespace-only project name or note body is `422`; real text is stored as sent | [#12](https://github.com/rdanielsstat/hub-platform/issues/12), [PR #18](https://github.com/rdanielsstat/hub-platform/pull/18) | `backend/tests/test_blank_text.py`, `frontend/tests/api.spec.ts` |
| Limits and caps | Every length and count limit is `422` when exceeded; over a cap is `403` | none (pre-tracker) | `backend/tests/test_text_limits.py`, `backend/tests/test_quotas.py` |
| Project creation journey log | One `project_create` JSON line per `POST /projects` with outcome, status, duration and `trace_id`, matching the trace and the latency exemplar, with no email, credentials or body | [PR #14](https://github.com/rdanielsstat/hub-platform/pull/14) | `backend/tests/test_journey_log.py` |
| On-call agent and dev rollback | A firing dev alert starts the handler with no human, opens the issue, rolls dev back to an image from a different commit, proves `POST /projects` works and records the outcome; prod is diagnosed only | [#6](https://github.com/rdanielsstat/hub-platform/issues/6), PRs [#17](https://github.com/rdanielsstat/hub-platform/pull/17), [#26](https://github.com/rdanielsstat/hub-platform/pull/26), [#28](https://github.com/rdanielsstat/hub-platform/pull/28) | `backend/tests/test_oncall*.py`, `backend/tests/test_workflow_permissions.py`, the 2026-10-17 drill (`security/OPERATIONAL_DIAGNOSIS.md`) |
