from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PayoutItem(Base):
    __tablename__ = "payout_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    payout_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("payouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)

    payout = relationship("Payout", back_populates="items")

    __table_args__ = (
        CheckConstraint(
            "item_type IN ('net_sales', 'fees', 'refunds')",
            name="valid_payout_item_type",
        ),
        Index("idx_payout_items_payout_id", "payout_id"),
    )
