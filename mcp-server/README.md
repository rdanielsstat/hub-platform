# Hub MCP server

An [MCP](https://modelcontextprotocol.io) server that lets an AI agent
(Claude Code, Claude Desktop, any MCP client) work with Hub's project
ideas as one signed-in user. Python 3.12, the official `mcp` SDK (v2),
speaking MCP over stdio.

It's a thin layer over the same REST API the web app uses
(`openapi.yaml`), so the API's ownership checks, field limits and usage
caps apply exactly as they do in the browser.

## Tools

| Tool | Arguments | Returns | Kind |
|---|---|---|---|
| `list_projects` | `status`, `tag`, `query` (all optional) | Summaries, most recently updated first | read-only |
| `get_project` | `project_id` | The project in full, with its notes | read-only |
| `create_project` | `name`; optional `pitch`, `description`, `status`, `tags`, `next_action` | The new project | write |
| `update_project` | `project_id`; any of `name`, `pitch`, `description`, `status`, `tags`, `next_action`, `excitement`, `potential`, `effort`, `target_date` | The updated project | write |
| `add_note` | `project_id`, `body` | The note and the updated project | write |

`status` is one of `Inbox`, `Exploring`, `Active`, `Parked`, `Graduated`,
`Killed` (an enum in the tool schema). `query` matches name, pitch,
description and tags, case-insensitively, like the dashboard's search.
Read-only tools carry MCP's `readOnlyHint`; the write tools are marked
non-destructive.

**No delete tools, on purpose.** An agent can capture, update and annotate
ideas, but deleting an idea or a note stays a human action in the web app
(`docs/permissions.md`). The client has no DELETE call at all, and a test
keeps it that way.

API errors come back to the agent as tool errors with the API's message,
e.g. `Hub API error 404: Project not found` or a 422 field error.

## Setup

Configuration is environment variables only (nothing is read from a file):

| Variable | Default | Meaning |
|---|---|---|
| `HUB_API_URL` | `http://localhost:8000` | The API. Deployed, the site's `/api`, e.g. `https://hub.dnls.dev/api` |
| `HUB_EMAIL` | (required) | The Hub account the agent acts as |
| `HUB_PASSWORD` | (required) | Its password |

Without `HUB_EMAIL` and `HUB_PASSWORD` it exits at once with a message on
stderr (exit code 2).

```
cd mcp-server
uv sync
HUB_EMAIL=demo@hub.dev HUB_PASSWORD=demo1234 uv run python -m hub_mcp
```

(It then waits for an MCP client on stdin; that's normal.)

### Claude Code

The repo root's `.mcp.json` registers it as the `hub` server, reading the
three variables from your shell. Export them, start Claude Code in the
repo, and approve the `hub` server when asked (or with `/mcp`):

```
export HUB_EMAIL=demo@hub.dev HUB_PASSWORD=demo1234   # the local demo account
claude
```

### Claude Desktop (or another client)

Add to the client's MCP config, with the absolute path to this folder:

```json
{
  "mcpServers": {
    "hub": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/hub-platform/mcp-server", "python", "-m", "hub_mcp"],
      "env": {
        "HUB_API_URL": "https://hub.dnls.dev/api",
        "HUB_EMAIL": "you@example.com",
        "HUB_PASSWORD": "..."
      }
    }
  }
}
```

## How it signs in

`POST /auth/login` (the OAuth2 password form) once, on the first tool
call; then `Authorization: Bearer <token>` on every request. When a token
expires (60 minutes by default) the next 401 triggers one fresh login and
a retry, so a long session keeps working without tripping the login rate
limit (5 per minute per IP, deployed). The token lives only in memory.

Deployed, requests go through CloudFront like the web app's, which adds
the origin-verification header the API requires; calling the raw API
Gateway URL gets 403.

## Security notes

- **It acts as one user, with that user's full access.** The API has no
  scoped or read-only tokens, so the agent can do anything the account
  can, except delete (no tool for it). Use your own account, or a
  separate one for experiments; locally, the demo account.
- **Your ideas go to the AI client's model.** Whatever a tool returns
  (names, pitches, notes) becomes part of the agent's context, so it's
  sent to the model provider behind the client you connect. That's your
  choice, for your own data; nothing is sent anywhere unless you connect
  a client (`security/DATA_POLICY.md`).
- **Notes are untrusted input to the agent.** A note could contain text
  that reads like an instruction. The tools can't delete anything, and
  Claude Code asks before each MCP tool call unless you've allowed it, so
  review write calls, especially after reading notes you didn't write
  (`security/AGENT_SECURITY.md`).
- **Credentials stay in the environment.** `.mcp.json` only references
  `${HUB_EMAIL}`/`${HUB_PASSWORD}`; never put a real password in a
  committed file.

## Tests

```
uv run pytest                  # unit tests: a fake Hub API, no services
uv run pytest -m integration   # live: a real backend on HUB_API_URL (default :8000)
uv run ruff check . && uv run ruff format --check .
```

Or from the repo root: `make test-mcp`, `make test-mcp-live` (needs
`make docker-up` or uvicorn), `make lint-mcp`. CI runs the unit tests and
Ruff in the `test` job, the live test against the Compose stack in the
`e2e` job, and pip-audit over `uv.lock` in `dependency-scan`.

| File | Covers |
|---|---|
| `tests/test_client.py` | Settings, the login form, Bearer auth, re-login on an expired token, error details, an unreachable API |
| `tests/test_server.py` | Each tool through a real MCP client session (in memory): schemas and annotations, filters and sorting, partial updates, refusals, API errors as tool errors, the client closed on shutdown |
| `tests/test_contract.py` | Every request the client makes is declared in `openapi.yaml`; the client has no DELETE |
| `tests/test_stdio.py` | `python -m hub_mcp` as a subprocess over stdio, and the missing-credentials exit |
| `tests/test_live_api.py` | Register a throwaway user on a real backend, then create, update, note, list and read back through the tools (`integration` marker) |
| `tests/fake_api.py` | The in-memory API the unit tests use, with the real auth, 404 and 422 shapes |

## Files

| File | What |
|---|---|
| `hub_mcp/server.py` | The tools (`create_server`) |
| `hub_mcp/client.py` | The API client: settings, login, Bearer auth, errors |
| `hub_mcp/__main__.py` | Entry point: reads the settings, runs over stdio |
| `pyproject.toml`, `uv.lock` | Dependencies: `mcp` (pinned by the lock at 2.2.0) and `httpx2` (which `mcp` uses too) |
