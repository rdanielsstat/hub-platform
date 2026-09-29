# Prompts

## v0.app front-end specification

This prompt was given to v0 to scaffold the initial site. It is not part of the Claude Code session.

```
Build a frontend for "hub platform" — a personal platform to capture, organize, and triage project ideas, from small to big, where ideas can be parked, held, or graduated into standalone builds. Full spec below.

[link text](./specs.md)

Requirements:

- Use React with Vite, Tailwind, and shadcn/ui. Do NOT use Next.js — this is a standalone SPA that will be exported and built out separately.
- Centralize every backend call in a single services/api layer, with a mock implementation (in-memory, using the seed projects from the spec) so the whole app runs with no real backend. All components import from this layer, never call fetch directly.
- Make it interactive: I should be able to use the main features from the spec (dashboard with filter/sort, quick capture, project detail with editing, notes, status changes).
- Design: beautiful, sleek, minimalist, simple by default. Responsive for phone and desktop.
- Seed the mock data with the project list from the spec so the dashboard isn't empty on first load.
```

---

## Claude Code prompts

### 1

```
There is a hub-platform-frontend.zip file in the base project folder. First, extract it so its contents are in the project root (it unzips to loose files: package.json, src/, components/, services/, etc.). This is a Vite + React + TypeScript frontend that was started in v0 and left incomplete.

Read the spec at _docs/specs.md first for the full context. Then:

1. Get it running: pnpm install then pnpm dev. Fix any install or build errors (dependencies are React 19 / Tailwind v4 / @base-ui, watch for version issues).
2. There's a missing file: App.tsx imports pages/project-detail.tsx which doesn't exist. Build that project-detail page to match the spec (all fields editable, status, scores, notes log, links, next action shown at top), using the existing components and the services/api layer.
3. Clean up leftover v0/Next.js cruft: fix components.json (rsc should be false, css path is wrong), remove unused public/ placeholder files.
4. Confirm the whole app runs against the mock API with the seeded projects showing on the dashboard, and every data call goes through services/api, never direct fetch.

Don't restructure what's already working. The services/api mock layer and the existing components are good, build on them.
```

### 2

```
find and remove every em dash across the whole project, replacing each with a colon, period, or comma as reads best in context, and check index.html, all components, and pages
```

### 3

```
great, i changed a couple back but mostly left these, it's great. now

In the app header (likely components/layout/app-header.tsx), remove the "h" avatar tile and put a single small filled dot to the left of the "hub" wordmark as an accent mark. Use the existing purple/primary theme token for the dot so it stays theme-aware in light and dark mode. Keep the lowercase "hub" wordmark and the "capture · triage · graduate" tagline. Don't change anything else.
```

### 4

```
In the app header (components/layout/app-header.tsx), remove the accent dot to the left of the wordmark entirely, so there's no mark or tile, just the wordmark and tagline. Change the wordmark from lowercase "hub" to capitalized "Hub". Keep the "capture · triage · graduate" tagline beneath it, and adjust spacing so the text sits cleanly without the dot. Don't change anything else in the header.
```

### 5

```
In the app header (components/layout/app-header.tsx), capitalize the tagline to "Capture · Triage · Graduate" (all three words). Don't change anything else.
```

### 6

```
In the app header (components/layout/app-header.tsx), change the wordmark "Hub" to lowercase "hub" and the tagline to lowercase "capture · triage · graduate". Don't change anything else.
```

### 7

```
Do a read-only review of this codebase and report your findings without changing any files yet. Cover:

Correctness: run pnpm build and tsc and report any type errors or build warnings. Check for any runtime errors in the components.
Consistency: look for inconsistencies in naming, formatting, casing of user-visible text, component patterns, and how data flows through the store and services/api layer. Flag anything that deviates from the patterns used elsewhere.
Dead code and cruft: unused imports, unused components, leftover v0/Next.js artifacts, unreferenced files, commented-out blocks.
Spec alignment: compare the app against _docs/specs.md and note anything missing, incomplete, or diverging from the spec.
Anything risky or fragile you'd want to fix before building further.

Give me a categorized list, ordered by severity, with the file and line for each item. Don't fix anything yet, I want to review the list and decide what to act on.
```

### 8

