# AGENTS.md

Standing instructions for AI coding agents working in this repo.

## Project

Hub: a personal platform to capture, organize, and triage project ideas, from
small sparks to standalone builds. See `_docs/specs.md` for the product spec
and data model. That document is the source of truth; don't duplicate it
here and don't let this file drift from it.

## Structure

- `frontend/`: the app. Vite + React SPA, self-contained (its own
  `package.json`, `src/`, config).
- `backend/`: the API. FastAPI app, self-contained (its own `pyproject.toml`,
  `app/`, `tests/`). See "Backend" below.
- `_docs/`: specs, planning notes, and session logs. Reference material, not
  code.
- `openapi.yaml` (repo root): the API contract frontend and backend are both
  built against.

## Frontend

Stack: Vite, React 19, TypeScript, Tailwind v4, shadcn/ui (`components.json`),
`@base-ui/react` for accessible primitives (dialogs, etc.), pnpm.

All commands run from inside `frontend/`:

```
pnpm install
pnpm dev            # start the dev server
pnpm build          # tsc -b && vite build, must be clean before calling a task done
pnpm lint           # eslint ., must stay 0 errors / 0 warnings
pnpm format         # prettier --write .
pnpm format:check   # prettier --check .
```

- The `@/` import alias resolves to `frontend/src` (set in both
  `tsconfig.json` and `vite.config.ts`).
- All data access goes through `frontend/src/services/api/`. Never call
  `fetch` directly from a component. That layer is real HTTP against the
  FastAPI backend (`services/api/real.ts`, via `http.ts`); it's the seam
  that would let a future consumer (native iOS, agents) swap in without
  touching components, so keep components talking to `api`/the store, not
  to the HTTP internals.

## Backend

FastAPI app in `backend/`, Python dependencies managed with `uv`.

```
uv sync                              # install, from inside backend/
SEED_DEMO_DATA=true uv run python -m app.db.init_local  # tables + demo data, once
uv run uvicorn app.main:app --reload # start the dev server (http://localhost:8000)
uv run pytest                        # run the test suite
```

- Storage: SQLite via SQLAlchemy (`app/db/`), kept database-agnostic so it
  can move to Postgres later via `DATABASE_URL` with no code change.
- Auth is roll-your-own: password hashing (argon2 via passlib) + JWT bearer
  tokens (PyJWT), OAuth2 password flow (`app/auth/`). Token-based so the same
  API can serve the web app and a future iOS app.
- Multi-user with per-user data isolation.
- `app/core/config.py` is the single settings source, read from environment
  variables with dev-safe defaults. Its `require_safe_jwt_secret()` runs at
  startup (`app/main.py`) and refuses to start outside a local `ENVIRONMENT`
  if `HUB_JWT_SECRET` is unset or still the built-in dev default.
- Importing the app does no database work. Locally, `uv run python -m
  app.db.init_local` creates tables and, with `SEED_DEMO_DATA=true`,
  seeds one demo account into an empty database (never re-seeds). It
  refuses to run with `USE_SSM` on (`app/db/init_local.py`).

See `backend/README.md` for the full setup, config table, and details.

## Testing

- Frontend: Vitest + React Testing Library, jsdom environment. `pnpm test`
  (from inside `frontend/`) runs `vitest run`.
  - This repo runs Vitest with `test.globals` off (tests import from
    `vitest` explicitly), so RTL's auto-cleanup doesn't kick in on its own;
    it's wired up by hand in `src/test-setup.ts`, which must stay.
  - `base-ui`'s `Dialog` keeps its content mounted (hidden) while closed. On
    a page that renders the quick-capture dialog, a broad role/text query
    can match the hidden dialog's content too, so scope such queries to a
    landmark instead of querying the whole document.
- Backend: pytest. `uv run pytest` (from inside `backend/`).
- Tests must stay green as part of "done," alongside lint/build.

## Working conventions

- Commit regularly; keep changes small and scoped to what was asked.
- Run lint, typecheck, build, and both test suites, and confirm they're
  clean before considering a task done.
- Don't commit unless explicitly asked to.
- Match the existing code style. ESLint + Prettier are configured in
  `frontend/`; lint must stay at 0 errors / 0 warnings.
- No em dashes in any prose you write here, in commit messages, in code
  comments, or in chat responses. Use a period, comma, or colon instead; or 
  rephrase.

## Do not

- Don't restructure or refactor working code unless asked.
- Don't add dependencies casually; only add what a task actually needs.
- Don't reproduce or edit files under `_docs/` as if they were code; they're
  planning/reference material.
