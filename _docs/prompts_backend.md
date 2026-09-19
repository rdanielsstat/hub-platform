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

## 7

Swap the backend's in-memory store for a real database: SQLite via SQLAlchemy, kept strictly database-agnostic so Postgres (Neon) can replace SQLite at deploy time without a rewrite, per the spec and AGENTS.md. Same API contract, same behavior, now durable across restarts. This step also replaces the demo seed data with a curated set and changes when seeding runs. Read AGENTS.md, backend/README.md, app/db/store.py, app/db/seed.py, and the existing models and routers first so the swap preserves current behavior exactly.

STORAGE SWAP
- Add SQLAlchemy and the SQLite driver as backend deps via uv. Use the SQLAlchemy ORM with a standard FastAPI session dependency injected into routers.
- Keep the db/ seam the routers depend on. The routers currently depend on get_store; the swap should touch the store/session layer and its wiring, not rewrite router logic. Preserve the exact ownership-scoping behavior: every project and note query scoped to the authenticated user; 404 (not 403) for another user's data.
- Define ORM models for users, auth_identities, projects, and notes, matching the current dataclasses and the spec's data model. Keep the JSON/API shapes identical (camelCase responses unchanged). This is a storage swap, not a contract change.
- Preserve the "touch parent project on note add/delete" behavior (updatedAt bump) that the dashboard's recently-updated sort depends on. The current code reuses update_project with no fields as the touch primitive; keep that behavior working however it's expressed against the DB.

DATABASE-AGNOSTIC (important — this is what keeps Postgres a drop-in later)
- Do NOT use any SQLite-only column types or behaviors. Choose SQLAlchemy types that map cleanly to both SQLite and Postgres for every field, especially: UUID ids, timezone-aware timestamps, the tags array, the links JSON, and the status enum. Where SQLite and Postgres differ, pick the portable option and note it.
- The database URL/path must come from config/env (a single settings source), not hardcoded in multiple places. Default to a local SQLite file for dev; the same code should accept a Postgres URL via env with no code change.
- Tell me explicitly anywhere you had to make a portability tradeoff, so I know what to watch when Postgres comes in.

SEED DATA (replace the current two-project seed entirely)
Seed the demo account (demo@hub.dev / demo1234) with these ten projects. Fill every field as specified; where a field is marked blank, leave it genuinely empty to show a raw/early-stage capture. Vary created/updated timestamps as described so the dashboard's "recently updated" and "stale / longest untouched" both have something to show (recent ones updated within days, stale ones untouched for months). Notes carry their own realistic timestamps.

1. "Dial in a sourdough starter" — status Parked; tags cooking, hobby; excitement 2, effort 2, potential 2; pitch "Keep a starter alive long enough to bake one good loaf."; description "Every attempt so far has died within two weeks. Want to actually understand hydration and feeding schedules instead of following recipes blindly."; next action "Buy a kitchen scale and try the no-discard method."; no target date; no links; old/stale dates. Notes: "Third attempt died. Maybe the kitchen's too cold. Revisit in winter."