```
This is batch one of a cleanup pass, from the review you did earlier. Work only on the items below, then stop. Don't touch anything not listed here.

1. Set up ESLint + Prettier for this Vite + React 19 + TypeScript project, using current standard configs for this stack. Add the config files, add the needed devDependencies, and add lint and format scripts to package.json. Configure them to agree with the existing code style (2-space indent, single quotes, no semicolons, as the codebase already uses) so this doesn't reformat everything into a huge diff. Run the linter and report what it finds, but only auto-fix formatting/style, do not make behavioral changes.

2. Remove dead code (from the review):

components/ui/badge.tsx (Badge, never used)
components/score-meter.tsx (ScoreMeter export, never rendered, but ScorePicker in the same file IS used, keep ScorePicker)
lib/project-utils.ts isActionable (never called)
the "hooks": "@/hooks" alias in components.json (points at a non-existent dir)
Do NOT remove components/ui/card.tsx, I'm keeping it for a later consistency fix.
Before removing each item, grep to confirm it's truly unreferenced. If anything is actually used, leave it and tell me.

3. Add a favicon. The public/ folder was removed earlier so the tab has no icon. Add a simple favicon (an SVG favicon is fine) and reference it in index.html. Keep it minimal and theme-neutral.

When done: run pnpm build and tsc to confirm everything still passes, run the new linter to confirm it's clean, and give me a short summary of what changed. Don't commit, I'll review and commit myself.
```

### 9

```
This is the lint-cleanup batch. Goal: get pnpm lint to pass with zero errors and zero warnings, without disabling rules wholesale or making changes that alter behavior. Work through each finding individually and stop when lint is green.

The 3 react-hooks/set-state-in-effect errors (notes-panel.tsx:16, project-detail.tsx:40, store.tsx:49): evaluate each one separately, don't treat them as identical.

For each, first decide whether the value can be derived during render instead of held in state + synced via effect (the rule's preferred fix). If a clean derivation is possible without changing behavior, do that.
If the effect is a genuine external-data synchronization (e.g. the store's initial fetch-on-mount) where the effect is correct and necessary, keep it and add a targeted // eslint-disable-next-line with a brief comment explaining why it's intentional. Do NOT disable the rule globally.
Tell me, per case, which approach you took and why.

The exhaustive-deps warning (project-detail.tsx:44): the effect intentionally depends on project?.id rather than project. Add a targeted disable-next-line with a one-line comment documenting that this is deliberate.

The 2 react-refresh/only-export-components warnings (dashboard-toolbar.tsx:14, button.tsx:58): these fire because each file exports a component plus a non-component (a constant/variant helper). Fix properly by moving the non-component export into a separate file and updating imports, so Fast Refresh works. If moving it is genuinely impractical for a given file, fall back to a targeted disable-next-line with a comment, but prefer the split.

When done: run pnpm lint (must be clean), pnpm build, and tsc (both must pass), and confirm the app still runs. Give me a per-item summary of what you did. Don't commit, I'll review and commit.
```

### 10

```
On the project-detail page, the next-action field (the pinned callout at the top) doesn't wrap long text, on narrow/mobile widths it overflows instead of wrapping to multiple lines. Fix it so the text wraps properly at all widths. Check whether it's a missing wrap/break style, a flex child that needs min-width:0, or a whitespace/nowrap issue, and fix the actual cause. Verify at 320px, 375px, and 390px widths that long next-action text wraps cleanly with no horizontal overflow. Don't change anything else.
```

### 11

```
This is batch 3, two small fixes from the earlier review. Do only these, then stop.

1. Note deletion needs a confirmation step. Currently deleting a note (components/detail/notes-panel.tsx) is instant with no confirmation, while deleting a project uses a two-step confirm (the confirmingDelete pattern in pages/project-detail.tsx). Make note deletion consistent with that: require an explicit confirm before it deletes, following the same interaction pattern already used for project deletion so it feels consistent. Don't invent a new pattern, match the existing one.

2. The Quick Capture dialog has no focus trap. The hand-rolled dialog (components/ui/dialog.tsx) doesn't trap focus, Tab currently moves focus out of the open dialog into the page behind it, and the backdrop isn't marked inert/aria-hidden. @base-ui/react is already a dependency and its dialog primitive handles this correctly. Either adopt the @base-ui dialog primitive for focus management, or add proper focus trapping + inert backdrop to the existing dialog, whichever is cleaner and less disruptive to the current dialog's look and API. Keep the dialog's current appearance and behavior otherwise.

When done: run pnpm lint (must stay 0/0), tsc, and pnpm build (both clean), verify the app runs, and confirm both fixes work (note delete now asks for confirmation; Tab stays within the open dialog). Don't commit, I'll review.
```

### 12

