"""Length limits on free-text fields: the API answers 422 before the
database sees anything, and the database's CHECK constraints (created by
create_all() here, migration 0002 in real databases) back that up."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.note import NOTE_BODY_MAX_LENGTH
from app.models.project import (
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
    NEXT_ACTION_MAX_LENGTH,
    PITCH_MAX_LENGTH,
)

PROJECT_LIMITS = {
    "name": NAME_MAX_LENGTH,
    "pitch": PITCH_MAX_LENGTH,
    "description": DESCRIPTION_MAX_LENGTH,
    "nextAction": NEXT_ACTION_MAX_LENGTH,
}


def test_limits_are_the_agreed_values():
    assert PROJECT_LIMITS == {
        "name": 256,
        "pitch": 2000,
        "description": 5000,
        "nextAction": 1000,
    }
    assert NOTE_BODY_MAX_LENGTH == 10000


@pytest.fixture()
def headers(register_and_login):
    return register_and_login("limits@example.com")


def _error_locs(res) -> list[list]:
    return [e["loc"] for e in res.json()["detail"]]


@pytest.mark.parametrize(("field", "limit"), PROJECT_LIMITS.items())
def test_create_accepts_the_limit_and_rejects_one_more(client, headers, field, limit):
    base = {"name": "p"}

    ok = client.post("/projects", json={**base, field: "x" * limit}, headers=headers)
    too_long = client.post(
        "/projects", json={**base, field: "x" * (limit + 1)}, headers=headers
    )

    assert ok.status_code == 201
    assert ok.json()[field] == "x" * limit
    assert too_long.status_code == 422
    assert ["body", field] in _error_locs(too_long)


@pytest.mark.parametrize(("field", "limit"), PROJECT_LIMITS.items())
def test_update_rejects_over_long_values_and_keeps_the_old_one(
    client, headers, field, limit
):
    project = client.post("/projects", json={"name": "p"}, headers=headers).json()

    res = client.patch(
        f"/projects/{project['id']}", json={field: "y" * (limit + 1)}, headers=headers
    )

    assert res.status_code == 422
    assert client.get(f"/projects/{project['id']}", headers=headers).json()[field] == (
        project[field]
    )


def test_limits_count_characters_not_bytes(client, headers):
    """256 emoji are 1024 bytes in UTF-8 but 256 characters: allowed."""
    res = client.post("/projects", json={"name": "🚀" * NAME_MAX_LENGTH}, headers=headers)

    assert res.status_code == 201


def test_note_body_limit(client, headers):
    project = client.post("/projects", json={"name": "p"}, headers=headers).json()
    url = f"/projects/{project['id']}/notes"

    ok = client.post(url, json={"body": "n" * NOTE_BODY_MAX_LENGTH}, headers=headers)
    too_long = client.post(
        url, json={"body": "n" * (NOTE_BODY_MAX_LENGTH + 1)}, headers=headers
    )

    assert ok.status_code == 201
    assert too_long.status_code == 422
    assert ["body", "body"] in _error_locs(too_long)
    assert len(client.get(url, headers=headers).json()) == 1


def _project_fields(**overrides) -> dict:
    return {
        "name": "p",
        "pitch": "",
        "description": "",
        "status": "Inbox",
        "tags": [],
        "excitement": 3,
        "effort": 3,
        "potential": 3,
        "next_action": "",
        "target_date": None,
        "links": [],
        **overrides,
    }


@pytest.mark.parametrize(
    ("column", "limit"),
    [
        ("name", NAME_MAX_LENGTH),
        ("pitch", PITCH_MAX_LENGTH),
        ("description", DESCRIPTION_MAX_LENGTH),
        ("next_action", NEXT_ACTION_MAX_LENGTH),
    ],
)
def test_database_rejects_over_long_project_fields_written_directly(
    store, column, limit
):
    """The backstop: something bypassing the API still can't store them."""
    user = store.create_user(email="direct@example.com", password_hash="h")
    store.create_project(owner_id=user.id, **_project_fields(**{column: "z" * limit}))

    with pytest.raises(IntegrityError):
        store.create_project(
            owner_id=user.id, **_project_fields(**{column: "z" * (limit + 1)})
        )
    store._db.rollback()


