# AGENTS.md

Standing instructions for AI coding agents working in this repo.

## Project

Hub: a personal platform to capture, organize, and triage project ideas, from
small sparks to standalone builds. See `_docs/specs.md` for the product spec
and data model. That document is the source of truth; don't duplicate it
here and don't let this file drift from it.

## Structure

- `frontend/`: the app. Vite + React SPA, self-contained (its own
  `package.json`, `src/`, config). Currently the only thing that runs.
- `backend/`: not built yet. See "Backend" below.
- `_docs/`: specs, planning notes, and session logs. Reference material, not
  code.

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

## Backend (planned, `backend/` does not exist yet)

Not built. When it is:

- FastAPI, Python dependencies managed with `uv`.
- Starts on an in-memory store, then SQLite via SQLAlchemy, kept
  database-agnostic so it can move to Postgres later without a rewrite.
- Auth is roll-your-own: password hashing + JWT bearer tokens, OAuth2
  password flow. Token-based so the same API serves the web app and a future
  iOS app.
- Multi-user with per-user data isolation.

Treat this section as intent, not fact, until the folder exists.

## Working conventions

- Commit regularly; keep changes small and scoped to what was asked.
- Run lint, typecheck, and build and confirm they're clean before considering
  a task done.
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
