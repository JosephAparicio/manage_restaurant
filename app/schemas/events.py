from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import EventType


class ProcessorEventCreate(BaseModel):
    event_id: str = Field(..., min_length=1, max_length=50)
    event_type: EventType
    occurred_at: datetime
    restaurant_id: str = Field(..., pattern=r"^res_")
    currency: str = Field(default="PEN", pattern=r"^[A-Z]{3}$")
    amount_cents: int = Field(..., ge=0)
    fee_cents: int = Field(default=0, ge=0)
    metadata: Optional[dict] = None


class ProcessorEventResponse(BaseModel):
    id: int
    event_id: str
    event_type: EventType
    occurred_at: datetime
    restaurant_id: str
    currency: str
    amount_cents: int
    fee_cents: int
    created_at: datetime
    idempotent: bool = False
    meta: dict = Field(
        default_factory=lambda: {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": str(uuid4()),
        }
    )

    model_config = ConfigDict(from_attributes=True)
