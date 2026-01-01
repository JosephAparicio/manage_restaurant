from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class RestaurantBalance(BaseModel):
    restaurant_id: str
    currency: str
    available_cents: int
    pending_cents: int
    total_cents: int
    last_event_at: Optional[datetime] = None
    meta: dict = Field(
        default_factory=lambda: {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": str(uuid4()),
        }
    )
