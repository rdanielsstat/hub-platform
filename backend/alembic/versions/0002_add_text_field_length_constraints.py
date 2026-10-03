"""add text field length constraints

CHECK constraints capping the free-text columns, in characters:

    projects.name         256
    projects.pitch        2000
    projects.description  5000
    projects.next_action  1000
    notes.body            10000

The API already rejects longer input (app/models/project.py,
app/models/note.py); these make the database enforce the same limits
for anything that writes to it directly. The columns stay Text, so no
type change and no table rewrite on Postgres.

Existing rows: Postgres validates every existing row when a CHECK
constraint is added, so one over-long value would fail this migration
with a cryptic constraint error. Instead it counts violations first and,
if there are any, stops with a message saying where. Nothing is
truncated: shortening someone's notes is a decision for a person, not a
migration. On Postgres the failure rolls back the whole run, and the
deploy stops before the new API code goes live (ops/DEPLOYMENT.md).

SQLite applies these through Alembic's batch mode (rebuild the table
with the constraint, copy the rows over).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02 17:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed here rather than imported from app/models: a migration must keep
# doing what it did when it was written, even if the app's limits change
# later (that would be a new migration).
LIMITS: dict[str, dict[str, int]] = {
    "projects": {
        "name": 256,
        "pitch": 2000,
        "description": 5000,
        "next_action": 1000,
    },
    "notes": {"body": 10000},
}


def _constraint_name(table: str, column: str) -> str:
    return f"ck_{table}_{column}_length"


def _check_existing_rows() -> None:
    bind = op.get_bind()
    too_long = []
    for table, columns in LIMITS.items():
        for column, limit in columns.items():
            count = bind.execute(
                sa.text(f"SELECT count(*) FROM {table} WHERE length({column}) > {limit}")
            ).scalar_one()
            if count:
                too_long.append(f"{table}.{column}: {count} row(s) over {limit}")
    if too_long:
        raise RuntimeError(
            "Can't add length limits: existing data is already longer. "
            + "; ".join(too_long)
            + ". Shorten those values by hand (or raise the limit in a new "
            "migration), then deploy again. Nothing was changed."
        )


def upgrade() -> None:
    _check_existing_rows()
    for table, columns in LIMITS.items():
        with op.batch_alter_table(table) as batch_op:
            for column, limit in columns.items():
                batch_op.create_check_constraint(
                    _constraint_name(table, column), f"length({column}) <= {limit}"
                )


def downgrade() -> None:
    for table, columns in LIMITS.items():
        with op.batch_alter_table(table) as batch_op:
            for column in columns:
                batch_op.drop_constraint(_constraint_name(table, column), type_="check")
