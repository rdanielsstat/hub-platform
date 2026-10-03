"""Tests for app/db/migrations.py and the scripts in backend/alembic/.

SQLite files stand in for Postgres here; tests/integration/ runs the
same migrations against real Postgres (see test_migrations_integration.py).
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.migrations import (
    BASELINE_REVISION,
    BASELINE_TABLES,
    alembic_config,
    current_revision,
    upgrade_to_head,
)
from app.db.orm import Base


@pytest.fixture()
def db_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'migrations.db'}"


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _revision(url: str) -> str | None:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return current_revision(conn)
    finally:
        engine.dispose()


def _head() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


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


def _scalars(url: str, query: str) -> list:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return conn.execute(text(query)).scalars().all()
    finally:
        engine.dispose()


def _make_pre_alembic_database(url: str) -> None:
    """The schema the old create_all() built, which is exactly revision
    0001, with no alembic_version table: what the deployed databases
    look like before their first Alembic bootstrap. (Today's create_all()
    would also add later changes, like 0002's constraints.)"""
    _migrate_to(url, BASELINE_REVISION)
    _execute(url, "DROP TABLE alembic_version")


USER_SQL = (
    "INSERT INTO users (id, email, created_at, updated_at) "
    "VALUES ('u1', 'kept@example.com', '2026-01-01', '2026-01-01')"
)


def _project_sql(project_id: str = "p1", name: str = "Kept project", description: str = "") -> str:
    return (
        "INSERT INTO projects (id, owner_id, name, pitch, description, status, tags, "
        "excitement, effort, potential, next_action, links, created_at, updated_at) "
        f"VALUES ('{project_id}', 'u1', '{name}', '', '{description}', 'Inbox', '[]', "
        "3, 3, 3, '', '[]', '2026-01-01', '2026-01-01')"
    )


def _note_sql(note_id: str, body: str = "kept note") -> str:
    return (
        "INSERT INTO notes (id, project_id, body, created_at) "
        f"VALUES ('{note_id}', 'p1', '{body}', '2026-01-01')"
    )


def test_there_is_exactly_one_head():
    """Two heads means two migrations branched off the same parent;
    `upgrade head` would refuse to run on the next deploy."""
    assert len(ScriptDirectory.from_config(alembic_config()).get_heads()) == 1


def test_upgrade_creates_every_table_on_an_empty_database(db_url):
    upgrade_to_head(db_url)

    assert BASELINE_TABLES | {"alembic_version"} <= _tables(db_url)
    assert _revision(db_url) == _head()


def test_migrations_match_the_orm_models(db_url):
    """The drift guard: a change to app/db/orm.py without a matching
    migration fails here. Fix it with
    `uv run alembic revision --autogenerate -m "..."` from backend/."""
    upgrade_to_head(db_url)

    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(
                MigrationContext.configure(conn, opts={"compare_type": True}),
                Base.metadata,
            )
    finally:
        engine.dispose()
    assert diff == []


def test_upgrade_is_idempotent_and_keeps_data(db_url, capsys):
    upgrade_to_head(db_url)
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, created_at, updated_at) "
                    "VALUES ('u1', 'kept@example.com', '2026-01-01', '2026-01-01')"
                )
            )
    finally:
        engine.dispose()

    upgrade_to_head(db_url)

    assert "already at head" in capsys.readouterr().out
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            emails = conn.execute(text("SELECT email FROM users")).scalars().all()
    finally:
        engine.dispose()
    assert emails == ["kept@example.com"]


def test_pre_alembic_database_is_stamped_not_recreated(db_url, capsys):
    """A database from the old create_all() (every deployed one, and any
    existing local hub.db): stamped at the baseline, then upgraded, with
    its data untouched."""
    _make_pre_alembic_database(db_url)
    _execute(db_url, USER_SQL, _project_sql(), _note_sql("n1"))
    assert "alembic_version" not in _tables(db_url)

    upgrade_to_head(db_url)

    assert f"stamped at baseline revision {BASELINE_REVISION}" in capsys.readouterr().out
    assert _revision(db_url) == _head()
    assert _scalars(db_url, "SELECT email FROM users") == ["kept@example.com"]
    assert _scalars(db_url, "SELECT name FROM projects") == ["Kept project"]
    assert _scalars(db_url, "SELECT body FROM notes") == ["kept note"]


def test_partial_pre_alembic_schema_is_refused(db_url):
    engine = create_engine(db_url)
    try:
        Base.metadata.tables["users"].create(bind=engine)
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="missing: auth_identities, notes, projects"):
        upgrade_to_head(db_url)

    assert "alembic_version" not in _tables(db_url)


def test_downgrade_to_base_and_back(db_url):
    """Every migration's downgrade() runs, and upgrading again works."""
    upgrade_to_head(db_url)
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            command.downgrade(alembic_config(conn), "base")
    finally:
        engine.dispose()

    assert not (BASELINE_TABLES & _tables(db_url))

    upgrade_to_head(db_url)
    assert _revision(db_url) == _head()


# ---- 0002: text field length constraints ----

LENGTH_CONSTRAINTS = {
    "projects": {
        "ck_projects_name_length",
        "ck_projects_pitch_length",
        "ck_projects_description_length",
        "ck_projects_next_action_length",
        "ck_projects_tags_count",
        "ck_projects_links_count",
    },
    "notes": {"ck_notes_body_length"},
    "users": {"ck_users_display_name_length"},
}


def _check_constraint_names(url: str, table: str) -> set[str]:
    engine = create_engine(url)
    try:
        return {c["name"] for c in inspect(engine).get_check_constraints(table)}
    finally:
        engine.dispose()


