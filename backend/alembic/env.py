"""Alembic environment: how migrations connect and what they compare
against.

Three ways in, one schema:
  - app/db/migrations.py (the bootstrap and init_local) passes an open
    connection in config.attributes["connection"], so the baseline stamp
    and the upgrade share one transaction.
  - The same module can instead pass config.attributes["database_url"].
  - The CLI (`uv run alembic ...` from backend/) passes neither: the URL
    comes from app/core/config.py's get_database_url(), after loading
    backend/.env the way init_local does.

render_as_batch is on for SQLite only: SQLite can't ALTER most column
or constraint changes in place, and batch mode rebuilds the table
instead. Postgres runs plain ALTERs.
"""

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from app.db.orm import Base

config = context.config

# Only the CLI has an ini file. Programmatic runs (app/db/migrations.py)
# build their Config without one, so they never reconfigure the host
# process's logging (fileConfig would replace the root handlers).
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _database_url() -> str:
    url = config.attributes.get("database_url")
    if url:
        return url
    # CLI only. Existing env vars win over the file, as in init_local.
    load_dotenv(ENV_FILE)
    from app.core.config import get_database_url

    return get_database_url()


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    dialect = connection.dialect.name if connection is not None else url.split(":")[0]
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=dialect.startswith("sqlite"),
        literal_binds=connection is None,
        dialect_opts={"paramstyle": "named"} if connection is None else {},
    )


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: emit the SQL instead of running it."""
    _configure(url=_database_url())
    with context.begin_transaction():
        context.run_migrations()


def _run_with(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run_with(connection)
        return
    engine = create_engine(_database_url())
    try:
        with engine.connect() as connection:
            _run_with(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
