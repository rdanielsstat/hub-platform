from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db.store import InMemoryStore, get_store
from app.main import app

TEST_PASSWORD = "password123"


@pytest.fixture()
def store() -> InMemoryStore:
    """A fresh, unseeded store per test, isolated from the app's seeded
    singleton and from every other test."""
    return InMemoryStore()


@pytest.fixture()
def client(store: InMemoryStore) -> Iterator[TestClient]:
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def register_and_login(client: TestClient):
    def _do(email: str) -> dict[str, str]:
        client.post(
            "/auth/register", json={"email": email, "password": TEST_PASSWORD}
        )
        res = client.post(
            "/auth/login", data={"username": email, "password": TEST_PASSWORD}
        )
        token = res.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _do
