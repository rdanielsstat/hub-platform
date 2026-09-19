from datetime import datetime

from app.models.base import CamelModel
from app.models.project import Project


class Note(CamelModel):
    id: str
    project_id: str
    body: str
    created_at: datetime


class CreateNoteInput(CamelModel):
    body: str


class AddNoteResponse(CamelModel):
    note: Note
    project: Project
