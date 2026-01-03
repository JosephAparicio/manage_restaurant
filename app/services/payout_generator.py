import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EntryType
from app.db.models import LedgerEntry
from app.db.repositories import LedgerRepository, PayoutRepository, RestaurantRepository
from app.exceptions import InsufficientBalanceException, PendingPayoutException
from app.metrics import balance_total, payouts_total
from app.schemas.payouts import PayoutCreate, PayoutRunRequest
from app.services.ledger_service import LedgerService

logger = logging.getLogger(__name__)


class PayoutGenerator:
    MIN_PAYOUT_AMOUNT = 10000  # 100.00 PEN - minimum to cover processing costs

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.payout_repo = PayoutRepository(session)
        self.ledger_repo = LedgerRepository(session)
        self.restaurant_repo = RestaurantRepository(session)
        self.ledger_service = LedgerService(session)

    async def generate_payouts_batch(self, payout_data: PayoutRunRequest) -> int:
        """Generate payouts for all restaurants for a given currency.

        PDF behavior:
        - For each restaurant in currency, if available >= min_amount: create payout (status=created)
          and write a ledger debit entry to reserve funds.
        - Runs inside a DB transaction (caller responsibility) so locks + inserts are atomic.

        Returns number of payouts created.
        """
        currency = payout_data.currency
        as_of = payout_data.as_of
        min_amount = payout_data.min_amount

        restaurant_ids = await self.restaurant_repo.list_active_restaurant_ids()
        payouts_created = 0

        for restaurant_id in restaurant_ids:
            # Skip restaurants that already have an active payout or already ran for this as_of
            has_pending = await self.payout_repo.has_pending_payouts(
                restaurant_id, currency
            )
            if has_pending:
                continue

            already_ran = await self.payout_repo.exists_for_as_of(
                restaurant_id=restaurant_id,
                currency=currency,
                as_of=as_of,
            )
            if already_ran:
                continue

            available_balance = await self.ledger_repo.get_available_balance_with_lock(
                restaurant_id, currency
            )

            if available_balance < min_amount:
                continue

            payout = await self.payout_repo.create_payout(
                restaurant_id=restaurant_id,
                amount_cents=available_balance,
                currency=currency,
                as_of=as_of,
            )

            breakdown = await self._get_breakdown_items(restaurant_id, currency)
            await self.payout_repo.create_items(payout_id=payout.id, items=breakdown)

            await self.ledger_service.create_payout_entry(
                restaurant_id=restaurant_id,
                payout_id=payout.id,
                amount_cents=available_balance,
                currency=currency,
            )

            payouts_total.labels(status="created").inc()
            payouts_created += 1

        return payouts_created

    async def generate_payout(self, payout_data: PayoutCreate) -> int:
        """Must be called within transaction context (uses SELECT FOR UPDATE)."""
        restaurant_id = payout_data.restaurant_id
        currency = payout_data.currency

        logger.info(
            "Starting payout generation restaurant_id=%s currency=%s",
            restaurant_id,
            currency,
            extra={"restaurant_id": restaurant_id, "currency": currency},
        )

        has_pending = await self.payout_repo.has_pending_payouts(
            restaurant_id, currency
        )
        if has_pending:
            logger.warning(
                "Pending payouts exist, rejecting new payout restaurant_id=%s currency=%s",
                restaurant_id,
                currency,
                extra={"restaurant_id": restaurant_id, "currency": currency},
            )
            raise PendingPayoutException(restaurant_id)

        available_balance = await self.ledger_repo.get_available_balance_with_lock(
            restaurant_id, currency
        )
        logger.info(
            "Available balance locked restaurant_id=%s currency=%s available_cents=%s",
            restaurant_id,
            currency,
            available_balance,
            extra={
                "restaurant_id": restaurant_id,
                "currency": currency,
                "available_cents": available_balance,
            },
        )

        if available_balance < self.MIN_PAYOUT_AMOUNT:
            logger.warning(
                "Insufficient balance for payout restaurant_id=%s currency=%s available_cents=%s min_cents=%s",
                restaurant_id,
                currency,
                available_balance,
                self.MIN_PAYOUT_AMOUNT,
                extra={
                    "restaurant_id": restaurant_id,
                    "currency": currency,
                    "available_cents": available_balance,
                    "min_cents": self.MIN_PAYOUT_AMOUNT,
                },
            )
            raise InsufficientBalanceException(
                restaurant_id, available_balance, self.MIN_PAYOUT_AMOUNT
            )

        payout = await self.payout_repo.create_payout(
            restaurant_id=restaurant_id,
            amount_cents=available_balance,
            currency=currency,
        )

        breakdown = await self._get_breakdown_items(restaurant_id, currency)
        await self.payout_repo.create_items(payout_id=payout.id, items=breakdown)

        await self.ledger_service.create_payout_entry(
            restaurant_id=restaurant_id,
            payout_id=payout.id,
            amount_cents=available_balance,
            currency=currency,
        )

        payouts_total.labels(status="created").inc()
        total_balance = await self.ledger_repo.get_total_balance(currency=currency)
        balance_total.set(total_balance)

        logger.info(
            "Payout created payout_id=%s restaurant_id=%s currency=%s amount_cents=%s",
            payout.id,
            restaurant_id,
            currency,
            available_balance,
            extra={
                "payout_id": payout.id,
                "restaurant_id": restaurant_id,
                "currency": currency,
                "amount_cents": available_balance,
            },
        )

        return payout.id

    async def _get_breakdown_items(
        self, restaurant_id: str, currency: str
    ) -> list[tuple[str, int]]:
        stmt = (
            select(
                LedgerEntry.entry_type,
                func.coalesce(func.sum(LedgerEntry.amount_cents), 0).label("amount"),
            )
            .where(LedgerEntry.restaurant_id == restaurant_id)
            .where(LedgerEntry.currency == currency)
            .where(
                (LedgerEntry.available_at.is_(None))
                | (LedgerEntry.available_at <= func.now())
            )
            .where(
                LedgerEntry.entry_type.in_(
                    [EntryType.SALE, EntryType.COMMISSION, EntryType.REFUND]
                )
            )
            .group_by(LedgerEntry.entry_type)
        )

        result = await self.session.execute(stmt)
        totals = {row.entry_type: int(row.amount) for row in result.fetchall()}

        items: list[tuple[str, int]] = []
        if EntryType.SALE in totals and totals[EntryType.SALE] != 0:
            items.append(("net_sales", totals[EntryType.SALE]))
        if EntryType.COMMISSION in totals and totals[EntryType.COMMISSION] != 0:
            items.append(("fees", totals[EntryType.COMMISSION]))
        if EntryType.REFUND in totals and totals[EntryType.REFUND] != 0:
            items.append(("refunds", totals[EntryType.REFUND]))

        return items
