"""Tests for the deployed demo account: cloud-mode seeding in
app/bootstrap_db.py (DEMO_PASSWORD_PARAM_NAME).

A throwaway SQLite file stands in for Neon, and a dict stands in for
SSM, so seeding and deletion really run and can be inspected row by row.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.auth.security import verify_password
from app.bootstrap_db import bootstrap, lambda_handler
from app.core import config
from app.db.seed import SEED_USER_EMAIL, SEED_USER_PASSWORD, seed
from app.db.session import enable_sqlite_foreign_keys
from app.db.store import Store
from app.models.project import Status

DB_PARAM = "/hub-prod/db-url-direct"
DEMO_PARAM = "/hub-prod/demo-password"
DEMO_PASSWORD = "cloud-demo-password-from-ssm"
TABLES = ("users", "auth_identities", "projects", "notes")


@pytest.fixture()
def ssm(tmp_path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Cloud mode (USE_SSM on) against a SQLite file, with SSM faked by
    a dict. DEMO_PASSWORD_PARAM_NAME starts absent. Returns the params
    dict (tests may edit it), the list of names fetched, and the file."""
    db_file = tmp_path / "cloud.db"
    params = {DB_PARAM: f"sqlite:///{db_file}", DEMO_PARAM: DEMO_PASSWORD}
    fetched: list[str] = []

    def fake_fetch(name: str) -> str:
        fetched.append(name)
        if name not in params:
            raise LookupError(f"ParameterNotFound: {name}")
        return params[name]

    def no_admin_connection(**kwargs: object) -> None:
        raise AssertionError("cloud mode must not open an admin connection")

    monkeypatch.setattr(config, "USE_SSM", True)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setenv("DB_URL_PARAM_NAME", DB_PARAM)
    monkeypatch.delenv("DEMO_PASSWORD_PARAM_NAME", raising=False)
    monkeypatch.setattr(config, "_fetch_ssm_parameter", fake_fetch)
    monkeypatch.setattr("app.bootstrap_db._connect", no_admin_connection)
    return {"params": params, "fetched": fetched, "db_file": db_file}


@pytest.fixture()
def demo_env(ssm, monkeypatch: pytest.MonkeyPatch) -> dict:
    """ssm, plus DEMO_PASSWORD_PARAM_NAME set: an environment that has a
    demo account."""
    monkeypatch.setenv("DEMO_PASSWORD_PARAM_NAME", DEMO_PARAM)
    return ssm


@contextmanager
def open_store(db_file) -> Iterator[Store]:
    url = f"sqlite:///{db_file}"
    engine = create_engine(url)
    enable_sqlite_foreign_keys(engine, url)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield Store(db)
    finally:
        db.close()
        engine.dispose()


def _rows(db_file) -> dict[str, set[tuple]]:
    """Every row of every table, every column, as sets of tuples."""
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        with engine.connect() as conn:
            return {
                table: {tuple(r) for r in conn.execute(text(f"SELECT * FROM {table}"))}
                for table in TABLES
            }
    finally:
        engine.dispose()


def _demo_content(store: Store) -> tuple[set[str], set[tuple[str, str]]]:
    """The demo user's project names and (project name, note body)
    pairs: what "the ten projects and their notes" means, independent of
    ids and timestamps."""
    user = store.get_user_by_email(SEED_USER_EMAIL)
    assert user is not None
    projects = store.list_projects(user.id)
    names = {p.name for p in projects}
    notes = {(p.name, n.body) for p in projects for n in store.list_notes(p.id)}
    return names, notes


@pytest.fixture()
def local_seed_content(store: Store) -> tuple[set[str], set[tuple[str, str]]]:
    """What the local seed produces, from a separate in-memory database,
    so cloud-mode results are compared against the real seed rather than
    a hand-copied list."""
    seed(store)
    return _demo_content(store)


def _other_users(db_file) -> dict[str, str]:
    """A second and third account with their own projects and notes.
    Emails deliberately look like the demo one, and a project shares a
    demo project's name, so a sloppy match on email or name would catch
    them. Returns email -> user id."""
    with open_store(db_file) as store:
        ids = {}
        for email in ("other@hub.dev", "demo@hub.dev.example.com"):
            user = store.create_user(email=email, password_hash="x")
            ids[email] = user.id
            for name in ("Train for a half-marathon", f"Private to {email}"):
                project = store.create_project(
                    owner_id=user.id,
                    name=name,
                    pitch="p",
                    description="d",
                    status=Status.ACTIVE,
                    tags=["t"],
                    excitement=3,
                    effort=3,
                    potential=3,
                    next_action="n",
                    target_date=None,
                    links=[],
                )
                store.create_note(project_id=project.id, body=f"note on {name}")
                store.create_note(project_id=project.id, body="Week 3 done")
        return ids


def _edit_demo(db_file) -> None:
    """Rename one demo project, delete another, add a project and a note."""
    with open_store(db_file) as store:
        user = store.get_user_by_email(SEED_USER_EMAIL)
        projects = sorted(store.list_projects(user.id), key=lambda p: p.name)
        store.update_project(projects[0].id, user.id, name="Edited by a reviewer")
        store.delete_project(projects[1].id, user.id)
        store.create_note(project_id=projects[2].id, body="A reviewer's note")
        store.create_project(
            owner_id=user.id,
            name="Added by a reviewer",
            pitch="",
            description="",
            status=Status.INBOX,
            tags=[],
            excitement=1,
            effort=1,
            potential=1,
            next_action="",
            target_date=None,
            links=[],
        )


