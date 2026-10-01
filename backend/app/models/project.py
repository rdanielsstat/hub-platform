from datetime import date, datetime
from enum import Enum

from pydantic import Field, field_validator

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

    @field_validator("url")
    @classmethod
    def _require_http_scheme(cls, value: str) -> str:
        # The frontend always normalizes a link to http(s) before saving,
        # but that's client-side only. Without this, a direct API call
        # could store e.g. a javascript: URL, which would then render as
        # a clickable href on the project-detail page.
        if not value.lower().startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return value


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

    # None is only the "not sent" default here. An explicit null is valid
    # for target_date alone (it clears the date); for any other field it
    # would hit a NOT NULL column, or for tags/links be stored and break
    # every later read of the project. Before-mode validators don't run on
    # omitted fields, so partial updates are unaffected.
    @field_validator(
        "name",
        "pitch",
        "description",
        "status",
        "tags",
        "excitement",
        "effort",
        "potential",
        "next_action",
        "links",
        mode="before",
    )
    @classmethod
    def _reject_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("may not be null")
        return value
