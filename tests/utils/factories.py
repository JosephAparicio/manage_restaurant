from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import uuid4


class EventFactory:
    @staticmethod
    def create_charge_event(
        restaurant_id: str = "res_test",
        event_id: Optional[str] = None,
        amount_cents: int = 10000,
        fee_cents: int = 250,
        occurred_at: Optional[datetime] = None,
        currency: str = "PEN",
    ) -> dict:
        return {
            "event_id": event_id or f"evt_{uuid4().hex[:8]}",
            "event_type": "charge_succeeded",
            "restaurant_id": restaurant_id,
            "amount_cents": amount_cents,
            "fee_cents": fee_cents,
            "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
            "currency": currency,
        }

    @staticmethod
    def create_refund_event(
        restaurant_id: str = "res_test",
        event_id: Optional[str] = None,
        amount_cents: int = 5000,
        occurred_at: Optional[datetime] = None,
        currency: str = "PEN",
    ) -> dict:
        return {
            "event_id": event_id or f"evt_{uuid4().hex[:8]}",
            "event_type": "refund_succeeded",
            "restaurant_id": restaurant_id,
            "amount_cents": amount_cents,
            "fee_cents": 0,
            "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
            "currency": currency,
        }

    @staticmethod
    def create_payout_paid_event(
        restaurant_id: str = "res_test",
        event_id: Optional[str] = None,
        amount_cents: int = 8000,
        payout_id: int = 1,
        occurred_at: Optional[datetime] = None,
        currency: str = "PEN",
    ) -> dict:
        return {
            "event_id": event_id or f"evt_{uuid4().hex[:8]}",
            "event_type": "payout_paid",
            "restaurant_id": restaurant_id,
            "amount_cents": amount_cents,
            "fee_cents": 0,
            "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
            "currency": currency,
            "metadata": {"payout_id": payout_id},
        }

    @staticmethod
    def create_mature_charge_event(
        restaurant_id: str = "res_test",
        event_id: Optional[str] = None,
        amount_cents: int = 10000,
        fee_cents: int = 250,
        days_ago: int = 10,
        currency: str = "PEN",
    ) -> dict:
        occurred_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return EventFactory.create_charge_event(
            restaurant_id=restaurant_id,
            event_id=event_id,
            amount_cents=amount_cents,
            fee_cents=fee_cents,
            occurred_at=occurred_at,
            currency=currency,
        )


class RestaurantFactory:
    @staticmethod
    def create_restaurant_id(suffix: Optional[str] = None) -> str:
        if suffix:
            return f"res_{suffix}"
        return f"res_{uuid4().hex[:8]}"


class PayoutFactory:
    @staticmethod
    def create_payout_data(
        restaurant_id: str = "res_test",
        currency: str = "PEN",
    ) -> dict:
        return {
            "restaurant_id": restaurant_id,
            "currency": currency,
        }
