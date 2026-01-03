from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import PayoutStatus
from app.db.base import Base


class Payout(Base):
    """Payout settlement record. Status lifecycle: created → processing → paid/failed."""

    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("restaurants.id", ondelete="RESTRICT"), nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), server_default="'PEN'", nullable=False
    )
    as_of: Mapped[date] = mapped_column(
        Date,
        server_default=func.current_date(),
        nullable=False,
    )
    status: Mapped[PayoutStatus] = mapped_column(
        String(50), server_default="'created'", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    items = relationship(
        "PayoutItem",
        back_populates="payout",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="positive_payout_amount"),
        CheckConstraint(
            "status IN ('created', 'processing', 'paid', 'failed')",
            name="valid_payout_status",
        ),
        UniqueConstraint(
            "restaurant_id",
            "currency",
            "as_of",
            name="uq_payout_restaurant_currency_asof",
        ),
        CheckConstraint(
            "(status = 'paid' AND paid_at IS NOT NULL) OR (status != 'paid' AND paid_at IS NULL)",
            name="paid_at_consistency",
        ),
        Index(
            "idx_payouts_pending",
            "restaurant_id",
            "status",
            postgresql_where="status IN ('created', 'processing')",
        ),
        Index("idx_payouts_as_of", "currency", "as_of"),
    )