```
Bug: on the project-detail page, clicking into an editable field and then leaving it (blur) without changing anything still triggers a save, which updates the project's updatedAt and incorrectly bumps it to the top of the dashboard's "recently updated" sort. A no-op (unchanged) blur should not save.

Fix it so each editable field only calls save on blur when its value has actually changed from the project's currently-stored value for that field. Apply this to all the blur-saved fields on this page (name, pitch, description, next action, and any others using the same on-blur save pattern), so touching a field without editing it does nothing.

Make sure a real change still saves normally, and confirm an unchanged blur does NOT change updatedAt. Keep lint at 0/0, tsc and build clean. Only touch what's needed for this. Don't commit.
```

### 13

```
Read this project's Claude Code session transcript(s), extract every prompt I (the user) sent, in order, and write them to _docs/prompts_cc.md as a numbered list, each prompt in a code block, with nothing of your own responses, just my prompts verbatim. If there are multiple sessions, separate them with headers.
```

### 14

```
Refactor the project's folder structure to the conventional Vite layout: move all application source into src/. Currently components/, lib/, pages/, services/, store.tsx, store-context.ts, and use-store.ts live at the repo root instead of under src/, a leftover from the v0/Next.js origin. Consolidate them under src/.

Requirements:
- Move components/, lib/, pages/, services/, store.tsx, store-context.ts, and use-store.ts into src/. Use git mv so history is preserved.
- Update the @/* path alias so it resolves to src/ instead of the repo root: in tsconfig.json (the paths mapping) and in vite.config.ts (the resolve alias). After this, @/ should point at src/.
- Update tsconfig.json's include list, since the root-level entries (store.tsx, etc.) no longer exist at root.
- Update any other config that references these paths: components.json (shadcn aliases / css path), .prettierignore, eslint.config.js ignores, anything else that hardcodes the old locations.
- Because everything imports via the @/ alias, most import statements shouldn't need changing, but check for any relative imports or hardcoded paths that break, and fix them.
- Leave public/, index.html, _docs/, and the root config files where they are, those belong at root.

When done: run pnpm install (in case anything path-related needs it), pnpm lint (must stay 0/0), tsc, and pnpm build (both clean), and run the app to confirm it still works. Report exactly what moved and what config changed. Don't commit, I'll review and commit.
```

### 15

```
Refactor the repo so the entire frontend application lives in a frontend/ subfolder at the repo root, in preparation for adding a backend/ alongside it. Right now the frontend sits directly at the repo root.

First inspect the current layout so you move the right things. Then:

- Move all frontend files and folders into frontend/ using git mv to preserve history: src/, public/, index.html, package.json, pnpm-lock.yaml, pnpm-workspace.yaml, tsconfig.json (and any other tsconfig.*.json), vite.config.ts, eslint.config.js, .prettierrc.json, .prettierignore, components.json, and any other frontend-specific config.
- Leave at the repo root: _docs/ and the root .gitignore.
- Do NOT move node_modules with git (it's gitignored); instead, after moving, reinstall inside frontend/ with pnpm install so it rebuilds in the new location.
- Handle .gitignore correctly for the new structure: the frontend's ignores (node_modules, dist, *.tsbuildinfo) should apply inside frontend/. Either add a frontend/.gitignore for those, or update the root .gitignore paths to be frontend/-scoped, whichever is cleaner. Keep repo-wide ignores at root.
- Check every config for paths that break when the app moves down a level: tsconfig paths/include, vite config, index.html's script src, components.json, and fix any that assumed the old root location. The @/ alias should still resolve to frontend/src.
- Confirm .prettierignore and eslint.config.js still target the right paths from inside frontend/.

When done: from inside frontend/, run pnpm install, pnpm lint (must stay 0/0), tsc, and pnpm build (both clean), and run the app to confirm it still works. Report exactly what moved and what config changed. Don't commit, I'll review and commit.
```

### 16

```
Right now the dashboard's "recently updated" sort only bumps a project's updatedAt when the project's own fields are edited. Adding or deleting a note writes to the note but doesn't bump the parent project, so actively-worked projects look stale.

Make changes to a project's child records bump the parent project's updatedAt. Currently that means note creation and note deletion. Implement it wherever these mutations are handled so the bump is applied consistently rather than per-component.

First look at how the store/services layer is actually structured and tell me where you're putting this. Don't assume a central seam exists if it doesn't.

Do not regress the existing no-op behavior: only a real change bumps updatedAt. The no-op blur fix for project fields must stay intact.

Note for future awareness: attachments aren't built yet, but when they are, the same rule should apply, creating or deleting an attachment should bump the parent project too. If there's a natural place to handle this centrally so attachments are covered automatically when added, prefer that; if not, just flag that the attachment feature will need to apply this same bump when it's built.

Verify: adding a note moves its project to the top of the recently-updated sort, deleting a note does too, a real project-field edit still bumps, and a no-op blur still doesn't. Keep lint at 0/0, tsc and build clean. Don't commit, I'll review.
```

