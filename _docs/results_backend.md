# Backend Results

## 1 - openapi.yaml contract

Wrote `openapi.yaml` (687 lines) at the repo root, derived from the frontend's API client and the spec's data model. Parses cleanly. No backend code written.

### Endpoints defined

**Auth** (spec-derived; frontend doesn't call these yet, see mismatches)
- `POST /auth/register` — email + password + optional displayName → token
- `POST /auth/login` — OAuth2 password grant (form-urlencoded, username=email) → token
- `GET /auth/me` — current user

**Projects** (from store.tsx's 5 calls)
- `GET /projects` → Project[], no query params
- `POST /projects` → Project
- `GET /projects/{projectId}` → Project
- `PATCH /projects/{projectId}` → Project
- `DELETE /projects/{projectId}` → 204

**Notes** (from store.tsx + notes-panel.tsx)
- `GET /projects/{projectId}/notes` → Note[], newest first
- `POST /projects/{projectId}/notes` → { note, project } (matches mock.ts's addNote exactly — returns both since adding a note bumps the parent project's updatedAt)
- `DELETE /notes/{noteId}` → returns the parent project, not the note (matches deleteNote(id): Promise<Project> in mock.ts)

**Attachments** — marked provisional throughout, see mismatches.

All project/note/attachment endpoints require bearerAuth; 404 is used uniformly for "not found or not yours," so the API never reveals another user's data exists.

### Mismatches to resolve before writing backend code

1. **Auth has zero frontend integration today.** No login/signup screens, no token storage, no Authorization header anywhere in frontend/src/. The auth endpoints are derived from the spec alone, not from any actual caller. Decide: wire the backend's auth before or alongside the frontend's login/signup screens, since right now there's nothing to test it against end-to-end.
2. **Attachments have no frontend API surface at all** — not in types.ts, mock.ts, or index.ts's ApiClient interface. Stubbed GET/POST /projects/{projectId}/attachments and DELETE /attachments/{attachmentId} from the spec's table columns and marked them PROVISIONAL. The bigger open question is the upload mechanism — direct-to-S3 presigned PUT vs. proxied multipart through the API — which the spec doesn't decide. Treat this section as a placeholder, not a contract to build against yet.
3. **camelCase vs snake_case.** Frontend types are camelCase (nextAction, targetDate, createdAt); the spec's tables are snake_case. Resolved by making the API JSON camelCase everywhere, matching the frontend exactly, so the mock→HTTP swap needs no component changes. This means FastAPI/Pydantic models need alias_generator config to serialize camelCase — flagged as deliberate.
4. **One deliberate exception to camelCase:** the token response (access_token, token_type) stays snake_case, per the OAuth2 spec's field naming, which FastAPI's built-in Swagger Authorize flow expects literally.
5. **links field type.** Spec lists it ambiguously as jsonb / text[]. Frontend's types.ts is unambiguous: links: string[]. Went with the flat array of URL strings. Flagging in case you wanted structured link objects (label a link as "repo" vs "demo").
6. **UpdateProjectInput** allows updatedAt in the frontend's TS type, but mock.ts always overwrites updatedAt server-side. Excluded updatedAt from the contract's UpdateProjectInput schema entirely, since it should never be client-settable. Confirm that's intentional.
7. **targetDate is date-only** (YYYY-MM-DD), while createdAt/updatedAt are full ISO datetimes. Modeled as format: date vs format: date-time respectively.
8. **No filtering/sorting/pagination on GET /projects,** even though the dashboard calls for filter-by-status/tag and sort-by-score/date. Today that's all client-side over the full list. Fine for v1 scale, will need revisiting if the list grows large.

## 2 - Labeled links

Changed project links from flat URL strings to labeled objects ({ label?: string; url: string }), across the contract and frontend. Four files touched.

### Files touched (confirmed before changing)

Links only appeared in types.ts, mock.ts, seed.ts, and project-detail.tsx. mock.ts passes the array through generically, so it needed no logic change, only the type flowing from types.ts.

- **openapi.yaml** — new Link schema ({ label?: string, url: string }), used by Project, CreateProjectInput, UpdateProjectInput
- **frontend/src/services/api/types.ts** — new Link type; Project.links and CreateProjectInput.links are now Link[]
- **frontend/src/services/api/seed.ts** — "This Incubator" now has labeled links (Repo, Demo); chess project's Lichess API link stays unlabeled
- **frontend/src/pages/project-detail.tsx** — display falls back to link.label || link.url; add row gained an optional "Label" input alongside the existing URL input, both wired to Enter-to-submit; removal keys off url

mock.ts needed no changes — it passes links through generically.

### Verified in-browser

(dev server on :5174, extension needed a reconnect first)
- Seeded labeled links ("Repo", "Demo") render with their labels
- Seeded unlabeled link renders as the raw URL
- Added a link with no label in one step (Enter in the URL field alone) — normalized to https:// and displayed as the URL
- Added a link with a label — displayed as the label
- Removed both test links to leave state as it was

Lint (0/0), tsc -b, vite build, and prettier --check all clean. Not committed.

## 3 - FastAPI backend scaffold

Scaffolded a skeleton FastAPI backend in backend/, managed by uv. Health endpoint only, no auth/models/logic. Not committed.

### Layout chosen, and why

```
backend/
  pyproject.toml       # uv-managed, deps: fastapi, uvicorn[standard]
  uv.lock
  .python-version      # 3.12
  .gitignore           # venv, __pycache__, .env, *.db, etc.
  README.md
  app/
    __init__.py
    main.py             # FastAPI() + CORS (localhost:5173) + router registration
    routers/
      __init__.py
      health.py          # GET /health -> {"status": "ok"}
    core/__init__.py     # placeholder — settings later
    auth/__init__.py     # placeholder — password hashing + JWT later
    models/__init__.py   # placeholder — Pydantic schemas + ORM models later
    db/__init__.py       # placeholder — in-memory store, then SQLite later
```

app/ (flat package, not src/) because this is a single deployable service, not a library meant to be installed elsewhere. routers/, auth/, models/, db/, core/ are split now, even though most are empty, because the openapi contract already implies that shape. Adding those seams now means the next session drops files in rather than restructuring.

### Commands to run it

```
cd backend
uv sync                              # install deps
uv run uvicorn app.main:app --reload # dev server, http://localhost:8000
```

### Verified clean

- GET /health → {"status":"ok"}, HTTP 200
- GET /docs → HTTP 200 (Swagger UI loads)
- GET /openapi.json → generated correctly, one path: /health
- git add -n backend/ confirms .venv/ and __pycache__/ are properly ignored

Nothing committed.

## 4 - Backend auth + projects (in-memory)

Built auth and project CRUD in backend/, scoped per user, against the in-memory store. Built to openapi.yaml. No notes/attachments, no database yet. 15/15 tests pass. Not committed.

### What was built

**Auth** (app/auth/, app/routers/auth.py)
- security.py: hash_password/verify_password via passlib with argon2, create_access_token/decode_access_token via PyJWT, HS256, 60-minute expiry.
- dependencies.py: get_current_user, an OAuth2PasswordBearer dependency that decodes the bearer token and loads the user; raises 401 on missing/invalid/expired token or unknown subject.
- routers/auth.py: POST /auth/register (409 on duplicate email), POST /auth/login (OAuth2PasswordRequestForm, so Swagger's Authorize button works), GET /auth/me.

**Projects** (app/routers/projects.py)
- Full CRUD scoped through get_current_user. Every store lookup takes (project_id, owner_id) together, so store.get_project returns None if the id doesn't exist or belongs to someone else, and the router turns that into a single 404 either way. Create assigns owner_id=current_user.id server-side; the client never supplies it.

**Store** (app/db/store.py, app/db/seed.py)
- InMemoryStore with UserRecord/ProjectRecord dataclasses, keyed by id, with an email index. get_store() is the dependency every router uses, so swapping in SQLAlchemy later only touches this file and the one Depends(get_store) wiring point, not the routers.
- seed.py populates one demo user with two projects (ported from the frontend's p-incubator/p-chess seed data). Credentials in the README: demo@hub.dev / demo1234.

**Models** (app/models/)
- base.py: CamelModel (alias_generator=to_camel, populate_by_name=True); every camelCase schema extends this.
- user.py, project.py: User, RegisterInput, Project, Link, CreateProjectInput, UpdateProjectInput matching openapi.yaml field-for-field, plus TokenResponse, which deliberately stays snake_case (access_token, token_type) per OAuth2 convention.

### Decisions / things the contract left open

1. **Argon2 over bcrypt.** Spec said "bcrypt/argon2." Picked argon2 — current passlib releases have a known compatibility break with recent bcrypt versions, and argon2 has no 72-byte password truncation quirk. Swappable via pwd_context in security.py.
2. **JWT secret.** Not specified. Defaults to a hardcoded dev string in security.py, overridable via HUB_JWT_SECRET. No config/settings module yet (app/core/ still empty) — first thing that'll need one.
3. **Token expiry.** Not specified. Picked 60 minutes; easy to change in security.py.
4. **PATCH semantics for targetDate.** Used exclude_unset=True on UpdateProjectInput, so omitting the field leaves it untouched but explicitly sending "targetDate": null clears it — matching the frontend's clear-date button.
5. **Case-insensitive email matching** on register/login (not in the contract, but avoids Foo@x.com and foo@x.com registering as two accounts).

### Verified

- uv run pytest → 15 passed (7 auth, 8 project/isolation), including the four isolation cases by name: 404-not-403 on GET, blocked PATCH, blocked DELETE with the project still intact for the owner, and list never leaking another user's projects.
- Live server: /health and /docs both 200; logged in as the seeded demo user via /docs; confirmed /auth/me and /projects return exact camelCase shapes matching openapi.yaml (including a link with "label": null); live cross-user check against the running server confirmed 404 on GET/PATCH of another user's project and 401 with no token.

Nothing committed.

## 5 - Frontend wired to backend (auth + projects)

Connected the frontend to the real FastAPI backend for auth and projects. Notes/attachments still on the mock. Verified end-to-end in the browser. Not committed.

### What was built

**Config** — frontend/src/lib/config.ts exports API_BASE_URL from VITE_API_BASE_URL (defaults to http://localhost:8000), backed by .env.example and vite-env.d.ts for typing.

**HTTP layer** (services/api/)
- token.ts — localStorage-backed JWT storage (hub.token).
- http.ts — httpRequest(): attaches Authorization: Bearer <token> unless skipAuth, JSON- or form-encodes the body, throws HttpError(status, message) from FastAPI's detail field, and calls a registered onUnauthorized handler when an authenticated request returns 401 (never fires for a plain wrong-password login, since that request carries no token).
- auth.ts — authApi.register/login/getCurrentUser/logout, always real (auth never had a mock).
- real.ts — realProjectsApi, real HTTP implementations of the five project endpoints, same signatures as mockApi's.

**The real/mock split** — services/api/index.ts now builds api as an object literal: project methods from realProjectsApi, note methods still from mockApi, each half labeled with a comment (MOCK — PENDING BACKEND) so the next slice knows what to swap. authApi exported alongside.

**Auth state** — auth-context.ts/auth.tsx/use-auth.ts mirror the existing store pattern: status 'loading'|'authenticated'|'unauthenticated', validates a stored token against /auth/me on mount, exposes login/register/logout.

**Gating** — main.tsx wraps the app in AuthProvider. App.tsx branches on status: unauthenticated renders only /login+/signup; authenticated mounts StoreProvider around the real app. Mounting StoreProvider only when authenticated ensures projects state (and its fetch-on-mount) resets cleanly between users and never fires while logged out.

**UI** — pages/login.tsx, pages/signup.tsx (matching existing style), sign-out control in AppHeader (email/display name + logout icon).

### What didn't line up

The mock's note-touches-parent-project behavior assumed the mock owned every project. Once projects moved to the backend, touchProject would throw "Project not found" for any real project id, crashing the notes panel. Fixed by making touchProject return null instead of throwing for unrecognized ids; addNote/deleteNote (mock + store.tsx) now treat a null project as "nothing to bump locally." Notes work on real projects; they just don't bump updatedAt client-side (no backend note endpoint yet — expected until the next slice).

One side effect: the frontend's old mock seed notes are now orphaned — invisible, since no real backend project has those ids. Harmless.

### Verified end-to-end (backend :8000 + frontend :5173)

- Signed up a new user → dashboard, empty list. Logged out (token cleared, confirmed via JS) → bounced to /login. Logged back in → same empty list.
- Logged in as demo@hub.dev → both seeded projects loaded from the backend with correct camelCase fields.
- Isolation: new user saw 0 projects, demo user saw exactly their 2 — confirmed both directions.
- Created a project via Quick Capture, edited a pitch and reloaded — edit survived (confirmed via curl to /projects too), deleted it — confirmed gone via curl.
- Added a note on a real project — works against the mock, no crash.
- Unauthenticated deep-link to /project/<id> redirects to login.

Note: the Chrome extension's synthetic clicks/typing were unreliable on the project-detail page; used native DOM dispatch as a fallback for some verification. Confirmed the flakiness was the automation link, not the app.

Lint, tsc -b, vite build, prettier --check all clean. Nothing committed.

## 6 - Notes backend + frontend wiring

Made notes real, following the projects pattern. 23 backend tests passing (was 15). The mock layer is now gone entirely. Verified end-to-end. Not committed.

### Backend
- app/models/note.py: Note, CreateNoteInput, AddNoteResponse (camelCase via CamelModel, matching openapi.yaml).
- app/db/store.py: NoteRecord dataclass + list_notes/get_note/create_note/delete_note on InMemoryStore. The parent-project "touch" reuses the existing update_project(project_id, owner_id) with no patch fields — it already bumps updated_at and returns the record, so no new bump logic was needed.
- app/routers/notes.py: GET/POST /projects/{project_id}/notes, DELETE /notes/{note_id}. Ownership enforced the same way as projects — 404 whether the project doesn't exist or belongs to someone else. For delete, ownership is checked via the note's parent project (notes have no owner of their own).
- app/main.py: registered the notes router.
- 8 new tests in tests/test_notes.py: CRUD, newest-first ordering, updatedAt bump on both add and delete, auth-required, and three isolation cases (list/add/delete on another user's project all 404, and B's note count untouched by A's failed attempts).

### Frontend
- services/api/real.ts: added realNotesApi (listNotes/addNote/deleteNote), same shape as mockApi had.
- services/api/index.ts: api is now built entirely from realProjectsApi + realNotesApi — no mock references left.
- store.tsx: dropped the if (project) null-guards in addNote/deleteNote — the backend always returns a real project now.

### What was removed
services/api/mock.ts and services/api/seed.ts, deleted entirely (not just trimmed). Once notes went real, nothing was left calling mockApi — the project methods were already dead code from when projects went real, and the note methods became dead by this task. Checked no other file imported from either module before deleting. openapi.yaml still documents attachments as provisional, but there's no Attachment type or UI anywhere in the frontend yet, so there was nothing attachment-shaped to preserve — an empty placeholder file would have been speculative structure AGENTS.md argues against. Whoever builds attachments creates what it needs from scratch, same as notes/projects did.

### Didn't line up
Nothing this time — contract, projects pattern, and the frontend note code all matched cleanly. The one non-obvious piece: update_project with zero kwargs was already exactly the "touch" primitive needed, so no new bump helper was required.

### Verified end-to-end (backend :8000 + frontend :5173, restarted fresh)
- Added a note → reloaded → note persisted (real backend, not mock).
- Dashboard sort: adding the note moved the project to the top.
- Added a note to another project to move it up, then deleted the first note → the first project jumped back to the top, confirming delete also bumps updatedAt server-side.
- Isolation verified against the API with two fresh users: A gets 404 listing or adding a note on B's project, B's note count unaffected.
- Browser clicks/typing worked reliably this session — no JS-dispatch fallbacks needed.

Lint, tsc -b, vite build all clean; 23 backend tests passing. Nothing committed.

## 7 - SQLite storage swap + curated demo seed

Swapped the in-memory store for SQLite via SQLAlchemy, kept database-agnostic for Postgres later. Replaced the demo seed with the ten curated projects. Data now survives restarts. 24 backend tests passing. Frontend untouched. Not committed.

### What was built
- **app/core/config.py** — single settings source: DATABASE_URL, defaults to sqlite:///./hub.db.
- **app/db/orm.py** — SQLAlchemy tables: UserTable, AuthIdentityTable, ProjectTable, NoteTable.
- **app/db/session.py** — engine, session factory, create_tables(), get_db_session() dependency, enable_sqlite_foreign_keys().
- **app/db/store.py** — rewritten: InMemoryStore → Store, backed by a SQLAlchemy Session instead of dicts. Same method surface and same UserRecord/ProjectRecord/NoteRecord DTOs the routers already depended on.
- **Wiring** — InMemoryStore → Store renamed across the routers and auth/dependencies.py. Purely mechanical: only the type import changed per file, router logic byte-identical.
- **Seeding** — seed.py replaced with the ten projects, notes, and varied timestamps. main.py calls create_tables() then seeds only if not store.has_users(), using its own short-lived session.
- **Tests** — conftest.py rebuilt: each test gets its own in-memory SQLite engine (StaticPool, FK enforcement attached), fresh and disposed per test. Forces DATABASE_URL=sqlite:///:memory: before any app import so the startup seed-check never touches a real DATABASE_URL a developer might have set. 24 tests (23 existing + 1 new cascade-delete test).

### Migration story
No Alembic yet. create_tables() runs Base.metadata.create_all() on startup — creates missing tables, does nothing if they exist. Fine while the schema's still moving pre-launch; becomes real Alembic migrations once it stabilizes, since create_all can't alter existing tables (only create new ones).

### Portability tradeoffs (for the eventual Postgres/Neon swap)
1. No SQLite driver package needed (stdlib). Postgres will need `uv add psycopg[binary]`.
2. UUIDs as String(36), not Postgres native UUID.
3. Tags and links as generic JSON, not Postgres JSONB (costs some Postgres-side JSON query/index efficiency later).
4. Free text as unbounded Text, not VARCHAR(n), to avoid a dev-vs-prod silent-truncation trap.
5. Status enum via SQLAlchemy Enum(values_callable=...) — native ENUM on Postgres, VARCHAR+check on SQLite.
6. Timezone-aware timestamps: DateTime(timezone=True) correct on both, but SQLite strips tzinfo on read. A _utc() helper in store.py reattaches UTC when missing. Masks the SQLite gap at the store layer rather than fixing it at the DB — reading timestamps straight off the SQLite file bypassing the store would give naive datetimes.
7. FK enforcement turned on for SQLite (PRAGMA foreign_keys=ON per connection) so dev matches Postgres.

### One behavior change (not just a swap)
The old in-memory delete_project never cleaned up a project's notes (orphaned but unreachable). Real FK enforcement would turn that into an IntegrityError, so added ondelete="CASCADE" on the notes FKs — which openapi.yaml's DELETE /projects/{projectId} already documented but the in-memory store never implemented. Bug fix the swap surfaced, covered by a new regression test. Also: create_user now flushes the user row before the auth-identity insert (SQLAlchemy doesn't auto-sequence the two unrelated inserts).

### Verified
- 24/24 backend tests pass; confirmed no dev hub.db touched by the test run.
- Fresh DB → seed appears: 10 projects, all six statuses (1/2/3/2/1/1), correct scores/tags/links (incl. null-label)/blank fields/target dates, notes in right counts and newest-first.
- Restart → no re-seed: created a project + note via API, restarted against the same hub.db, confirmed 11 projects (not 20), new data intact with original timestamps.
- Touch behavior survives: verified over HTTP and visually — added a note to "Pivot into UX design", watched it jump to the top of the dashboard sort.
- Cascade delete: new test confirms deleting a project with notes succeeds (204) and the notes are actually gone.
- Frontend untouched (git status zero diff).

Note: found a stray uvicorn --reload process (not one it started) that had crashed mid-edit and left hub.db partial; removed the file and re-verified from a clean one.

## 8 - Tier 1 config/security hardening

Moved all security-relevant settings into the config module and added a startup guard that makes shipping the insecure default secret impossible in production, while local dev still needs zero setup. 32 backend tests passing. Frontend untouched. Not committed.

### What moved into config
app/core/config.py is now the single source for everything security-relevant:

| Setting | Env var | Default |
|---|---|---|
| Environment indicator | ENVIRONMENT | local |
| Database URL | DATABASE_URL | sqlite:///./hub.db (unchanged) |
| JWT secret | HUB_JWT_SECRET | dev-only-insecure-secret-change-me (DEV_JWT_SECRET) |
| JWT algorithm | — (fixed constant) | HS256 |
| Token expiry | ACCESS_TOKEN_EXPIRE_MINUTES | 60 |

security.py now imports JWT_SECRET/JWT_ALGORITHM/ACCESS_TOKEN_EXPIRE_MINUTES from config instead of reading os.environ itself — no os import left in that file. No argon2 numeric parameters were hardcoded to begin with (passlib's CryptContext just names the scheme and uses its own defaults), so there was nothing to move; left as-is and flagged rather than inventing config knobs for values that were never set.

### How the prod guard works
require_safe_jwt_secret(environment, secret, dev_default) in config.py — a pure function (takes inputs as arguments defaulting to the module's resolved settings, so tests never touch real env vars). main.py calls it as the first line after imports, before FastAPI() is constructed:
- local/development/dev (case-insensitive): if the secret is still the dev default, print a warning and continue; otherwise silent.
- anything else (production, staging, ...): raise RuntimeError if the secret is empty/unset or still the dev default. Verified it crashes uvicorn at import time (exit 1) before binding a port; setting a real HUB_JWT_SECRET lets it start clean.

One real bug caught during verification: the warning print wasn't showing under uvicorn with output redirected to a file — Python block-buffers print() on a non-TTY stdout. Added flush=True; the warning now appears immediately. Worth knowing since it's the kind of thing that silently disappears in a real deployment's log capture.

### Env vars (documented in .env.example and README)
ENVIRONMENT, DATABASE_URL, HUB_JWT_SECRET, ACCESS_TOKEN_EXPIRE_MINUTES — table with defaults and prod-required flags in the README, same four with explanatory comments in the new .env.example. Only HUB_JWT_SECRET is marked required in production. Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))"

### Verified
- 32/32 tests pass (24 existing + 8 new in tests/test_config.py: local-with-dev-secret, local-missing-secret, the development/dev aliases, case-insensitivity, production-with-dev-secret, production-missing-secret, other-non-local-env, production-with-a-real-secret).
- Frictionless local dev: started with a fully wiped environment (env -i, zero vars) — starts clean, warning printed, seeded demo login works, all 10 projects load.
- Production guard: ENVIRONMENT=production with no secret → crashes at import with the exact RuntimeError, before serving anything. Adding HUB_JWT_SECRET → starts and serves fine.
- Nothing hardcoded in security.py: confirmed by grep.

Frontend untouched, no rate-limiting/account caps (out of scope). Nothing committed.

## 9 Write/load error handling + unified optimism

Added error handling to all write and load paths, surfaced load errors with retry, and standardized on pessimistic writes everywhere. Verified all failure paths in the browser. Not committed.

### What changed

New files:
- lib/toast.ts — a toastManager usable outside React so the store itself can trigger toasts, plus notifyError().
- lib/errors.ts — toUserMessage(err, fallback) (backend's curated HttpError.message when available, friendly fallback otherwise) and reportError(err, fallback) (calls notifyError, except for a 401 — see below).
- components/ui/toaster.tsx — the visual toast, styled to match the app's card/border/shadow language. Mounted once in App.tsx.

Store (store.tsx) — every write (create/update/deleteProject, add/deleteNote) now waits for the API, updates projects state only on success, calls reportError + re-throws on failure. The existing error state is now actually consumed.

Dashboard — added an ErrorState component (same visual pattern as EmptyState) shown instead of the grid/stats/toolbar when the load fails, with a "Try again" that calls refresh().

Project detail — save() returns Promise<boolean>; the four fields with local draft state (name, pitch, description, nextAction) revert to project.<field> on failure. Status/scores/target-date/tags/links needed no revert (directly controlled by project.*, so a failed save already leaves them showing the correct unchanged value). handleDelete catches and resets the confirm-delete UI on failure. Same load-error/retry treatment extended to the "not found" branch.

Notes panel — remove() flipped from optimistic to pessimistic (the one inconsistent case): waits for deleteNote to resolve before removing from local state, with a deletingId guard disabling the button mid-flight.

Quick capture — logic was already correct (dialog stays open, data intact on failure); documented why.

### Optimistic-update convention: pessimistic, everywhere
Every write waits for the server before the store's projects state changes. Reasons: it satisfies "never show data that didn't save" by construction (state is backend-confirmed, nothing to roll back); four of five paths were already pessimistic (only note-deletion was the outlier, the smaller/lower-risk change); individual writes are cheap and inputs already echo keystrokes immediately, so the app stays responsive without full optimistic-rollback machinery.

### How errors surface
- Writes: a toast (bottom-right, auto-dismiss 6s, dismissible) with a plain-language message — backend's curated string or a generic network fallback. The four local-draft fields also revert to last-known-good.
- Loads: dashboard and project-detail's "not found" branch show a dedicated error state with the message and a "Try again".
- 401 mid-write: reportError skips toasting a 401 — already routed to logout/login by the existing handler, so no confusing double message.

### Tech debt
Removed the entire Robustness section and the write-optimism line. Updated the "duplicated empty-state layouts" entry from three to four, since the new load-error state is a fourth divergent-but-similar shape (didn't want to leave it stale).

### Verification
Tested with the backend stopped and, more precisely, with window.fetch overridden to fail one specific request while everything else hit the real backend (the task's suggested alternative) — this sidestepped an unrelated environment quirk (this session's tab logs out quickly whenever the backend becomes unreachable at all; confirmed via code inspection and fetch instrumentation that nothing in the app polls or reloads on its own).

Confirmed live:
- Create failure: toast "Couldn't create that project. Try again.", dialog stays open with typed name intact, still exactly 10 projects (no phantom).
- Edit failure: toast "Couldn't save that change. Try again.", title reverted to its saved value.
- Note-delete failure: toast "Couldn't delete that note. Try again.", note stayed in the list.
- Dashboard load failure: full ErrorState with message and a working "Try again" that recovered once the override was removed.
- Happy path: login, load, a real note delete, and reload all worked throughout.

Also fixed a bug in its own test scripts (React onBlur fires via native focusout, not blur) — irrelevant to app code. Lint 0/0, tsc, build, prettier all clean. Nothing committed.

## 10 - Dark mode persistence

Theme now persists across reloads, respects system preference on first load, applies before paint (no flash), and the theme-color meta follows the toggle. Not committed.

### What the mechanism looks like now
- **index.html** — a small inline `<script>` in `<head>`, before any stylesheet or app code, runs synchronously: reads localStorage['hub.theme']; if unset, falls back to matchMedia('(prefers-color-scheme: dark)'); if dark, adds the dark class to `<html>` and sets an approximate dark theme-color. Wrapped in try/catch (falls back to light if storage/matchMedia unavailable). This eliminates the flash — the class is on `<html>` before the browser paints.
- **src/lib/theme.ts** (new) — source of truth from React's side: getStoredTheme/setStoredTheme (try/catch localStorage) and updateThemeColorMeta(), which reads the actual computed background-color off `<body>` and writes it into the meta tag, so it can't drift from the palette in index.css.
- **app-header.tsx's useTheme** — initial React state reads off the DOM (does `<html>` have the dark class) rather than re-deriving, trusting the inline script's resolution. toggle() flips state and persists the explicit choice. An effect applies the class and calls updateThemeColorMeta() whenever dark changes, so the meta updates on toggle, not just load. Toggle button untouched.

### Didn't line up
- The classic "normalize color via canvas fillStyle" trick (to force rgb() for theme-color) no longer works in current Chrome — canvas now preserves oklch() too. Added it defensively, checked the actual output, found it did nothing, removed it. theme-color accepts any valid CSS color and oklch() is supported by the browsers that read this meta (Chrome/Android, Safari/iOS), so it's passed through as-is. Simpler.
- No access to true OS-level prefers-color-scheme emulation (no CDP media-emulation). Machine's real preference is light; confirmed live that a cleared preference resolves to light. For the dark-OS branch, verified the resolution expression in isolation with matchMedia mocked for all four combinations (no-stored+dark, no-stored+light, stored-light+dark-system, stored-dark+light-system) — all correct, including explicit-choice-wins. Algorithm-level, not a true dark-OS end-to-end test; flagged rather than claimed.

### Verified
- Toggle dark → reload: stays dark (html class, meta, screenshot).
- Toggle light → reload: stays light (same checks).
- Cleared preference + real (light) system pref → starts light, live.
- Dark-system branch verified in isolation (couldn't drive a real dark-OS reload).
- theme-color meta changes on toggle both directions, matching light/dark --background exactly.
- Lint 0/0, tsc, build, prettier clean.

## 11 - Consistency cleanup batch (5 items)

Worked through all five consistency items one at a time, lint/tsc/build clean after each. Behavior-preserving throughout. Verified in-browser. Tech-debt updated. Not committed.

### Item 1 — Shared empty/error-state component
Added components/ui/empty-state.tsx exporting EmptyState with a variant ('page' | 'panel', deriving heading tag/size and the dashed-border box), a tone ('neutral' | 'danger'), and optional icon/message/action. Replaced all four call sites: not-found.tsx, dashboard's empty/no-matches state, dashboard's load-error state, project-detail's not-found/load-error branches. All four verified live, including the danger-tone error state (forced via a temporary fetch override) and its retry button.

### Item 2 — Back-to-dashboard button
project-detail's "All ideas" link now uses buttonVariants({ variant: 'ghost', size: 'sm' }) instead of raw classes. Confirmed the hover background-pill state now appears (it didn't before).

### Item 3 — Rating widget
Kept ScorePicker, removed RatingInput. Reason: ScorePicker sets aria-pressed per button, conveying selection state to assistive tech; RatingInput only had aria-label with no pressed-state signal — a real accessibility gap, not cosmetic. Merged RatingInput's one advantage (the numeric "X/5" readout) into ScorePicker's header row before deleting (grep-confirmed zero remaining references first). Migrated project-detail's three rating controls; edit-and-save confirmed live (Potential 3→5, "Updated just now", reverted).

### Item 4 — Card primitive
project-detail's ratings, target-date, tags, and links sections now use the Card primitive instead of hand-rolled border/bg divs, regaining shadow-sm. The "Next action" accent box was deliberately left alone (different intentional treatment). Layout classes preserved.

### Item 5 — Dead fallback branches
formatDate no longer accepts null; its null-check return removed. In project-detail.tsx, removed the due useMemo entirely and inlined formatDate(project.targetDate) inside the existing project.targetDate ? guard (its only call site), which also dropped useMemo from imports. Verified with-date and no-date cases render correctly. daysUntil's null branch correctly left alone (dashboard's target-date sort uses it).

### Didn't line up / notes
- The tech-debt "no date" placeholder note was left untouched as instructed. Flag: Item 5 removed the branches it referenced, so its literal wording is now stale, but the underlying product question (show nothing vs "None" when there's no date) is still open.
- project-detail's not-found branch got proper buttonVariants styling for free via the Item 1 migration — it had been hand-rolling raw classes too.
- Self-corrected mid-implementation on Item 5: first pass only narrowed formatDate's type but left a dead else-branch; caught it in final verification and removed it properly.

### Verification
Each item ran lint (0/0)/tsc/build individually as it landed; final suite clean. Full click-through via the extension: dashboard normal, no-matches, clear-filters recovery, danger-tone error + retry, two project-detail pages (with/without target date), not-found page — all confirmed. The true zero-projects "Nothing captured yet" variant wasn't exercised live (would require deleting all seed data); its logic is identical to the confirmed no-matches branch with different icon/copy/action, so relying on code review there.

tech-debt.md: five resolved Consistency bullets removed (and the empty section header). Notes and Open-questions untouched. Servers/tab shut down. Nothing committed.

## 12 - Stale + quick-win badges

Added isStale/isQuickWin helpers, a shared IndicatorBadge, and wired both badges into the project card. Added Vitest (repo had no frontend test setup) with 19 unit tests. Verified in-browser. Not committed.

### Helper logic (lib/project-utils.ts)
- isQuickWin(p): status ∈ {Inbox, Exploring, Active} && excitement >= 4 && effort <= 2
- isStale(p, now = new Date()): status ∈ {Active, Exploring} and (now - updatedAt) >= 30 days. `now` injectable for deterministic tests.

### Badges
New IndicatorBadge (components/indicator-badge.tsx) mirrors StatusBadge's exact pill shape (rounded-full, dot + text, same padding/type scale) as one shared piece — a Quick win and Stale badge are the same shape with different colors, and duplicating StatusBadge's markup would recreate the pattern the last cleanup removed. Wired into project-card.tsx next to the status pill, wrapped in flex-wrap so it degrades if a card shows all three. Colors: quick win = lime (positive, distinct from Active's emerald and Parked's amber); stale = zinc/gray (deliberately muted, not rose/amber, per "gentle nudge, not alarming").

### Tests
Repo had no test framework, so stopped and asked — you chose Vitest. Added it as a devDependency, a pnpm test script, and lib/project-utils.test.ts with 19 cases: quick-win at/around the excitement-4/effort-2 thresholds, excluded for all three closed statuses; stale at/around the 30-day boundary, excluded for Inbox/Parked/Killed/Graduated; combined both/neither. All pass; lint, build, format:check clean.

### Seed projects, actual result
- Quick win: only "Read 24 books this year" (Active, excitement 4, effort 2 — exactly on threshold).
- Stale: none — the only old seed projects are Parked/Killed/Graduated, correctly excluded. Verified live, then confirmed the stale badge renders by client-side-spoofing one response (non-destructive, restored after) to backdate "Train for a half-marathon" 40 days + drop effort to 2 → correctly showed Active + Quick win + Stale on one line, no overflow.
- Confirmed Parked/Killed/Graduated never show stale even though three are 21–130 days old — correct per spec.

### Didn't line up
The verification note expected "Train for a half-marathon" and "Pivot into UX design" to look quick-win-ish; neither qualifies under the exact definition (both have effort 4-5). And no Active/Exploring seed project is naturally 30+ days stale. So with real seed data only one badge shows anywhere today (quick win on "Read 24 books this year"); everything else was verified by temporary fetch-spoofing. If you want the seed to actually exercise the stale case, that's a seed-data change (backdating an Active project's updatedAt) not made since it wasn't asked for.

## 13 - Seed tweak: exercise both badges in the demo

Seed-data only (backend/app/db/seed.py). No badge logic or frontend touched. 32 backend tests pass, seed syntax valid. Not committed.

### Resulting badge map
| Project | Status | Badges |
|---|---|---|
| Dial in a sourdough starter | Parked | none |
| Etsy shop for my prints | Exploring | Quick win + Stale |
| Automate my budgeting spreadsheet | Active | Stale |
| Train for a half-marathon | Active | none |
| Pivot into UX design | Exploring | none |
| Build my portfolio site | Inbox | none |
| Read 24 books this year | Active | Quick win (unchanged) |
| Learn enough Spanish for the trip | Parked | none |
| Start a podcast with the group chat | Killed | none |
| Declutter and sell old furniture | Graduated | none |

All six statuses still represented at the same counts (Inbox 1, Exploring 2, Active 3, Parked 2, Graduated 1, Killed 1).

### What changed
- Etsy shop for my prints (both-badges): effort 3 → 2 (excitement stays 4, clears quick-win), updatedAt 9d → 40d ago. Notes and createdAt pushed back proportionally (createdAt 45 → 70d; notes 30/18/9 → 61/49/40d) so every note still falls after creation and no later than the new updatedAt.
- Automate my budgeting spreadsheet (stale-only): scores left alone (already fails quick-win), updatedAt 2d → 40d ago, createdAt 14 → 55d, notes 10/2 → 48/40d. Target date (~3 weeks out) left, giving a "deadline coming, no progress" story.
- Comments above both blocks updated to match the new narrative. Nothing else touched.

### Recreate the local DB
```
cd backend
rm hub.db
uv run uvicorn app.main:app --port 8000
```
(seeding only runs against an empty DB, so deleting hub.db is required — the server re-seeds on startup)

## 14 - Pre-deploy read-only review

All objective checks green. No correctness bugs, no untracked security holes, no debug cruft. Frontend/backend contract matches openapi.yaml across auth, projects, notes. Findings are mostly polish plus two decisions. No files modified.

### Objective checks
- Frontend: eslint 0/0; tsc -b && vite build clean; vitest 19/19 pass.
- Backend: pytest 32/32 pass (4 deprecation warnings from third-party libs only — httpx/starlette, passlib/crypt, argon2-cffi — not app code).

### Fix before deploy
1. **CORS hardcoded to localhost** — main.py:16-22. allow_origins is localhost:5173 only. Not a security bug (safe restrictive default) but a functional blocker: once the frontend deploys, requests fail CORS until prod/staging origins are added. Not covered by tech-debt's generic Deploy bullet.
2. **Spec-required observability doesn't exist and isn't tracked as deferred** — spec §2 lists error tracking (Sentry) + dashboards as a v1 layer, not in §9 Deferred. No Sentry SDK either package; no React error boundary in App.tsx, so a render-time bug white-screens with only a console log. Decide: add it, or add to tech-debt as a deliberate deferral so it's not silently missing.

### Real findings — can wait
Correctness:
- auth.py:15-27 — register() does check-then-insert with no try/except around the unique-constraint violation; users.email is unique at the ORM level, so a race between two simultaneous same-email registrations would surface as a 500 instead of the documented 409. Narrow window, easy to close.
- project.py:20 — Link.url is str while openapi.yaml documents format: uri; not enforced server-side. Cosmetic.

Consistency (partly slipped back after the cleanup pass):
- Inconsistent void on fire-and-forget async calls in JSX handlers: project-detail.tsx:133,138,149,155 use void save(...); :245,302,308,314,325 call save(...) bare. Same split in notes-panel.tsx and quick-capture-dialog.tsx. No runtime difference (all handle their own errors); inconsistent within single files.
- stats-row.tsx:19-27 hardcodes the six-status order instead of deriving from the exported STATUSES. DRY nit.

Dead code:
- theme.ts:16-23 — getStoredTheme() exported, never called (app-header reads the DOM class directly). Safe to delete.
- auth.ts:38-40 — authApi.logout() exported, never called; the real logout path duplicates the one-line clearToken() directly. Wire it up or delete.

Doc drift:
- AGENTS.md still describes the API layer as an in-memory mock (services/api/mock.ts) — that file no longer exists; the layer is real HTTP (real.ts).
- openapi.yaml's top description still says "the backend does not exist yet."
- tech-debt.md still lists stale/quick-win surfacing as unbuilt — shipped. And its Notes section says the "no date" branches are "currently unreachable" — the cleanup pass deleted them outright; only the underlying product question (what to show for no date) is still open.

Spec alignment:
- seed.py's demo projects differ from spec §11's listed projects — reads like a deliberate design upgrade, not drift; confirm intentional.
- Confirmed the only deferrals present are attachments, PWA, Postgres/Neon, rate-limiting/caps — matching tech-debt exactly. No other half-built or silently-missing v1 features beyond observability above.

Tests:
- Backend 32: strong auth + isolation coverage. Minor gaps: case-insensitive duplicate-email registration untested; expired-but-well-formed JWT untested (only a garbage token is).
- Frontend 19: all for isStale/isQuickWin. Nothing else (auth forms, store writes, dashboard filtering/sorting, project-detail) is tested. Consistent with the project's stage; "19 tests" doesn't imply broad coverage.

### Already tracked in tech-debt — confirmed still accurate, not re-flagged
- Rate-limiting, account/project caps — neither exists.
- "Logout-on-any-failure too aggressive" — confirmed, exact spot: auth.tsx:32-44. On app load, if a token exists, getCurrentUser()'s .catch() clears the token on ANY rejection, not just a real 401, so a network blip/cold-start during that check logs the user out. (http.ts:66's global 401 handler is correctly scoped; this is specifically the app-mount check.)
- Postgres portability tradeoffs, no-Alembic-yet — accurate, unchanged.

No files modified.

## 15 - Pre-deploy cleanup batch

Error boundary added and verified, two dead exports resolved, doc drift fixed, two deploy-time deferrals now tracked. All checks green. Not committed.

### 1. Error boundary (verified working)
New components/error-boundary.tsx: a class component (getDerivedStateFromError + componentDidCatch) wrapping the entire app in App.tsx (around the loading/unauthenticated/authenticated tree and the Toaster, so it catches crashes anywhere, not just routed pages). On catch it logs to console.error (placeholder until Sentry) and renders the existing EmptyState in page/danger mode: "Something went wrong" + explanation + a Reload button (window.location.assign('/')).

Verified live: temporarily threw inside DashboardPage, confirmed the fallback rendered instead of a white screen, confirmed componentDidCatch's console.error fired with the error + component stack, confirmed Reload does a real navigation, then removed the throw and confirmed normal rendering. dashboard.tsx has no net diff.

### 2. Dead exports
- getStoredTheme() (lib/theme.ts) — deleted. Zero references.
- authApi.logout() (services/api/auth.ts) — kept and wired up instead of deleted. auth.tsx's logout now calls authApi.logout() instead of duplicating clearToken() inline. Reasoning: AGENTS.md's rule is all data access goes through services/api/; the inline clearToken() was the kind of around-the-layer call that rule prevents, so routing through the api layer is the more correct fix. (The other clearToken() in auth.tsx — boot-time invalid-token cleanup — is a different concern, left as-is.)

### 3. Doc drift fixed
- AGENTS.md: API-layer paragraph rewritten to describe real.ts/http.ts as the actual state; no more mock.ts reference.
- openapi.yaml: top description no longer says "the backend does not exist yet"; now says the backend implements the contract, attachments still provisional.
- tech-debt.md: removed the shipped stale/quick-win roadmap entry; rewrote the Notes entry so it no longer claims the no-date branches are unreachable (they were deleted), keeping the open product question.

### 4. New tracked deferrals (tech-debt.md)
- CORS origins hardcoded to localhost in main.py; deployed frontend origins must be added at deploy or requests fail CORS.
- Observability/Sentry not wired; error boundary covers the frontend-crash half, backend/error-tracking deferred to deploy.

Verification: lint 0/0, tsc, build, test 19/19, format:check — all clean. Deferred items (register race, void-consistency, stats-row, Link.url) left untouched as instructed. Nothing committed.

## 16 - Frontend critical-logic tests

Added logic tests for the store, auth flow, http/token layer, and remaining pure helpers. 71 tests total (was 19), all passing. One dep added (jsdom, per the earlier decision). No app code changed. Not committed.

### Added (all in frontend/)
- **src/lib/render-hook.tsx** — a small hand-rolled renderHook/flush helper (real React createRoot + act, no RTL) to mount StoreProvider/AuthProvider and read hook state across renders.
- **src/store.test.tsx (13)** — initial load (success/failure); each write path (create/update/delete project, addNote, deleteNote): success updates state correctly, failure leaves projects referentially unchanged and rejects. Plus getProject.
- **src/auth.test.tsx (8)** — on-mount token check (no token / valid / invalid, including token cleared on invalid); login/register success and failure; logout.
- **src/services/api/token.test.ts (6)** — get/set/clear round-trip; all three degrade to a no-throw no-op when Storage methods throw.
- **src/services/api/http.test.ts (11)** — bearer attached/omitted/skipAuth; string and FastAPI-array detail parsed into HttpError; non-JSON fallback to status text; onUnauthorized fires only on a 401-with-token; 204/200 handling.
- **Extended project-utils.test.ts (+15)** — opportunityScore, daysUntil (null/future/past/same-day boundary), formatRelative (all buckets), formatDate (date-only vs full ISO).

Total 71 tests passing. lint 0/0, build clean, format:check clean.

### Dependency
jsdom as a devDependency (your call earlier). Store/auth logic lives entirely in React hooks, which only run during a render, so there was no way to exercise them without a renderer. Scoped via a per-file // @vitest-environment jsdom pragma so the rest of the suite stays in the faster node environment.

### Left for the component pass
Anything rendering actual UI, DOM queries, or user interaction (clicks, forms) — none of that is here.

### Hard to test / design notes
Nothing flagged as a design concern. The pessimistic-write pattern made the "state unchanged on failure" tests trivial (assert the same array reference); the auth on-mount logout-on-any-failure behavior was straightforward to pin as-is without changing it.

### Note
git status shows _docs/prompts_backend.md and _docs/results_backend.md modified on disk; the agent didn't touch either (didn't edit _docs/ as code). Flagged as possibly something else in the environment writing to them — verify before committing.
````