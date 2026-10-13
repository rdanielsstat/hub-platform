"""Every API operation hub_mcp calls is declared in openapi.yaml (repo
root), the contract the backend is tested against
(backend/tests/test_openapi_contract.py). A renamed or removed endpoint
fails here instead of at an agent's first call."""

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.anyio

SPEC = yaml.safe_load(
    (Path(__file__).resolve().parents[2] / "openapi.yaml").read_text()
)


def _spec_pattern(path: str) -> re.Pattern[str]:
    return re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", path) + "$")


SPEC_OPERATIONS = [
    (method.upper(), _spec_pattern(path))
    for path, item in SPEC["paths"].items()
    for method in item
    if method in {"get", "post", "patch", "put", "delete"}
]


async def test_every_call_the_client_makes_is_in_the_spec(make_client, api):
    project = api.seed(name="Contract")
    client = make_client()
    await client.list_projects()
    await client.get_project(project["id"])
    await client.list_notes(project["id"])
    await client.create_project({"name": "New"})
    await client.update_project(project["id"], {"status": "Active"})
    await client.add_note(project["id"], "A note")
    await client.aclose()

    made = {(r.method, r.url.path) for r in api.requests}
    assert len(made) == 7  # login plus the six calls above
    for method, path in made:
        assert any(
            m == method and pattern.match(path) for m, pattern in SPEC_OPERATIONS
        ), f"{method} {path} is not in openapi.yaml"


def test_the_client_never_deletes():
    # No tool deletes an idea or a note (hub_mcp/server.py); the client
    # has no DELETE call for one to reach for.
    from hub_mcp import client

    source = Path(client.__file__).read_text()
    assert '"DELETE"' not in source
