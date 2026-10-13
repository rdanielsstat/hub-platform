"""Entry point: `uv run python -m hub_mcp` (from mcp-server/), speaking
MCP over stdio. Configured by environment variables; see README.md."""

import sys

from hub_mcp.client import ConfigError, HubClient, Settings
from hub_mcp.server import create_server


def main() -> None:
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        # stderr: stdout is the MCP channel.
        print(f"hub-mcp: {exc}", file=sys.stderr)
        sys.exit(2)
    create_server(lambda: HubClient(settings)).run("stdio")


if __name__ == "__main__":
    main()
