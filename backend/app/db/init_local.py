"""Local-only database setup: create tables, and seed the demo account
when SEED_DEMO_DATA is on.

Run standalone before starting the app locally: `python -m
app.db.init_local`. Docker Compose does this for you (see the
`init_local` service). Nothing here runs at app import.

Refuses to run at all when USE_SSM is on: deployed databases get their
schema from the bootstrap, and must never receive the demo account and
its hardcoded password.

Idempotent: create_tables() only creates what's missing, and seeding
only ever happens into a database with no users, so an existing
database is never re-seeded, duplicated, or overwritten.
"""

import sys

from app.core import config
from app.db.seed import seed
from app.db.session import SessionLocal, create_tables
from app.db.store import Store


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

    create_tables()

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
    try:
        init_local()
    except Exception as exc:
        print(f"Local database init failed: {exc!r}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
