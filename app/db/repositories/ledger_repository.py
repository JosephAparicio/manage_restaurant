from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EntryType
from app.db.models import LedgerEntry


class LedgerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_entry(
        self,
        restaurant_id: str,
        amount_cents: int,
        currency: str,
        entry_type: EntryType,
        description: Optional[str] = None,
        related_event_id: Optional[str] = None,
        related_payout_id: Optional[int] = None,
        available_at: Optional[datetime] = None,
    ) -> LedgerEntry:
        entry = LedgerEntry(
            restaurant_id=restaurant_id,
            amount_cents=amount_cents,
            currency=currency,
            entry_type=entry_type,
            description=description,
            related_event_id=related_event_id,
            related_payout_id=related_payout_id,
            available_at=available_at,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_available_balance(
        self, restaurant_id: str, currency: str = "PEN"
    ) -> int:
        stmt = (
            select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
            .where(LedgerEntry.restaurant_id == restaurant_id)
            .where(LedgerEntry.currency == currency)
            .where(
                (LedgerEntry.available_at.is_(None))
                | (LedgerEntry.available_at <= func.now())
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_pending_balance(
        self, restaurant_id: str, currency: str = "PEN"
    ) -> int:
        stmt = (
            select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
            .where(LedgerEntry.restaurant_id == restaurant_id)
            .where(LedgerEntry.currency == currency)
            .where(LedgerEntry.available_at > func.now())
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_last_event_at(
        self, restaurant_id: str, currency: str = "PEN"
    ) -> Optional[datetime]:
        """Get the timestamp of the last processed event for the restaurant."""
        stmt = (
            select(func.max(LedgerEntry.created_at))
            .where(LedgerEntry.restaurant_id == restaurant_id)
            .where(LedgerEntry.currency == currency)
            .where(LedgerEntry.related_event_id.isnot(None))
        )
        result = await self.session.execute(stmt)
        return result.scalar()

    async def get_balance_summary(
        self, restaurant_id: str, currency: str = "PEN"
    ) -> tuple[int, int, Optional[datetime]]:
        """
        Get all balance metrics in a single optimized query.

        Returns: (available_cents, pending_cents, last_event_at)
        """
        stmt = select(
            func.coalesce(
                func.sum(
                    func.case(
                        (
                            (LedgerEntry.available_at.is_(None))
                            | (LedgerEntry.available_at <= func.now()),
                            LedgerEntry.amount_cents,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("available"),
            func.coalesce(
                func.sum(
                    func.case(
                        (LedgerEntry.available_at > func.now(), LedgerEntry.amount_cents),
                        else_=0,
                    )
                ),
                0,
            ).label("pending"),
            func.max(
                func.case(
                    (LedgerEntry.related_event_id.isnot(None), LedgerEntry.created_at),
                    else_=None,
                )
            ).label("last_event_at"),
        ).where(
            (LedgerEntry.restaurant_id == restaurant_id)
            & (LedgerEntry.currency == currency)
        )

        result = await self.session.execute(stmt)
        row = result.one()
        return row.available, row.pending, row.last_event_at
