# Hub API

FastAPI backend for Hub. Skeleton only today: a `GET /health` endpoint and
the module layout the real API will grow into. See `../_docs/specs.md` and
`../openapi.yaml` for the intended contract.

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
- `http://localhost:8000/docs` (auto-generated OpenAPI docs)

CORS is currently open to the Vite dev server at `http://localhost:5173`.
