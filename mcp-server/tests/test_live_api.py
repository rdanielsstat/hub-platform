"""The tools against a real Hub backend, end to end: `uv run pytest -m
integration` with one on HUB_API_URL (default http://localhost:8000),
e.g. `make docker-up`. CI runs it against the Compose stack. Registers
a throwaway account, so it never touches existing data, and refuses to
run against anything but a local backend (tests/live_guard.py)."""

import os
import uuid

import httpx2
import pytest
from mcp import Client

from hub_mcp.client import HubClient, Settings
from hub_mcp.server import create_server
from tests.live_guard import require_local_api

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

API_URL = os.environ.get("HUB_API_URL", "http://localhost:8000").rstrip("/")


async def _tool(client, tool, **arguments):
    result = await client.call_tool(tool, arguments)
    assert not result.is_error, result.content[0].text
    value = result.structured_content
    return value["result"] if set(value) == {"result"} else value


async def test_capture_update_note_and_read_back():
    require_local_api(API_URL)
    email = f"mcp-{uuid.uuid4().hex[:12]}@example.com"
    password = "mcp-live-password-123"
    async with httpx2.AsyncClient(base_url=API_URL) as http:
        registered = await http.post(
            "/auth/register", json={"email": email, "password": password}
        )
    assert registered.status_code == 201, registered.text

    settings = Settings(api_url=API_URL, email=email, password=password)
    server = create_server(lambda: HubClient(settings))
    async with Client(server) as client:
        created = await _tool(
            client, "create_project", name="Live MCP idea", tags=["mcp"]
        )
        await _tool(
            client,
            "update_project",
            project_id=created["id"],
            status="Exploring",
            next_action="Try it from Claude Code",
        )
        await _tool(client, "add_note", project_id=created["id"], body="From MCP")
        listed = await _tool(client, "list_projects", tag="mcp")
        full = await _tool(client, "get_project", project_id=created["id"])
        missing = await client.call_tool(
            "get_project", {"project_id": str(uuid.uuid4())}
        )

    assert [p["id"] for p in listed] == [created["id"]]
    assert full["project"]["status"] == "Exploring"
    assert full["project"]["nextAction"] == "Try it from Claude Code"
    assert [n["body"] for n in full["notes"]] == ["From MCP"]
    assert missing.is_error
    assert "404" in missing.content[0].text
