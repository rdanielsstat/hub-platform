# Backend Prompts

## 1

```
Read _docs/specs.md fully, then read the frontend's API client in frontend/src/services/api/ (types.ts, mock.ts, seed.ts, index.ts) to understand exactly what the frontend expects: the entities, fields, endpoints, and the shape of every request and response it makes.

Create openapi.yaml at the repository root: the explicit API contract the backend must implement.

Specify every endpoint, method, path, request body, response body, and which endpoints require authentication, derived from what the frontend's API client actually calls. Match the data model in the spec (users, auth_identities, projects, notes, attachments; the status enum; the 1-5 score fields; per-user ownership).

Don't build the backend yet, just the contract. When done, walk me through the endpoints you defined and flag anywhere the frontend's expectations and the spec's data model don't line up, so we resolve mismatches before writing any backend code.
you can read agents.md for more context too
```

## 2

```
Change a project's links from a flat list of URL strings to a list of labeled link objects, where each link has an optional label and a url. This touches both the API contract and the frontend, since the frontend currently stores and displays links as plain strings. Do it as one scoped change.

Shape: each link is { label?: string; url: string }. The label is optional. When a link has no label, display it by showing the url itself (the current behavior). When it has a label, show the label instead, as a clean clickable link to the url.

In openapi.yaml: update the Project schema (and any create/update input schemas) so links is an array of these objects instead of an array of strings. Match the camelCase convention already used everywhere else in the contract.

In the frontend:
- Update the Link type and the Project type in frontend/src/services/api/types.ts.
- Update the mock (mock.ts) and seed data (seed.ts) so existing seeded links become objects. Give the seeded links sensible labels where the URL makes it obvious (e.g. a github.com link labeled "Repo", a live demo labeled "Demo"), and leave label off where it's just a reference URL, so both the labeled and unlabeled display paths are exercised by the seed data.
- Update wherever links are displayed (project detail, and anywhere else they render) to use the label when present and fall back to the url when not.
- Update wherever links are added/edited so a link can be entered with an optional label alongside the url. Keep it fast: a url with no label must still be addable in one step. Match the existing form/interaction patterns on that page, don't invent a new one.

First look at how links are currently typed, stored, displayed, and added, and tell me the files you're touching before changing them. Don't assume where link editing lives.

Keep everything else about links unchanged. Don't regress the no-op-blur behavior or the updatedAt bump rules. Keep lint at 0/0, tsc and build clean. Verify: a seeded labeled link shows its label, a seeded unlabeled link shows its url, you can add a link with a label and without one, and both render correctly. Don't commit, I'll review.
```

## 3

```
Scaffold a FastAPI backend in a new backend/ folder at the repo root. This is a skeleton only: no auth, no data models, no business logic yet. The goal is a running FastAPI app I can build on next.

Read _docs/specs.md and AGENTS.md first for context on the intended backend (FastAPI, Python deps via uv, will later hold roll-your-own auth and a database). Also glance at openapi.yaml so the scaffold's structure is compatible with the contract it will implement, but do NOT implement any of the contract's endpoints yet.

Set up:
- A backend/ folder with a Python project managed by uv (uv init style, pyproject.toml, pinned Python version).
- FastAPI and uvicorn as dependencies, added via uv.
- A minimal app: a FastAPI instance, a single GET /health endpoint returning a simple ok status, and CORS configured to allow the frontend dev origin (Vite's localhost) so the two can talk later.
- A sensible module layout for a small FastAPI app that will grow to include auth, routers, models, and a data store, but leave those as empty/placeholder structure, don't fill them in. Tell me the layout you chose and why before or as you create it.
- A backend/.gitignore for Python (venv, __pycache__, .env, etc.).
- A short backend/README.md with the actual commands to install deps and run the dev server.

When done: run the app with uv and confirm GET /health responds and the auto-generated /docs page loads. Report the exact commands to run it, the folder structure you created, and confirm it runs clean. Don't commit, I'll review.
```

## 4

```
Build the first real backend slice in backend/: authentication plus project endpoints, scoped per user, against an in-memory store. Build to the existing openapi.yaml contract. Do not build notes or attachments yet, those come in a later step. Do not add a database yet, the store stays in-memory.

Read openapi.yaml, _docs/specs.md, and AGENTS.md first. Implement only the auth endpoints and the project endpoints from the contract:
- POST /auth/register, POST /auth/login, GET /auth/me
- GET/POST /projects, GET/PATCH/DELETE /projects/{projectId}

Requirements:
- Roll-your-own auth: hash passwords (bcrypt or argon2 via passlib), issue JWT bearer tokens, OAuth2 password flow, matching how the contract already describes login (form-urlencoded, username=email; snake_case token response). A protected endpoint with no/invalid token returns 401.
- Per-user isolation is the point of this step: every project read and write is scoped to the authenticated user. A user requesting a project that isn't theirs gets 404 (not 403), so the API never reveals another user's data exists. Creating a project assigns the current user as owner.
- Match the contract's shapes exactly: camelCase JSON everywhere (Pydantic alias config), the status enum, 1-5 score fields, labeled links, the field names the frontend expects. The response shapes must match what openapi.yaml specifies so the frontend can wire to this unchanged later.
- Fill in the placeholder modules from the scaffold (auth/, models/, db/, routers/) rather than restructuring. Keep the in-memory store swappable for a real database later (the db/ seam).
- Seed the in-memory store with one test user and a couple of projects owned by that user, so there's something to log in as and see. Note the seeded credentials in the README.

Testing (set up the harness this step, it doesn't exist yet):
- Add pytest + httpx (or FastAPI's TestClient) as dev deps via uv.
- Auth tests: register a new user; log in and get a token; login with wrong password is rejected; a protected endpoint with no token returns 401.
- Isolation tests (the important ones): create user A and user B, each with their own project; confirm A can list and get A's project; confirm A gets 404 (not 403) trying to GET B's project; confirm A cannot PATCH or DELETE B's project; confirm A's project list never includes B's projects.
- Add the test command to the README.

When done: run the app with uv and confirm the auth and project endpoints work via /docs, and run the full test suite and confirm it passes (report the count). Walk me through what you built, the module layout you filled in, and anything in the contract that was ambiguous or that you had to decide. Don't commit, I'll review.
```