def test_database_rejects_over_long_note_written_directly(store):
    user = store.create_user(email="direct-note@example.com", password_hash="h")
    project = store.create_project(owner_id=user.id, **_project_fields())

    with pytest.raises(IntegrityError):
        store.create_note(project_id=project.id, body="b" * (NOTE_BODY_MAX_LENGTH + 1))
    store._db.rollback()


# ---- tags, links, display name (migration 0003) ----

from app.models.project import (  # noqa: E402
    LINK_LABEL_MAX_LENGTH,
    LINK_URL_MAX_LENGTH,
    LINKS_MAX_ITEMS,
    TAG_MAX_LENGTH,
    TAGS_MAX_ITEMS,
)
from app.models.user import DISPLAY_NAME_MAX_LENGTH  # noqa: E402


def test_list_limits_are_the_agreed_values():
    assert (TAGS_MAX_ITEMS, TAG_MAX_LENGTH) == (50, 64)
    assert (LINKS_MAX_ITEMS, LINK_URL_MAX_LENGTH, LINK_LABEL_MAX_LENGTH) == (50, 2048, 200)
    assert DISPLAY_NAME_MAX_LENGTH == 100


def _url(length: int) -> str:
    prefix = "https://example.com/"
    return prefix + "a" * (length - len(prefix))


@pytest.mark.parametrize(
    ("ok", "too_long", "loc"),
    [
        (
            {"tags": [f"t{i}" for i in range(50)]},
            {"tags": [f"t{i}" for i in range(51)]},
            ["body", "tags"],
        ),
        ({"tags": ["x" * 64]}, {"tags": ["x" * 65]}, ["body", "tags", 0]),
        (
            {"links": [{"url": f"https://e.com/{i}"} for i in range(50)]},
            {"links": [{"url": f"https://e.com/{i}"} for i in range(51)]},
            ["body", "links"],
        ),
        (
            {"links": [{"url": _url(2048)}]},
            {"links": [{"url": _url(2049)}]},
            ["body", "links", 0, "url"],
        ),
        (
            {"links": [{"url": "https://e.com", "label": "l" * 200}]},
            {"links": [{"url": "https://e.com", "label": "l" * 201}]},
            ["body", "links", 0, "label"],
        ),
    ],
)
def test_tag_and_link_limits_on_create_and_update(client, headers, ok, too_long, loc):
    created = client.post("/projects", json={"name": "p", **ok}, headers=headers)
    rejected = client.post("/projects", json={"name": "p", **too_long}, headers=headers)
    patched = client.patch(
        f"/projects/{created.json()['id']}", json=too_long, headers=headers
    )

    assert created.status_code == 201
    assert rejected.status_code == 422
    assert loc in _error_locs(rejected)
    assert patched.status_code == 422


def test_display_name_limit(client):
    ok = client.post(
        "/auth/register",
        json={"email": "dn-ok@example.com", "password": "password123",
              "displayName": "d" * 100},
    )
    too_long = client.post(
        "/auth/register",
        json={"email": "dn-long@example.com", "password": "password123",
              "displayName": "d" * 101},
    )

    assert ok.status_code == 201
    assert too_long.status_code == 422
    assert ["body", "displayName"] in _error_locs(too_long)


def test_database_rejects_too_many_tags_or_links_written_directly(store):
    user = store.create_user(email="lists@example.com", password_hash="h")
    store.create_project(owner_id=user.id, **_project_fields(tags=["t"] * 50))

    for overrides in ({"tags": ["t"] * 51}, {"links": [{"url": "https://e.com"}] * 51}):
        with pytest.raises(IntegrityError):
            store.create_project(owner_id=user.id, **_project_fields(**overrides))
        store._db.rollback()


def test_database_rejects_long_display_name_written_directly(store):
    store.create_user(email="dn1@example.com", password_hash="h", display_name="d" * 100)

    with pytest.raises(IntegrityError):
        store.create_user(email="dn2@example.com", password_hash="h", display_name="d" * 101)
