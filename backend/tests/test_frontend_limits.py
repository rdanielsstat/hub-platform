"""The frontend's form limits (frontend/src/lib/limits.ts, used as
`maxLength`) must match the API's. Fails when one side changes without the
other, so a form can't let users type more than the API accepts, or stop
them short of it."""

import re
from pathlib import Path

import pytest

from app.models.note import NOTE_BODY_MAX_LENGTH
from app.models.project import (
    DESCRIPTION_MAX_LENGTH,
    LINK_LABEL_MAX_LENGTH,
    LINK_URL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    NEXT_ACTION_MAX_LENGTH,
    PITCH_MAX_LENGTH,
    TAG_MAX_LENGTH,
    TAGS_MAX_ITEMS,
)
from app.models.user import DISPLAY_NAME_MAX_LENGTH, PASSWORD_MAX_LENGTH

LIMITS_TS = Path(__file__).resolve().parents[2] / "frontend/src/lib/limits.ts"

# Frontend constant -> the API's value.
EXPECTED = {
    "PASSWORD_MAX_LENGTH": PASSWORD_MAX_LENGTH,
    "DISPLAY_NAME_MAX_LENGTH": DISPLAY_NAME_MAX_LENGTH,
    "PROJECT_NAME_MAX_LENGTH": NAME_MAX_LENGTH,
    "PITCH_MAX_LENGTH": PITCH_MAX_LENGTH,
    "DESCRIPTION_MAX_LENGTH": DESCRIPTION_MAX_LENGTH,
    "NEXT_ACTION_MAX_LENGTH": NEXT_ACTION_MAX_LENGTH,
    "NOTE_MAX_LENGTH": NOTE_BODY_MAX_LENGTH,
    "TAG_MAX_LENGTH": TAG_MAX_LENGTH,
    "TAGS_MAX_ITEMS": TAGS_MAX_ITEMS,
    "LINK_URL_MAX_LENGTH": LINK_URL_MAX_LENGTH,
    "LINK_LABEL_MAX_LENGTH": LINK_LABEL_MAX_LENGTH,
    # No backend constant: email-validator's own 254-character maximum,
    # checked against the API below.
    "EMAIL_MAX_LENGTH": 254,
}


def _frontend_limits() -> dict[str, int]:
    text = LIMITS_TS.read_text(encoding="utf-8")
    return {
        name: int(value)
        for name, value in re.findall(r"export const (\w+) = (\d+)\b", text)
    }


def test_every_frontend_limit_matches_the_api():
    frontend = _frontend_limits()

    assert frontend == EXPECTED


def _email(length: int) -> str:
    """A syntactically valid address of exactly `length` characters (local
    part of 64, domain labels of at most 63)."""
    local = "a" * 64
    remaining = length - len(local) - 1 - len(".com")
    labels = []
    while remaining > 0:
        size = min(63, remaining)
        labels.append("b" * size)
        remaining -= size + 1
    domain = ".".join(labels)
    address = f"{local}@{domain}.com"
    return address[:length] if len(address) > length else address


@pytest.mark.parametrize(("length", "status"), [(254, 201), (255, 422)])
def test_api_email_limit_is_254(client, length, status):
    email = _email(length)
    assert len(email) in (length, length - 1)
    if len(email) != length:
        pytest.skip("couldn't build an address of exactly this length")

    res = client.post(
        "/auth/register", json={"email": email, "password": "password123"}
    )

    assert res.status_code == status
