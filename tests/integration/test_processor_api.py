import asyncio
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EntryType


@pytest.mark.integration
class TestProcessorEventsAPI:
    async def test_process_charge_event_created(
        self,
        client: AsyncClient,
        sample_charge_event_data: dict,
    ) -> None:
        response = await client.post(
            "/v1/processor/events", json=sample_charge_event_data
        )

        assert response.status_code == 201
        data = response.json()

        assert data["event_id"] == sample_charge_event_data["event_id"]
        assert data["event_type"] == "charge_succeeded"
        assert data["restaurant_id"] == sample_charge_event_data["restaurant_id"]
        assert data["amount_cents"] == 10000
        assert data["fee_cents"] == 250
        assert data["idempotent"] is False

    async def test_process_event_idempotency(
        self,
        client: AsyncClient,
        sample_charge_event_data: dict,
    ) -> None:
        response1 = await client.post(
            "/v1/processor/events", json=sample_charge_event_data
        )
        assert response1.status_code == 201

        response2 = await client.post(
            "/v1/processor/events", json=sample_charge_event_data
        )
        assert response2.status_code == 200

        data2 = response2.json()
        assert data2["idempotent"] is True
        assert data2["event_id"] == sample_charge_event_data["event_id"]

    async def test_process_refund_event(
        self,
        client: AsyncClient,
        sample_refund_event_data: dict,
    ) -> None:
        response = await client.post(
            "/v1/processor/events", json=sample_refund_event_data
        )

        assert response.status_code == 201
        data = response.json()

        assert data["event_type"] == "refund_succeeded"
        assert data["amount_cents"] == 5000
        assert data["fee_cents"] == 0

    async def test_process_payout_paid_event(
        self,
        client: AsyncClient,
        sample_payout_paid_event_data: dict,
    ) -> None:
        response = await client.post(
            "/v1/processor/events", json=sample_payout_paid_event_data
        )

        assert response.status_code == 201
        data = response.json()

        assert data["event_type"] == "payout_paid"
        assert "metadata" in sample_payout_paid_event_data

    async def test_process_event_invalid_data(
        self,
        client: AsyncClient,
    ) -> None:
        invalid_data = {
            "event_id": "evt_invalid",
            "event_type": "invalid_type",
            "restaurant_id": "res_001",
            "amount_cents": -100,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }

        response = await client.post("/v1/processor/events", json=invalid_data)

        assert response.status_code == 422

    async def test_process_event_missing_fields(
        self,
        client: AsyncClient,
    ) -> None:
        incomplete_data = {
            "event_id": "evt_incomplete",
            "event_type": "charge_succeeded",
        }

        response = await client.post("/v1/processor/events", json=incomplete_data)

        assert response.status_code == 422

    async def test_process_event_invalid_restaurant_id(
        self,
        client: AsyncClient,
    ) -> None:
        invalid_data = {
            "event_id": "evt_test_002",
            "event_type": "charge_succeeded",
            "restaurant_id": "invalid_format",
            "amount_cents": 10000,
            "fee_cents": 250,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }

        response = await client.post("/v1/processor/events", json=invalid_data)

        assert response.status_code == 422

    @pytest.mark.idempotency
    async def test_concurrent_event_processing(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
    ) -> None:
        event_data = {
            "event_id": "evt_concurrent",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 10000,
            "fee_cents": 250,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "currency": "PEN",
        }

        responses = await asyncio.gather(
            client.post("/v1/processor/events", json=event_data),
            client.post("/v1/processor/events", json=event_data),
            client.post("/v1/processor/events", json=event_data),
        )

        status_codes = [r.status_code for r in responses]
        assert 201 in status_codes
        assert status_codes.count(201) == 1
        assert all(code in [200, 201] for code in status_codes)

    async def test_process_event_multi_currency(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
    ) -> None:
        pen_event = {
            "event_id": "evt_pen",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 10000,
            "fee_cents": 250,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "currency": "PEN",
        }

        usd_event = {
            "event_id": "evt_usd",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 5000,
            "fee_cents": 150,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "currency": "USD",
        }

        response_pen = await client.post("/v1/processor/events", json=pen_event)
        response_usd = await client.post("/v1/processor/events", json=usd_event)

        assert response_pen.status_code == 201
        assert response_usd.status_code == 201
        assert response_pen.json()["currency"] == "PEN"
        assert response_usd.json()["currency"] == "USD"
