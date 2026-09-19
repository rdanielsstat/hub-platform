# Hub API

FastAPI backend for Hub. Implements auth and project endpoints against an
in-memory store; notes and attachments aren't built yet. See
`../_docs/specs.md` and `../openapi.yaml` for the full intended contract.

## Setup

```
uv sync
```

## Run the dev server

```
uv run uvicorn app.main:app --reload
```

Then visit:

- `http://localhost:8000/health`
- `http://localhost:8000/docs` (auto-generated OpenAPI docs, includes a
  working "Authorize" button for the bearer token)

CORS is currently open to the Vite dev server at `http://localhost:5173`.

## Seeded demo account

The in-memory store seeds one user with two projects on startup, so there's
something to log in as and see:

- email: `demo@hub.dev`
- password: `demo1234`

The store is in-memory: it resets to just this seed data every time the
server restarts.

## Run the tests

```
uv run pytest
```

Tests run against a fresh, unseeded in-memory store per test (see
`tests/conftest.py`), independent of the app's seeded singleton.

## Auth

Roll-your-own: passwords hashed with argon2 (via passlib), JWT bearer
tokens (via PyJWT), OAuth2 password flow. `POST /auth/login` takes
`application/x-www-form-urlencoded` with `username` (the email) and
`password`, matching openapi.yaml and FastAPI's built-in OAuth2 tooling.

The JWT signing secret defaults to a hardcoded dev-only value
(`app/auth/security.py`). Set `HUB_JWT_SECRET` before running this
anywhere but a laptop.
