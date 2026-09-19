from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.base import CamelModel


class User(CamelModel):
    id: str
    email: EmailStr
    display_name: str | None = None
    created_at: datetime
    updated_at: datetime


class RegisterInput(CamelModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str | None = None


class TokenResponse(BaseModel):
    """Field names follow the OAuth2 spec (snake_case), not CamelModel,
    for compatibility with standard OAuth2 client tooling."""

    access_token: str
    token_type: str = "bearer"
