"""Notes against real Postgres: ordering, ownership through the parent
project, and the cascade when a project is deleted."""

import time

import pytest
from sqlalchemy import text

from app.core import config

pytestmark = pytest.mark.integration


@pytest.fixture()
def owner(client, register_and_login):
    headers = register_and_login("notes-owner@example.com")
    project = client.post("/projects", json={"name": "Noted"}, headers=headers).json()
    return headers, project


def _add(client, headers, project_id: str, body: str):
    return client.post(
        f"/projects/{project_id}/notes", json={"body": body}, headers=headers
    )


def test_add_note_returns_note_and_bumps_the_project(client, owner):
    headers, project = owner
    time.sleep(0.01)

    res = _add(client, headers, project["id"], "First thought")

    assert res.status_code == 201
    body = res.json()
    assert body["note"]["body"] == "First thought"
    assert body["note"]["projectId"] == project["id"]
    assert body["project"]["updatedAt"] > project["updatedAt"]


def test_notes_are_listed_newest_first(client, owner):
    headers, project = owner
    for body in ("one", "two", "three"):
        _add(client, headers, project["id"], body)
        time.sleep(0.005)

    notes = client.get(f"/projects/{project['id']}/notes", headers=headers).json()

    assert [n["body"] for n in notes] == ["three", "two", "one"]


def test_delete_note_returns_the_updated_project(client, owner):
    headers, project = owner
    note = _add(client, headers, project["id"], "temporary").json()["note"]

    res = client.delete(f"/notes/{note['id']}", headers=headers)

    assert res.status_code == 200
    assert res.json()["id"] == project["id"]
    assert client.get(f"/projects/{project['id']}/notes", headers=headers).json() == []


def test_other_users_cannot_see_add_or_delete_notes(client, owner, register_and_login):
    headers, project = owner
    note = _add(client, headers, project["id"], "private").json()["note"]
    intruder = register_and_login("intruder@example.com")

    assert (
        client.get(f"/projects/{project['id']}/notes", headers=intruder).status_code
        == 404
    )
    assert _add(client, intruder, project["id"], "sneaky").status_code == 404
    assert client.delete(f"/notes/{note['id']}", headers=intruder).status_code == 404
    assert (
        len(client.get(f"/projects/{project['id']}/notes", headers=headers).json()) == 1
    )


def test_deleting_a_project_cascades_to_its_notes(client, owner, store):
    headers, project = owner
    _add(client, headers, project["id"], "a")
    _add(client, headers, project["id"], "b")

    client.delete(f"/projects/{project['id']}", headers=headers)

    assert store._db.execute(text("SELECT count(*) FROM notes")).scalar_one() == 0


def test_large_unicode_note_round_trips(client, owner):
    headers, project = owner
    # 14 characters x 700 = 9800, under the 10,000-character limit; well
    # over that in UTF-8 bytes, which the limit doesn't count.
    body = "Ünïcödé 日本語 🚀 " * 700

    _add(client, headers, project["id"], body)
    (note,) = client.get(f"/projects/{project['id']}/notes", headers=headers).json()

    assert note["body"] == body


def test_note_body_limit_on_postgres(client, owner):
    headers, project = owner

    assert _add(client, headers, project["id"], "n" * 10000).status_code == 201
    assert _add(client, headers, project["id"], "n" * 10001).status_code == 422


def test_note_cap_on_postgres(client, owner, monkeypatch):
    headers, project = owner
    monkeypatch.setattr(config, "MAX_NOTES_PER_PROJECT", 2)

    statuses = [
        _add(client, headers, project["id"], f"n{i}").status_code for i in range(3)
    ]

    assert statuses == [201, 201, 403]
