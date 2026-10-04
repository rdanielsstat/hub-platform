"""Alembic migrations and the bootstrap, on real Postgres.

The unit tests (tests/test_migrations.py) cover the same logic on
SQLite; these catch what only Postgres does differently: the native
enum type, transactional DDL, and the least-privilege role the local
bootstrap creates.
"""

import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app import bootstrap_db
from app.core import config
from app.db.migrations import (
    BASELINE_TABLES,
    alembic_config,
    current_revision,
    upgrade_to_head,
)
from app.db.orm import Base
from tests.integration.conftest import ADMIN_URL, admin_engine

pytestmark = pytest.mark.integration

HEAD = ScriptDirectory.from_config(alembic_config()).get_current_head()


def _revision(url: str) -> str | None:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return current_revision(conn)
    finally:
        engine.dispose()


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_migrated_schema_matches_the_orm_on_postgres(pg_url):
    engine = create_engine(pg_url)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(
                MigrationContext.configure(conn, opts={"compare_type": True}),
                Base.metadata,
            )
    finally:
        engine.dispose()

    assert diff == []
    assert _revision(pg_url) == HEAD


def test_status_is_a_native_postgres_enum(pg_url):
    engine = create_engine(pg_url)
    try:
        with engine.connect() as conn:
            labels = (
                conn.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_type t "
                        "JOIN pg_enum e ON e.enumtypid = t.oid "
                        "WHERE t.typname = 'status' ORDER BY e.enumsortorder"
                    )
                )
                .scalars()
                .all()
            )
    finally:
        engine.dispose()

    assert labels == ["Inbox", "Exploring", "Active", "Parked", "Graduated", "Killed"]


def test_second_upgrade_is_a_no_op(fresh_database, capsys):
    upgrade_to_head(fresh_database)
    upgrade_to_head(fresh_database)

    assert "already at head" in capsys.readouterr().out
    assert _revision(fresh_database) == HEAD


def _migrate_to(url: str, revision: str) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            command.upgrade(alembic_config(conn), revision)
    finally:
        engine.dispose()


def _execute(url: str, *statements: str) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
    finally:
        engine.dispose()


USER_SQL = (
    "INSERT INTO users (id, email, created_at, updated_at) "
    "VALUES ('u1', 'kept@example.com', now(), now())"
)


def _project_sql(project_id: str = "p1", description: str = "") -> str:
    return (
        "INSERT INTO projects (id, owner_id, name, pitch, description, status, tags, "
        "excitement, effort, potential, next_action, links, created_at, updated_at) "
        f"VALUES ('{project_id}', 'u1', 'Kept', '', '{description}', 'Inbox', '[]', "
        "3, 3, 3, '', '[]', now(), now())"
    )


def test_pre_alembic_database_is_stamped_and_keeps_its_data(fresh_database):
    """What happens to the deployed Neon databases on their first
    Alembic bootstrap: the old create_all() schema (revision 0001's
    tables, no alembic_version), real rows, then stamp and upgrade."""
    _migrate_to(fresh_database, "0001")
    _execute(
        fresh_database,
        "DROP TABLE alembic_version",
        USER_SQL,
        _project_sql(),
        "INSERT INTO notes (id, project_id, body, created_at) "
        "VALUES ('n1', 'p1', 'kept note', now())",
    )

    upgrade_to_head(fresh_database)

    assert _revision(fresh_database) == HEAD
    engine = create_engine(fresh_database)
    try:
        with engine.connect() as conn:
            emails = conn.execute(text("SELECT email FROM users")).scalars().all()
            notes = conn.execute(text("SELECT body FROM notes")).scalars().all()
    finally:
        engine.dispose()
    assert emails == ["kept@example.com"]
    assert notes == ["kept note"]