### 17

```
Create an AGENTS.md at the repo root: standing instructions for AI coding agents working in this project. First inspect the repo (folder layout, frontend/package.json, existing config) so the contents are accurate rather than assumed. Keep it concise and factual, this is a reference agents read every session, not a spec.

Include:

Project: one or two lines on what this is (hub, a platform to capture, organize, and triage project ideas). Point to _docs/specs.md as the source of truth for the product and data model rather than duplicating it.

Structure: the actual layout after inspecting. Frontend app lives in frontend/ (with its own src/, config, etc.). Backend will live in backend/ (not built yet). Shared docs in _docs/.

Frontend stack & commands: Vite + React 19 + TypeScript, Tailwind v4, shadcn/ui, @base-ui/react, pnpm. The real scripts from frontend/package.json (dev, build, lint, format), noting they run from inside frontend/. Note the @/ alias points at frontend/src, and that all data access goes through frontend/src/services/api/ (never direct fetch).

Backend (planned, not built): FastAPI in backend/, Python deps via uv. Starts on an in-memory store, then SQLite via SQLAlchemy kept database-agnostic for later Postgres. Auth is roll-your-own (password hashing + JWT bearer tokens, OAuth2 password flow), token-based so the same API serves web and a future iOS app. Multi-user with per-user data isolation. Mark this section clearly as intended/planned since the folder doesn't exist yet.

Working conventions: commit regularly; keep changes small and scoped; run lint/typecheck/build and confirm clean before considering a task done; don't commit unless asked; match existing code style (ESLint/Prettier configured, must stay 0/0).

Do-not: don't restructure working code without being asked; don't add dependencies casually; don't reproduce or edit _docs/ planning files as if they were code.

After creating it, show it to me so I can adjust. Don't commit.
```

### 18

```
Read _docs/specs.md fully, then read the frontend's API client in frontend/src/services/api/ (types.ts, mock.ts, seed.ts, index.ts) to understand exactly what the frontend expects: the entities, fields, endpoints, and the shape of every request and response it makes.

Create openapi.yaml at the repository root: the explicit API contract the backend must implement.

Specify every endpoint, method, path, request body, response body, and which endpoints require authentication, derived from what the frontend's API client actually calls. Match the data model in the spec (users, auth_identities, projects, notes, attachments; the status enum; the 1-5 score fields; per-user ownership).

Don't build the backend yet, just the contract. When done, walk me through the endpoints you defined and flag anywhere the frontend's expectations and the spec's data model don't line up, so we resolve mismatches before writing any backend code.
you can read agents.md for more context too
```

### 19

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

### 20

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

### 21

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

### 22

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

### 23

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

### 24

```
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
```

### 25

```
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
```

### 26

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

### 27

```
Fix dark mode so the theme choice persists and behaves correctly. Right now the theme resets to light on every reload and ignores the user's system preference, and the theme-color meta tag is static so it doesn't follow the toggle. Read the current theme handling first (it lives in components/layout/app-header.tsx's useTheme hook, and check index.html for the theme-color meta and any theme setup, and main.tsx / index.css for where theme class is applied) before changing anything, so you fix the actual mechanism rather than adding a parallel one.

Do:
- Persist the theme choice across reloads (localStorage, wrapped in try/catch so it degrades gracefully if storage is unavailable).
- On first load with no stored choice, respect the system preference (prefers-color-scheme) instead of defaulting to light. A stored explicit choice always wins over the system preference.
- Apply the resolved theme before first paint so there's no flash of the wrong theme on load (the common approach is a tiny inline script in index.html that sets the theme class on <html> before the app mounts — do whatever avoids the flash cleanly).
- Make the <meta name="theme-color"> follow the current theme so the mobile browser chrome matches light/dark, and update it when the theme toggles, not just on load.
- Keep the existing toggle control and its behavior; this is about persistence, system-preference, and no-flash, not redesigning the toggle.

Verification:
- Toggle to dark, reload → stays dark. Toggle to light, reload → stays light.
- Clear the stored preference and load with the OS set to dark → app starts in dark; with OS light → starts light.
- Confirm there's no flash of the wrong theme on reload.
- Confirm the theme-color meta actually changes when toggling (check the tag's value updates).
- If the Chrome extension is available, verify visually in both modes; if not, say what you couldn't check.
- Keep lint 0/0, tsc and build clean.

Report what the theme mechanism looks like now and anything that didn't line up. Don't commit, I'll review.
```

### 28

