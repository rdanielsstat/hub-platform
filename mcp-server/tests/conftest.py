import pytest

from hub_mcp.client import HubClient, Settings
from tests.fake_api import EMAIL, PASSWORD, FakeHubApi


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def api() -> FakeHubApi:
    return FakeHubApi()


@pytest.fixture
def settings() -> Settings:
    return Settings(api_url="http://hub.test", email=EMAIL, password=PASSWORD)


@pytest.fixture
def make_client(api, settings):
    """A HubClient wired to the fake API (a factory, as create_server
    takes)."""
    return lambda: HubClient(settings, transport=api.transport())
