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