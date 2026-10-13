#!/bin/sh
# Starts the Hub MCP server with its password read from the macOS
# keychain, so the password is never in Claude Code's environment, which
# every shell command an agent runs inherits. It exists only in this
# process and the server it becomes (exec), for that server's lifetime.
#
# Registered in the repo root's .mcp.json. Needs:
#   HUB_EMAIL             the Hub account (from your shell; not a secret)
#   a keychain item       service "hub-mcp" (or HUB_KEYCHAIN_SERVICE),
#                         account HUB_EMAIL, added once with:
#     security add-generic-password -s hub-mcp -a you@example.com -w
#   HUB_API_URL           optional, as for the server itself
#
# See mcp-server/README.md. The password is never printed.

set -u

if [ -z "${HUB_EMAIL:-}" ]; then
    echo "hub-mcp: set HUB_EMAIL to the Hub account the agent acts as." >&2
    exit 2
fi

service="${HUB_KEYCHAIN_SERVICE:-hub-mcp}"

if ! command -v security >/dev/null 2>&1; then
    echo "hub-mcp: the macOS keychain ('security' command) isn't available here. On another system, start the server with HUB_PASSWORD set for its process only (see mcp-server/README.md)." >&2
    exit 2
fi

if ! password=$(security find-generic-password -s "$service" -a "$HUB_EMAIL" -w 2>/dev/null); then
    echo "hub-mcp: no keychain item for service '$service', account '$HUB_EMAIL'. Add it once with: security add-generic-password -s $service -a $HUB_EMAIL -w" >&2
    exit 2
fi

dir=$(cd "$(dirname "$0")" && pwd)
HUB_PASSWORD="$password"
export HUB_PASSWORD
unset password
exec uv run --directory "$dir" python -m hub_mcp
