import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import LedgerRepository, PayoutRepository
from app.exceptions import InsufficientBalanceException, PendingPayoutException
from app.metrics import balance_total, payouts_total
from app.schemas.payouts import PayoutCreate
from app.services.ledger_service import LedgerService

logger = logging.getLogger(__name__)


class PayoutGenerator:
    MIN_PAYOUT_AMOUNT = 10000  # 100.00 PEN - minimum to cover processing costs

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.payout_repo = PayoutRepository(session)
        self.ledger_repo = LedgerRepository(session)
        self.ledger_service = LedgerService(session)

    async def generate_payout(self, payout_data: PayoutCreate) -> int:
        """Must be called within transaction context (uses SELECT FOR UPDATE)."""
        restaurant_id = payout_data.restaurant_id
        currency = payout_data.currency

        logger.info(f"Starting payout generation for restaurant {restaurant_id}")

        has_pending = await self.payout_repo.has_pending_payouts(restaurant_id)
        if has_pending:
            logger.warning(
                f"Restaurant {restaurant_id} has pending payouts, rejecting new payout"
            )
            raise PendingPayoutException(restaurant_id)

        available_balance = await self.ledger_repo.get_available_balance_with_lock(
            restaurant_id, currency
        )
        logger.info(
            f"Restaurant {restaurant_id} available balance (locked): {available_balance} cents"
        )

        if available_balance < self.MIN_PAYOUT_AMOUNT:
            logger.warning(
                f"Restaurant {restaurant_id} insufficient balance: {available_balance} < {self.MIN_PAYOUT_AMOUNT}"
            )
            raise InsufficientBalanceException(
                restaurant_id, available_balance, self.MIN_PAYOUT_AMOUNT
            )

        payout = await self.payout_repo.create_payout(
            restaurant_id=restaurant_id,
            amount_cents=available_balance,
            currency=currency,
        )

        await self.ledger_service.create_payout_entry(
            restaurant_id=restaurant_id,
            payout_id=payout.id,
            amount_cents=available_balance,
            currency=currency,
        )

        payouts_total.labels(status="pending").inc()
        new_balance = await self.ledger_repo.get_available_balance(
            restaurant_id, currency
        )
        balance_total.set(new_balance)

        logger.info(
            f"Payout {payout.id} created successfully for restaurant {restaurant_id}: {available_balance} cents"
        )

        return payout.id
