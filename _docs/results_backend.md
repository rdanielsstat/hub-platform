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