```
This is a consistency cleanup batch from the tech-debt file. Work through the items below one at a time, in order. After each item, run lint (must stay 0/0), tsc, and build (both clean) before moving to the next, so a regression is caught at the item that caused it, not at the end. These are pattern-alignment changes to existing working code: do not change behavior, only align to patterns already used elsewhere in the codebase. Read each relevant file before changing it, and grep to confirm usages before removing or replacing anything.

Item 1 — Shared empty/error-state component.
There are now four near-identical empty/error-state layouts: the not-found page, the dashboard empty state, the dashboard load-error state (with retry), and project-detail's not-found/load-error branches. Extract one reusable component that covers both the plain-empty shape and the error-with-retry shape (e.g. an optional retry action and an icon/title/message), and replace all four call sites with it. Keep each call site's current wording, icon, and behavior identical — this is deduplication, not a redesign. Confirm all four still render and the retry buttons still work.

Item 2 — Back-to-dashboard button.
project-detail hand-rolls its back button with raw classes instead of using buttonVariants, so it misses the hover/focus-visible/transition states the real button variants have. Replace it with the proper buttonVariants (matching whatever ghost/link variant fits its current look) so it gains the standard interaction states. Keep it looking essentially the same, just properly styled via the shared variants.

Item 3 — Rating widget.
There are multiple rating-widget implementations with diverging aria patterns (ScorePicker vs RatingInput). Standardize on one. First inspect both, tell me which you're keeping and why (keep the one that's more complete/accessible), then migrate all usages to it and remove the other. Confirm the scores still display and edit correctly everywhere they're used, and that the kept one's aria pattern is sound.

Item 4 — Card primitive.
project-detail's section cards reuse the border/bg recipe by hand but drop shadow-sm and don't use the Card primitive (this is why card.tsx was kept). Migrate those sections to the Card primitive so they match the rest of the app's card styling. Keep the layout intact; this is about using the shared primitive and regaining the consistent shadow, not restructuring the sections.

Item 5 — Dead fallback branches.
Remove the two unreachable branches: formatDate's null-iso return in lib/project-utils.ts, and the ': "-"' (now empty-string) else in the due useMemo in project-detail.tsx. Both are guarded against by callers, confirm that's still true before removing. Also address the "no date" placeholder note in the tech-debt file's Notes section while you're in these files: decide with me — actually, leave that one as-is and just flag it, since it's a product decision (what to show when there's no date) not a cleanup.

After all five: run the full check suite once more, do a click-through of the affected screens (dashboard empty, dashboard normal, a project detail, the not-found page) to confirm nothing looks or behaves differently except the intended shadow/interaction-state gains. If the Chrome extension is available verify visually; if not, say what you couldn't check. Update the tech-debt file to remove the entries you resolved (items 1-5's consistency entries), leaving the placeholder note.

Report per-item what you changed, which rating widget you kept and why, and anything that didn't line up. Don't commit, I'll review.
```

### 29

```
Add "stale" and "quick win" badges to project cards on the dashboard, per spec §4.2 (surface what's gone stale and high-excitement/low-effort picks). This is a new, small feature built on the now-clean card and component patterns. Read the dashboard (dashboard.tsx), the project card (components/project-card.tsx), the status badge (components/status-badge.tsx) for the existing badge pattern, and lib/project-utils.ts (which already has daysUntil / opportunityScore helpers) before building.

Definitions (use exactly these):
- Quick win: excitement >= 4 AND effort <= 2. Only for open statuses (Inbox, Exploring, Active) — a Killed/Graduated/Parked project isn't a "win to grab," so don't badge those.
- Stale: not updated in 30+ days (updatedAt older than 30 days from now). Only for statuses where going cold is a problem: Active and Exploring. Do NOT mark Inbox, Parked, Killed, or Graduated as stale — Parked/Killed/Graduated are intentionally at rest, and a brand-new Inbox capture being old isn't the same signal. (Active/Exploring are the "supposed to be moving" states.)

Build:
- Add two small pure helper functions to lib/project-utils.ts: isStale(project) and isQuickWin(project), implementing exactly the definitions above. Keep them pure and unit-testable (take a project, return boolean; base "now" on Date so they're testable, or accept an optional now param).
- Add badges to the project card, using the SAME visual badge pattern already used for status (status-badge.tsx) so they look native, not bolted on. A "Quick win" badge and a "Stale" badge. A project can have both, one, or neither. Keep them visually distinct from the status badge and from each other (e.g. quick win reads positive, stale reads as a gentle attention cue — not alarming, this is a nudge not an error). Don't overload the card; badges should be compact.
- These are indicators only in this step — no new filter or sort. (Sorting already exists; this is the "surface it visibly" part of the spec, not a new control.)

Testing:
- Add unit tests for isStale and isQuickWin covering: quick win true/false around the excitement/effort thresholds; quick win NOT applied to closed statuses; stale true/false around the 30-day boundary; stale NOT applied to Inbox/Parked/Killed/Graduated; a project that is both; a project that is neither. Use a fixed/injected "now" so the 30-day boundary tests are deterministic. (These are frontend helpers — put them wherever the frontend's tests live; if there's no frontend test setup yet, tell me before adding one rather than pulling in a whole test framework unprompted.)

Verification:
- The seed data is designed to exercise this: "Train for a half-marathon" and "Pivot into UX design" should show quick-win-ish / active signals, and the deliberately-stale ones ("Dial in a sourdough starter" is Parked so should NOT be stale; check which Active/Exploring seed projects cross 30 days). Confirm in the browser that the right projects show the right badges and the wrong ones don't — especially that Parked/Killed/Graduated never show "stale."
- Confirm a project with both badges renders cleanly and a project with neither looks normal.
- If the Chrome extension is available, verify visually; if not, say what you couldn't check.
- Keep lint 0/0, tsc and build clean.

Report the helper logic, how the badges look, which seed projects ended up badged, and anything that didn't line up. Don't commit, I'll review.
```