def test_length_constraints_exist_and_are_enforced_on_postgres(pg_url):
    engine = create_engine(pg_url)
    try:
        with engine.connect() as conn:
            names = set(
                conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE contype = 'c' AND conname LIKE 'ck_%'"
                    )
                ).scalars()
            )
    finally:
        engine.dispose()
    assert names == {
        "ck_projects_name_length",
        "ck_projects_pitch_length",
        "ck_projects_description_length",
        "ck_projects_next_action_length",
        "ck_notes_body_length",
        "ck_projects_tags_count",
        "ck_projects_links_count",
        "ck_users_display_name_length",
    }


def test_0002_refuses_over_long_existing_data_and_rolls_back(fresh_database):
    _migrate_to(fresh_database, "0001")
    _execute(fresh_database, USER_SQL, _project_sql(description="d" * 5001))

    with pytest.raises(RuntimeError, match="projects.description: 1 row"):
        upgrade_to_head(fresh_database)

    assert _revision(fresh_database) == "0001"


def test_downgrade_to_base_removes_tables_and_the_enum(fresh_database):
    upgrade_to_head(fresh_database)
    engine = create_engine(fresh_database)
    try:
        with engine.begin() as conn:
            command.downgrade(alembic_config(conn), "base")
        with engine.connect() as conn:
            enum_left = conn.execute(
                text("SELECT 1 FROM pg_type WHERE typname = 'status'")
            ).first()
    finally:
        engine.dispose()

    assert not (BASELINE_TABLES & _tables(fresh_database))
    assert enum_left is None

    upgrade_to_head(fresh_database)
    assert _revision(fresh_database) == HEAD


def test_partial_schema_is_refused_without_writing_anything(fresh_database):
    """A database with only some of the app's tables is refused before
    any DDL runs: no alembic_version, no new tables."""
    engine = create_engine(fresh_database)
    try:
        Base.metadata.tables["users"].create(bind=engine)
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="missing"):
        upgrade_to_head(fresh_database)

    assert _tables(fresh_database) == {"users"}


# ---- the local bootstrap, end to end ----


@pytest.fixture()
def bootstrap_target(monkeypatch):
    """Point the local bootstrap at a new database and role on the
    Compose Postgres, then drop both."""
    suffix = uuid.uuid4().hex[:10]
    role, dbname, password = f"hub_it_role_{suffix}", f"hub_it_boot_{suffix}", "it-pass"
    admin = make_url(ADMIN_URL)
    app_url = admin.set(username=role, password=password, database=dbname)

    monkeypatch.setattr(config, "USE_SSM", False)
    monkeypatch.setattr(config, "_database_url", None)
    monkeypatch.setenv("DATABASE_URL", app_url.render_as_string(hide_password=False))
    monkeypatch.setenv("MASTER_DB_HOST", admin.host or "localhost")
    monkeypatch.setenv("MASTER_DB_PORT", str(admin.port or 5432))
    monkeypatch.setenv("MASTER_DB_USER", admin.username or "postgres")
    monkeypatch.setenv("MASTER_DB_PASSWORD", admin.password or "")

    yield app_url.render_as_string(hide_password=False)

    engine = admin_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
            conn.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
    finally:
        engine.dispose()


def test_local_bootstrap_migrates_as_the_least_privilege_role(bootstrap_target):
    """The Compose path for real: create role and database, grant only
    CONNECT + USAGE/CREATE on public, then migrate as that role. Proves
    those grants are enough for the migrations (CREATE TYPE included)."""
    bootstrap_db.bootstrap()
    bootstrap_db.bootstrap()  # idempotent

    assert _revision(bootstrap_target) == HEAD
    engine = create_engine(bootstrap_target)
    try:
        with engine.connect() as conn:
            owners = set(
                conn.execute(
                    text("SELECT tableowner FROM pg_tables WHERE schemaname = 'public'")
                ).scalars()
            )
            is_superuser = conn.execute(
                text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            ).scalar_one()
    finally:
        engine.dispose()

    assert owners == {make_url(bootstrap_target).username}
    assert is_superuser is False
