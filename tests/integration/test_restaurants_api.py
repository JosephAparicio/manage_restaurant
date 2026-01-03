from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestRestaurantsAPI:
    async def test_get_balance_empty(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
    ) -> None:
        response = await client.get(f"/v1/restaurants/{sample_restaurant_id}/balance")

        assert response.status_code == 200
        data = response.json()

        assert data["restaurant_id"] == sample_restaurant_id
        assert data["currency"] == "PEN"
        assert data["available_cents"] == 0
        assert data["pending_cents"] == 0
        assert data["total_cents"] == 0

    async def test_get_balance_with_charge(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
    ) -> None:
        event_data = {
            "event_id": "evt_balance_001",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 10000,
            "fee_cents": 250,
            "occurred_at": (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat(),
            "currency": "PEN",
        }

        await client.post("/v1/processor/events", json=event_data)

        response = await client.get(f"/v1/restaurants/{sample_restaurant_id}/balance")

        assert response.status_code == 200
        data = response.json()

        assert data["available_cents"] == 9750
        assert data["pending_cents"] == 0

    async def test_get_balance_with_pending(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
    ) -> None:
        event_data = {
            "event_id": "evt_balance_pending",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 10000,
            "fee_cents": 250,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "currency": "PEN",
        }

        await client.post("/v1/processor/events", json=event_data)

        response = await client.get(f"/v1/restaurants/{sample_restaurant_id}/balance")

        assert response.status_code == 200
        data = response.json()

        assert data["available_cents"] == -250
        assert data["pending_cents"] == 10000
        assert data["total_cents"] == 9750

    async def test_get_balance_multi_currency(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
    ) -> None:
        pen_event = {
            "event_id": "evt_pen_balance",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 10000,
            "fee_cents": 250,
            "occurred_at": (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat(),
            "currency": "PEN",
        }

        usd_event = {
            "event_id": "evt_usd_balance",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 5000,
            "fee_cents": 150,
            "occurred_at": (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat(),
            "currency": "USD",
        }

        await client.post("/v1/processor/events", json=pen_event)
        await client.post("/v1/processor/events", json=usd_event)

        response_pen = await client.get(
            f"/v1/restaurants/{sample_restaurant_id}/balance?currency=PEN"
        )
        response_usd = await client.get(
            f"/v1/restaurants/{sample_restaurant_id}/balance?currency=USD"
        )

        assert response_pen.status_code == 200
        assert response_usd.status_code == 200

        pen_data = response_pen.json()
        usd_data = response_usd.json()

        assert pen_data["available_cents"] == 9750
        assert usd_data["available_cents"] == 4850

    async def test_get_balance_after_refund(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
    ) -> None:
        charge_event = {
            "event_id": "evt_charge_refund",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 10000,
            "fee_cents": 250,
            "occurred_at": (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat(),
            "currency": "PEN",
        }

        refund_event = {
            "event_id": "evt_refund_balance",
            "event_type": "refund_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 3000,
            "fee_cents": 0,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "currency": "PEN",
        }

        await client.post("/v1/processor/events", json=charge_event)
        await client.post("/v1/processor/events", json=refund_event)

        response = await client.get(f"/v1/restaurants/{sample_restaurant_id}/balance")

        assert response.status_code == 200
        data = response.json()

        assert data["available_cents"] == 6750

    async def test_get_balance_with_last_event_at(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
    ) -> None:
        event_data = {
            "event_id": "evt_last_event",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 10000,
            "fee_cents": 250,
            "occurred_at": (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat(),
            "currency": "PEN",
        }

        await client.post("/v1/processor/events", json=event_data)

        response = await client.get(f"/v1/restaurants/{sample_restaurant_id}/balance")

        assert response.status_code == 200
        data = response.json()

        assert data["last_event_at"] is not None
