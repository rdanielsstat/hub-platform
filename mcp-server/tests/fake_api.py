"""An in-memory stand-in for the Hub API, mounted on httpx2.MockTransport:
just the endpoints hub_mcp calls, with the real API's auth, ownership
404s, camelCase fields and error shapes."""

import json
import uuid
from datetime import UTC, datetime
from itertools import count
from typing import Any
from urllib.parse import parse_qs

import httpx2

EMAIL = "agent@example.com"
PASSWORD = "correct-horse"
# A well-formed project id that no project has.
MISSING_ID = "00000000-0000-4000-8000-000000000000"


class FakeHubApi:
    def __init__(self) -> None:
        self.projects: dict[str, dict[str, Any]] = {}
        self.notes: dict[str, list[dict[str, Any]]] = {}
        self.requests: list[httpx2.Request] = []
        self.logins = 0
        self.valid_tokens: set[str] = set()
        self._ids = count(1)
        self._clock = count(1)

    # --- test helpers ---------------------------------------------------

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self.handle)

    def expire_tokens(self) -> None:
        self.valid_tokens.clear()

    def seed(self, **fields: Any) -> dict[str, Any]:
        project = self._new_project(fields)
        self.projects[project["id"]] = project
        self.notes[project["id"]] = []
        return project

    # --- request handling -----------------------------------------------

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        path, method = request.url.path, request.method
        if (method, path) == ("POST", "/auth/login"):
            return self._login(request)
        auth = request.headers.get("Authorization", "")
        if auth.removeprefix("Bearer ") not in self.valid_tokens:
            return _error(401, "Could not validate credentials")

        parts = path.strip("/").split("/")
        body = json.loads(request.content) if request.content else None
        if parts == ["projects"]:
            if method == "GET":
                return _ok(list(self.projects.values()))
            return self._create(body)
        if len(parts) >= 2 and parts[0] == "projects":
            project = self.projects.get(parts[1])
            if project is None:
                return _error(404, "Project not found")
            if len(parts) == 2 and method == "GET":
                return _ok(project)
            if len(parts) == 2 and method == "PATCH":
                project.update(body)
                project["updatedAt"] = self._now()
                return _ok(project)
            if len(parts) == 3 and parts[2] == "notes":
                if method == "GET":
                    return _ok(self.notes[project["id"]])
                note = {
                    "id": f"n{next(self._ids)}",
                    "projectId": project["id"],
                    "body": body["body"],
                    "createdAt": self._now(),
                }
                self.notes[project["id"]].insert(0, note)
                project["updatedAt"] = note["createdAt"]
                return _ok({"note": note, "project": project}, status=201)
        return _error(404, "Not Found")

    def _login(self, request: httpx2.Request) -> httpx2.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        if form.get("username") != EMAIL or form.get("password") != PASSWORD:
            return _error(401, "Incorrect email or password")
        self.logins += 1
        token = f"token-{self.logins}"
        self.valid_tokens.add(token)
        return _ok({"access_token": token, "token_type": "bearer"})

    def _create(self, body: dict[str, Any]) -> httpx2.Response:
        if len(body.get("name", "")) > 256:
            return httpx2.Response(
                422,
                json={
                    "detail": [
                        {
                            "loc": ["body", "name"],
                            "msg": "String should have at most 256 characters",
                        }
                    ]
                },
            )
        project = self._new_project(body)
        self.projects[project["id"]] = project
        self.notes[project["id"]] = []
        return _ok(project, status=201)

    def _new_project(self, fields: dict[str, Any]) -> dict[str, Any]:
        now = self._now()
        return {
            "id": str(uuid.uuid4()),  # as the backend does
            "name": "Untitled",
            "pitch": "",
            "description": "",
            "status": "Inbox",
            "tags": [],
            "excitement": 3,
            "effort": 3,
            "potential": 3,
            "nextAction": "",
            "targetDate": None,
            "links": [],
            "createdAt": now,
            "updatedAt": now,
        } | fields

    def _now(self) -> str:
        # Strictly increasing, so "most recently updated" is well defined.
        return datetime(2026, 10, 1, 0, 0, next(self._clock), tzinfo=UTC).isoformat()


def _ok(payload: Any, status: int = 200) -> httpx2.Response:
    return httpx2.Response(status, json=payload)


def _error(status: int, detail: str) -> httpx2.Response:
    return httpx2.Response(status, json={"detail": detail})
