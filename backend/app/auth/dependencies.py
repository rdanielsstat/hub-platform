from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.auth.cookies import clear_auth_cookie_header
from app.auth.security import decode_access_token
from app.core.config import AUTH_COOKIE_NAME
from app.db.store import Store, UserRecord, get_store

# auto_error off: a request with no Authorization header may still carry
# the session cookie, so get_current_user decides when it's a 401.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_current_user(
    request: Request,
    bearer_token: str | None = Depends(oauth2_scheme),
    store: Store = Depends(get_store),
) -> UserRecord:
    """The user from the Authorization: Bearer header (API clients) or,
    failing that, the httpOnly session cookie (the web app). The header
    wins when both are sent."""
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)
    token = bearer_token or cookie_token
    headers = {"WWW-Authenticate": "Bearer"}
    if not bearer_token and cookie_token:
        # A cookie that doesn't validate (expired, signed with a rotated
        # secret, tampered) is cleared, since JavaScript can't remove it.
        headers["Set-Cookie"] = clear_auth_cookie_header()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers=headers,
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = decode_access_token(token)
    if user_id is None:
        raise credentials_exception
    user = store.get_user(user_id)
    if user is None:
        raise credentials_exception
    return user
