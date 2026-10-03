"""add tag, link and display name limits

CHECK constraints:

    users.display_name   at most 100 characters (NULL allowed)
    projects.tags        at most 50 entries
    projects.links       at most 50 entries

The API also limits each tag (64 characters) and each link's url (2048)
and label (200) (app/models/project.py). Those per-element limits are
API-only: a CHECK constraint can't portably inspect every element of a
JSON array. json_array_length() itself exists in SQLite and in Postgres
(for the json type these columns have there).

Existing rows: like 0002, counts violations first and stops with a
message rather than letting Postgres fail the ALTER, and never truncates
or deletes anything. On Postgres the whole run rolls back; on SQLite too
(app/db/migrations.py runs migrations in a real transaction).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-03 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, constraint name, condition, violation query). Fixed here, not
# imported from app/models, so this migration keeps meaning what it meant.
CONSTRAINTS = [
    (
        "users",
        "ck_users_display_name_length",
        "length(display_name) <= 100",
        "SELECT count(*) FROM users WHERE length(display_name) > 100",
    ),
    (
        "projects",
        "ck_projects_tags_count",
        "json_array_length(tags) <= 50",
        "SELECT count(*) FROM projects WHERE json_array_length(tags) > 50",
    ),
    (
        "projects",
        "ck_projects_links_count",
        "json_array_length(links) <= 50",
        "SELECT count(*) FROM projects WHERE json_array_length(links) > 50",
    ),
]


def _check_existing_rows() -> None:
    bind = op.get_bind()
    too_long = []
    for _table, name, condition, query in CONSTRAINTS:
        count = bind.execute(sa.text(query)).scalar_one()
        if count:
            too_long.append(f"{name} ({condition}): {count} row(s) over")
    if too_long:
        raise RuntimeError(
            "Can't add tag, link and display name limits: existing data "
            "already exceeds them. "
            + "; ".join(too_long)
            + ". Fix those rows by hand (or raise the limit in a new "
            "migration), then deploy again. Nothing was changed."
        )


def upgrade() -> None:
    _check_existing_rows()
    for table in ("users", "projects"):
        with op.batch_alter_table(table) as batch_op:
            for t, name, condition, _query in CONSTRAINTS:
                if t == table:
                    batch_op.create_check_constraint(name, condition)


def downgrade() -> None:
    for table in ("users", "projects"):
        with op.batch_alter_table(table) as batch_op:
            for t, name, _condition, _query in CONSTRAINTS:
                if t == table:
                    batch_op.drop_constraint(name, type_="check")
