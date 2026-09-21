"""Password hashing and JWT issuance/verification.

No security-relevant values live here — secret, algorithm, and expiry
all come from app/core/config.py, the single settings source.
"""

from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, get_jwt_secret

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Hash of a placeholder, never-issued password, computed once at import.
# login() verifies against this when the email lookup misses, so a
# nonexistent-email attempt pays the same argon2 cost as a real
# wrong-password attempt — otherwise the two are distinguishable by
# response time, which lets an attacker enumerate registered emails.
DUMMY_PASSWORD_HASH = pwd_context.hash(
    "not-a-real-password-this-is-only-used-for-timing"
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None
