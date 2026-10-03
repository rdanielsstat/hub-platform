from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.base import CamelModel

# Longest password accepted at sign-up and at login. argon2 hashes the
# whole input and is slow by design, so an uncapped login would let one
# request burn seconds of Lambda CPU.
PASSWORD_MAX_LENGTH = 256

# Longest display name, in characters. Also a CHECK constraint on users
# (app/db/orm.py, migration 0003).
DISPLAY_NAME_MAX_LENGTH = 100


class User(CamelModel):
    id: str
    email: EmailStr
    display_name: str | None = None
    created_at: datetime
    updated_at: datetime


class RegisterInput(CamelModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=PASSWORD_MAX_LENGTH)
    display_name: str | None = Field(default=None, max_length=DISPLAY_NAME_MAX_LENGTH)


class TokenResponse(BaseModel):
    """Field names follow the OAuth2 spec (snake_case), not CamelModel,
    for compatibility with standard OAuth2 client tooling."""

    access_token: str
    token_type: str = "bearer"
