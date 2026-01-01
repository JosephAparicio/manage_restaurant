from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import LedgerRepository
from app.schemas.balance import RestaurantBalance


class BalanceCalculator:
    def __init__(self, session: AsyncSession) -> None:
        self.ledger_repo = LedgerRepository(session)

    async def get_balance(
        self, restaurant_id: str, currency: str = "PEN"
    ) -> RestaurantBalance:
        available, pending, last_event_at = (
            await self.ledger_repo.get_balance_summary(restaurant_id, currency)
        )

        return RestaurantBalance(
            restaurant_id=restaurant_id,
            currency=currency,
            available_cents=available,
            pending_cents=pending,
            total_cents=available + pending,
            last_event_at=last_event_at,
        )
