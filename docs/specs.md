# Hub

Hub is a personal platform for capturing, organizing, and triaging project ideas, from small sparks to standalone builds. Each project has a status that reflects where it stands, from an initial inbox capture through active work to a parked, graduated, or killed end state.

Hub is multi-user. Anyone can register an account. Each account's projects and notes are isolated from every other account.

## Architecture

- Backend: a FastAPI application in `backend/`.
- Frontend: a React (Vite) single-page application in `frontend/`, responsive on desktop and mobile.
- All frontend data access goes through `frontend/src/services/api/`; components do not call `fetch` directly.
- Storage: SQLite via SQLAlchemy. Column types are chosen to be portable across databases: string UUIDs, JSON for tags and links, a portable status enum, and timezone-aware timestamps.
- Authentication is token-based: hashed passwords and JWT bearer tokens, not cookie or session based.
- Every project and note is scoped to its owning user. The backend looks up records by ID and owner together, never by ID alone.
- A frontend error boundary catches render errors and displays a fallback instead of a blank or crashed page.

## Data model

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
| provider | text | `"password"` |
| provider_subject | text | email, for the password provider |
| password_hash | text, nullable | argon2 hash, set for the password provider |
| created_at | timestamptz | |

### `projects`
| field | type | notes |
|---|---|---|
| id | string (uuid) / pk | |
| owner_id | fk → users | every query filters on this |
| name | text | |
| pitch | text | one-line summary, separate from description |
| description | text | free-form detail |
| status | enum | `Inbox`, `Exploring`, `Active`, `Parked`, `Graduated`, `Killed` |
| tags | JSON list of text | |
| excitement | int 1-5 | |
| effort | int 1-5 | |
| potential | int 1-5 | |
| next_action | text | the single next concrete step |
| target_date | date, nullable | |
| links | JSON list of `{ label, url }` | label is optional |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### `notes`
| field | type | notes |
|---|---|---|
| id | string (uuid) / pk | |
| project_id | fk → projects | |
| body | text | |
| created_at | timestamptz | |

Every read and write is scoped to the authenticated user, enforced by fetching records by ID and owner together.

## Screens

1. **Login.** Email and password, against `POST /auth/login` (OAuth2 password flow).
2. **Sign up.** Self-registration: email, password, and optional display name. Email uniqueness is enforced (`409` on a duplicate).
3. **Dashboard.** The logged-in user's projects. Filter by status and tag, free-text search across name, pitch, description, and tags, and sort by update time, opportunity (excitement plus potential minus effort), excitement, effort, name, or target date. Cards show a **stale** badge (status Active or Exploring, untouched 30 or more days) and a **quick-win** badge (status Inbox, Exploring, or Active, with excitement 4 or higher and effort 2 or lower). The dashboard has loading, error, empty, and no-matches states, and a quick-capture entry point.
4. **Project detail.** Every field is editable: status, scores, next action, tags, links, and target date. Includes a notes log with add and delete. The next action is shown prominently.
5. **Quick capture.** A minimal add form: name (required), one-line pitch, and optional description. Reachable from the header on every authenticated screen.

The app shows a loading state while checking for a stored token, the login and signup routes when unauthenticated, and the full application once authenticated. A `401` response to any authenticated request logs the user out.

## Auth

- Passwords are hashed with argon2.
- JWT bearer tokens are issued on register and login, and verified on every authenticated request.
- Login uses the OAuth2 password flow: `POST /auth/login` takes `application/x-www-form-urlencoded` with `username` (the email) and `password`.
- `backend/app/core/config.py` is the settings source: database URL, JWT secret, algorithm, and token expiry, read from environment variables with local-dev defaults.
- At startup, outside a local `ENVIRONMENT`, the app refuses to start if `HUB_JWT_SECRET` is unset or still the built-in dev default.
- The database seeds one demo account with a set of sample projects and notes the first time it is empty. An existing database is never re-seeded.

## Testing

- Backend: pytest.
- Frontend: Vitest with React Testing Library.
