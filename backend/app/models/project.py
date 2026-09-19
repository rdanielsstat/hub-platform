from datetime import date, datetime
from enum import Enum

from pydantic import Field

from app.models.base import CamelModel


class Status(str, Enum):
    INBOX = "Inbox"
    EXPLORING = "Exploring"
    ACTIVE = "Active"
    PARKED = "Parked"
    GRADUATED = "Graduated"
    KILLED = "Killed"


class Link(CamelModel):
    label: str | None = None
    url: str


class Project(CamelModel):
    id: str
    name: str
    pitch: str
    description: str
    status: Status
    tags: list[str]
    excitement: int = Field(ge=1, le=5)
    effort: int = Field(ge=1, le=5)
    potential: int = Field(ge=1, le=5)
    next_action: str
    target_date: date | None
    links: list[Link]
    created_at: datetime
    updated_at: datetime


class CreateProjectInput(CamelModel):
    name: str
    pitch: str = ""
    description: str = ""
    status: Status = Status.INBOX
    tags: list[str] = Field(default_factory=list)
    excitement: int = Field(default=3, ge=1, le=5)
    effort: int = Field(default=3, ge=1, le=5)
    potential: int = Field(default=3, ge=1, le=5)
    next_action: str = ""
    target_date: date | None = None
    links: list[Link] = Field(default_factory=list)


class UpdateProjectInput(CamelModel):
    """Partial update. Only fields the client actually sent should be
    applied; routers must use `exclude_unset=True` when reading this."""

    name: str | None = None
    pitch: str | None = None
    description: str | None = None
    status: Status | None = None
    tags: list[str] | None = None
    excitement: int | None = Field(default=None, ge=1, le=5)
    effort: int | None = Field(default=None, ge=1, le=5)
    potential: int | None = Field(default=None, ge=1, le=5)
    next_action: str | None = None
    target_date: date | None = None
    links: list[Link] | None = None
