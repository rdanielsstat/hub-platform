"""The MCP tools. Each one is a thin call to the Hub API as the
configured user, so the API's own checks (ownership, field limits,
per-user caps) apply exactly as they do to the web app.

Deliberately no delete tools: an agent can capture, update and annotate
ideas but never remove one or a note. Deleting stays a human action in
the web app (docs/permissions.md).
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from hub_mcp.client import HubApiError, HubClient

Status = Literal["Inbox", "Exploring", "Active", "Parked", "Graduated", "Killed"]

INSTRUCTIONS = (
    "Hub holds one person's project ideas. Each has a status (Inbox, "
    "Exploring, Active, Parked, Graduated, Killed), a one-line pitch, a "
    "next action, tags, and 1-5 scores for excitement, potential and "
    "effort. Use list_projects to find ideas, get_project for the full "
    "record and its notes, create_project to capture a new idea, "
    "update_project to change one, and add_note to record progress. "
    "Ideas and notes can't be deleted through these tools."
)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, open_world_hint=False
)

# What list_projects returns per idea: enough to choose one, without the
# long description and the links.
SUMMARY_FIELDS = (
    "id",
    "name",
    "pitch",
    "status",
    "tags",
    "nextAction",
    "excitement",
    "potential",
    "effort",
    "targetDate",
    "updatedAt",
)


def _matches(project: dict[str, Any], query: str) -> bool:
    """Case-insensitive match on name, pitch, description or a tag, like
    the dashboard's search box."""
    needle = query.casefold()
    haystack = [project["name"], project["pitch"], project["description"]]
    return any(needle in text.casefold() for text in haystack + project["tags"])


def create_server(client_factory: Callable[[], HubClient]) -> MCPServer:
    """client_factory is called once per server run; the client is
    closed when the server stops."""
    holder: dict[str, HubClient] = {}

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[None]:
        holder["client"] = client_factory()
        try:
            yield
        finally:
            await holder.pop("client").aclose()

    server = MCPServer("hub", instructions=INSTRUCTIONS, lifespan=lifespan)

    async def call(method: str, *args: Any) -> Any:
        try:
            return await getattr(holder["client"], method)(*args)
        except HubApiError as exc:
            # Surfaced to the agent as a tool error with the API's message
            # (e.g. "404: Project not found", a 422 field error).
            raise ToolError(f"Hub API error {exc}") from exc

    @server.tool(annotations=READ_ONLY)
    async def list_projects(
        status: Status | None = None,
        tag: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        """List the user's project ideas, most recently updated first.
        Optionally filter by status, by an exact tag, and by a search
        query matched against name, pitch, description and tags."""
        projects = await call("list_projects")
        if status:
            projects = [p for p in projects if p["status"] == status]
        if tag:
            projects = [p for p in projects if tag in p["tags"]]
        if query:
            projects = [p for p in projects if _matches(p, query)]
        projects.sort(key=lambda p: p["updatedAt"], reverse=True)
        return [{k: p[k] for k in SUMMARY_FIELDS} for p in projects]

    @server.tool(annotations=READ_ONLY)
    async def get_project(project_id: str) -> dict[str, Any]:
        """One project idea in full (description, links, dates), with its
        notes, newest first."""
        project = await call("get_project", project_id)
        notes = await call("list_notes", project_id)
        return {"project": project, "notes": notes}

    @server.tool(annotations=WRITE)
    async def create_project(
        name: str,
        pitch: str = "",
        description: str = "",
        status: Status = "Inbox",
        tags: list[str] | None = None,
        next_action: str = "",
    ) -> dict[str, Any]:
        """Capture a new project idea. Only the name is required; it
        starts in Inbox unless a status is given. Scores default to 3."""
        return await call(
            "create_project",
            {
                "name": name,
                "pitch": pitch,
                "description": description,
                "status": status,
                "tags": tags or [],
                "nextAction": next_action,
            },
        )

    @server.tool(annotations=WRITE)
    async def update_project(
        project_id: str,
        name: str | None = None,
        pitch: str | None = None,
        description: str | None = None,
        status: Status | None = None,
        tags: list[str] | None = None,
        next_action: str | None = None,
        excitement: int | None = None,
        potential: int | None = None,
        effort: int | None = None,
        target_date: str | None = None,
    ) -> dict[str, Any]:
        """Change fields of a project idea; only the arguments given are
        changed. tags replaces the whole list. Scores are 1-5;
        target_date is YYYY-MM-DD."""
        fields = {
            "name": name,
            "pitch": pitch,
            "description": description,
            "status": status,
            "tags": tags,
            "nextAction": next_action,
            "excitement": excitement,
            "potential": potential,
            "effort": effort,
            "targetDate": target_date,
        }
        patch = {k: v for k, v in fields.items() if v is not None}
        if not patch:
            raise ToolError("Nothing to update: pass at least one field.")
        return await call("update_project", project_id, patch)

    @server.tool(annotations=WRITE)
    async def add_note(project_id: str, body: str) -> dict[str, Any]:
        """Add a note (a thought, progress, a decision) to a project
        idea. Returns the note and the updated project."""
        if not body.strip():
            raise ToolError("A note needs some text.")
        return await call("add_note", project_id, body.strip())

    return server
