from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth.dependencies import get_current_user
from app.auth.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.store import DuplicateEmailError, Store, UserRecord, get_store
from app.models.user import RegisterInput, TokenResponse, User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
def register(
    body: RegisterInput, store: Store = Depends(get_store)
) -> TokenResponse:
    if store.get_user_by_email(body.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    try:
        user = store.create_user(
            email=body.email,
            password_hash=hash_password(body.password),
            display_name=body.display_name,
        )
    except DuplicateEmailError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    store: Store = Depends(get_store),
) -> TokenResponse:
    user = store.get_user_by_email(form_data.username)
    # Verify against a dummy hash when the email doesn't exist, so this
    # branch costs the same as a real wrong-password check (see
    # DUMMY_PASSWORD_HASH) instead of returning faster and leaking which
    # emails are registered via response timing.
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    if user is None or not verify_password(form_data.password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=User)
def read_current_user(
    current_user: UserRecord = Depends(get_current_user),
) -> User:
    return User.model_validate(current_user, from_attributes=True)