### 30

```
Seed-data only (backend/app/db/seed.py). Don't touch any badge logic or frontend code. Check frontend/src/lib/project-utils.ts for the exact isStale/isQuickWin rules first.

Right now no seed project shows a stale badge and only one shows quick-win. Fix the demo to show both:
- Make one Active or Exploring project stale: set updatedAt to ~40 days ago.
- Make one Active or Exploring project show both badges: excitement >= 4, effort <= 2, and updatedAt ~40 days ago.
- Leave "Read 24 books this year" as the quick-win-only example.
- Keep all six statuses still represented; only change updatedAt/scores, and fix any note timestamps that end up newer than their backdated project.

The seed only runs on an empty database, so give me the command to recreate the local DB (delete the sqlite file + restart) and I'll run it myself. Tell me the resulting badge map. Don't commit.
```

### 31

```
Read-only review pass to confirm the project is in solid shape before deployment. Do NOT change any files in this task — this is a review that produces a report, and I'll decide what to act on. Read AGENTS.md and _docs/specs.md first for intent, then review the actual current state of both frontend/ and backend/.

Run the objective checks first and report results:
- Frontend: pnpm lint, tsc, pnpm build, pnpm test — report pass/fail and any output.
- Backend: uv run pytest — report the count and pass/fail.
Report exact results; if anything is not green, that's the top of the report.

Then do a read-only review covering:
- Correctness: any type errors, build warnings, obvious runtime risks, or logic that looks wrong. Check the frontend/backend contract still matches (the api layer's calls vs the FastAPI routes vs openapi.yaml) — flag any drift.
- Consistency: naming, formatting, patterns, user-visible text (casing, tone). Flag anything that diverges from patterns used elsewhere, since a consistency pass was recently done — note if anything slipped back.
- Dead code / cruft: unused imports, unused exports, unreferenced files, leftover debug code, commented-out blocks, stray console logs.
- Spec alignment: compare the app against _docs/specs.md and note anything missing, incomplete, or diverging — but distinguish "genuinely missing" from "deliberately deferred" (attachments, PWA, Postgres, rate-limiting are known deferrals, not gaps; don't re-flag those as problems, just confirm they're the only deferrals).
- Security/robustness quick scan: anything obviously risky for a soon-to-be-deployed multi-user app that ISN'T already tracked in _docs/tech-debt.md. Cross-reference tech-debt.md so you don't re-report known items — only surface genuinely new findings.
- Tests: note any meaningful gaps in coverage for the critical paths (auth, per-user isolation, the badge/stale/quick-win logic), but don't treat exhaustive coverage as required.

Give me a categorized list ordered by severity, with file/line for each item, and for each: whether it's a real problem, a nice-to-have, or already tracked in tech-debt. Explicitly call out anything that should be fixed before deploy vs. anything that can wait. If the whole thing is genuinely in good shape, say so plainly rather than inventing issues to look thorough. Don't fix anything, don't commit.
```

### 32

