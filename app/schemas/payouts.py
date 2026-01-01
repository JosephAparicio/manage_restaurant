from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import PayoutStatus


class PayoutCreate(BaseModel):
    restaurant_id: str = Field(..., pattern=r"^res_")
    currency: str = Field(default="PEN", pattern=r"^[A-Z]{3}$")


class PayoutResponse(BaseModel):
    id: int
    restaurant_id: str
    amount_cents: int
    currency: str
    status: PayoutStatus
    created_at: datetime
    paid_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    meta: dict = Field(
        default_factory=lambda: {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": str(uuid4()),
        }
    )

    model_config = ConfigDict(from_attributes=True)


class PayoutGenerateResponse(BaseModel):
    message: str
    payouts_created: int
