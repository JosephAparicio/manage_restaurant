from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EntryType
from app.db.base import Base


class LedgerEntry(Base):
    """Immutable ledger entry. Balance calculated from sum, never stored."""

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("restaurants.id", ondelete="RESTRICT"), nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), server_default="'PEN'", nullable=False
    )
    entry_type: Mapped[EntryType] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    related_event_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        ForeignKey("processor_events.event_id", ondelete="RESTRICT"),
        nullable=True,
    )
    related_payout_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("payouts.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    available_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('sale', 'commission', 'refund', 'payout_reserve')",
            name="valid_entry_type",
        ),
        Index("idx_ledger_restaurant_currency", "restaurant_id", "currency"),
        Index(
            "idx_ledger_available_at",
            "available_at",
            postgresql_where="available_at IS NOT NULL",
        ),
    )
