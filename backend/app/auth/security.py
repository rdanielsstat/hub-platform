"""Password hashing and JWT issuance/verification.

No security-relevant values live here — secret, algorithm, and expiry
all come from app/core/config.py, the single settings source.
"""

from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, get_jwt_secret

# Pinned explicitly to what passlib produced (it copied argon2-cffi's
# defaults at import), so new hashes are indistinguishable from existing
# ones and a future argon2-cffi release can't change them silently.
# Verification reads the parameters from each stored hash, so hashes
# made with other parameters still verify.
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

# Hash of a placeholder, never-issued password, computed once at import.
# login() verifies against this when the email lookup misses, so a
# nonexistent-email attempt pays the same argon2 cost as a real
# wrong-password attempt — otherwise the two are distinguishable by
# response time, which lets an attacker enumerate registered emails.
DUMMY_PASSWORD_HASH = _password_hasher.hash(
    "not-a-real-password-this-is-only-used-for-timing"
)


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """False for a wrong password, and also for a stored hash that
    isn't a valid argon2 hash at all (empty, truncated, another scheme),
    rather than raising: either way the password doesn't check out."""
    if not isinstance(password_hash, str):
        return False
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None
