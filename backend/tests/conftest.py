import os

# Must happen before any `app.*` import. app.main does no database work
# at import, but anything that later calls
# app.core.config.get_database_url() (env var, since USE_SSM is unset
# in tests) resolves and caches it once per process. Forcing this to an in-memory database here (rather than
# e.g. setdefault) guarantees the test suite can never touch a real
# DATABASE_URL some developer happens to have set in their shell, let
# alone the dev hub.db file.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# Same idea for telemetry: the app imported below must never try to
# export to a real collector. tests/test_observability.py builds its own
# instrumented apps with in-memory exporters instead.
os.environ["OTEL_SDK_DISABLED"] = "true"

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.orm import Base  # noqa: E402
from app.db.session import enable_sqlite_foreign_keys  # noqa: E402
from app.db.store import Store, get_store  # noqa: E402
from app.main import app  # noqa: E402

TEST_PASSWORD = "password123"


@pytest.fixture()
def store() -> Iterator[Store]:
    """A fresh, isolated in-memory SQLite database per test — distinct
    from the process-wide one configured above, and never the dev
    database (hub.db) or shared with any other test.

    StaticPool keeps every connection this engine hands out pointing at
    the same single `:memory:` database; without it, SQLAlchemy's default
    pooling would give different operations different (empty) in-memory
    databases and tables would appear to vanish mid-test.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    enable_sqlite_foreign_keys(engine, "sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    db = TestSessionLocal()
    try:
        yield Store(db)
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def client(store: Store) -> Iterator[TestClient]:
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def register_and_login(client: TestClient):
    def _do(email: str) -> dict[str, str]:
        client.post("/auth/register", json={"email": email, "password": TEST_PASSWORD})
        res = client.post(
            "/auth/login", data={"username": email, "password": TEST_PASSWORD}
        )
        token = res.json()["access_token"]
        # Login also set the session cookie, which TestClient would send on
        # every later request. Drop it so each test authenticates only with
        # the headers it passes, and "no headers" really means anonymous.
        client.cookies.clear()
        return {"Authorization": f"Bearer {token}"}

    return _do
