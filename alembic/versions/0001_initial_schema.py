"""initial schema (squashed)

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-01-04

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "restaurants",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("id LIKE 'res_%'", name="restaurant_id_format"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_restaurants_name",
        "restaurants",
        ["name"],
        unique=False,
    )
    op.create_index(
        "idx_restaurants_active",
        "restaurants",
        ["is_active"],
        unique=False,
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.create_table(
        "payouts",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("restaurant_id", sa.String(length=50), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'PEN'"),
            nullable=False,
        ),
        sa.Column(
            "as_of",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default=sa.text("'created'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("amount_cents > 0", name="positive_payout_amount"),
        sa.CheckConstraint(
            "status IN ('created', 'processing', 'paid', 'failed')",
            name="valid_payout_status",
        ),
        sa.CheckConstraint(
            "(status = 'paid' AND paid_at IS NOT NULL) OR (status != 'paid' AND paid_at IS NULL)",
            name="paid_at_consistency",
        ),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "restaurant_id",
            "currency",
            "as_of",
            name="uq_payout_restaurant_currency_asof",
        ),
    )

    op.create_index(
        "idx_payouts_pending",
        "payouts",
        ["restaurant_id", "status"],
        unique=False,
        postgresql_where=sa.text("status IN ('created', 'processing')"),
    )
    op.create_index(
        "idx_payouts_as_of",
        "payouts",
        ["currency", "as_of"],
        unique=False,
    )

    op.create_index(
        "idx_payouts_restaurant_status",
        "payouts",
        ["restaurant_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_payouts_created",
        "payouts",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "processor_events",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("event_id", sa.String(length=50), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("restaurant_id", sa.String(length=50), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'PEN'"),
            nullable=False,
        ),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "fee_cents",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('charge_succeeded', 'refund_succeeded', 'payout_paid')",
            name="valid_event_type",
        ),
        sa.CheckConstraint("amount_cents >= 0", name="positive_amount"),
        sa.CheckConstraint("fee_cents >= 0", name="positive_fee"),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )

    op.create_index(
        "idx_processor_events_event_id",
        "processor_events",
        ["event_id"],
        unique=True,
    )

    op.create_index(
        "idx_processor_events_restaurant",
        "processor_events",
        ["restaurant_id"],
        unique=False,
    )
    op.create_index(
        "idx_processor_events_type",
        "processor_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "idx_processor_events_restaurant_occurred",
        "processor_events",
        ["restaurant_id", "occurred_at"],
        unique=False,
    )

    op.create_table(
        "ledger_entries",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("restaurant_id", sa.String(length=50), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'PEN'"),
            nullable=False,
        ),
        sa.Column("entry_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("related_event_id", sa.String(length=100), nullable=True),
        sa.Column("related_payout_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "entry_type IN ('sale', 'commission', 'refund', 'payout_reserve')",
            name="valid_entry_type",
        ),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["related_event_id"],
            ["processor_events.event_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["related_payout_id"],
            ["payouts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_ledger_restaurant_currency",
        "ledger_entries",
        ["restaurant_id", "currency"],
        unique=False,
    )
    op.create_index(
        "idx_ledger_available_at",
        "ledger_entries",
        ["available_at"],
        unique=False,
        postgresql_where=sa.text("available_at IS NOT NULL"),
    )

    op.create_index(
        "idx_ledger_restaurant_created",
        "ledger_entries",
        ["restaurant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_ledger_related_event",
        "ledger_entries",
        ["related_event_id"],
        unique=False,
        postgresql_where=sa.text("related_event_id IS NOT NULL"),
    )
    op.create_index(
        "idx_ledger_related_payout",
        "ledger_entries",
        ["related_payout_id"],
        unique=False,
        postgresql_where=sa.text("related_payout_id IS NOT NULL"),
    )

    op.create_table(
        "payout_items",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
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

    op.drop_index(
        "idx_ledger_related_payout",
        table_name="ledger_entries",
        postgresql_where=sa.text("related_payout_id IS NOT NULL"),
    )
    op.drop_index(
        "idx_ledger_related_event",
        table_name="ledger_entries",
        postgresql_where=sa.text("related_event_id IS NOT NULL"),
    )
    op.drop_index("idx_ledger_restaurant_created", table_name="ledger_entries")

    op.drop_index(
        "idx_ledger_available_at",
        table_name="ledger_entries",
        postgresql_where=sa.text("available_at IS NOT NULL"),
    )
    op.drop_index("idx_ledger_restaurant_currency", table_name="ledger_entries")
    op.drop_table("ledger_entries")

    op.drop_index(
        "idx_processor_events_restaurant_occurred",
        table_name="processor_events",
    )
    op.drop_index("idx_processor_events_type", table_name="processor_events")
    op.drop_index("idx_processor_events_restaurant", table_name="processor_events")

    op.drop_index("idx_processor_events_event_id", table_name="processor_events")
    op.drop_table("processor_events")

    op.drop_index("idx_payouts_created", table_name="payouts")
    op.drop_index("idx_payouts_restaurant_status", table_name="payouts")

    op.drop_index("idx_payouts_as_of", table_name="payouts")
    op.drop_index(
        "idx_payouts_pending",
        table_name="payouts",
        postgresql_where=sa.text("status IN ('created', 'processing')"),
    )
    op.drop_table("payouts")

    op.drop_index(
        "idx_restaurants_active",
        table_name="restaurants",
        postgresql_where=sa.text("is_active = TRUE"),
    )
    op.drop_index("idx_restaurants_name", table_name="restaurants")

    op.drop_table("restaurants")
