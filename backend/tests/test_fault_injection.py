"""FAULT_INJECT_5XX (app/core/config.py): the drill's switch that makes
POST /projects answer 500. Off by default, never on in prod."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.core.config import fault_inject_5xx_enabled

BACKEND = Path(__file__).resolve().parents[1]


def test_off_by_default_at_import() -> None:
    """A fresh interpreter with FAULT_INJECT_5XX unset sees it off."""
    env = {k: v for k, v in os.environ.items() if k != "FAULT_INJECT_5XX"}
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.core import config; print(config.FAULT_INJECT_5XX)",
        ],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "False"


def test_unset_means_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FAULT_INJECT_5XX", raising=False)
    assert fault_inject_5xx_enabled("dev") is False


@pytest.mark.parametrize("value", ["", "false", "0", "no", "off"])
def test_falsy_values_are_off(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("FAULT_INJECT_5XX", value)
    assert fault_inject_5xx_enabled("dev") is False


def test_true_turns_it_on_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAULT_INJECT_5XX", "true")
    assert fault_inject_5xx_enabled("dev") is True


def test_never_on_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAULT_INJECT_5XX", "true")
    assert fault_inject_5xx_enabled("prod") is False


def test_project_creation_works_with_the_flag_off(
    client: TestClient, register_and_login
) -> None:
    auth_headers = register_and_login("fault-off@example.com")
    assert config.FAULT_INJECT_5XX is False
    res = client.post("/projects", json={"name": "Fine"}, headers=auth_headers)
    assert res.status_code == 201


def test_flag_on_makes_project_creation_500(
    client: TestClient,
    register_and_login,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_headers = register_and_login("fault-on@example.com")
    monkeypatch.setattr(config, "FAULT_INJECT_5XX", True)
    res = client.post("/projects", json={"name": "Broken"}, headers=auth_headers)
    assert res.status_code == 500
    # Nothing was created.
    assert client.get("/projects", headers=auth_headers).json() == []
    # Other routes are untouched.
    assert client.get("/projects", headers=auth_headers).status_code == 200