## 5

```
Wire the frontend to the real backend for auth and projects. The backend (backend/, FastAPI) now implements auth and project endpoints per openapi.yaml against an in-memory store; the frontend still runs entirely on its in-memory mock with no login. This step connects them for auth and projects only. Notes and attachments have no backend yet and must keep working off the mock.

Read AGENTS.md, openapi.yaml, backend/README.md (for the run command and seeded demo credentials), and the frontend's services/api/ layer first, so you wire to the real contract and understand the existing seam.

Build:
- Login and signup screens. Login: email + password. Signup: email + password + optional display name. Match the app's existing visual style (sleek, minimal, the patterns already used elsewhere). Show clear errors (wrong credentials, email already taken).
- Auth flow against the backend: register → POST /auth/register, login → POST /auth/login (OAuth2 password form, username=email), fetch current user → GET /auth/me.
- Token storage and the auth header: store the JWT, attach it as a bearer token on every authenticated request, and clear it on logout. Handle a 401 (expired/invalid token) by sending the user back to login rather than leaving the app in a broken state.
- Gate the app behind auth: an unauthenticated user sees login/signup; an authenticated user sees the app. Add a sign-out control (the account/profile area is fine).
- Swap the services/api/ layer so auth and project calls hit the real backend over HTTP, while notes and attachments keep using the mock. Keep the single-seam design: components still go through the api layer, never call fetch directly. Make the real/mock split clean and obvious in the api layer, with a clear marker that notes/attachments are pending a backend so the next step knows exactly what to swap.

Config:
- The backend runs on localhost:8000, the frontend on localhost:5173 (CORS is already set for this). Put the backend base URL in one place (an env var / config module), not hardcoded across files, so it can point at a deployed backend later.

Testing and verification (I want this checked as you go, per how we're working now):
- After building, run the backend and frontend together and verify end to end in the browser: sign up a new user, log out, log back in, and confirm you see that user's projects (empty for a brand-new user). Then log in as the seeded demo user (demo@hub.dev / demo1234) and confirm the seeded projects load from the backend.
- Verify isolation through the real UI: the new user does not see the demo user's projects.
- Verify creating/editing/deleting a project through the UI persists against the backend (survives a page reload while the backend stays running), and that notes still work (against the mock).
- Verify a logged-out user cannot reach the app, and that logging out clears the token.
- Keep lint at 0/0, tsc and build clean. If the Chrome extension is connected, verify visually; if not, tell me what you could not verify visually rather than claiming it works.

Report what you built, how the real/mock split is structured, and anything in the contract or existing frontend that didn't line up. Don't commit, I'll review.
```

## 6

```
Build the notes backend and wire the frontend to it, following the same pattern as the projects slice. Notes currently run on the frontend mock; make them real. Read openapi.yaml, AGENTS.md, backend/README.md, and the frontend's services/api/ layer (especially how projects were wired in real.ts and how the mock currently handles notes) first.

Backend (backend/, in-memory store for now, same as projects):
- Implement the note endpoints from openapi.yaml: GET /projects/{projectId}/notes, POST /projects/{projectId}/notes, DELETE /notes/{noteId}.
- Per-user isolation, same as projects: a user can only list/add/delete notes on projects they own. Adding or deleting a note on a project that isn't theirs (or doesn't exist) returns 404, never revealing another user's data.
- Match the contract's shapes exactly (camelCase). POST returns { note, project } and DELETE returns the parent project, because per our earlier decision, creating or deleting a note bumps the parent project's updatedAt. Do that bump server-side, and return the updated project so the frontend can re-sort the dashboard.
- Fill in the note pieces in the existing module layout (models/, db/store.py, a notes router) rather than restructuring. Keep the store swappable.

Frontend:
- Add real HTTP note methods (in real.ts or alongside it) and swap the api layer (services/api/index.ts) so notes now come from the backend, removing the MOCK — PENDING BACKEND note methods. Update the store's addNote/deleteNote to use the backend's returned project to bump updatedAt (the null-handling workaround added when projects went real can now go, since the backend owns the notes and always returns a real project).
- Clean up the now-dead mock notes code and the orphaned seed notes, so the mock layer only carries what's still pending (attachments). Tell me what you removed.

Testing:
- Backend: add note tests to the suite following the existing auth/projects test pattern. Cover: owner can list/add/delete their own notes; adding and deleting a note bumps the parent project's updatedAt; isolation — a user gets 404 adding or deleting a note on another user's project, and cannot list another user's notes. Report the test count.
- End-to-end in the browser (both servers running): add a note on a project, confirm it persists across a page reload (it's real now, not in-memory mock), confirm the project jumps to the top of the dashboard's recently-updated sort, delete a note and confirm the same. Confirm notes are isolated per user. If the Chrome extension is flaky again, tell me what you couldn't verify visually rather than claiming it.

Keep lint at 0/0, tsc, build, and the backend tests all clean. Report what you built, what you removed from the mock, and anything that didn't line up. Don't commit, I'll review.
```