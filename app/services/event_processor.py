import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EventType
from app.db.models import ProcessorEvent
from app.db.repositories import EventRepository, PayoutRepository, RestaurantRepository
from app.metrics import balance_total, events_total
from app.schemas.events import ProcessorEventCreate
from app.core.enums import PayoutStatus
from app.services.ledger_service import LedgerService

logger = logging.getLogger(__name__)


class EventProcessor:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.event_repo = EventRepository(session)
        self.restaurant_repo = RestaurantRepository(session)
        self.ledger_service = LedgerService(session)

    def _event_type_value(self, event: ProcessorEvent) -> str:
        event_type = event.event_type
        return event_type.value if hasattr(event_type, "value") else str(event_type)

    async def process_event(
        self, event_data: ProcessorEventCreate
    ) -> tuple[ProcessorEvent, bool]:
        await self.restaurant_repo.get_or_create(
            restaurant_id=event_data.restaurant_id, name=event_data.restaurant_id
        )

        event, is_new = await self.event_repo.create_event(
            event_id=event_data.event_id,
            event_type=event_data.event_type,
            occurred_at=event_data.occurred_at,
            restaurant_id=event_data.restaurant_id,
            currency=event_data.currency,
            amount_cents=event_data.amount_cents,
            fee_cents=event_data.fee_cents,
            metadata_=event_data.metadata,
        )

        event_type_value = self._event_type_value(event)

        if is_new:
            logger.info(
                "Processing new event event_id=%s event_type=%s restaurant_id=%s",
                event.event_id,
                event_type_value,
                event.restaurant_id,
                extra={
                    "event_id": event.event_id,
                    "restaurant_id": event.restaurant_id,
                    "event_type": event_type_value,
                },
            )
            events_total.labels(event_type=event_type_value).inc()
            if event.event_type == EventType.CHARGE_SUCCEEDED:
                await self.ledger_service.create_sale_entries(
                    restaurant_id=event.restaurant_id,
                    event_id=event.event_id,
                    amount_cents=event.amount_cents,
                    fee_cents=event.fee_cents,
                    occurred_at=event.occurred_at,
                    currency=event.currency,
                )
            elif event.event_type == EventType.REFUND_SUCCEEDED:
                await self.ledger_service.create_refund_entry(
                    restaurant_id=event.restaurant_id,
                    event_id=event.event_id,
                    amount_cents=event.amount_cents,
                    currency=event.currency,
                )
            elif event.event_type == EventType.PAYOUT_PAID:
                await self._process_payout_paid(event)

            total_balance = await self.ledger_service.ledger_repo.get_total_balance(
                currency=event.currency
            )
            balance_total.set(total_balance)
        else:
            logger.info(
                "Idempotent event received event_id=%s restaurant_id=%s",
                event.event_id,
                event.restaurant_id,
                extra={
                    "event_id": event.event_id,
                    "restaurant_id": event.restaurant_id,
                    "event_type": event_type_value,
                },
            )

        return event, is_new

    async def _process_payout_paid(self, event: ProcessorEvent) -> None:

        payout_repo = PayoutRepository(self.session)
        payout_id = event.metadata_.get("payout_id") if event.metadata_ else None

        if not payout_id:
            logger.warning(
                "payout_paid missing payout_id in metadata event_id=%s restaurant_id=%s",
                event.event_id,
                event.restaurant_id,
                extra={
                    "event_id": event.event_id,
                    "restaurant_id": event.restaurant_id,
                    "event_type": self._event_type_value(event),
                },
            )
            return

        payout = await payout_repo.get_by_id(payout_id)
        if not payout:
            logger.warning(
                "payout_paid references non-existent payout event_id=%s restaurant_id=%s payout_id=%s",
                event.event_id,
                event.restaurant_id,
                payout_id,
                extra={
                    "event_id": event.event_id,
                    "restaurant_id": event.restaurant_id,
                    "event_type": self._event_type_value(event),
                    "payout_id": payout_id,
                },
            )
            return

        await payout_repo.update_status(payout, PayoutStatus.PAID)
        logger.info(
            "Payout marked as paid payout_id=%s from event_id=%s restaurant_id=%s",
            payout_id,
            event.event_id,
            event.restaurant_id,
            extra={
                "event_id": event.event_id,
                "restaurant_id": event.restaurant_id,
                "event_type": self._event_type_value(event),
                "payout_id": payout_id,
            },
        )
