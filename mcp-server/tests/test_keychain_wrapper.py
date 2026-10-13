"""H1: run-with-keychain.sh loads the password from the macOS keychain
and hands it only to the MCP server process, so it never sits in Claude
Code's environment (which every agent shell command inherits).

The real `security` and `uv` are replaced by stubs on PATH: the stub
`security` plays a keychain, the stub `uv` records what the server
would have been started with."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "mcp-server" / "run-with-keychain.sh"
SECRET = "keychain-test-value-123"


@pytest.fixture
def stubs(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("dirname", "sh"):
        os.symlink(shutil.which(tool), bin_dir / tool)
    record = tmp_path / "record.json"

    def write(name, body):
        path = bin_dir / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    # A keychain holding one item: service hub-mcp, account agent@example.com.
    write(
        "security",
        'echo "$@" > "' + str(tmp_path / "security-args") + '"\n'
        'if [ "$1" = find-generic-password ] && [ "$3" = "${EXPECT_SERVICE:-hub-mcp}" ] '
        '&& [ "$5" = agent@example.com ] && [ "$6" = -w ]; then echo ' + SECRET + "; "
        "else echo 'item not found' >&2; exit 44; fi",
    )
    write(
        "uv",
        'printf \'{"password": "%s", "args": "%s", "api": "%s"}\' '
        '"$HUB_PASSWORD" "$*" "$HUB_API_URL" > "' + str(record) + '"',
    )
    return bin_dir, record, tmp_path


def run(stubs, **env):
    bin_dir, _, _ = stubs
    return subprocess.run(
        ["/bin/sh", str(WRAPPER)],
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": str(bin_dir), **env},
    )


def test_the_password_reaches_only_the_server(stubs):
    _, record, tmp_path = stubs
    done = run(stubs, HUB_EMAIL="agent@example.com", HUB_API_URL="https://h/api")
    assert done.returncode == 0, done.stderr
    started = json.loads(record.read_text())
    assert started["password"] == SECRET
    assert started["args"] == f"run --directory {WRAPPER.parent} python -m hub_mcp"
    assert started["api"] == "https://h/api"
    assert (tmp_path / "security-args").read_text().split() == [
        "find-generic-password",
        "-s",
        "hub-mcp",
        "-a",
        "agent@example.com",
        "-w",
    ]
    # Never echoed by the wrapper itself.
    assert SECRET not in done.stdout and SECRET not in done.stderr


def test_a_different_keychain_service_can_be_named(stubs):
    _, record, _ = stubs
    done = run(
        stubs,
        HUB_EMAIL="agent@example.com",
        HUB_KEYCHAIN_SERVICE="hub-mcp-prod",
        EXPECT_SERVICE="hub-mcp-prod",
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(record.read_text())["password"] == SECRET


def test_no_keychain_item_stops_with_instructions(stubs):
    _, record, _ = stubs
    done = run(stubs, HUB_EMAIL="someone-else@example.com")
    assert done.returncode == 2
    assert "security add-generic-password -s hub-mcp -a someone-else@example.com" in (
        done.stderr
    )
    assert not record.exists()


def test_no_email_stops_before_the_keychain(stubs):
    _, record, tmp_path = stubs
    done = run(stubs)
    assert done.returncode == 2
    assert "HUB_EMAIL" in done.stderr
    assert not (tmp_path / "security-args").exists()
    assert not record.exists()


def test_without_the_security_command_it_explains(stubs):
    bin_dir, record, _ = stubs
    (bin_dir / "security").unlink()
    done = run(stubs, HUB_EMAIL="agent@example.com")
    assert done.returncode == 2
    assert "macOS keychain" in done.stderr
    assert not record.exists()


def test_mcp_json_uses_the_wrapper_and_holds_no_password():
    config = json.loads((ROOT / ".mcp.json").read_text())
    server = config["mcpServers"]["hub"]
    assert server["args"][-1] == "mcp-server/run-with-keychain.sh"
    assert "HUB_PASSWORD" not in json.dumps(server)
