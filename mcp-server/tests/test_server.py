"""The MCP tools, called through a real MCP client session (in memory)
against the fake API."""

import json

import pytest
from mcp import Client

from hub_mcp.server import create_server

pytestmark = pytest.mark.anyio


async def call(server, tool, **arguments):
    """(is_error, value): the error message, or the tool's return value
    from the structured result (a list comes wrapped as {"result": [...]})."""
    async with Client(server) as client:
        result = await client.call_tool(tool, arguments)
    if result.is_error:
        return True, result.content[0].text
    value = result.structured_content
    return False, value["result"] if set(value) == {"result"} else value


async def test_exposes_the_five_tools_and_no_delete(make_client):
    async with Client(create_server(make_client)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {
        "list_projects",
        "get_project",
        "create_project",
        "update_project",
        "add_note",
    }
    for name in ("list_projects", "get_project"):
        assert tools[name].annotations.read_only_hint is True
    for name in ("create_project", "update_project", "add_note"):
        assert tools[name].annotations.read_only_hint is False
        assert tools[name].annotations.destructive_hint is False
    status = tools["create_project"].input_schema["properties"]["status"]
    assert status["enum"] == [
        "Inbox",
        "Exploring",
        "Active",
        "Parked",
        "Graduated",
        "Killed",
    ]


async def test_list_projects_filters_and_sorts_newest_first(api, make_client):
    api.seed(name="Chess trainer", status="Active", tags=["games"])
    api.seed(name="Garden log", pitch="Track the CHESSboard garden", tags=["home"])
    api.seed(name="Recipe box", status="Active", tags=["home"], description="")
    server = create_server(make_client)

    _, everything = await call(server, "list_projects")
    assert [p["name"] for p in everything] == [
        "Recipe box",
        "Garden log",
        "Chess trainer",
    ]
    assert set(everything[0]) == {
        "id",
        "name",
        "pitch",
        "status",
        "tags",
        "nextAction",
        "excitement",
        "potential",
        "effort",
        "targetDate",
        "updatedAt",
    }
    _, active = await call(server, "list_projects", status="Active")
    assert [p["name"] for p in active] == ["Recipe box", "Chess trainer"]
    _, home = await call(server, "list_projects", tag="home", status="Active")
    assert [p["name"] for p in home] == ["Recipe box"]
    _, chess = await call(server, "list_projects", query="chess")
    assert [p["name"] for p in chess] == ["Garden log", "Chess trainer"]


async def test_list_projects_rejects_an_unknown_status(make_client):
    is_error, message = await call(
        create_server(make_client), "list_projects", status="Done"
    )
    assert is_error
    assert "status" in message


async def test_get_project_includes_notes(api, make_client):
    project = api.seed(name="Chess trainer")
    server = create_server(make_client)
    await call(server, "add_note", project_id=project["id"], body="First")
    _, result = await call(server, "get_project", project_id=project["id"])
    assert result["project"]["name"] == "Chess trainer"
    assert [n["body"] for n in result["notes"]] == ["First"]


async def test_create_project_sends_camel_case_with_defaults(api, make_client):
    _, project = await call(
        create_server(make_client),
        "create_project",
        name="Chess trainer",
        tags=["games"],
        next_action="Sketch the UI",
    )
    sent = json.loads(api.requests[-1].content)
    assert sent == {
        "name": "Chess trainer",
        "pitch": "",
        "description": "",
        "status": "Inbox",
        "tags": ["games"],
        "nextAction": "Sketch the UI",
    }
    assert project["status"] == "Inbox"
    assert project["nextAction"] == "Sketch the UI"


async def test_update_project_sends_only_the_given_fields(api, make_client):
    project = api.seed(name="Chess trainer")
    server = create_server(make_client)
    _, updated = await call(
        server,
        "update_project",
        project_id=project["id"],
        status="Exploring",
        excitement=5,
        target_date="2026-12-01",
    )
    assert json.loads(api.requests[-1].content) == {
        "status": "Exploring",
        "excitement": 5,
        "targetDate": "2026-12-01",
    }
    assert updated["status"] == "Exploring"
    assert updated["name"] == "Chess trainer"


async def test_update_project_with_no_fields_is_refused(api, make_client):
    project = api.seed(name="Chess trainer")
    is_error, message = await call(
        create_server(make_client), "update_project", project_id=project["id"]
    )
    assert is_error
    assert "Nothing to update" in message
    assert api.requests == []


async def test_add_note_trims_and_refuses_blank(api, make_client):
    project = api.seed(name="Chess trainer")
    server = create_server(make_client)
    _, added = await call(server, "add_note", project_id=project["id"], body="  Hi  ")
    assert added["note"]["body"] == "Hi"
    is_error, message = await call(
        server, "add_note", project_id=project["id"], body=" "
    )
    assert is_error
    assert "needs some text" in message


async def test_api_errors_become_tool_errors(make_client):
    is_error, message = await call(
        create_server(make_client), "get_project", project_id="missing"
    )
    assert is_error
    assert "Hub API error 404: Project not found" in message


async def test_the_api_client_is_closed_when_the_server_stops(api, settings):
    from hub_mcp.client import HubClient

    clients = []

    def factory():
        clients.append(HubClient(settings, transport=api.transport()))
        return clients[-1]

    await call(create_server(factory), "list_projects")
    assert len(clients) == 1
    assert clients[0]._http.is_closed
