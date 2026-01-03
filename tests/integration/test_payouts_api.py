import asyncio
from datetime import date, datetime, timezone, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.db.models import Payout
from app.db.repositories import PayoutRepository


@pytest.mark.integration
class TestPayoutsAPI:
    async def test_run_payouts_success(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
        db_session: AsyncSession,
    ) -> None:
        # Create a matured charge event to ensure restaurant exists and has available funds
        event_data = {
            "event_id": "evt_payout_batch_001",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 15000,
            "fee_cents": 250,
            "occurred_at": (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat(),
            "currency": "PEN",
        }
        await client.post("/v1/processor/events", json=event_data)

        payout_data = {
            "currency": "PEN",
            "as_of": date(2025, 12, 27).isoformat(),
            "min_amount": 10000,
        }

        response = await client.post("/v1/payouts/run", json=payout_data)

        assert response.status_code == 202
        data = response.json()

        assert data["message"] == "Payout process initiated"
        assert data["currency"] == "PEN"
        assert data["as_of"] == date(2025, 12, 27).isoformat()
        assert data["min_amount"] == 10000

        # Wait for background task to complete
        await asyncio.sleep(0.5)

        # Validate at least one payout was created for the restaurant
        payout_repo = PayoutRepository(db_session)
        assert await payout_repo.exists_for_as_of(
            restaurant_id=sample_restaurant_id,
            currency="PEN",
            as_of=date(2025, 12, 27),
        )

        stmt = select(func.count(Payout.id)).where(
            Payout.restaurant_id == sample_restaurant_id,
            Payout.currency == "PEN",
            Payout.as_of == date(2025, 12, 27),
        )
        result = await db_session.execute(stmt)
        assert (result.scalar() or 0) >= 1

    async def test_get_payout_success(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
        db_session: AsyncSession,
    ) -> None:
        event_data = {
            "event_id": "evt_payout_get_001",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 10000,
            "fee_cents": 0,
            "occurred_at": (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat(),
            "currency": "PEN",
        }
        await client.post("/v1/processor/events", json=event_data)

        payout_repo = PayoutRepository(db_session)
        payout = await payout_repo.create_payout(
            restaurant_id=sample_restaurant_id,
            amount_cents=10000,
            currency="PEN",
        )
        await payout_repo.create_items(
            payout_id=payout.id,
            items=[("net_sales", 10000), ("fees", 0)],
        )
        await db_session.commit()

        response = await client.get(f"/v1/payouts/{payout.id}")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == payout.id
        assert data["restaurant_id"] == sample_restaurant_id
        assert data["amount_cents"] == 10000
        assert data["currency"] == "PEN"
        assert data["status"] == "created"
        assert "items" in data
        assert len(data["items"]) == 2

    async def test_get_payout_not_found(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.get("/v1/payouts/999999")

        assert response.status_code == 404

    async def test_payout_flow_end_to_end(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
    ) -> None:
        event_data = {
            "event_id": "evt_payout_flow",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 15000,
            "fee_cents": 250,
            "occurred_at": (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat(),
            "currency": "PEN",
        }

        await client.post("/v1/processor/events", json=event_data)

        balance_response = await client.get(
            f"/v1/restaurants/{sample_restaurant_id}/balance"
        )
        assert balance_response.json()["available_cents"] == 14750

        payout_data = {
            "currency": "PEN",
            "as_of": date(2025, 12, 27).isoformat(),
            "min_amount": 5000,
        }

        payout_response = await client.post("/v1/payouts/run", json=payout_data)
        assert payout_response.status_code == 202

        await asyncio.sleep(0.5)

        final_balance = await client.get(
            f"/v1/restaurants/{sample_restaurant_id}/balance"
        )
        final_data = final_balance.json()

        assert final_data["available_cents"] <= 0

    async def test_payout_insufficient_balance(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
        db_session: AsyncSession,
    ) -> None:
        event_data = {
            "event_id": "evt_payout_low_001",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 5000,
            "fee_cents": 0,
            "occurred_at": (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat(),
            "currency": "PEN",
        }
        await client.post("/v1/processor/events", json=event_data)

        payout_data = {
            "currency": "PEN",
            "as_of": date(2025, 12, 27).isoformat(),
            "min_amount": 10000,
        }

        response = await client.post("/v1/payouts/run", json=payout_data)

        assert response.status_code == 202

        await asyncio.sleep(0.5)

    async def test_payout_with_pending_payout(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
        db_session: AsyncSession,
    ) -> None:
        event_data = {
            "event_id": "evt_payout_pending_001",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 20000,
            "fee_cents": 0,
            "occurred_at": (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat(),
            "currency": "PEN",
        }
        await client.post("/v1/processor/events", json=event_data)

        payout_repo = PayoutRepository(db_session)
        await payout_repo.create_payout(
            restaurant_id=sample_restaurant_id,
            amount_cents=10000,
            currency="PEN",
            as_of=date(2025, 12, 27),
        )
        await db_session.commit()

        payout_data = {
            "currency": "PEN",
            "as_of": date(2025, 12, 27).isoformat(),
            "min_amount": 5000,
        }

        response = await client.post("/v1/payouts/run", json=payout_data)

        assert response.status_code == 202

    @pytest.mark.concurrency
    async def test_concurrent_payout_generation(
        self,
        client: AsyncClient,
        sample_restaurant_id: str,
        db_session: AsyncSession,
    ) -> None:
        event_data = {
            "event_id": "evt_payout_concurrent_001",
            "event_type": "charge_succeeded",
            "restaurant_id": sample_restaurant_id,
            "amount_cents": 50000,
            "fee_cents": 0,
            "occurred_at": (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat(),
            "currency": "PEN",
        }
        await client.post("/v1/processor/events", json=event_data)

        payout_data = {
            "currency": "PEN",
            "as_of": date(2025, 12, 27).isoformat(),
            "min_amount": 10000,
        }

        responses = await asyncio.gather(
            client.post("/v1/payouts/run", json=payout_data),
            client.post("/v1/payouts/run", json=payout_data),
            client.post("/v1/payouts/run", json=payout_data),
        )

        assert all(r.status_code == 202 for r in responses)

        await asyncio.sleep(1)
