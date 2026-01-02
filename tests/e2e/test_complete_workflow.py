import asyncio
import pytest
from datetime import datetime, timezone

from httpx import AsyncClient
from tests.utils import EventFactory


@pytest.mark.e2e
class TestCompleteWorkflow:
    async def test_complete_restaurant_lifecycle(
        self,
        client: AsyncClient,
    ) -> None:
        restaurant_id = "res_e2e_001"
        
        # Step 1: Process multiple charge events
        charge1 = EventFactory.create_mature_charge_event(
            restaurant_id=restaurant_id,
            event_id="evt_e2e_001",
            amount_cents=20000,
            fee_cents=500,
            days_ago=10,
        )
        charge2 = EventFactory.create_mature_charge_event(
            restaurant_id=restaurant_id,
            event_id="evt_e2e_002",
            amount_cents=15000,
            fee_cents=375,
            days_ago=8,
        )
        
        response1 = await client.post("/v1/processor/events", json=charge1)
        response2 = await client.post("/v1/processor/events", json=charge2)
        
        assert response1.status_code == 201
        assert response2.status_code == 201
        
        # Step 2: Check balance after charges
        balance_response = await client.get(
            f"/v1/restaurants/{restaurant_id}/balance?currency=PEN"
        )
        balance_data = balance_response.json()
        
        expected_balance = (20000 - 500) + (15000 - 375)
        assert balance_data["available_cents"] == expected_balance
        assert balance_data["pending_cents"] == 0
        
        # Step 3: Process a refund
        refund = EventFactory.create_refund_event(
            restaurant_id=restaurant_id,
            event_id="evt_e2e_refund",
            amount_cents=5000,
        )
        
        refund_response = await client.post("/v1/processor/events", json=refund)
        assert refund_response.status_code == 201
        
        # Step 4: Check balance after refund
        balance_after_refund = await client.get(
            f"/v1/restaurants/{restaurant_id}/balance?currency=PEN"
        )
        balance_data_refund = balance_after_refund.json()
        
        assert balance_data_refund["available_cents"] == expected_balance - 5000
        
        # Step 5: Request payout
        payout_data = {
            "restaurant_id": restaurant_id,
            "currency": "PEN",
        }
        
        payout_response = await client.post("/v1/payouts/run", json=payout_data)
        assert payout_response.status_code == 202
        
        # Wait for background task
        await asyncio.sleep(0.5)
        
        # Step 6: Verify final balance is zero
        final_balance = await client.get(
            f"/v1/restaurants/{restaurant_id}/balance?currency=PEN"
        )
        final_data = final_balance.json()
        
        assert final_data["available_cents"] <= 0

    async def test_multi_restaurant_isolation(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that multiple restaurants' data is properly isolated."""
        restaurant1 = "res_e2e_multi_1"
        restaurant2 = "res_e2e_multi_2"
        
        # Create events for both restaurants
        event1 = EventFactory.create_mature_charge_event(
            restaurant_id=restaurant1,
            event_id="evt_multi_1",
            amount_cents=10000,
            fee_cents=250,
        )
        
        event2 = EventFactory.create_mature_charge_event(
            restaurant_id=restaurant2,
            event_id="evt_multi_2",
            amount_cents=20000,
            fee_cents=500,
        )
        
        await client.post("/v1/processor/events", json=event1)
        await client.post("/v1/processor/events", json=event2)
        
        # Check balances are independent
        balance1 = await client.get(f"/v1/restaurants/{restaurant1}/balance")
        balance2 = await client.get(f"/v1/restaurants/{restaurant2}/balance")
        
        assert balance1.json()["available_cents"] == 9750
        assert balance2.json()["available_cents"] == 19500

    async def test_multi_currency_workflow(
        self,
        client: AsyncClient,
    ) -> None:
        """Test workflow with multiple currencies."""
        restaurant_id = "res_e2e_currency"
        
        # Process PEN and USD events
        pen_event = EventFactory.create_mature_charge_event(
            restaurant_id=restaurant_id,
            event_id="evt_currency_pen",
            amount_cents=10000,
            fee_cents=250,
            currency="PEN",
        )
        
        usd_event = EventFactory.create_mature_charge_event(
            restaurant_id=restaurant_id,
            event_id="evt_currency_usd",
            amount_cents=5000,
            fee_cents=150,
            currency="USD",
        )
        
        await client.post("/v1/processor/events", json=pen_event)
        await client.post("/v1/processor/events", json=usd_event)
        
        # Check balances for each currency
        pen_balance = await client.get(
            f"/v1/restaurants/{restaurant_id}/balance?currency=PEN"
        )
        usd_balance = await client.get(
            f"/v1/restaurants/{restaurant_id}/balance?currency=USD"
        )
        
        assert pen_balance.json()["available_cents"] == 9750
        assert usd_balance.json()["available_cents"] == 4850
        assert pen_balance.json()["currency"] == "PEN"
        assert usd_balance.json()["currency"] == "USD"
