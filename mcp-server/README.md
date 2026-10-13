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
| `create_project` | `name`; optional `pitch`, `description`, `status`, `tags`, `next_action` | The new project | write (adds) |
| `update_project` | `project_id`; any of `name`, `pitch`, `description`, `status`, `tags`, `next_action`, `excitement`, `potential`, `effort`, `target_date`; `allow_clear`, `confirm_bulk` | The updated project | destructive (overwrites) |
| `add_note` | `project_id`, `body` | The note and the updated project | write (adds) |

`status` is one of `Inbox`, `Exploring`, `Active`, `Parked`, `Graduated`,
`Killed` (an enum in the tool schema). `query` matches name, pitch,
description and tags, case-insensitively, like the dashboard's search.
`project_id` must be a project's UUID, as `list_projects` returns it;
anything else is refused before a request is sent.

MCP annotations: the read-only tools carry `readOnlyHint`;
`create_project` and `add_note` only add, so they're marked
non-destructive; `update_project` overwrites what was there, so it's
marked destructive, and Claude Code asks before every call to it.

**Guards on `update_project`:**
- The name can't be blanked (a project needs one).
- Blanking the pitch or description is refused unless `allow_clear=True`,
  which an agent should pass only when the user asked for it.
- After three status changes within ten minutes, another needs
  `confirm_bulk=True`, after asking the user. An agent told to "set every
  idea to Killed" is stopped after three.

**No delete tools, on purpose.** An agent can capture, update and annotate
ideas, but deleting an idea or a note stays a human action in the web app
(`docs/permissions.md`). The client has no DELETE call at all, and a test
keeps it that way.

The server's instructions tell the model that names, pitches,
descriptions, tags and note text are untrusted user content, to be
treated as data and never followed as instructions.

API errors come back to the agent as tool errors with the API's message,
e.g. `Hub API error 404: Project not found` or a 422 field error, capped
at 500 characters (a proxy's HTML error page doesn't flood the context).

## Setup

The server reads environment variables only (nothing from a file):

| Variable | Default | Meaning |
|---|---|---|
| `HUB_API_URL` | `http://localhost:8000` | The API. Deployed, the site's `/api`, e.g. `https://hub.dnls.dev/api` |
| `HUB_EMAIL` | (required) | The Hub account the agent acts as |
| `HUB_PASSWORD` | (required) | Its password. Set by `run-with-keychain.sh` for the server's process only; don't export it in your shell |
| `HUB_ALLOW_INSECURE_HTTP` | off | `1` lets the password go over plain `http://` to a host that isn't local (a trusted private network only). Without it, `http://` is refused except for `localhost`, `*.localhost` and loopback addresses |
| `HUB_KEYCHAIN_SERVICE` | `hub-mcp` | For `run-with-keychain.sh`: the keychain item's service name |

Without `HUB_EMAIL` and `HUB_PASSWORD`, or with an `http://` URL to a
remote host, it exits at once with a message on stderr (exit code 2).

### Claude Code (macOS keychain)

The repo root's `.mcp.json` registers it as the `hub` server, started
through `run-with-keychain.sh`. That script reads the password from the
macOS keychain and passes it to the server process only, so it's never
in Claude Code's environment, which every shell command an agent runs
inherits. Once:

```
cd mcp-server && uv sync && cd ..
security add-generic-password -s hub-mcp -a demo@hub.dev -w   # prompts for the password
```

Then, each time:

```
export HUB_EMAIL=demo@hub.dev   # not a secret; HUB_API_URL too, if not localhost:8000
claude
```

and approve the `hub` server when asked (or with `/mcp`). Locally, use
the demo account (`demo1234`, the password to store above). For the live
site, store your own account's password under its email, and set
`HUB_API_URL=https://hub.dnls.dev/api`. Update a stored password with
`security add-generic-password -U -s hub-mcp -a <email> -w`.

Don't `export HUB_PASSWORD`: anything in your shell's environment is
visible to every command the agent runs. The guard hook
(`agent-hooks/guard.py`) also denies commands that print the environment.

### Claude Desktop (or another client)

