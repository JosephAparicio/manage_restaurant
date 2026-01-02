from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EventType
from app.db.models import ProcessorEvent


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_event(
        self,
        event_id: str,
        event_type: EventType,
        occurred_at: datetime,
        restaurant_id: str,
        currency: str,
        amount_cents: int,
        fee_cents: int,
        metadata_: Optional[dict] = None,
    ) -> tuple[ProcessorEvent, bool]:
        """Create a new event or return existing one if duplicate.

        Args:
            event_id: Unique identifier for the event.
            event_type: Type of event (charge_succeeded, refund_succeeded, payout_paid).
            occurred_at: When the event occurred (timezone-aware).
            restaurant_id: Restaurant identifier.
            currency: Currency code (e.g., 'usd').
            amount_cents: Amount in cents.
            fee_cents: Fee amount in cents.
            metadata_: Optional metadata dictionary.

        Returns:
            Tuple of (ProcessorEvent instance, is_new flag).
            is_new=True if event was created, False if already existed.
        """
        stmt = select(ProcessorEvent).where(ProcessorEvent.event_id == event_id)
        result = await self.session.execute(stmt)
        existing_event = result.scalar_one_or_none()

        if existing_event:
            return existing_event, False

        event = ProcessorEvent(
            event_id=event_id,
            event_type=event_type,
            occurred_at=occurred_at,
            restaurant_id=restaurant_id,
            currency=currency,
            amount_cents=amount_cents,
            fee_cents=fee_cents,
            metadata_=metadata_,
        )
        self.session.add(event)
        await self.session.flush()
        return event, True

    async def get_by_event_id(self, event_id: str) -> Optional[ProcessorEvent]:
        stmt = select(ProcessorEvent).where(ProcessorEvent.event_id == event_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, id: int) -> Optional[ProcessorEvent]:
        stmt = select(ProcessorEvent).where(ProcessorEvent.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
