from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.db.store import (
    Store,
    NoteRecord,
    ProjectRecord,
    UserRecord,
    get_store,
)
from app.models.note import AddNoteResponse, CreateNoteInput, Note
from app.models.project import Project

router = APIRouter(tags=["notes"])


def _to_note(record: NoteRecord) -> Note:
    return Note.model_validate(record, from_attributes=True)


def _to_project(record: ProjectRecord) -> Project:
    return Project.model_validate(record, from_attributes=True)


def _get_owned_project_or_404(
    project_id: str, owner_id: str, store: Store
) -> ProjectRecord:
    record = store.get_project(project_id, owner_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return record


@router.get("/projects/{project_id}/notes", response_model=list[Note])
def list_notes(
    project_id: str,
    current_user: UserRecord = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> list[Note]:
    _get_owned_project_or_404(project_id, current_user.id, store)
    return [_to_note(n) for n in store.list_notes(project_id)]


@router.post(
    "/projects/{project_id}/notes",
    response_model=AddNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_note(
    project_id: str,
    payload: CreateNoteInput,
    current_user: UserRecord = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> AddNoteResponse:
    _get_owned_project_or_404(project_id, current_user.id, store)
    note = store.create_note(project_id=project_id, body=payload.body)
    project = store.update_project(project_id, current_user.id)
    assert project is not None  # ownership just confirmed above
    return AddNoteResponse(note=_to_note(note), project=_to_project(project))


@router.delete("/notes/{note_id}", response_model=Project)
def delete_note(
    note_id: str,
    current_user: UserRecord = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> Project:
    note = store.get_note(note_id)
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Note not found"
        )
    _get_owned_project_or_404(note.project_id, current_user.id, store)
    store.delete_note(note_id)
    project = store.update_project(note.project_id, current_user.id)
    assert project is not None
    return _to_project(project)
