"""Fixes from the 2026-10-13 security sweep (security/REMEDIATION_LOG.md):
destructive updates (H2), project id injection (M1), untrusted note text
(M2), bounded error text (L4) and no password over plain http (L5)."""

import json

import httpx2
import pytest
from mcp import Client

from hub_mcp.client import ConfigError, HubApiError, HubClient, Settings
from hub_mcp.server import INSTRUCTIONS, create_server
from tests.fake_api import EMAIL, PASSWORD

pytestmark = pytest.mark.anyio


async def call(server, tool, **arguments):
    async with Client(server) as client:
        result = await client.call_tool(tool, arguments)
    if result.is_error:
        return True, result.content[0].text
    value = result.structured_content
    return False, value["result"] if set(value) == {"result"} else value


# --- H2: update_project is destructive, and guarded ----------------------


async def test_update_project_is_marked_destructive(make_client):
    async with Client(create_server(make_client)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert tools["update_project"].annotations.destructive_hint is True
    # The others only add; they stay non-destructive.
    assert tools["create_project"].annotations.destructive_hint is False
    assert tools["add_note"].annotations.destructive_hint is False


@pytest.mark.parametrize(
    "field, value",
    [("pitch", ""), ("description", ""), ("pitch", "   "), ("description", "\n")],
)
async def test_clearing_pitch_or_description_needs_allow_clear(
    api, make_client, field, value
):
    project = api.seed(name="Chess", pitch="Train openings", description="Long")
    server = create_server(make_client)
    is_error, message = await call(
        server, "update_project", project_id=project["id"], **{field: value}
    )
    assert is_error
    assert "allow_clear" in message
    assert api.projects[project["id"]][field] != value  # untouched

    is_error, updated = await call(
        server,
        "update_project",
        project_id=project["id"],
        allow_clear=True,
        **{field: value},
    )
    assert not is_error
    assert updated[field] == value


async def test_the_name_can_never_be_cleared(api, make_client):
    project = api.seed(name="Chess")
    is_error, message = await call(
        create_server(make_client),
        "update_project",
        project_id=project["id"],
        name="  ",
        allow_clear=True,
    )
    assert is_error
    assert "name" in message
    assert api.projects[project["id"]]["name"] == "Chess"


async def test_bulk_status_changes_need_confirmation(api, make_client):
    ids = [api.seed(name=f"Idea {i}")["id"] for i in range(5)]
    server = create_server(make_client)
    async with Client(server) as client:
        results = [
            await client.call_tool(
                "update_project", {"project_id": i, "status": "Killed"}
            )
            for i in ids[:4]
        ]
        confirmed = await client.call_tool(
            "update_project",
            {"project_id": ids[3], "status": "Killed", "confirm_bulk": True},
        )
    assert [r.is_error for r in results] == [False, False, False, True]
    assert "confirm_bulk" in results[3].content[0].text
    assert not confirmed.is_error
    assert [api.projects[i]["status"] for i in ids] == [
        "Killed",
        "Killed",
        "Killed",
        "Killed",
        "Inbox",
    ]


async def test_other_fields_are_not_limited(api, make_client):
    ids = [api.seed(name=f"Idea {i}")["id"] for i in range(5)]
    async with Client(create_server(make_client)) as client:
        results = [
            await client.call_tool("update_project", {"project_id": i, "excitement": 4})
            for i in ids
        ]
    assert not any(r.is_error for r in results)


# --- M1: project ids are UUIDs, nothing else ------------------------------


@pytest.mark.parametrize(
    "project_id",
    [
        "x/../../auth/me",
        "../auth/me",
        "..%2f..%2fauth%2fme",
        "00000000-0000-4000-8000-000000000000/notes",
        "00000000-0000-4000-8000-000000000000?x=1",
        "00000000-0000-4000-8000-000000000000#x",
        "not-a-uuid",
        "",
    ],
)
async def test_project_ids_that_are_not_uuids_never_reach_the_api(
    api, make_client, project_id
):
    client = make_client()
    for method, args in (
        ("get_project", (project_id,)),
        ("list_notes", (project_id,)),
        ("update_project", (project_id, {"status": "Active"})),
        ("add_note", (project_id, "x")),
    ):
        with pytest.raises(HubApiError, match="project id"):
            await getattr(client, method)(*args)
    await client.aclose()
    assert api.requests == []


async def test_a_traversal_id_is_a_tool_error(api, make_client):
    is_error, message = await call(
        create_server(make_client), "get_project", project_id="x/../../auth/me"
    )
    assert is_error
    assert "project id" in message
    assert api.requests == []


async def test_uppercase_uuids_are_accepted_and_sent_canonical(api, make_client):
    project = api.seed(name="Chess")
    client = make_client()
    await client.get_project(project["id"].upper())
    await client.aclose()
    assert api.requests[-1].url.path == f"/projects/{project['id']}"


# --- M2: the model is told note text is data ------------------------------


def test_instructions_mark_user_text_as_untrusted():
    text = INSTRUCTIONS.lower()
    assert "untrusted" in text
    assert "never" in text and "instructions" in text


# --- L4: error text from the API is bounded -------------------------------


async def test_non_json_error_text_is_capped(settings):
    page = "<html>" + "x" * 10_000 + "</html>"

    def handler(request):
        if request.url.path == "/auth/login":
            return httpx2.Response(200, json={"access_token": "t"})
        return httpx2.Response(502, text=page)

    client = HubClient(settings, transport=httpx2.MockTransport(handler))
    with pytest.raises(HubApiError) as caught:
        await client.list_projects()
    await client.aclose()
    assert caught.value.status == 502
    assert len(caught.value.detail) <= 520
    assert caught.value.detail.endswith("(truncated)")


async def test_long_json_details_are_capped_too(settings):
    def handler(request):
        if request.url.path == "/auth/login":
            return httpx2.Response(200, json={"access_token": "t"})
        return httpx2.Response(400, json={"detail": "y" * 5000})

    client = HubClient(settings, transport=httpx2.MockTransport(handler))
    with pytest.raises(HubApiError) as caught:
        await client.list_projects()
    await client.aclose()
    assert len(caught.value.detail) <= 520


async def test_short_errors_are_unchanged(api, make_client):
    client = make_client()
    with pytest.raises(HubApiError) as caught:
        await client.get_project("00000000-0000-4000-8000-000000000000")
    await client.aclose()
    assert caught.value.detail == "Project not found"


# --- L5: no password over plain http to a remote host ----------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://hub.dnls.dev/api",
        "http://192.168.1.20:8000",
        "http://localhost.evil.com",
        "HTTP://HUB.EXAMPLE.COM",
    ],
)
def test_http_to_a_remote_host_is_refused(url):
    env = {"HUB_EMAIL": EMAIL, "HUB_PASSWORD": PASSWORD, "HUB_API_URL": url}
    with pytest.raises(ConfigError, match="HUB_ALLOW_INSECURE_HTTP"):
        Settings.from_env(env)
    with pytest.raises(ConfigError):
        Settings(api_url=url, email=EMAIL, password=PASSWORD)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://[::1]:8000",
        "http://hub.localhost:8000",
        "https://hub.dnls.dev/api",
    ],
)
def test_https_and_local_http_are_allowed(url):
    env = {"HUB_EMAIL": EMAIL, "HUB_PASSWORD": PASSWORD, "HUB_API_URL": url}
    assert Settings.from_env(env).api_url == url


def test_the_documented_override_allows_remote_http():
    env = {
        "HUB_EMAIL": EMAIL,
        "HUB_PASSWORD": PASSWORD,
        "HUB_API_URL": "http://hub.internal:8000",
        "HUB_ALLOW_INSECURE_HTTP": "1",
    }
    assert Settings.from_env(env).allow_insecure_http is True


def test_other_schemes_are_refused():
    env = {"HUB_EMAIL": EMAIL, "HUB_PASSWORD": PASSWORD, "HUB_API_URL": "ftp://x"}
    with pytest.raises(ConfigError, match="http"):
        Settings.from_env(env)


def test_the_password_is_not_in_the_settings_repr():
    settings = Settings(api_url="https://hub.test", email=EMAIL, password=PASSWORD)
    assert PASSWORD not in repr(settings)
    assert PASSWORD not in json.dumps(str(settings))
