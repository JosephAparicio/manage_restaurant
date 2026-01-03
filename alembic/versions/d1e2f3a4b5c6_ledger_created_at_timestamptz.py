"""convert ledger_entries.created_at to timestamptz

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
Create Date: 2026-01-03

"""

from alembic import op
import sqlalchemy as sa


revision = "d1e2f3a4b5c6"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Interpret existing naive timestamps as UTC and convert to timestamptz.
    op.execute(
        "ALTER TABLE ledger_entries "
        "ALTER COLUMN created_at TYPE TIMESTAMPTZ "
        "USING created_at AT TIME ZONE 'UTC'"
    )


def downgrade() -> None:
    # Convert timestamptz back to naive timestamp (drop timezone information).
    op.execute(
        "ALTER TABLE ledger_entries "
        "ALTER COLUMN created_at TYPE TIMESTAMP "
        "USING created_at AT TIME ZONE 'UTC'"
    )
