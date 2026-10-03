"""Schema migrations (Alembic), run programmatically.

The one way any database gets its schema outside the test suite:
  - app/bootstrap_db.py (every deploy, and Docker Compose's bootstrap)
  - app/db/init_local.py (local SQLite, and Compose's init_local)
  - `uv run alembic upgrade head` from backend/ by hand, same result

Migration scripts live in backend/alembic/versions/. To change the
schema: edit app/db/orm.py, then from backend/ run
`uv run alembic revision --autogenerate -m "what changed"`, review the
generated file, and commit it. The next bootstrap applies it.

Pre-Alembic databases: anything created by the old create_all() has all
the baseline tables but no alembic_version table. upgrade_to_head()
stamps those at BASELINE_REVISION (recording that the baseline is
already applied, without running it) and then upgrades as usual. That
covers the deployed Neon databases, existing local hub.db files and
Compose volumes, with no manual step and no data touched.

Idempotent: at head already, an upgrade does nothing. The stamp and the
upgrade run in one transaction, on Postgres and SQLite alike, so a
failed migration leaves the database exactly as it was (see
_migration_engine() for what SQLite needs for that).
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Connection, Engine

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT_LOCATION = BACKEND_DIR / "alembic"

# The revision that reproduces the pre-Alembic create_all() schema.
BASELINE_REVISION = "0001"
BASELINE_TABLES = frozenset({"users", "auth_identities", "projects", "notes"})


def alembic_config(connection: Connection | None = None) -> Config:
    """A Config with no ini file, so alembic/env.py leaves the host
    process's logging alone. The script location is absolute, so this
    works from any working directory (the Lambda's included)."""
    cfg = Config()
    cfg.set_main_option("script_location", str(SCRIPT_LOCATION))
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def _stamp_pre_alembic_baseline(connection: Connection, cfg: Config) -> None:
    """Stamp a create_all() database at the baseline. Refuses a database
    holding only some of the baseline tables: that isn't a schema any
    version of this app produced, so guessing could lose data."""
    # "No revision recorded" rather than "no alembic_version table": an
    # empty version table (left by an interrupted run on a driver that
    # committed DDL early) means unstamped just the same.
    if current_revision(connection) is not None:
        return
    tables = set(inspect(connection).get_table_names())
    present = BASELINE_TABLES & tables
    if not present:
        return  # empty database: the upgrade creates everything
    if present != BASELINE_TABLES:
        missing = ", ".join(sorted(BASELINE_TABLES - present))
        raise RuntimeError(
            "Database has some of the app's tables but not all (missing: "
            f"{missing}) and no recorded revision. Refusing to guess its "
            "schema version; fix it by hand, then stamp it with "
            "`uv run alembic stamp <revision>`."
        )
    command.stamp(cfg, BASELINE_REVISION)
    print(f"Pre-Alembic schema found: stamped at baseline revision {BASELINE_REVISION}.")


def _migration_engine(database_url: str) -> Engine:
    """An engine whose transactions really cover DDL.

    Postgres: as is. SQLite: SQLite itself supports transactional DDL,
    but Python's sqlite3 driver manages transactions on its own and lets
    DDL (CREATE TABLE, the table rebuilds of batch migrations) commit
    outside the transaction SQLAlchemy thinks it has open. A failed
    migration could then leave half its changes behind, e.g. a new
    alembic_version table without the stamp in it. So turn the driver's
    handling off and issue BEGIN ourselves (SQLAlchemy's documented
    pysqlite recipe).

    SQLite foreign keys stay off (SQLite's default): batch migrations
    rebuild a table by copying it, dropping the original and renaming the
    copy, and with foreign keys on, dropping `projects` would
    cascade-delete every note."""
    if not database_url.startswith("sqlite"):
        return create_engine(database_url)
    engine = create_engine(database_url, connect_args={"isolation_level": None})

    @event.listens_for(engine, "begin")
    def _begin(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN")

    return engine


def upgrade_to_head(database_url: str) -> None:
    """Bring the database at database_url up to the latest revision. A
    dedicated engine, disposed afterwards: this runs once per process
    (bootstrap, init_local) and exits."""
    engine = _migration_engine(database_url)
    try:
        with engine.begin() as connection:
            cfg = alembic_config(connection)
            _stamp_pre_alembic_baseline(connection, cfg)
            before = current_revision(connection)
            command.upgrade(cfg, "head")
            after = current_revision(connection)
    finally:
        engine.dispose()
    if before == after:
        print(f"Schema already at head (revision {after}).")
    else:
        print(f"Schema migrated from revision {before} to {after}.")
