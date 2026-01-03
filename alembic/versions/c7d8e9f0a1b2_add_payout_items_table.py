"""add payout_items table

Revision ID: c7d8e9f0a1b2
Revises: b1a2c3d4e5f6
Create Date: 2026-01-03

"""

from alembic import op
import sqlalchemy as sa


revision = "c7d8e9f0a1b2"
down_revision = "b1a2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payout_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("payout_id", sa.BigInteger(), nullable=False),
        sa.Column("item_type", sa.String(length=50), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "item_type IN ('net_sales', 'fees', 'refunds')",
            name="valid_payout_item_type",
        ),
        sa.ForeignKeyConstraint(
            ["payout_id"],
            ["payouts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_payout_items_payout_id",
        "payout_items",
        ["payout_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_payout_items_payout_id", table_name="payout_items")
    op.drop_table("payout_items")
