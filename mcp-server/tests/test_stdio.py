"""The real entry point, `python -m hub_mcp`, over stdio: what an MCP
client (Claude Code, Claude Desktop) actually launches."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

pytestmark = pytest.mark.anyio

PROJECT_DIR = Path(__file__).resolve().parents[1]


async def test_lists_its_tools_over_stdio():
    # Listing tools makes no API call, so no backend is needed; the
    # credentials only have to be present.
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "hub_mcp"],
        cwd=PROJECT_DIR,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HUB_API_URL": "http://127.0.0.1:9",
            "HUB_EMAIL": "agent@example.com",
            "HUB_PASSWORD": "unused",
        },
    )
    async with Client(params) as client:
        tools = await client.list_tools()
    assert len(tools.tools) == 5


def test_missing_credentials_exit_with_a_message_on_stderr():
    env = {k: v for k, v in os.environ.items() if not k.startswith("HUB_")}
    done = subprocess.run(
        [sys.executable, "-m", "hub_mcp"],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert done.returncode == 2
    assert done.stdout == ""
    assert "Set HUB_EMAIL and HUB_PASSWORD" in done.stderr
