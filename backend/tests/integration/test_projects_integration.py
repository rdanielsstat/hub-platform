"""Projects against real Postgres: JSON columns, the native status
enum, dates, per-user isolation and foreign-key cascades."""

import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core import config

pytestmark = pytest.mark.integration

FULL_PROJECT = {
    "name": "Ünïcödé project 日本語 🚀",
    "pitch": "One line",
    "description": "Long brain-dump\nwith newlines",
    "status": "Exploring",
    "tags": ["ai", "side-project", "naïve"],
    "excitement": 5,
    "effort": 2,
    "potential": 4,
    "nextAction": "Sketch the data model",
    "targetDate": "2026-12-31",
    "links": [
        {"label": "Repo", "url": "https://example.com/repo"},
        {"url": "http://example.com/no-label"},
    ],
}


def test_create_and_read_back_every_field(client, register_and_login):
    headers = register_and_login("projects@example.com")

    created = client.post("/projects", json=FULL_PROJECT, headers=headers)
    assert created.status_code == 201
    project = client.get(f"/projects/{created.json()['id']}", headers=headers).json()

    for field in (
        "name",
        "pitch",
        "description",
        "status",
        "tags",
        "excitement",
        "effort",
        "potential",
        "nextAction",
        "targetDate",
    ):
        assert project[field] == FULL_PROJECT[field], field
    assert project["links"] == [
        {"label": "Repo", "url": "https://example.com/repo"},
        {"label": None, "url": "http://example.com/no-label"},
    ]
    assert project["createdAt"] == project["updatedAt"]


def test_partial_update_changes_only_sent_fields_and_bumps_updated_at(
    client, register_and_login
):
    headers = register_and_login("patch@example.com")
    project = client.post("/projects", json=FULL_PROJECT, headers=headers).json()
    time.sleep(0.01)

    res = client.patch(
        f"/projects/{project['id']}",
        json={"status": "Active", "tags": [], "targetDate": None},
        headers=headers,
    )

    updated = res.json()
    assert res.status_code == 200
    assert updated["status"] == "Active"
    assert updated["tags"] == []
    assert updated["targetDate"] is None
    assert updated["name"] == FULL_PROJECT["name"]
    assert updated["updatedAt"] > project["updatedAt"]
    assert updated["createdAt"] == project["createdAt"]


def test_projects_are_isolated_per_user(client, register_and_login):
    alice = register_and_login("alice@example.com")
    bob = register_and_login("bob@example.com")
    project = client.post("/projects", json={"name": "Alice's"}, headers=alice).json()

    assert client.get("/projects", headers=bob).json() == []
    assert client.get(f"/projects/{project['id']}", headers=bob).status_code == 404
    assert (
        client.patch(
            f"/projects/{project['id']}", json={"name": "x"}, headers=bob
        ).status_code
        == 404
    )
    assert client.delete(f"/projects/{project['id']}", headers=bob).status_code == 404
    assert len(client.get("/projects", headers=alice).json()) == 1


def test_delete_removes_the_project(client, register_and_login):
    headers = register_and_login("delete@example.com")
    project = client.post("/projects", json={"name": "Doomed"}, headers=headers).json()

    assert (
        client.delete(f"/projects/{project['id']}", headers=headers).status_code == 204
    )
    assert client.get(f"/projects/{project['id']}", headers=headers).status_code == 404


def test_postgres_enum_rejects_unknown_status(store):
    """The API validates status first; the native enum is the backstop
    for anything writing to the table directly."""
    user = store.create_user(email="enum@example.com", password_hash="h")

    with pytest.raises(DBAPIError):
        store.create_project(
            owner_id=user.id,
            name="p",
            pitch="",
            description="",
            status="Bogus",
            tags=[],
            excitement=3,
            effort=3,
            potential=3,
            next_action="",
            target_date=None,
            links=[],
        )
    store._db.rollback()


def test_deleting_a_user_cascades_to_projects(client, register_and_login, store):
    headers = register_and_login("cascade@example.com")
    client.post("/projects", json={"name": "Orphan-to-be"}, headers=headers)

    store._db.execute(text("DELETE FROM users WHERE email = 'cascade@example.com'"))
    store._db.commit()

    assert store._db.execute(text("SELECT count(*) FROM projects")).scalar_one() == 0


def test_postgres_check_constraint_rejects_over_long_name(store):
    """Migration 0002's constraint, independent of the API's validation."""
    user = store.create_user(email="long@example.com", password_hash="h")

    with pytest.raises(DBAPIError):
        store.create_project(
            owner_id=user.id,
            name="n" * 257,
            pitch="",
            description="",
            status="Inbox",
            tags=[],
            excitement=3,
            effort=3,
            potential=3,
            next_action="",
            target_date=None,
            links=[],
        )
    store._db.rollback()


def test_api_rejects_over_long_fields_on_postgres(client, register_and_login):
    headers = register_and_login("long-api@example.com")

    res = client.post("/projects", json={"name": "x" * 257}, headers=headers)

    assert res.status_code == 422


def test_project_cap_on_postgres(client, register_and_login, monkeypatch):
    monkeypatch.setattr(config, "MAX_PROJECTS_PER_USER", 2)
    headers = register_and_login("capped@example.com")

    statuses = [
        client.post("/projects", json={"name": f"p{i}"}, headers=headers).status_code
        for i in range(3)
    ]

    assert statuses == [201, 201, 403]


def test_postgres_check_constraint_counts_json_array_entries(store):
    """Migration 0003's json_array_length() constraints, on Postgres's json type."""
    user = store.create_user(email="many-tags@example.com", password_hash="h")
    fields = dict(
        name="p",
        pitch="",
        description="",
        status="Inbox",
        links=[],
        excitement=3,
        effort=3,
        potential=3,
        next_action="",
        target_date=None,
    )
    store.create_project(owner_id=user.id, tags=["t"] * 50, **fields)

    with pytest.raises(DBAPIError):
        store.create_project(owner_id=user.id, tags=["t"] * 51, **fields)
    store._db.rollback()


def test_api_rejects_too_many_tags_and_long_link_urls_on_postgres(
    client, register_and_login
):
    headers = register_and_login("lists-api@example.com")

    too_many = client.post(
        "/projects", json={"name": "p", "tags": ["t"] * 51}, headers=headers
    )
    long_url = client.post(
        "/projects",
        json={"name": "p", "links": [{"url": "https://e.com/" + "a" * 2040}]},
        headers=headers,
    )

    assert too_many.status_code == 422
    assert long_url.status_code == 422