```
Small cleanup batch from the pre-deploy review. Low-risk, verifiable. Read AGENTS.md, openapi.yaml, _docs/tech-debt.md, and the files named below before changing them.

1. Add a React error boundary so a render-time crash shows a graceful fallback instead of a white screen. Wrap the app (around the routed content in App.tsx, or at whatever level catches the whole rendered tree) in an error boundary component that renders a simple, on-brand "Something went wrong" fallback with a way to reload/return to the dashboard. Match the app's existing visual style (reuse the EmptyState component if it fits). This is the only real code change in this batch.

2. Delete two dead exports (grep to confirm zero references first, then remove):
- getStoredTheme() in frontend/src/lib/theme.ts (never called; app-header reads the DOM class directly).
- authApi.logout() in frontend/src/services/api/auth.ts (never called; the real logout path in auth.tsx duplicates the one-line clearToken()). Since auth.tsx duplicates it, prefer wiring auth.tsx to call authApi.logout() instead of deleting, if that's cleaner — your call, tell me which you did and why.

3. Fix doc drift (docs only, no code):
- AGENTS.md: the API layer is no longer an in-memory mock (services/api/mock.ts is gone); it's real HTTP via real.ts. Update that section to describe the actual current state.
- openapi.yaml: the top-level description still says "the backend does not exist yet" — it exists and matches this contract. Fix that line.
- _docs/tech-debt.md: remove the "Dashboard stale/quick-win surfacing" roadmap entry (shipped). Fix the Notes section's stale claim that the "no date" branches are "currently unreachable" (they were deleted); keep the underlying open product question (what to show when there's no date) but describe it accurately.

4. Add tech-debt entries for the two deploy-time items the review surfaced, so they're tracked deferrals not surprises:
- CORS origins are hardcoded to localhost in main.py; the deployed frontend origins (prod + staging) must be added there at deploy or all requests fail CORS.
- Observability: spec §2 calls for Sentry error tracking; not built. The error boundary (this batch) covers graceful frontend failure, but Sentry/backend error tracking is deferred to the deploy phase — record it as a deliberate deferral.

Do NOT touch: the register race condition, the void-consistency nits, the stats-row DRY item, or Link.url validation — those are for the later cleanup/security passes, not this batch.

Verify: frontend lint 0/0, tsc, build, and the existing tests still pass. Manually confirm the error boundary actually catches a thrown render error and shows the fallback (you can temporarily throw in a component to test, then remove it). Report what you changed, and for the dead-export item which approach you took. Don't commit, I'll review.
```

### 33

```
Add frontend unit/logic tests for the critical non-UI logic, using the existing Vitest setup. This pass is about the store, the auth flow, and any remaining pure logic — NOT component rendering or DOM interaction (that's a separate later pass, don't pull in React Testing Library or test components here). Read the files under test first: store.tsx, auth.tsx, services/api/ (index.ts, real.ts, auth.ts, http.ts, token.ts), lib/project-utils.ts, and the existing test (project-utils.test.ts) to match its conventions.

What to cover:

Store (store.tsx) — the highest-value target. Test its behavior by mocking the api layer (vi.mock the '@/services/api' module or inject a fake) so each test controls whether a call resolves or rejects, with no real backend. Cover:
- Initial load: populates projects on success; sets the error state on failure (and clears/handles loading correctly).
- Each write path (createProject, updateProject, deleteProject, addNote, deleteNote): on success, state updates correctly (created project added, updated project replaced, deleted removed, note add/delete bumps the parent project via the returned project); on failure, state is NOT changed (pessimistic — the whole point), the error is surfaced, and the call rejects/re-throws so callers can react.
- Confirm the pessimistic guarantee explicitly: a failed write leaves projects exactly as it was.

Auth (auth.tsx / auth flow) — mock authApi and the token storage. Cover:
- login: stores the token and sets the user/status to authenticated on success; surfaces an error and does not authenticate on failure (e.g. wrong password).
- register: analogous.
- logout: clears the token and resets to unauthenticated.
- On-mount token check: with a stored token that validates, ends authenticated; with a stored token that fails validation, ends unauthenticated and the token is cleared. (This is the logout-on-any-failure spot flagged in tech-debt — test the current behavior as it actually is; don't change it in this pass, just capture it so a later change is caught.)
- token.ts: get/set/clear round-trip, and that it degrades gracefully (no throw) if storage access throws.

http.ts — the request helper: attaches the bearer token when present and omits it when skipAuth; parses a FastAPI error detail into HttpError with the right status/message; invokes the onUnauthorized handler on a 401-with-token but not on other failures. Mock fetch for these.

Pure helpers — confirm project-utils.ts beyond isStale/isQuickWin (already covered): opportunityScore, daysUntil, formatRelative, formatDate, parseDateOnly — a few representative cases each, including boundary/null-ish inputs where the function accepts them.

Approach and quality bar:
- Mock at the module/dependency boundary (the api layer, authApi, fetch, localStorage), not by spinning up a backend. Tests must be deterministic and not depend on network, timers, or real storage — inject/fake anything time- or environment-dependent (reuse the injected-now pattern the existing helper tests use).
- Match the existing test file's style and location conventions.
- Test behavior, not implementation details — assert on outcomes (state, return values, thrown errors, calls made), not internal wiring, so the tests survive refactors.
- Do NOT change app code to make it testable unless something is genuinely untestable as written; if you hit that, stop and tell me what and why before changing it, rather than quietly refactoring app logic in a testing task.

When done: run pnpm test and report the count and that all pass; keep lint 0/0, tsc and build clean. Tell me what's covered, what you deliberately left for the component pass, and anything that was hard to test (which often points at a design worth revisiting). Don't commit, I'll review.
```

