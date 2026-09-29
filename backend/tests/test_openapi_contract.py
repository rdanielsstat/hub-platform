"""openapi.yaml (repo root) is the contract the frontend and backend are
both built against. Fail on any path + method declared on one side and
missing from the other, so the two can't silently drift apart.

Paths are compared exactly as written, path parameter names included:
the spec is the contract document, so a parameter named differently in
the spec and in the code is a real mismatch, not noise to normalise.
"""

from pathlib import Path

import yaml

from app.main import app

SPEC_PATH = Path(__file__).resolve().parents[2] / "openapi.yaml"
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def _operations(paths: dict) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, item in paths.items()
        for method in item
        if method in HTTP_METHODS
    }


def test_spec_and_app_declare_the_same_operations():
    spec = yaml.safe_load(SPEC_PATH.read_text())
    in_spec = _operations(spec["paths"])
    in_app = _operations(app.openapi()["paths"])

    only_in_spec = sorted(in_spec - in_app, key=lambda op: (op[1], op[0]))
    only_in_app = sorted(in_app - in_spec, key=lambda op: (op[1], op[0]))

    assert not only_in_spec and not only_in_app, (
        "openapi.yaml and the FastAPI app disagree.\n"
        f"  In openapi.yaml but not the app: {only_in_spec}\n"
        f"  In the app but not openapi.yaml: {only_in_app}"
    )


def test_spec_declares_the_deployed_server():
    spec = yaml.safe_load(SPEC_PATH.read_text())

    assert "https://hub.dnls.dev/api" in [server["url"] for server in spec["servers"]]