2. "Etsy shop for my prints" — status Exploring; tags creative, side-hustle, art; excitement 4, effort 3, potential 3; pitch "Turn the illustrations I already make into a tiny income stream."; description "I've got a backlog of prints sitting in a folder. Test whether anyone would actually pay for them before investing in inventory."; next action "List the first three prints and see if anything sells in a month."; no target date; links: {label "Seller guide", url https://www.etsy.com/seller-handbook}, {no label, url https://www.pinterest.com}. Notes (spread over weeks): "Ordered sample prints to check quality" / "Shipping costs are brutal for large sizes, maybe stick to A4/A5" / "Name idea: 'Second Sun Studio'?"

3. "Automate my budgeting spreadsheet" — status Active; tags finance, productivity; excitement 3, effort 4, potential 4; pitch "Stop manually typing every transaction into a sheet I abandon by March."; description "The tracking always dies because entry is tedious. If categorization were automatic I might actually stick with it."; next action "Figure out how to import the bank CSV and auto-categorize."; target date ~3 weeks out; links: {label "Template", url https://docs.google.com/spreadsheets}; recent dates. Notes: "Categorize transactions automatically, look into bank CSV export" / "Manual entry is the thing I always give up on, fix that first"

4. "Train for a half-marathon" — status Active; tags health, running, fitness; excitement 5, effort 4, potential 3; pitch "Go from couch-ish to 21k without wrecking my knees."; description "Signed up already so there's no backing out. Need a structured plan rather than just running randomly until something hurts."; next action "Do the week 4 long run this weekend."; target date ~10 weeks out; links: {label "Race day", url https://www.runsignup.com}, {label "12-week plan", url https://www.halhigdon.com}; recent dates. Notes: "Week 3 done, knee held up fine" / "Need better shoes before mileage ramps"

5. "Pivot into UX design" — status Exploring; tags career, learning, design; excitement 5, effort 5, potential 4; pitch "Move from my current role into UX within a year."; description "I keep gravitating toward the design side of every project. Want to test whether it's a real career move or just a grass-is-greener thing, before committing money to it."; next action "Finish the first module of the UX cert and redesign one app as a case study."; target date ~6 months out; links: {label "Course", url https://www.coursera.org}, {no label, url https://www.behance.net}. Notes (the most-noted, a heavily-worked idea): "Talked to Priya who made the switch, coffee notes: portfolio > credentials" / "Started the Google UX cert" / "Redesign a real app as a case study, pick something I use daily" / "Imposter feelings are loud but the work is genuinely fun"

6. "Build my portfolio site" — status Inbox; tags web, career; excitement 3, effort 3, potential 3; pitch blank; description "Need a personal site. Nothing more than that yet."; next action blank; no target date; no links; created very recently, untouched since. No notes.

7. "Read 24 books this year" — status Active; tags reading, habit; excitement 4, effort 2, potential 3; pitch "Two books a month, actually finished, not just started."; description "I buy books faster than I read them. A visible count might keep me honest."; next action "Pick the next book tonight instead of doom-scrolling."; target date end of this year; links: {label "Reading list", url https://www.thestorygraph.com}. Notes: "9 down, ahead of pace. Next: that sci-fi everyone won't shut up about."

8. "Learn enough Spanish for the trip" — status Parked; tags language, learning, travel; excitement 4, effort 3, potential 2; pitch "Order food and ask directions without switching to English."; description "Not aiming for fluency, just enough to be polite and get around. Keeps stalling because app streaks aren't the same as talking."; next action "Book a few italki conversation sessions."; target date ~4 months out; links: {no label, url https://www.duolingo.com}, {label "Podcast", url https://www.duolingo.com/podcast}; somewhat stale. Notes: "Duolingo streak died at 12 days lol" / "Actually need conversation practice, not more app streaks"

9. "Start a podcast with the group chat" — status Killed; tags creative, audio; excitement 2, effort 4, potential 2; pitch "A casual weekly podcast with the friends."; description "Fun in theory. In practice nobody can commit to a schedule and I'd end up doing all the editing."; next action blank; no target date; no links. Notes: "Everyone's excited for exactly one weekend then vanishes" / "Killing this. Fun idea, zero follow-through from anyone including me."

10. "Declutter and sell old furniture" — status Graduated; tags home, minimalism; excitement 3, effort 3, potential 3; pitch "Clear out the stuff I don't use and make a little cash doing it."; description "Moving soon-ish and half this furniture isn't coming with me. Sell what's worth selling, donate the rest."; next action blank; no target date; links: {label "Listings", url https://www.facebook.com/marketplace}. Notes: "Sold the desk and the bookshelf, $180 total" / "Done. Apartment feels twice as big. Worth it."

SEEDING BEHAVIOR
- Seed only when the database is empty (no users). A fresh DB gets the demo account and these ten projects; an existing DB is never re-seeded, duplicated, or overwritten on restart. Keep the seeded credentials in the README.

MIGRATIONS
- For v1, create tables on startup if they don't exist (no Alembic needed yet). Tell me explicitly that's what you did, so the story for future schema changes is clear.

TESTING
- The existing suite (23 passing) must still pass against the new storage. Rework the fixtures so each test runs against its own fresh, isolated database (in-memory SQLite or a temp file per test), never a shared dev DB and never the developer's real data. Confirm the isolation tests still genuinely test cross-user isolation.
- Report the test count and confirm all green.

VERIFICATION (both servers running)
- Persistence across restart is the whole point: log in, create a project and a note, restart the backend, log back in, confirm they're still there.
- Confirm the demo seed appears on a fresh (empty) database and is NOT duplicated when the backend restarts on an existing database.
- Confirm the dashboard's recently-updated sort still bumps on note add/delete (the touch behavior survived the swap), and that the ten seeded projects display across all six statuses with their varied scores, dates, links, and notes.
- If the Chrome extension is flaky, say what you couldn't verify visually rather than claiming it.

Keep frontend lint/type checks clean if you touch the frontend (you likely won't), and keep the backend tests green. Report what you built, the session and table-creation approach, every portability tradeoff you made, and anything that didn't line up. Don't commit, I'll review.

## 8

Harden the backend's auth/config for deployment readiness, Tier 1 only: move secrets and security-relevant settings into the existing config module and make unsafe defaults impossible to ship, while keeping local development frictionless. Do not add rate-limiting or account caps in this step (those are deferred to pre-deploy). Read app/core/config.py, app/auth/security.py, AGENTS.md, and backend/README.md first.

Requirements:
- Move all security-relevant settings into app/core/config.py as the single source: the JWT signing secret, the token expiry, and the argon2/password-hashing parameters if any are currently hardcoded. Nothing security-relevant should be hardcoded in security.py anymore; it should read from config.
- Keep local dev frictionless: running locally with no extra setup must still work exactly as it does now. A dev fallback for the JWT secret is fine ONLY in a local context.
- Make unsafe defaults impossible in production: introduce an environment indicator (e.g. an ENV / ENVIRONMENT setting, defaulting to "local"/"development"). When the environment is NOT local, the app must refuse to start (raise on startup) if the JWT secret is unset or is still the known dev fallback value. Locally, it falls back with at most a printed warning. The goal: it is impossible to run in production on the insecure default secret, but a developer never has to configure anything to run locally.
- Document the env vars: update backend/README.md and backend/.env.example (create it if absent) with every config var, its default, and which ones MUST be set in production (the JWT secret especially). Make clear local dev needs none of them.
- Keep the DATABASE_URL config that already exists consistent with this pattern (it should live in the same settings module).

Testing:
- Existing suite (24) must still pass.
- Add tests for the new guard: the app/config refuses to start (or the check function raises) when environment is production and the secret is missing or is the dev default; and it does NOT raise in local/dev with the fallback. Don't hardcode the real secret in tests.
- Report the test count.

Verification:
- Confirm the backend still starts and runs locally with no env vars set (frictionless dev preserved), seeded demo login still works.
- Confirm that simulating a production environment without a secret set fails fast with a clear error, and that setting the secret makes it start.
- Confirm nothing security-relevant remains hardcoded in security.py.

Do not touch the frontend. Keep backend tests green. Report what moved into config, how the prod guard works, the exact env vars and their defaults, and anything that didn't line up. Don't commit, I'll review.

## 9

```
Add real error handling to the frontend's write and load paths, surface load errors to the user, and unify the optimistic-update strategy. These are related concerns in the same layer, do them together. Read the store (store.tsx), the api layer (services/api/), the components that trigger writes (project-detail.tsx, notes-panel.tsx, quick-capture, dashboard), and the tech-debt file's Robustness and write-optimism entries first.

Context: writes now hit a real backend over HTTP and can genuinely fail (network error, expired token, a slow cold-start on scale-to-zero hosting). Today the store's createProject/updateProject/deleteProject and the note calls have no error handling, and several are fire-and-forget (void save(...)). The store also tracks an `error` state that no component reads, so a failed load shows the user nothing. And there are two different optimistic-update conventions: note deletion updates local state before the API resolves, while project field edits wait for the call to resolve.

Do:
- Error handling on write paths: createProject/updateProject/deleteProject and the note add/delete calls should handle a failed request instead of silently doing nothing or throwing an unhandled rejection. On failure, the user should see a clear, non-technical message (a toast/inline error consistent with the app's style), and the UI should not be left showing a change that didn't actually persist.
- Surface load errors: the store's `error` state should actually be read and shown when a load fails (e.g. the dashboard failing to fetch projects should show an error state with a way to retry, not a silent empty screen). If the existing `error` field is the right mechanism, use it; if it needs adjusting, adjust it.
- Unify optimistic updates: pick ONE convention for all writes and apply it consistently. Decide between optimistic (update UI immediately, roll back on failure) and pessimistic (wait for the server, then update). Tell me which you chose and why. Whichever it is, a failed write must leave the UI in a correct state (either rolled back, or never optimistically changed), never showing data that didn't save. This resolves the two-strategies inconsistency in the tech-debt file.
- Handle the already-built 401 path consistently with the above (an expired token mid-write should route to login, as it already does, not show a generic error).

Verification:
- Simulate failures, not just happy path: with the backend stopped (or a request forced to fail), confirm a failed create/edit/delete shows a clear error and doesn't leave a phantom change in the UI, and a failed initial load shows an error state with retry rather than a blank/empty dashboard. Then confirm all of it works normally against the running backend.
- If the Chrome extension is available, verify visually; if not, say what you couldn't check.
- Keep lint 0/0, tsc and build clean.

Report what you changed, which optimistic-update convention you standardized on and why, and how errors now surface to the user. Update the tech-debt file to remove the Robustness and write-optimism entries now that they're addressed. Don't commit, I'll review.
```