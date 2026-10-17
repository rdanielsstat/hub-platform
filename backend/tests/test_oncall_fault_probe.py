"""The create-project probe (oncall/fault_probe.py), against a stub Hub
API on a local http.server in a thread. No network access.

The stub checks the headers the real site needs, and answers 403 the way
the edge does when one is missing: Cloudflare refuses a Python-urllib
User-Agent ("error code: 1010", run 39067154127), and the API needs the
site's Origin and the form Content-Type on sign-in and the token on
project creation."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from oncall import fault_probe
from oncall.fault_probe import CANNOT_RUN, FAULT, OK, main

PASSWORD = "stub-password-not-real"
TOKEN = "stub-token-not-real"


class _Stub:
    def __init__(self) -> None:
        self.create_status = 201
        self.login_status = 200
        self.requests: list[tuple[str, str, dict]] = []
        self.missing: list[str] = []
        self.deleted: list[str] = []
        self.origin = ""


def _handler(stub: _Stub):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def _send(self, status: int, body: dict | None = None) -> None:
            data = json.dumps(body or {}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _record(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            stub.requests.append((self.command, self.path, dict(self.headers)))

        def _edge_refuses(self) -> bool:
            """403 like Cloudflare for a missing or Python-urllib agent."""
            agent = self.headers.get("User-Agent", "")
            if not agent or agent.startswith("Python-urllib"):
                stub.missing.append("User-Agent")
                self.send_response(403)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"error code: 1010")
                return True
            return False

        def _require(self, name: str, value: str) -> bool:
            if self.headers.get(name) != value:
                stub.missing.append(name)
                self._send(403, {"detail": "Forbidden"})
                return False
            return True

        def do_POST(self) -> None:
            self._record()
            if self._edge_refuses():
                return
            if self.path == "/api/auth/login":
                if not (
                    self._require("Origin", stub.origin)
                    and self._require(
                        "Content-Type", "application/x-www-form-urlencoded"
                    )
                ):
                    return
                self._send(stub.login_status, {"access_token": TOKEN})
            elif self.path == "/api/projects":
                if not (
                    self._require("Authorization", f"Bearer {TOKEN}")
                    and self._require("Content-Type", "application/json")
                ):
                    return
                body = (
                    {"id": "probe-1"} if stub.create_status < 300 else {"detail": "x"}
                )
                self._send(stub.create_status, body)
            else:
                self._send(404)

        def do_DELETE(self) -> None:
            self._record()
            if self._edge_refuses():
                return
            if not self._require("Authorization", f"Bearer {TOKEN}"):
                return
            stub.deleted.append(self.path)
            self.send_response(204)
            self.end_headers()

    return Handler


@pytest.fixture()
def stub() -> Iterator[tuple[_Stub, str]]:
    state = _Stub()
    server = HTTPServer(("127.0.0.1", 0), _handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.origin = f"http://127.0.0.1:{server.server_port}"
    try:
        yield state, f"http://127.0.0.1:{server.server_port}/api"
    finally:
        server.shutdown()
        server.server_close()


def _env(url: str, **extra: str) -> dict[str, str]:
    return {
        "PROBE_API_URL": url,
        "DEMO_PASSWORDS": json.dumps({"dev": PASSWORD}),
        "PROBE_RETRY_DELAY_S": "0",
        **extra,
    }


def test_a_500_from_project_creation_exits_1(stub, capsys) -> None:
    state, url = stub
    state.create_status = 500
    assert main(_env(url), sleep=lambda _: None) == FAULT
    creates = [r for r in state.requests if r[:2] == ("POST", "/api/projects")]
    assert len(creates) == 3  # retried, then counted as the fault


def test_a_201_from_project_creation_exits_0_and_deletes_the_probe(stub) -> None:
    state, url = stub
    state.create_status = 201
    assert main(_env(url), sleep=lambda _: None) == OK
    assert ("DELETE", "/api/projects/probe-1") in [r[:2] for r in state.requests]


def test_one_cold_start_500_then_201_exits_0(stub) -> None:
    state, url = stub
    state.create_status = 503

    def recover(_: float) -> None:
        state.create_status = 201

    assert main(_env(url), sleep=recover) == OK


def test_a_4xx_means_the_probe_cannot_run(stub) -> None:
    state, url = stub
    state.login_status = 401
    assert main(_env(url), sleep=lambda _: None) == CANNOT_RUN


def test_login_sends_the_site_origin_and_create_sends_the_token(stub) -> None:
    state, url = stub
    main(_env(url), sleep=lambda _: None)
    login = next(r for r in state.requests if r[1] == "/api/auth/login")
    assert login[2]["Origin"] == url.removesuffix("/api")
    create = next(r for r in state.requests if r[1] == "/api/projects")
    assert create[2]["Authorization"] == f"Bearer {TOKEN}"


def test_never_prints_credentials_or_bodies(stub, capsys) -> None:
    state, url = stub
    for status in (201, 500):
        state.create_status = status
        main(_env(url), sleep=lambda _: None)
    out = capsys.readouterr()
    text = out.out + out.err
    assert PASSWORD not in text
    assert TOKEN not in text
    assert "probe-1" not in text
    assert "detail" not in text


def test_missing_settings_cannot_run(capsys) -> None:
    assert main({}, sleep=lambda _: None) == CANNOT_RUN
    assert main({"PROBE_API_URL": "http://127.0.0.1:1/api"}) == CANNOT_RUN
    assert PASSWORD not in capsys.readouterr().out


def test_no_answer_cannot_run() -> None:
    # Port 1 on localhost: nothing listens, so every request fails fast.
    env = _env("http://127.0.0.1:1/api", PROBE_ATTEMPTS="2")
    assert main(env, sleep=lambda _: None) == CANNOT_RUN


def test_the_probe_sends_every_header_the_site_needs(stub) -> None:
    state, url = stub
    assert main(_env(url), sleep=lambda _: None) == OK
    assert state.missing == []
    assert state.deleted == ["/api/projects/probe-1"]
    agents = {r[2].get("User-Agent") for r in state.requests}
    assert agents == {fault_probe.USER_AGENT}


def test_login_403_exits_2_naming_the_step_and_status(stub, capsys) -> None:
    state, url = stub
    state.login_status = 403
    assert main(_env(url), sleep=lambda _: None) == CANNOT_RUN
    out = capsys.readouterr().out
    assert "login failed: POST /auth/login answered 403" in out
    assert "error code" not in out and "detail" not in out


def test_a_missing_header_exits_2(stub, monkeypatch, capsys) -> None:
    """urllib's own signature, as before this fix: the edge refuses it."""
    state, url = stub
    monkeypatch.setattr(fault_probe, "USER_AGENT", "Python-urllib/3.12")
    assert main(_env(url), sleep=lambda _: None) == CANNOT_RUN
    assert state.missing == ["User-Agent"]
    assert "POST /auth/login answered 403" in capsys.readouterr().out


def test_create_500_on_every_try_exits_1(stub) -> None:
    state, url = stub
    state.create_status = 500
    assert main(_env(url), sleep=lambda _: None) == FAULT
    assert state.missing == []


def test_create_4xx_exits_2_naming_the_step_and_status(stub, capsys) -> None:
    state, url = stub
    state.create_status = 403
    assert main(_env(url), sleep=lambda _: None) == CANNOT_RUN
    out = capsys.readouterr().out
    assert "create failed: POST /projects answered 403" in out
    assert "detail" not in out


def test_the_user_agent_is_named_not_pythons_default() -> None:
    assert fault_probe.USER_AGENT == "hub-platform-oncall-probe/1.0"
    assert not fault_probe.USER_AGENT.startswith("Python-urllib")
