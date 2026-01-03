from datetime import date
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import PayoutStatus
from app.db.models import Payout, PayoutItem
from app.metrics import payouts_total


class PayoutRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_payout(
        self,
        restaurant_id: str,
        amount_cents: int,
        currency: str = "PEN",
        as_of: Optional[date] = None,
        metadata_: Optional[dict] = None,
    ) -> Payout:
        payout_kwargs: dict = {
            "restaurant_id": restaurant_id,
            "amount_cents": amount_cents,
            "currency": currency,
            "status": PayoutStatus.CREATED,
            "metadata_": metadata_,
        }
        if as_of is not None:
            payout_kwargs["as_of"] = as_of

        payout = Payout(**payout_kwargs)
        self.session.add(payout)
        await self.session.flush()
        return payout

    async def exists_for_as_of(
        self, restaurant_id: str, currency: str, as_of: date
    ) -> bool:
        stmt = (
            select(Payout.id)
            .where(Payout.restaurant_id == restaurant_id)
            .where(Payout.currency == currency)
            .where(Payout.as_of == as_of)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_by_id(self, id: int) -> Optional[Payout]:
        stmt = select(Payout).options(selectinload(Payout.items)).where(Payout.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_items(self, payout_id: int, items: list[tuple[str, int]]) -> None:
        for item_type, amount_cents in items:
            self.session.add(
                PayoutItem(
                    payout_id=payout_id,
                    item_type=item_type,
                    amount_cents=amount_cents,
                )
            )
        await self.session.flush()

    async def has_pending_payouts(self, restaurant_id: str, currency: str) -> bool:
        stmt = (
            select(Payout)
            .where(Payout.restaurant_id == restaurant_id)
            .where(Payout.currency == currency)
            .where(Payout.status.in_([PayoutStatus.CREATED, PayoutStatus.PROCESSING]))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_pending_payouts(
        self, restaurant_id: Optional[str] = None
    ) -> List[Payout]:
        stmt = select(Payout).where(
            Payout.status.in_([PayoutStatus.CREATED, PayoutStatus.PROCESSING])
        )
        if restaurant_id:
            stmt = stmt.where(Payout.restaurant_id == restaurant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        payout: Payout,
        status: PayoutStatus,
        failure_reason: Optional[str] = None,
    ) -> Payout:
        payout.status = status
        if status == PayoutStatus.PAID:
            payout.paid_at = func.now()
            payouts_total.labels(status="paid").inc()
        elif status == PayoutStatus.FAILED:
            payouts_total.labels(status="failed").inc()
        if failure_reason:
            payout.failure_reason = failure_reason
        await self.session.flush()
        return payout
