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
