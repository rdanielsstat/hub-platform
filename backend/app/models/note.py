from datetime import datetime

from pydantic import Field

from app.models.base import CamelModel
from app.models.project import NOT_BLANK, Project

# Longest accepted note body, in characters. Also a CHECK constraint on the
# notes table (app/db/orm.py, migration 0002).
NOTE_BODY_MAX_LENGTH = 10000


class Note(CamelModel):
    id: str
    project_id: str
    body: str
    created_at: datetime


class CreateNoteInput(CamelModel):
    # Not empty or whitespace only (NOT_BLANK).
    body: str = Field(max_length=NOTE_BODY_MAX_LENGTH, pattern=NOT_BLANK)


class AddNoteResponse(CamelModel):
    note: Note
    project: Project
