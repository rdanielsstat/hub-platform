def test_owner_can_add_list_and_delete_notes(client, register_and_login):
    headers = register_and_login("notes-crud@example.com")
    project_id = client.post(
        "/projects", json={"name": "Idea"}, headers=headers
    ).json()["id"]

    res = client.post(
        f"/projects/{project_id}/notes",
        json={"body": "First note"},
        headers=headers,
    )
    assert res.status_code == 201
    body = res.json()
    assert body["note"]["body"] == "First note"
    assert body["note"]["projectId"] == project_id
    note_id = body["note"]["id"]

    res = client.get(f"/projects/{project_id}/notes", headers=headers)
    assert res.status_code == 200
    assert [n["id"] for n in res.json()] == [note_id]

    res = client.delete(f"/notes/{note_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["id"] == project_id

    res = client.get(f"/projects/{project_id}/notes", headers=headers)
    assert res.json() == []


def test_notes_are_returned_newest_first(client, register_and_login):
    headers = register_and_login("notes-order@example.com")
    project_id = client.post(
        "/projects", json={"name": "Idea"}, headers=headers
    ).json()["id"]

    client.post(
        f"/projects/{project_id}/notes", json={"body": "Oldest"}, headers=headers
    )
    client.post(
        f"/projects/{project_id}/notes", json={"body": "Newest"}, headers=headers
    )

    res = client.get(f"/projects/{project_id}/notes", headers=headers)
    bodies = [n["body"] for n in res.json()]
    assert bodies == ["Newest", "Oldest"]


def test_adding_a_note_bumps_the_parent_projects_updated_at(client, register_and_login):
    headers = register_and_login("notes-bump-add@example.com")
    created = client.post(
        "/projects", json={"name": "Idea"}, headers=headers
    ).json()
    project_id = created["id"]
    original_updated_at = created["updatedAt"]

    res = client.post(
        f"/projects/{project_id}/notes",
        json={"body": "Bumps updatedAt"},
        headers=headers,
    )
    assert res.json()["project"]["id"] == project_id
    assert res.json()["project"]["updatedAt"] != original_updated_at

    res = client.get(f"/projects/{project_id}", headers=headers)
    assert res.json()["updatedAt"] != original_updated_at


def test_deleting_a_note_bumps_the_parent_projects_updated_at(client, register_and_login):
    headers = register_and_login("notes-bump-delete@example.com")
    project_id = client.post(
        "/projects", json={"name": "Idea"}, headers=headers
    ).json()["id"]
    note_id = client.post(
        f"/projects/{project_id}/notes", json={"body": "Note"}, headers=headers
    ).json()["note"]["id"]

    before = client.get(f"/projects/{project_id}", headers=headers).json()["updatedAt"]

    res = client.delete(f"/notes/{note_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["updatedAt"] != before


def test_notes_require_authentication(client, register_and_login):
    headers = register_and_login("notes-auth@example.com")
    project_id = client.post(
        "/projects", json={"name": "Idea"}, headers=headers
    ).json()["id"]

    assert client.get(f"/projects/{project_id}/notes").status_code == 401
    assert (
        client.post(f"/projects/{project_id}/notes", json={"body": "x"}).status_code
        == 401
    )


# -- per-user isolation --------------------------------------------------


def test_user_cannot_list_notes_on_another_users_project(client, register_and_login):
    headers_a = register_and_login("notes-iso-list-a@example.com")
    headers_b = register_and_login("notes-iso-list-b@example.com")
    project_b_id = client.post(
        "/projects", json={"name": "B's project"}, headers=headers_b
    ).json()["id"]
    client.post(
        f"/projects/{project_b_id}/notes", json={"body": "B's note"}, headers=headers_b
    )

    res = client.get(f"/projects/{project_b_id}/notes", headers=headers_a)
    assert res.status_code == 404


def test_user_gets_404_adding_a_note_to_another_users_project(client, register_and_login):
    headers_a = register_and_login("notes-iso-add-a@example.com")
    headers_b = register_and_login("notes-iso-add-b@example.com")
    project_b_id = client.post(
        "/projects", json={"name": "B's project"}, headers=headers_b
    ).json()["id"]

    res = client.post(
        f"/projects/{project_b_id}/notes",
        json={"body": "Hijacked note"},
        headers=headers_a,
    )
    assert res.status_code == 404

    res = client.get(f"/projects/{project_b_id}/notes", headers=headers_b)
    assert res.json() == []


def test_user_gets_404_deleting_a_note_on_another_users_project(
    client, register_and_login
):
    headers_a = register_and_login("notes-iso-delete-a@example.com")
    headers_b = register_and_login("notes-iso-delete-b@example.com")
    project_b_id = client.post(
        "/projects", json={"name": "B's project"}, headers=headers_b
    ).json()["id"]
    note_id = client.post(
        f"/projects/{project_b_id}/notes",
        json={"body": "B's note"},
        headers=headers_b,
    ).json()["note"]["id"]

    res = client.delete(f"/notes/{note_id}", headers=headers_a)
    assert res.status_code == 404

    res = client.get(f"/projects/{project_b_id}/notes", headers=headers_b)
    assert [n["id"] for n in res.json()] == [note_id]
