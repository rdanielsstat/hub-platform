"""One-time-per-deploy database bootstrap. Owns table creation: the app
itself does no database work at import (see app/main.py).

Run standalone, separate from normal app startup: `python -m
app.bootstrap_db`, or via lambda_handler below. Two modes, picked by
USE_SSM:

  - Cloud (USE_SSM on): Neon already provides the role and database, so
    this only creates tables, connecting with the URL in
    DB_URL_PARAM_NAME (the direct, non-pooled endpoint: PgBouncer's
    transaction mode is a poor fit for DDL). No master credentials, no
    CREATE ROLE, no CREATE DATABASE. Then seeds the demo account, if
    this environment has one (see "Demo account" below).
  - Local (USE_SSM off): against the Docker Compose Postgres, creates
    this environment's database and a least-privilege login role for
    the app, grants that role exactly what table creation and normal
    CRUD need (CONNECT on the database, USAGE + CREATE on the public
    schema), then creates the tables connected as that role.

Fully idempotent: safe to run on every deploy. An existing role/database
is left as-is (not recreated, not have its password changed); the GRANT
statements always re-run, since GRANT is itself a no-op when the
privilege is already held; table creation only creates what's missing.
Any failure propagates: lambda_handler fails the invocation and the CLI
exits 1, never reporting success against an unreachable database.

Local mode's two credential sources, kept deliberately separate:
  - MASTER credentials: superuser (or otherwise privileged) credentials
    used only here to create the database/role and grant privileges.
    From MASTER_DB_HOST/PORT/USER/PASSWORD env vars.
  - APP credentials: the exact per-environment values
    app/core/config.py's get_database_url() already resolves for the
    app's own DATABASE_URL, so the role created here has the same name
    and password the app will actually connect with.

Demo account (cloud mode only). DEMO_PASSWORD_PARAM_NAME names an SSM
SecureString holding the demo password, and is absent entirely in an
environment with no demo account. Absent or empty: nothing is seeded.
Set: the demo user (app/db/seed.py's email, projects and notes) is
created with that password if it doesn't exist yet; an existing demo
user is left exactly as it is. Set but the parameter is missing or
empty: raise. The local seed's hardcoded password is never used here.
"""

import json
import os
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import errors as pg_errors
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core import config
from app.db.orm import Base
from app.db.seed import SEED_USER_EMAIL, seed
from app.db.session import enable_sqlite_foreign_keys
from app.db.store import Store

ADMIN_DATABASE = "postgres"

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _quote_identifier(name: str) -> str:
    """A dynamic Postgres identifier (role/database name) can't be a
    bind parameter — only literal values can. Validate against a strict
    charset first, then quote, rather than interpolating an unchecked
    string into SQL."""
    if not _IDENTIFIER_RE.fullmatch(name):
        raise ValueError(f"Unsafe Postgres identifier: {name!r}")
    return f'"{name}"'


def _quote_literal(value: str) -> str:
    """CREATE ROLE ... PASSWORD takes a plain string literal in its
    grammar (an Sconst), not a bind parameter — `PASSWORD $1` is a
    syntax error, so this can't go through execute()'s params like the
    SELECT checks below do. Standard SQL string-literal escaping
    (doubling embedded quotes) is safe here with
    standard_conforming_strings on, which every supported Postgres
    version defaults to."""
    return "'" + value.replace("'", "''") + "'"


def _connect(**kwargs: object) -> psycopg.Connection:
    """Thin wrapper so tests can substitute a fake connection without
    touching a real socket."""
    return psycopg.connect(**kwargs)  # type: ignore[arg-type]


def get_master_credentials() -> dict[str, object]:
    """Superuser credentials, resolved separately from the app's own
    DATABASE_URL. Never cached at module scope (this runs
    once per process invocation, not per-request)."""
    if config.USE_SSM:
        param_name = os.environ["MASTER_DB_PARAM_NAME"]
        creds = json.loads(config._fetch_ssm_parameter(param_name))
        return {
            "host": creds["host"],
            "port": int(creds["port"]),
            "user": creds["username"],
            "password": creds["password"],
        }
    return {
        "host": os.environ["MASTER_DB_HOST"],
        "port": int(os.environ.get("MASTER_DB_PORT", "5432")),
        "user": os.environ["MASTER_DB_USER"],
        "password": os.environ["MASTER_DB_PASSWORD"],
    }


def get_app_target() -> dict[str, str]:
    """The role/database this environment's app will connect as —
    parsed from the exact URL app/core/config.py's get_database_url()
    already builds, so nothing here can drift from what the app uses."""
    url = make_url(config.get_database_url())
    if url.get_backend_name() != "postgresql":
        raise RuntimeError(
            f"DATABASE_URL resolves to a {url.get_backend_name()!r} URL, not "
            "Postgres. Bootstrap only applies to the Postgres deployment "
            "path; there's nothing to bootstrap for the local SQLite "
            "default."
        )
    if not url.username or not url.database:
        raise RuntimeError(
            "DATABASE_URL is missing a username or database name; can't "
            "determine what role/database to bootstrap."
        )
    return {
        "role": url.username,
        "password": url.password or "",
        "dbname": url.database,
    }


def _role_exists(cur: psycopg.Cursor, role: str) -> bool:
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
    return cur.fetchone() is not None


def _database_exists(cur: psycopg.Cursor, dbname: str) -> bool:
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
    return cur.fetchone() is not None


