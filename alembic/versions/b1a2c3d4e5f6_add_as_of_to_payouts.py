"""add as_of to payouts

Revision ID: b1a2c3d4e5f6
Revises: 76dcf364c4e7
Create Date: 2026-01-03

"""

from alembic import op
import sqlalchemy as sa


revision = "b1a2c3d4e5f6"
down_revision = "76dcf364c4e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payouts",
        sa.Column(
            "as_of",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
    )

    op.create_unique_constraint(
        "uq_payout_restaurant_currency_asof",
        "payouts",
        ["restaurant_id", "currency", "as_of"],
    )

    op.create_index("idx_payouts_as_of", "payouts", ["currency", "as_of"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_payouts_as_of", table_name="payouts")
    op.drop_constraint("uq_payout_restaurant_currency_asof", "payouts", type_="unique")
    op.drop_column("payouts", "as_of")
