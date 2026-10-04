from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.security import OAuth2PasswordRequestForm

from app.auth.cookies import clear_auth_cookie, set_auth_cookie
from app.auth.dependencies import get_current_user
from app.auth.rate_limit import limit_login_attempts, limit_register_attempts
from app.auth.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from app.core.quotas import enforce_account_cap
from app.db.store import DuplicateEmailError, Store, UserRecord, get_store
from app.models.user import PASSWORD_MAX_LENGTH, RegisterInput, TokenResponse, User

router = APIRouter(prefix="/auth", tags=["auth"])


def _start_session(response: Response, user_id: str) -> TokenResponse:
    """Issue a token, both as the httpOnly session cookie (the web app
    uses only this) and in the body (for API clients that send it back as
    an Authorization: Bearer header)."""
    token = create_access_token(user_id)
    set_auth_cookie(response, token)
    return TokenResponse(access_token=token)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_register_attempts)],
)
def register(
    body: RegisterInput, response: Response, store: Store = Depends(get_store)
) -> TokenResponse:
    if store.get_user_by_email(body.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    enforce_account_cap(store)
    try:
        user = store.create_user(
            email=body.email,
            password_hash=hash_password(body.password),
            display_name=body.display_name,
        )
    except DuplicateEmailError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from None
    return _start_session(response, user.id)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(limit_login_attempts)],
)
def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    store: Store = Depends(get_store),
) -> TokenResponse:
    # Same cap as registration, checked before any argon2 work: no stored
    # password can be longer, so nothing valid is turned away. A 422 in
    # FastAPI's usual validation shape, like an over-long sign-up password.
    if len(form_data.password) > PASSWORD_MAX_LENGTH:
        raise RequestValidationError(
            [
                {
                    "type": "string_too_long",
                    "loc": ("body", "password"),
                    "msg": f"String should have at most {PASSWORD_MAX_LENGTH} characters",
                    "input": None,
                    "ctx": {"max_length": PASSWORD_MAX_LENGTH},
                }
            ]
        )
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
    return _start_session(response, user.id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    """Clear the session cookie. Needs no credentials: it only tells
    the browser to drop its own cookie. JWTs are stateless, so a token
    already copied elsewhere stays valid until it expires."""
    clear_auth_cookie(response)


@router.get("/me", response_model=User)
def read_current_user(
    current_user: UserRecord = Depends(get_current_user),
) -> User:
    return User.model_validate(current_user, from_attributes=True)