def _ensure_role(cur: psycopg.Cursor, role: str, password: str) -> None:
    if _role_exists(cur, role):
        print(f"Role {role!r} already exists, skipping.")
        return
    try:
        cur.execute(
            f"CREATE ROLE {_quote_identifier(role)} WITH LOGIN "
            f"PASSWORD {_quote_literal(password)} "
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION"
        )
        print(f"Created role {role!r}.")
    except pg_errors.DuplicateObject:
        print(f"Role {role!r} was created concurrently, skipping.")


def _ensure_database(cur: psycopg.Cursor, dbname: str) -> None:
    if _database_exists(cur, dbname):
        print(f"Database {dbname!r} already exists, skipping.")
        return
    try:
        cur.execute(f"CREATE DATABASE {_quote_identifier(dbname)}")
        print(f"Created database {dbname!r}.")
    except pg_errors.DuplicateDatabase:
        print(f"Database {dbname!r} was created concurrently, skipping.")


def _grant_privileges(cur: psycopg.Cursor, dbname: str, role: str) -> None:
    """Least-privilege grant: CONNECT on the database, plus USAGE +
    CREATE on the public schema, which is exactly what create_tables()
    (CREATE TABLE/INDEX) and normal CRUD after that need. No superuser,
    no CREATEDB/CREATEROLE, no ownership of the database itself. GRANT
    is idempotent (a no-op if already held), so this always runs."""
    cur.execute(
        f"GRANT CONNECT ON DATABASE {_quote_identifier(dbname)} "
        f"TO {_quote_identifier(role)}"
    )
    cur.execute(f"GRANT USAGE, CREATE ON SCHEMA public TO {_quote_identifier(role)}")
    print(
        f"Granted CONNECT on {dbname!r} and USAGE, CREATE on schema public "
        f"to {role!r}."
    )


def _create_tables(database_url: str) -> None:
    """Create any missing tables, connected with database_url. A
    dedicated engine, disposed afterwards, rather than the app's cached
    one in app/db/session.py: this runs once and exits."""
    engine = create_engine(database_url)
    try:
        Base.metadata.create_all(bind=engine)
    finally:
        engine.dispose()
    print("Tables created (any that already existed were left as-is).")


@contextmanager
def _store(database_url: str) -> Iterator[Store]:
    """A Store on its own engine, disposed afterwards, for the same
    reason as _create_tables()."""
    engine = create_engine(database_url)
    enable_sqlite_foreign_keys(engine, database_url)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield Store(db)
    finally:
        db.close()
        engine.dispose()


def _demo_password_param_name() -> str | None:
    """The SSM parameter holding this environment's demo password, or
    None when the environment has no demo account."""
    return os.environ.get("DEMO_PASSWORD_PARAM_NAME", "").strip() or None


def _read_demo_password(param_name: str) -> str:
    """Raises rather than returning an empty password; a missing
    parameter raises from the SSM client itself."""
    password = config._fetch_ssm_parameter(param_name)
    if not password.strip():
        raise RuntimeError(
            f"SSM parameter {param_name!r} (DEMO_PASSWORD_PARAM_NAME) is "
            "empty. Refusing to create the demo account without a password."
        )
    return password


def _seed_demo_account(database_url: str) -> None:
    param_name = _demo_password_param_name()
    if param_name is None:
        print("DEMO_PASSWORD_PARAM_NAME is not set: no demo account here, not seeding.")
        return
    password = _read_demo_password(param_name)
    with _store(database_url) as store:
        if store.get_user_by_email(SEED_USER_EMAIL) is not None:
            print(f"Demo account {SEED_USER_EMAIL!r} already exists, leaving it as-is.")
            return
        seed(store, password=password)
    print(f"Seeded demo account {SEED_USER_EMAIL!r}.")


def bootstrap() -> None:
    if config.USE_SSM:
        database_url = config.get_database_url()
        _create_tables(database_url)
        _seed_demo_account(database_url)
        return

    master = get_master_credentials()
    target = get_app_target()

    admin_conn = _connect(
        host=master["host"],
        port=master["port"],
        user=master["user"],
        password=master["password"],
        dbname=ADMIN_DATABASE,
        autocommit=True,
    )
    try:
        with admin_conn.cursor() as cur:
            _ensure_role(cur, target["role"], target["password"])
            _ensure_database(cur, target["dbname"])
    finally:
        admin_conn.close()

    # GRANTs on the target database's schema need a connection to that
    # database, not the admin one.
    target_conn = _connect(
        host=master["host"],
        port=master["port"],
        user=master["user"],
        password=master["password"],
        dbname=target["dbname"],
        autocommit=True,
    )
    try:
        with target_conn.cursor() as cur:
            _grant_privileges(cur, target["dbname"], target["role"])
    finally:
        target_conn.close()

    # As the app's own role, so the tables belong to the role that will
    # use them.
    _create_tables(config.get_database_url())


def lambda_handler(event: object, context: object) -> dict[str, str]:
    """AWS Lambda entry point, invoked once per deploy via a container
    image with command `app.bootstrap_db.lambda_handler` — the deploy
    pipeline's equivalent of running the CLI below. Reads the exact same
    env vars (USE_SSM, DB_URL_PARAM_NAME) as the CLI, since it calls the
    same bootstrap() function.

    Unlike main() below, this does not catch exceptions: a failed
    bootstrap must propagate and show up as a failed Lambda invocation,
    not a quietly-successful one. `event` and `context` are unused: every
    invocation is the same idempotent bootstrap, which never deletes or
    changes existing data.
    """
    bootstrap()
    return {"status": "ok", "message": "Bootstrap complete."}


def main() -> None:
    try:
        bootstrap()
    except Exception as exc:
        print(f"Bootstrap failed: {exc!r}", file=sys.stderr)
        raise SystemExit(1)
    print("Bootstrap complete.")


if __name__ == "__main__":
    main()
