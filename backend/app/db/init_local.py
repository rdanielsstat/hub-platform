"""Local-only database setup: migrate the schema to the latest Alembic
revision (app/db/migrations.py), and seed the demo account when
SEED_DEMO_DATA is on.

Run standalone before starting the app locally: `python -m
app.db.init_local`. Docker Compose does this for you (see the
`init_local` service). Nothing here runs at app import.

Refuses to run at all when USE_SSM is on: deployed databases get their
schema from the bootstrap, and must never receive the demo account and
its hardcoded password.

Reads backend/.env when run as a script (see main()), so SEED_DEMO_DATA
and DATABASE_URL can live there instead of on the command line.

Idempotent: a database already at the latest revision is left alone (a
pre-Alembic one is stamped, not recreated), and seeding
only ever happens into a database with no users, so an existing
database is never re-seeded, duplicated, or overwritten.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

from app.core import config
from app.db.migrations import upgrade_to_head
from app.db.seed import seed
from app.db.session import SessionLocal
from app.db.store import Store

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def init_local(
    use_ssm: bool = config.USE_SSM,
    seed_demo_data: bool = config.SEED_DEMO_DATA,
) -> None:
    if use_ssm:
        raise RuntimeError(
            "app.db.init_local is for local development only and refuses "
            "to run with USE_SSM on. Deployed databases are set up by the "
            "bootstrap."
        )

    upgrade_to_head(config.get_database_url())

    if not seed_demo_data:
        print("Tables ready. SEED_DEMO_DATA is off, not seeding.")
        return
    with SessionLocal() as db:
        store = Store(db)
        if store.has_users():
            print("Tables ready. Database already has users, not seeding.")
            return
        seed(store)
    print("Tables ready. Seeded demo data.")


def main() -> None:
    # Only here, not at import: importing this module (as the tests do)
    # must never pull a developer's .env into the process. Existing env
    # vars win over the file. The flags are then re-read rather than
    # taken from config's constants, which were fixed when config was
    # imported, before the file was loaded. DATABASE_URL needs nothing
    # extra: config reads it lazily on first use.
    load_dotenv(ENV_FILE)
    try:
        init_local(
            use_ssm=config.env_flag("USE_SSM"),
            seed_demo_data=config.env_flag("SEED_DEMO_DATA"),
        )
    except Exception as exc:
        print(f"Local database init failed: {exc!r}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