### 34

```
Add thorough component and user-flow tests for the frontend, using React Testing Library on top of the existing Vitest + jsdom setup. This is the deep UI-behavior pass. First read the earlier logic tests (store.test.tsx, auth.test.tsx, http.test.ts, project-utils.test.ts) and the render-hook helper to match conventions, then read every component/page you'll be testing before writing its tests.

Setup:
- Add React Testing Library (@testing-library/react, @testing-library/user-event, @testing-library/jest-dom) as devDependencies.
- Make jsdom the global default test environment in the Vitest config (the logic pass scoped it per-file; component tests need it everywhere). Remove the now-redundant per-file // @vitest-environment jsdom pragmas since the default covers them. Confirm the existing 71 tests still pass unchanged after this switch.
- Add a jest-dom setup file wired into the Vitest config so the custom matchers are available.
- Prefer user-event over fireEvent, and query by accessible role/label/text the way a user perceives the UI, not by test-ids or class names.

Quality bar — read this carefully, it matters more than the count:
- Test BEHAVIOR a user can observe and reach: what renders in each state, what happens on each interaction, what the user sees as a result. Assert on visible text, roles, labels, presence/absence of elements, and enabled/disabled state.
- Do NOT test styling, class names, colors, animation, exact DOM structure, or implementation details. If a purely cosmetic change would break the test, the test is wrong — rewrite it to assert behavior instead.
- Mock at the boundary (the api layer / authApi / fetch), never a real backend. Deterministic, no network, no real timers where they'd cause flakiness.
- Tests must survive refactors: assert outcomes, not internal wiring.

Per-screen / per-component coverage (thorough — every state and interaction):
- Login screen: renders; submitting valid credentials calls login and navigates/authenticates; wrong credentials shows a clear error; loading/disabled state during submit; link to signup works.
- Signup screen: renders; successful registration authenticates; "email already taken" shows the specific error; validation of required fields; loading state.
- Dashboard: all states — loading, error (with working retry), empty ("nothing captured yet"), no-matches (with clear-filters), and populated. Filtering by status, filtering by tag, search query, and sorting all actually change what's shown. The stale/quick-win badges render on the right cards.
- Project detail: renders a project's fields; editing a field and blurring saves (calls updateProject with the change) and an unchanged blur does NOT save (the no-op-blur behavior); status change, score changes, target date, tags add/remove, links add/remove (labeled and unlabeled); the next-action pinned display; delete requires the two-step confirm and then navigates; the not-found and load-error branches render.
- Quick capture: opens, validates, creates a project on submit, stays open with data intact on failure, closes on success; focus-trap behavior if feasible to assert.
- Notes panel: lists notes, adds a note (appears in list), delete requires confirm then removes; failure leaves the note in place (pessimistic).
- Error boundary: a child that throws renders the fallback instead of crashing.
- Any small presentational components with real conditional logic (status badge, indicator badges, stats row) — light coverage of the conditional behavior only.

Critical full-flow tests (a FEW, high-value only — not dozens):
- Auth → dashboard: unauthenticated user sees login; after logging in, lands on the dashboard showing their projects.
- Capture → see it → edit it: from the dashboard, quick-capture a project, see it appear, open it, edit a field, confirm the change persists in the UI.
- (Optional third if it's clean) note add → dashboard re-sort: add a note to a project and confirm the dashboard reflects the resulting recency change.
Keep these to the journeys that would genuinely hurt if they broke; don't turn every per-screen test into a flow test.

Rules:
- Do NOT change app code to make it testable unless something is genuinely untestable as written. If you hit that, STOP and tell me what and why before changing it — do not quietly refactor app logic in a testing task.
- If something is impractical to test well (e.g. focus-trap, some jsdom limitation), say so and skip it with a note rather than writing a weak or flaky test for it.

When done: run pnpm test and report the total count and that all pass (including the prior 71 still green); keep lint 0/0, tsc and build clean. Report what's covered per screen, which flows you added, anything you skipped and why, and anything that was hard to test (which may point at a design worth revisiting). Don't commit, I'll review.
```
