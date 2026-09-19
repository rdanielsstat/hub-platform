"""Application settings, sourced from environment variables.

Single source for the database URL: everything that needs it (engine
setup, migrations later) reads it from here, never hardcodes it.
Defaults to a local SQLite file for dev. The same code accepts a
Postgres URL (e.g. `postgresql+psycopg://user:pass@host/db`) via
DATABASE_URL with no code change — see app/db/session.py.
"""

import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./hub.db")