A desktop client has no agent shell, so the password can sit in its
config's `env` for the server process. Use the absolute path to this
folder, and prefer the keychain wrapper anyway on macOS:

```json
{
  "mcpServers": {
    "hub": {
      "command": "sh",
      "args": ["/path/to/hub-platform/mcp-server/run-with-keychain.sh"],
      "env": {
        "HUB_API_URL": "https://hub.dnls.dev/api",
        "HUB_EMAIL": "you@example.com"
      }
    }
  }
}
```

On a system without the macOS keychain, run
`uv run --directory /path/to/hub-platform/mcp-server python -m hub_mcp`
with `HUB_PASSWORD` in that server entry's `env` (never in a shell an
agent uses).

To try it by hand: `cd mcp-server && HUB_EMAIL=demo@hub.dev
HUB_PASSWORD=demo1234 uv run python -m hub_mcp` (it then waits for an MCP
client on stdin; that's normal).

## How it signs in

`POST /auth/login` (the OAuth2 password form) once, on the first tool
call; then `Authorization: Bearer <token>` on every request. When a token
expires (60 minutes by default) the next 401 triggers one fresh login and
a retry, so a long session keeps working without tripping the login rate
limit (5 per minute per IP, deployed). The token lives only in memory,
and the password never appears in the settings' `repr`.

Deployed, requests go through CloudFront like the web app's, which adds
the origin-verification header the API requires; calling the raw API
Gateway URL gets 403. API clients send no `Origin` header, so the login
CSRF check on `/auth/login` (`backend/README.md`) doesn't affect them.

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
  that reads like an instruction. The server tells the model never to
  follow it; the tools can't delete anything; `update_project` is marked
  destructive, so Claude Code asks before each call; and the
  `allow_clear` and `confirm_bulk` guards stop silent blanking and mass
  status changes. Review write calls, especially after reading notes you
  didn't write (`security/AGENT_SECURITY.md`).
- **Project ids are UUIDs.** An id can't steer a request to another
  endpoint (`x/../../auth/me`): anything that isn't a UUID is refused
  before sending, and ids are URL-encoded in the path as a second layer.
- **The password stays out of the agent's reach.** It's in the macOS
  keychain and in the server's own process, not in a file, not in
  `.mcp.json`, and not in Claude Code's environment. It's never sent over
  plain http to a remote host.

## Tests

```
uv run pytest                  # unit tests: a fake Hub API, no services
uv run pytest -m integration   # live: a local backend on HUB_API_URL (default :8000)
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
| `tests/test_hardening.py` | The 2026-10-13 sweep's fixes: `update_project` destructive, `allow_clear`, `confirm_bulk`; non-UUID ids never reach the API; the untrusted-content instruction; capped error text; no password over remote http, and the override |
| `tests/test_keychain_wrapper.py` | `run-with-keychain.sh` with stub `security` and `uv`: the password reaches only the server, a missing item, email or keychain stops with instructions; `.mcp.json` holds no password |
| `tests/test_contract.py` | Every request the client makes is declared in `openapi.yaml`; the client has no DELETE |
| `tests/test_stdio.py` | `python -m hub_mcp` as a subprocess over stdio, and the missing-credentials exit |
| `tests/test_live_guard.py` | The live test refuses any backend that isn't local |
| `tests/test_live_api.py` | Register a throwaway user on a local backend, then create, update, note, list and read back through the tools (`integration` marker); refuses non-local URLs (`tests/live_guard.py`) |
| `tests/fake_api.py` | The in-memory API the unit tests use, with UUID ids and the real auth, 404 and 422 shapes |

## Files

| File | What |
|---|---|
| `hub_mcp/server.py` | The tools (`create_server`) and their guards |
| `hub_mcp/client.py` | The API client: settings (https check), login, Bearer auth, project id checks, errors |
| `hub_mcp/__main__.py` | Entry point: reads the settings, runs over stdio |
| `run-with-keychain.sh` | Starts the server with the password from the macOS keychain (`.mcp.json` uses it) |
| `pyproject.toml`, `uv.lock` | Dependencies: `mcp` (pinned by the lock at 2.2.0) and `httpx2` (which `mcp` uses too) |
