"""Tests for password hashing in app/auth/security.py.

The *_HASH constants below are literal strings produced by the previous
implementation (passlib 1.7.4's CryptContext(schemes=["argon2"]) on
argon2-cffi 25.1.0), captured before passlib was removed. They are the
regression guard for every password hash already stored in a database:
if any of them stops verifying, existing accounts are locked out, since
a hash can't be reversed to re-hash it. Never regenerate them.
"""

import re
import sys

import pytest

from app.auth.security import DUMMY_PASSWORD_HASH, hash_password, verify_password

PASSWORD = "correct horse battery staple"
UNICODE_PASSWORD = "pässwörd 🔐 密码"

# passlib with this app's configuration, i.e. the parameters every
# existing account was hashed with.
PASSLIB_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$TGnN+b/3XouxllIqpXQu5Q"
    "$ZHvaQcS+pV4nieCvISB3jpvzkSb/RdiUV8gm6zG5fX4"
)
PASSLIB_UNICODE_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$y1mr1fpfa03JOWfMOedcCw"
    "$gjoxH72psGjcTo5631PDf9gO6+mDY0WWkvrr1ZNxalY"
)
# passlib with argon2-cffi's pre-21.2 defaults (t=2, m=102400, p=8,
# 16-byte hash), which passlib would have inherited on an older install.
PASSLIB_LEGACY_PARAMS_HASH = (
    "$argon2id$v=19$m=102400,t=2,p=8$SOld6/1fKyUEAMBYS+k9Zw$Rs69DZWXfQZ+N4yfXhwQlg"
)

# The exact format the previous implementation produced: argon2id,
# version 19, 64 MiB, 3 passes, 4 lanes, then a 16-byte salt (22
# unpadded base64 chars) and a 32-byte hash (43 chars).
HASH_FORMAT = re.compile(
    r"^\$argon2id\$v=19\$m=65536,t=3,p=4\$[A-Za-z0-9+/]{22}\$[A-Za-z0-9+/]{43}$"
)


# ---- existing hashes keep verifying ----


@pytest.mark.parametrize(
    ("stored_hash", "password"),
    [
        (PASSLIB_HASH, PASSWORD),
        (PASSLIB_UNICODE_HASH, UNICODE_PASSWORD),
        (PASSLIB_LEGACY_PARAMS_HASH, PASSWORD),
    ],
)
def test_hashes_from_the_previous_implementation_still_verify(stored_hash, password):
    assert verify_password(password, stored_hash) is True


@pytest.mark.parametrize(
    "stored_hash", [PASSLIB_HASH, PASSLIB_UNICODE_HASH, PASSLIB_LEGACY_PARAMS_HASH]
)
def test_wrong_password_fails_against_previous_hashes(stored_hash):
    assert verify_password("not the password", stored_hash) is False


# ---- new hashes ----


def test_new_hashes_match_the_previous_format_and_parameters():
    assert HASH_FORMAT.fullmatch(hash_password(PASSWORD))


def test_dummy_hash_uses_the_same_parameters():
    """login() verifies against this for unknown emails; it must cost
    the same as a real account's hash or response time leaks which
    emails exist."""
    assert HASH_FORMAT.fullmatch(DUMMY_PASSWORD_HASH)


def test_round_trip():
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


def test_wrong_password_fails():
    assert verify_password("not the password", hash_password(PASSWORD)) is False


def test_same_password_hashes_differently_each_time():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)

    assert first != second
    assert verify_password(PASSWORD, first) is True
    assert verify_password(PASSWORD, second) is True


# ---- edge-case passwords ----


def test_empty_password():
    empty_hash = hash_password("")

    assert verify_password("", empty_hash) is True
    assert verify_password(" ", empty_hash) is False
    assert verify_password("", hash_password(PASSWORD)) is False


@pytest.mark.parametrize(
    "password",
    [
        "x" * 256,  # RegisterInput's max_length
        "x" * 10_000,  # beyond passlib's 4096-byte cap, e.g. via /auth/login
    ],
    ids=["256-chars", "10000-chars"],
)
def test_very_long_password(password):
    stored = hash_password(password)

    assert verify_password(password, stored) is True
    assert verify_password(password[:-1], stored) is False
    assert verify_password(password + "x", stored) is False


def test_unicode_password():
    stored = hash_password(UNICODE_PASSWORD)

    assert verify_password(UNICODE_PASSWORD, stored) is True
    assert verify_password("passwörd 🔐 密码", stored) is False


# ---- malformed stored hashes fail like a wrong password ----


@pytest.mark.parametrize(
    "bad_hash",
    [
        "",
        "not-a-hash",
        PASSLIB_HASH[:40],  # truncated mid-parameters
        PASSLIB_HASH[:-10],  # truncated hash part
        PASSLIB_HASH[:-5] + "!!!!!",  # invalid base64
        "$argon2id$v=19$m=65536,t=3,p=4$$",  # empty salt and hash
        "$2b$12$abcdefghijklmnopqrstuuMhHK2DWe5rgmHG6oZ9ooJW3N2bM/Vi",  # bcrypt
    ],
)
def test_malformed_hash_fails_verification_without_raising(bad_hash):
    assert verify_password(PASSWORD, bad_hash) is False


def test_none_hash_fails_verification_without_raising():
    """The previous implementation returned False for None; kept."""
    assert verify_password(PASSWORD, None) is False  # type: ignore[arg-type]


# ---- passlib is gone ----


def test_app_does_not_import_passlib():
    import app.main  # noqa: F401

    assert not [m for m in sys.modules if m == "passlib" or m.startswith("passlib.")]
