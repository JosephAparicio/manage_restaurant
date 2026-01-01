from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EntryType
from app.db.repositories import LedgerRepository


class LedgerService:
    MATURITY_DAYS = 7

    def __init__(self, session: AsyncSession) -> None:
        self.ledger_repo = LedgerRepository(session)

    async def create_sale_entries(
        self,
        restaurant_id: str,
        event_id: str,
        amount_cents: int,
        fee_cents: int,
        occurred_at: datetime,
        currency: str = "PEN",
    ) -> None:
        available_at = occurred_at + timedelta(days=self.MATURITY_DAYS)

        await self.ledger_repo.create_entry(
            restaurant_id=restaurant_id,
            amount_cents=amount_cents,
            currency=currency,
            entry_type=EntryType.SALE,
            description=f"Sale from event {event_id}",
            related_event_id=event_id,
            available_at=available_at,
        )

        if fee_cents > 0:
            await self.ledger_repo.create_entry(
                restaurant_id=restaurant_id,
                amount_cents=-fee_cents,
                currency=currency,
                entry_type=EntryType.COMMISSION,
                description=f"Commission for event {event_id}",
                related_event_id=event_id,
                available_at=None,
            )

    async def create_refund_entry(
        self,
        restaurant_id: str,
        event_id: str,
        amount_cents: int,
        currency: str = "PEN",
    ) -> None:
        await self.ledger_repo.create_entry(
            restaurant_id=restaurant_id,
            amount_cents=-amount_cents,
            currency=currency,
            entry_type=EntryType.REFUND,
            description=f"Refund from event {event_id}",
            related_event_id=event_id,
            available_at=None,
        )

    async def create_payout_entry(
        self,
        restaurant_id: str,
        payout_id: int,
        amount_cents: int,
        currency: str = "PEN",
    ) -> None:
        await self.ledger_repo.create_entry(
            restaurant_id=restaurant_id,
            amount_cents=-amount_cents,
            currency=currency,
            entry_type=EntryType.PAYOUT_RESERVE,
            description=f"Payout reserve for payout {payout_id}",
            related_payout_id=payout_id,
            available_at=None,
        )
