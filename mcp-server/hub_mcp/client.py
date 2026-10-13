"""Async client for the Hub API, the way an agent uses it.

Bearer auth (the API accepts `Authorization: Bearer` alongside the web
app's cookie). It logs in once per process with the configured email and
password, and once more if the token is rejected later (tokens expire
after ACCESS_TOKEN_EXPIRE_MINUTES, 60 by default), so a long-running
agent session keeps working without hitting the login rate limit.

Every path used here is in openapi.yaml; tests/test_contract.py fails if
one goes missing. Project ids are checked to be UUIDs before they go into
a path, so an id can't steer a request to another endpoint, and the
password is never sent over plain http to a remote host.
"""

import ipaddress
import os
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlsplit

import httpx2

DEFAULT_API_URL = "http://localhost:8000"
TIMEOUT_SECONDS = 15.0
# Longest API error text passed on to the model; a proxy's HTML error
# page shouldn't flood the agent's context.
MAX_ERROR_CHARS = 500
# The backend's project ids (uuid4), any case; nothing else goes in a path.
PROJECT_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
INSECURE_HTTP_OVERRIDE = "HUB_ALLOW_INSECURE_HTTP"


class ConfigError(Exception):
    """A required setting is missing."""


class HubApiError(Exception):
    """The API answered with an error status, or couldn't be reached
    (status 0)."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{status}: {detail}" if status else detail)
        self.status = status
        self.detail = detail


def _is_local_host(host: str) -> bool:
    """localhost, *.localhost, or a loopback address."""
    host = host.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class Settings:
    api_url: str
    email: str
    password: str = field(repr=False)
    # HUB_ALLOW_INSECURE_HTTP=1: let the password go over plain http to a
    # host that isn't local (a trusted private network only).
    allow_insecure_http: bool = False

    def __post_init__(self) -> None:
        parts = urlsplit(self.api_url)
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https") or not parts.hostname:
            raise ConfigError(
                f"HUB_API_URL must be an http(s) URL, not {self.api_url!r}."
            )
        if (
            scheme == "http"
            and not _is_local_host(parts.hostname)
            and not self.allow_insecure_http
        ):
            raise ConfigError(
                f"Refusing to send the Hub password over plain http to "
                f"{parts.hostname}: use https, or set {INSECURE_HTTP_OVERRIDE}=1 "
                "for a trusted private network."
            )

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        """HUB_API_URL (default http://localhost:8000; deployed, the
        site's /api, e.g. https://hub.dnls.dev/api), HUB_EMAIL and
        HUB_PASSWORD (the account the agent acts as; set by
        run-with-keychain.sh, not exported by hand), and
        HUB_ALLOW_INSECURE_HTTP."""
        env = dict(os.environ) if env is None else env
        email = env.get("HUB_EMAIL", "").strip()
        password = env.get("HUB_PASSWORD", "")
        if not email or not password:
            raise ConfigError(
                "Set HUB_EMAIL and HUB_PASSWORD to the Hub account the agent "
                "acts as (and HUB_API_URL if the API isn't on localhost:8000). "
                "With Claude Code, start the server through "
                "mcp-server/run-with-keychain.sh, which reads the password "
                "from the macOS keychain."
            )
        api_url = env.get("HUB_API_URL", "").strip() or DEFAULT_API_URL
        insecure = env.get(INSECURE_HTTP_OVERRIDE, "").strip().lower()
        return cls(
            api_url=api_url.rstrip("/"),
            email=email,
            password=password,
            allow_insecure_http=insecure in ("1", "true", "yes"),
        )


def _project_path(project_id: str, suffix: str = "") -> str:
    """/projects/<id><suffix>, with the id checked to be a UUID and then
    URL-encoded as a second layer: "x/../../auth/me" never becomes a
    request to /auth/me."""
    if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
        shown = repr(project_id)[:80]
        raise HubApiError(
            400,
            f"Invalid project id {shown}: a project id is the UUID that "
            "list_projects returns. Nothing was sent.",
        )
    return f"/projects/{quote(project_id.lower(), safe='')}{suffix}"


def _capped(text: str) -> str:
    if len(text) <= MAX_ERROR_CHARS:
        return text
    return text[:MAX_ERROR_CHARS] + " ... (truncated)"


def _error_detail(response: httpx2.Response) -> str:
    """FastAPI's `detail`: a string, or a list of validation errors;
    capped at MAX_ERROR_CHARS either way."""
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else None
    except ValueError:
        return _capped(response.text or response.reason_phrase)
    if isinstance(detail, list):
        return _capped(
            "; ".join(
                f"{'.'.join(str(p) for p in item.get('loc', [])[1:])}: {item.get('msg')}"
                for item in detail
                if isinstance(item, dict)
            )
        )
    return _capped(str(detail) if detail is not None else response.reason_phrase)


class HubClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._http = httpx2.AsyncClient(
            base_url=settings.api_url, timeout=TIMEOUT_SECONDS, transport=transport
        )
        self._token: str | None = None

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx2.Response:
        try:
            return await self._http.request(method, path, **kwargs)
        except httpx2.RequestError as exc:
            raise HubApiError(
                0, f"Can't reach the Hub API at {self._settings.api_url}: {exc}"
            ) from exc

    async def _login(self) -> str:
        response = await self._send(
            "POST",
            "/auth/login",
            data={
                "username": self._settings.email,
                "password": self._settings.password,
            },
        )
        if response.status_code != 200:
            raise HubApiError(
                response.status_code, f"Login failed: {_error_detail(response)}"
            )
        self._token = response.json()["access_token"]
        return self._token

    async def _request(self, method: str, path: str, json: Any = None) -> Any:
        token = self._token or await self._login()
        response = await self._authorized(method, path, token, json)
        if response.status_code == 401:
            # Expired or rotated token: log in again, once.
            response = await self._authorized(method, path, await self._login(), json)
        if response.status_code >= 400:
            raise HubApiError(response.status_code, _error_detail(response))
        return response.json() if response.content else None

    async def _authorized(
        self, method: str, path: str, token: str, json: Any
    ) -> httpx2.Response:
        return await self._send(
            method, path, json=json, headers={"Authorization": f"Bearer {token}"}
        )

    async def list_projects(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/projects")

    async def get_project(self, project_id: str) -> dict[str, Any]:
        return await self._request("GET", _project_path(project_id))

    async def list_notes(self, project_id: str) -> list[dict[str, Any]]:
        return await self._request("GET", _project_path(project_id, "/notes"))

    async def create_project(self, fields: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/projects", json=fields)

    async def update_project(
        self, project_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request("PATCH", _project_path(project_id), json=fields)

    async def add_note(self, project_id: str, body: str) -> dict[str, Any]:
        return await self._request(
            "POST", _project_path(project_id, "/notes"), json={"body": body}
        )
