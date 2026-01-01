import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EventType
from app.db.models import ProcessorEvent
from app.db.repositories import EventRepository
from app.schemas.events import ProcessorEventCreate
from app.services.ledger_service import LedgerService

logger = logging.getLogger(__name__)


class EventProcessor:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.event_repo = EventRepository(session)
        self.ledger_service = LedgerService(session)

    async def process_event(
        self, event_data: ProcessorEventCreate
    ) -> tuple[ProcessorEvent, bool]:
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

        if is_new:
            logger.info(
                f"Processing new event: {event.event_id} ({event.event_type.value}) for restaurant {event.restaurant_id}"
            )
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
        else:
            logger.info(
                f"Idempotent hit: event {event.event_id} already processed"
            )

        return event, is_new