def test_0002_adds_the_named_check_constraints(db_url):
    upgrade_to_head(db_url)

    for table, names in LENGTH_CONSTRAINTS.items():
        assert names <= _check_constraint_names(db_url, table)


def test_orm_declares_the_same_constraints_as_0002():
    """create_all() (unit tests) and the migrations build the same limits."""
    for table, names in LENGTH_CONSTRAINTS.items():
        declared = {
            c.name for c in Base.metadata.tables[table].constraints if c.name
        }
        assert names <= declared


def test_0002_keeps_notes_when_sqlite_rebuilds_the_projects_table(db_url):
    """SQLite adds a constraint by copying the table, dropping the
    original and renaming the copy. With foreign keys on, that drop would
    cascade-delete every note; upgrade_to_head() keeps them off."""
    _migrate_to(db_url, BASELINE_REVISION)
    _execute(db_url, USER_SQL, _project_sql(), _note_sql("n1"), _note_sql("n2", "second"))

    upgrade_to_head(db_url)

    assert sorted(_scalars(db_url, "SELECT body FROM notes")) == ["kept note", "second"]
    assert _scalars(db_url, "SELECT name FROM projects") == ["Kept project"]


def test_0002_refuses_existing_over_long_data_and_changes_nothing(db_url):
    _migrate_to(db_url, BASELINE_REVISION)
    _execute(db_url, USER_SQL, _project_sql(description="d" * 5001))

    with pytest.raises(RuntimeError, match=r"projects\.description: 1 row\(s\) over 5000"):
        upgrade_to_head(db_url)

    assert _revision(db_url) == BASELINE_REVISION
    assert not _check_constraint_names(db_url, "projects")
    assert _scalars(db_url, "SELECT length(description) FROM projects") == [5001]


@pytest.mark.parametrize(
    ("statement", "ok_statement"),
    [
        (_project_sql("p2", name="n" * 257), _project_sql("p3", name="n" * 256)),
        (
            _project_sql("p2", description="d" * 5001),
            _project_sql("p3", description="d" * 5000),
        ),
        (_note_sql("n2", "b" * 10001), _note_sql("n3", "b" * 10000)),
    ],
)
def test_database_enforces_the_limits_after_migrating(db_url, statement, ok_statement):
    upgrade_to_head(db_url)
    _execute(db_url, USER_SQL, _project_sql())

    _execute(db_url, ok_statement)
    with pytest.raises(IntegrityError):
        _execute(db_url, statement)


def test_0002_downgrade_removes_the_constraints(db_url):
    upgrade_to_head(db_url)
    _execute(db_url, USER_SQL, _project_sql(), _note_sql("n1"))

    _migrate_down(db_url, BASELINE_REVISION)

    assert not _check_constraint_names(db_url, "projects")
    assert not _check_constraint_names(db_url, "notes")
    assert not _check_constraint_names(db_url, "users")
    assert _scalars(db_url, "SELECT body FROM notes") == ["kept note"]


def _migrate_down(url: str, revision: str) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            command.downgrade(alembic_config(conn), revision)
    finally:
        engine.dispose()


def test_failed_first_upgrade_of_a_pre_alembic_database_leaves_no_trace(db_url):
    """Stamp, then 0002 refuses: the whole run rolls back on SQLite too,
    so the next run (after the data is fixed) starts clean. Before the
    run was made transactional, an empty alembic_version table survived
    and the retry tried to re-create every table."""
    _make_pre_alembic_database(db_url)
    _execute(db_url, USER_SQL, _project_sql(description="d" * 5001))

    with pytest.raises(RuntimeError, match="existing data is already longer"):
        upgrade_to_head(db_url)

    assert "alembic_version" not in _tables(db_url)
    assert not _check_constraint_names(db_url, "projects")

    _execute(db_url, "UPDATE projects SET description = 'short'")
    upgrade_to_head(db_url)

    assert _revision(db_url) == _head()
    assert _scalars(db_url, "SELECT description FROM projects") == ["short"]


def test_empty_version_table_counts_as_unstamped(db_url, capsys):
    _make_pre_alembic_database(db_url)
    _execute(db_url, "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")

    upgrade_to_head(db_url)

    assert "stamped at baseline" in capsys.readouterr().out
    assert _revision(db_url) == _head()


# ---- 0003: tag, link and display name limits ----


def test_0003_refuses_existing_violations_and_changes_nothing(db_url):
    _migrate_to(db_url, "0002")
    _execute(
        db_url,
        "INSERT INTO users (id, email, display_name, created_at, updated_at) "
        f"VALUES ('u1', 'long@example.com', '{'d' * 101}', '2026-01-01', '2026-01-01')",
    )

    with pytest.raises(RuntimeError, match=r"ck_users_display_name_length .*1 row"):
        upgrade_to_head(db_url)

    assert _revision(db_url) == "0002"
    assert "ck_users_display_name_length" not in _check_constraint_names(db_url, "users")


def test_0003_counts_json_array_entries(db_url):
    upgrade_to_head(db_url)
    tags_50 = "[" + ",".join('"t"' for _ in range(50)) + "]"
    tags_51 = "[" + ",".join('"t"' for _ in range(51)) + "]"
    _execute(db_url, USER_SQL, _project_sql().replace("'[]', 3", f"'{tags_50}', 3", 1))

    with pytest.raises(IntegrityError):
        _execute(db_url, _project_sql("p2").replace("'[]', 3", f"'{tags_51}', 3", 1))