# ---- Change A: seeding in cloud mode ----


def test_absent_demo_param_seeds_nothing(ssm, capsys):
    bootstrap()

    assert _rows(ssm["db_file"])["users"] == set()
    assert ssm["fetched"] == [DB_PARAM]
    assert "DEMO_PASSWORD_PARAM_NAME" in capsys.readouterr().out


def test_empty_demo_param_name_seeds_nothing(ssm, monkeypatch, capsys):
    monkeypatch.setenv("DEMO_PASSWORD_PARAM_NAME", "")

    bootstrap()

    assert _rows(ssm["db_file"])["users"] == set()
    assert ssm["fetched"] == [DB_PARAM]
    assert "DEMO_PASSWORD_PARAM_NAME" in capsys.readouterr().out


def test_absent_demo_param_lambda_result_is_unchanged(ssm):
    assert lambda_handler({}, None) == {
        "status": "ok",
        "message": "Bootstrap complete.",
    }


def test_demo_param_seeds_user_projects_and_notes(demo_env, local_seed_content):
    bootstrap()

    with open_store(demo_env["db_file"]) as store:
        names, notes = _demo_content(store)
    assert len(names) == 10
    assert (names, notes) == local_seed_content
    assert DEMO_PARAM in demo_env["fetched"]


def test_demo_user_gets_the_ssm_password_never_the_local_one(demo_env):
    bootstrap()

    with open_store(demo_env["db_file"]) as store:
        user = store.get_user_by_email(SEED_USER_EMAIL)
    assert verify_password(DEMO_PASSWORD, user.password_hash)
    assert not verify_password(SEED_USER_PASSWORD, user.password_hash)


def test_seeding_twice_does_not_duplicate_or_change_anything(demo_env, capsys):
    bootstrap()
    before = _rows(demo_env["db_file"])
    capsys.readouterr()

    bootstrap()

    assert _rows(demo_env["db_file"]) == before
    assert "already exists" in capsys.readouterr().out


def test_second_run_does_not_update_the_password(demo_env):
    bootstrap()
    demo_env["params"][DEMO_PARAM] = "a-rotated-password"

    bootstrap()

    with open_store(demo_env["db_file"]) as store:
        user = store.get_user_by_email(SEED_USER_EMAIL)
    assert verify_password(DEMO_PASSWORD, user.password_hash)
    assert not verify_password("a-rotated-password", user.password_hash)


def test_edited_demo_data_survives_a_second_run(demo_env):
    bootstrap()
    _edit_demo(demo_env["db_file"])
    edited = _rows(demo_env["db_file"])

    bootstrap()

    assert _rows(demo_env["db_file"]) == edited
    with open_store(demo_env["db_file"]) as store:
        names, notes = _demo_content(store)
    assert "Edited by a reviewer" in names
    assert "Added by a reviewer" in names
    assert any(body == "A reviewer's note" for _, body in notes)


def test_set_but_empty_demo_password_raises_and_seeds_nothing(demo_env):
    demo_env["params"][DEMO_PARAM] = ""

    with pytest.raises(RuntimeError, match=DEMO_PARAM):
        bootstrap()

    assert _rows(demo_env["db_file"])["users"] == set()


def test_whitespace_only_demo_password_raises(demo_env):
    demo_env["params"][DEMO_PARAM] = "   "

    with pytest.raises(RuntimeError, match=DEMO_PARAM):
        bootstrap()

    assert _rows(demo_env["db_file"])["users"] == set()


def test_missing_demo_password_parameter_raises_and_seeds_nothing(demo_env):
    del demo_env["params"][DEMO_PARAM]

    with pytest.raises(LookupError, match="ParameterNotFound"):
        bootstrap()

    assert _rows(demo_env["db_file"])["users"] == set()


def test_local_seed_still_defaults_to_its_own_password(store):
    assert SEED_USER_PASSWORD == "demo1234"

    seed(store)

    user = store.get_user_by_email(SEED_USER_EMAIL)
    assert verify_password(SEED_USER_PASSWORD, user.password_hash)
    assert len(store.list_projects(user.id)) == 10


def test_seed_uses_a_given_password(store):
    seed(store, password="something-else")

    user = store.get_user_by_email(SEED_USER_EMAIL)
    assert verify_password("something-else", user.password_hash)
    assert not verify_password(SEED_USER_PASSWORD, user.password_hash)


# ---- no reset path: every invocation is a plain bootstrap ----


@pytest.mark.parametrize(
    "event",
    [{}, None, {"reset_demo": True}, {"reset_demo": False}, {"anything": 1}],
)
def test_every_invocation_is_a_plain_bootstrap_that_deletes_nothing(demo_env, event):
    """The demo reset was removed. An old {"reset_demo": true} payload, or
    any other event, must run the normal idempotent bootstrap and leave
    edited demo data exactly as it is."""
    bootstrap()
    _edit_demo(demo_env["db_file"])
    edited = _rows(demo_env["db_file"])

    result = lambda_handler(event, None)

    assert result == {"status": "ok", "message": "Bootstrap complete."}
    assert _rows(demo_env["db_file"]) == edited
