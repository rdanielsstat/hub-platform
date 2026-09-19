def test_create_get_patch_delete_own_project(client, register_and_login):
    headers = register_and_login("crud@example.com")

    res = client.post("/projects", json={"name": "Idea"}, headers=headers)
    assert res.status_code == 201
    body = res.json()
    project_id = body["id"]
    assert body["status"] == "Inbox"
    assert body["excitement"] == 3
    assert body["links"] == []

    res = client.get(f"/projects/{project_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Idea"

    res = client.patch(
        f"/projects/{project_id}",
        json={
            "status": "Active",
            "links": [{"label": "Repo", "url": "https://example.com"}],
        },
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "Active"
    assert res.json()["links"] == [{"label": "Repo", "url": "https://example.com"}]

    res = client.delete(f"/projects/{project_id}", headers=headers)
    assert res.status_code == 204

    res = client.get(f"/projects/{project_id}", headers=headers)
    assert res.status_code == 404


def test_created_project_is_owned_by_the_creator(client, register_and_login):
    headers = register_and_login("owner@example.com")
    res = client.post("/projects", json={"name": "Idea"}, headers=headers)
    project_id = res.json()["id"]

    res = client.get("/projects", headers=headers)
    assert [p["id"] for p in res.json()] == [project_id]


def test_projects_require_authentication(client):
    res = client.get("/projects")
    assert res.status_code == 401


# -- per-user isolation --------------------------------------------------


def test_user_can_list_and_get_their_own_project(client, register_and_login):
    headers_a = register_and_login("iso-list-a@example.com")
    res = client.post("/projects", json={"name": "A's project"}, headers=headers_a)
    project_id = res.json()["id"]

    res = client.get("/projects", headers=headers_a)
    assert [p["id"] for p in res.json()] == [project_id]

    res = client.get(f"/projects/{project_id}", headers=headers_a)
    assert res.status_code == 200


def test_user_gets_404_not_403_for_another_users_project(client, register_and_login):
    headers_a = register_and_login("iso-get-a@example.com")
    headers_b = register_and_login("iso-get-b@example.com")

    res = client.post("/projects", json={"name": "B's project"}, headers=headers_b)
    project_b_id = res.json()["id"]

    res = client.get(f"/projects/{project_b_id}", headers=headers_a)
    assert res.status_code == 404


def test_user_cannot_patch_another_users_project(client, register_and_login):
    headers_a = register_and_login("iso-patch-a@example.com")
    headers_b = register_and_login("iso-patch-b@example.com")

    res = client.post("/projects", json={"name": "B's project"}, headers=headers_b)
    project_b_id = res.json()["id"]

    res = client.patch(
        f"/projects/{project_b_id}", json={"name": "Hijacked"}, headers=headers_a
    )
    assert res.status_code == 404

    res = client.get(f"/projects/{project_b_id}", headers=headers_b)
    assert res.json()["name"] == "B's project"


def test_user_cannot_delete_another_users_project(client, register_and_login):
    headers_a = register_and_login("iso-delete-a@example.com")
    headers_b = register_and_login("iso-delete-b@example.com")

    res = client.post("/projects", json={"name": "B's project"}, headers=headers_b)
    project_b_id = res.json()["id"]

    res = client.delete(f"/projects/{project_b_id}", headers=headers_a)
    assert res.status_code == 404

    res = client.get(f"/projects/{project_b_id}", headers=headers_b)
    assert res.status_code == 200


def test_project_list_never_includes_another_users_projects(client, register_and_login):
    headers_a = register_and_login("iso-list2-a@example.com")
    headers_b = register_and_login("iso-list2-b@example.com")

    client.post("/projects", json={"name": "A1"}, headers=headers_a)
    client.post("/projects", json={"name": "B1"}, headers=headers_b)
    client.post("/projects", json={"name": "B2"}, headers=headers_b)

    res = client.get("/projects", headers=headers_a)
    assert [p["name"] for p in res.json()] == ["A1"]
