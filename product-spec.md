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

**Validation.** The UI requires a non-blank project name and note before it will save. The API does not enforce this: it accepts empty or whitespace-only project names and notes. This is a known mismatch with "name (required)" above. The API validates the password (8 to 256 characters), email format, scores (1 to 5), status values, link URLs (http or https), and every length and count limit in the tables above (`422` when exceeded); the database enforces the same limits with CHECK constraints, except per-tag and per-link lengths.

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
