from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

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

    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="positive_payout_amount"),
        CheckConstraint(
            "status IN ('created', 'processing', 'paid', 'failed')",
            name="valid_payout_status",
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
    )
