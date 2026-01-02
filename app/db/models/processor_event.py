from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EventType
from app.db.base import Base


class ProcessorEvent(Base):
    """Processor webhook event log. Idempotency guaranteed by unique event_id."""

    __tablename__ = "processor_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    event_type: Mapped[EventType] = mapped_column(String(50), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    restaurant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("restaurants.id", ondelete="RESTRICT"), nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(3), server_default="'PEN'", nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_cents: Mapped[int] = mapped_column(
        BigInteger, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint("amount_cents >= 0", name="positive_amount"),
        CheckConstraint("fee_cents >= 0", name="positive_fee"),
        CheckConstraint(
            "event_type IN ('charge_succeeded', 'refund_succeeded', 'payout_paid')",
            name="valid_event_type",
        ),
        Index("idx_processor_events_event_id", "event_id", unique=True),
    )
