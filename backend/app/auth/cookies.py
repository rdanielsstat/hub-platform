"""The browser session cookie (see AUTH_COOKIE_NAME in app/core/config.py).

Set on login/register, cleared on logout and whenever a request's cookie
fails to validate, so a stale cookie doesn't keep getting sent.
"""

from fastapi import Response

from app.core.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    AUTH_COOKIE_NAME,
    AUTH_COOKIE_SECURE,
)

_COOKIE_ATTRIBUTES = {
    "path": "/",
    "secure": AUTH_COOKIE_SECURE,
    "httponly": True,
    "samesite": "strict",
}


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **_COOKIE_ATTRIBUTES,
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, **_COOKIE_ATTRIBUTES)


def clear_auth_cookie_header() -> str:
    """The Set-Cookie value that clears the cookie, for responses built
    as an HTTPException rather than a Response."""
    response = Response()
    clear_auth_cookie(response)
    return response.headers["set-cookie"]
