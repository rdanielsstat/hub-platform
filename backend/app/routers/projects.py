from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.db.store import ProjectRecord, Store, UserRecord, get_store
from app.models.project import CreateProjectInput, Project, UpdateProjectInput

router = APIRouter(prefix="/projects", tags=["projects"])


def _to_project(record: ProjectRecord) -> Project:
    return Project.model_validate(record, from_attributes=True)


def _get_owned_or_404(
    project_id: str, owner_id: str, store: Store
) -> ProjectRecord:
    record = store.get_project(project_id, owner_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return record


@router.get("", response_model=list[Project])
def list_projects(
    current_user: UserRecord = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> list[Project]:
    return [_to_project(r) for r in store.list_projects(current_user.id)]


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
def create_project(
    body: CreateProjectInput,
    current_user: UserRecord = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> Project:
    record = store.create_project(owner_id=current_user.id, **body.model_dump())
    return _to_project(record)


@router.get("/{project_id}", response_model=Project)
def get_project(
    project_id: str,
    current_user: UserRecord = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> Project:
    record = _get_owned_or_404(project_id, current_user.id, store)
    return _to_project(record)


@router.patch("/{project_id}", response_model=Project)
def update_project(
    project_id: str,
    body: UpdateProjectInput,
    current_user: UserRecord = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> Project:
    _get_owned_or_404(project_id, current_user.id, store)
    patch = body.model_dump(exclude_unset=True)
    record = store.update_project(project_id, current_user.id, **patch)
    if record is None:
        # Ownership was confirmed above, so the project was deleted
        # between that check and this update.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found: it was deleted while being updated",
        )
    return _to_project(record)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    current_user: UserRecord = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> None:
    _get_owned_or_404(project_id, current_user.id, store)
    store.delete_project(project_id, current_user.id)
