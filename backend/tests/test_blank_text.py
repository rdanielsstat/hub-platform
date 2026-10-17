"""Blank project names and note bodies (issue #12): empty or
whitespace-only is a 422 on create, update and add note; real text is
stored exactly as sent."""

import pytest

BLANKS = ["", " ", "   ", "\t", "\n", " \n\t "]


@pytest.fixture()
def headers(register_and_login):
    return register_and_login("blank@example.com")


@pytest.fixture()
def project_id(client, headers) -> str:
    res = client.post("/projects", json={"name": "Keep me"}, headers=headers)
    assert res.status_code == 201
    return res.json()["id"]


def _locs(res) -> list[list]:
    return [e["loc"] for e in res.json()["detail"]]


@pytest.mark.parametrize("name", BLANKS, ids=repr)
def test_create_refuses_a_blank_name(client, headers, name):
    res = client.post("/projects", json={"name": name}, headers=headers)
    assert res.status_code == 422
    assert ["body", "name"] in _locs(res)
    assert client.get("/projects", headers=headers).json() == []


@pytest.mark.parametrize("name", BLANKS, ids=repr)
def test_update_refuses_a_blank_name_and_keeps_the_old_one(
    client, headers, project_id, name
):
    res = client.patch(f"/projects/{project_id}", json={"name": name}, headers=headers)
    assert res.status_code == 422
    assert ["body", "name"] in _locs(res)
    assert client.get(f"/projects/{project_id}", headers=headers).json()["name"] == (
        "Keep me"
    )


def test_update_without_a_name_still_works(client, headers, project_id):
    res = client.patch(
        f"/projects/{project_id}", json={"pitch": "new pitch"}, headers=headers
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Keep me"
    assert res.json()["pitch"] == "new pitch"


@pytest.mark.parametrize("body", BLANKS, ids=repr)
def test_add_note_refuses_a_blank_body(client, headers, project_id, body):
    res = client.post(
        f"/projects/{project_id}/notes", json={"body": body}, headers=headers
    )
    assert res.status_code == 422
    assert ["body", "body"] in _locs(res)
    assert client.get(f"/projects/{project_id}/notes", headers=headers).json() == []


@pytest.mark.parametrize("text", ["a", " padded ", "\tTabbed name", "x" * 256])
def test_real_text_is_stored_exactly_as_sent(client, headers, text):
    res = client.post("/projects", json={"name": text}, headers=headers)
    assert res.status_code == 201
    assert res.json()["name"] == text


def test_note_with_text_is_stored_exactly_as_sent(client, headers, project_id):
    res = client.post(
        f"/projects/{project_id}/notes", json={"body": "  line one\n"}, headers=headers
    )
    assert res.status_code == 201
    assert res.json()["note"]["body"] == "  line one\n"
