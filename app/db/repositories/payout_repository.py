from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PayoutStatus
from app.db.models import Payout


class PayoutRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_payout(
        self,
        restaurant_id: str,
        amount_cents: int,
        currency: str = "PEN",
        metadata_: Optional[dict] = None,
    ) -> Payout:
        payout = Payout(
            restaurant_id=restaurant_id,
            amount_cents=amount_cents,
            currency=currency,
            status=PayoutStatus.CREATED,
            metadata_=metadata_,
        )
        self.session.add(payout)
        await self.session.flush()
        return payout

    async def get_by_id(self, id: int) -> Optional[Payout]:
        stmt = select(Payout).where(Payout.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def has_pending_payouts(self, restaurant_id: str) -> bool:
        stmt = (
            select(Payout)
            .where(Payout.restaurant_id == restaurant_id)
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
        if failure_reason:
            payout.failure_reason = failure_reason
        await self.session.flush()
        return payout
