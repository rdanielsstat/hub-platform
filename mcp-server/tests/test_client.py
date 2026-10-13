"""HubClient against the fake API: settings, login, token refresh and
error reporting."""

import httpx2
import pytest

from hub_mcp.client import ConfigError, HubApiError, HubClient, Settings
from tests.fake_api import EMAIL

pytestmark = pytest.mark.anyio


def test_settings_from_env_defaults_the_url_and_trims_it():
    settings = Settings.from_env({"HUB_EMAIL": " a@b.c ", "HUB_PASSWORD": "pw"})
    assert settings == Settings("http://localhost:8000", "a@b.c", "pw")
    deployed = Settings.from_env(
        {
            "HUB_EMAIL": "a@b.c",
            "HUB_PASSWORD": "pw",
            "HUB_API_URL": "https://hub.dnls.dev/api/",
        }
    )
    assert deployed.api_url == "https://hub.dnls.dev/api"


@pytest.mark.parametrize(
    "env", [{}, {"HUB_EMAIL": "a@b.c"}, {"HUB_PASSWORD": "pw"}, {"HUB_EMAIL": " "}]
)
def test_settings_require_email_and_password(env):
    with pytest.raises(ConfigError, match="HUB_EMAIL and HUB_PASSWORD"):
        Settings.from_env(env)


async def test_logs_in_once_with_the_oauth2_form_then_sends_bearer(api, make_client):
    api.seed(name="One")
    client = make_client()
    await client.list_projects()
    await client.list_projects()
    await client.aclose()

    login, first, second = api.requests
    assert login.url.path == "/auth/login"
    assert login.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert f"username={EMAIL.replace('@', '%40')}" in login.content.decode()
    assert first.headers["Authorization"] == "Bearer token-1"
    assert second.headers["Authorization"] == "Bearer token-1"
    assert api.logins == 1


async def test_an_expired_token_is_replaced_by_logging_in_again(api, make_client):
    client = make_client()
    await client.list_projects()
    api.expire_tokens()
    assert await client.list_projects() == []
    await client.aclose()
    assert api.logins == 2
    assert api.requests[-1].headers["Authorization"] == "Bearer token-2"


async def test_a_wrong_password_is_reported_without_retrying(api, settings):
    client = HubClient(
        Settings(settings.api_url, settings.email, "wrong"), transport=api.transport()
    )
    with pytest.raises(HubApiError) as caught:
        await client.list_projects()
    await client.aclose()
    assert caught.value.status == 401
    assert "Login failed: Incorrect email or password" in str(caught.value)
    assert len(api.requests) == 1


async def test_api_errors_carry_status_and_detail(api, make_client):
    client = make_client()
    with pytest.raises(HubApiError) as missing:
        await client.get_project("nope")
    with pytest.raises(HubApiError) as invalid:
        await client.create_project({"name": "x" * 300})
    await client.aclose()
    assert (missing.value.status, missing.value.detail) == (404, "Project not found")
    assert invalid.value.status == 422
    assert invalid.value.detail == "name: String should have at most 256 characters"


async def test_an_unreachable_api_is_a_clear_error(settings):
    def refuse(request):
        raise httpx2.ConnectError("connection refused", request=request)

    client = HubClient(settings, transport=httpx2.MockTransport(refuse))
    with pytest.raises(HubApiError) as caught:
        await client.list_projects()
    await client.aclose()
    assert caught.value.status == 0
    assert "Can't reach the Hub API at http://hub.test" in str(caught.value)
