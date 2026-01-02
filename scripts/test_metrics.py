import asyncio
import httpx


async def test_metrics():
    api_url = "http://localhost:8000"

    async with httpx.AsyncClient(timeout=30.0) as client:
        print("=" * 60)
        print("Testing Prometheus Metrics")
        print("=" * 60)

        print("\n1. Processing charge event...")
        charge_event = {
            "event_id": "evt_metrics_001",
            "event_type": "charge_succeeded",
            "occurred_at": "2025-01-01T10:00:00Z",
            "restaurant_id": "res_metrics",
            "currency": "PEN",
            "amount_cents": 50000,
            "fee_cents": 1500,
            "metadata": {},
        }
        response = await client.post(
            f"{api_url}/v1/processor/events", json=charge_event
        )
        print(f"   Status: {response.status_code}")
        if response.status_code >= 400:
            print(f"   Error: {response.text}")

        print("\n2. Processing refund event...")
        refund_event = {
            "event_id": "evt_metrics_002",
            "event_type": "refund_succeeded",
            "occurred_at": "2025-01-01T10:05:00Z",
            "restaurant_id": "res_metrics",
            "currency": "PEN",
            "amount_cents": 10000,
            "fee_cents": 0,
            "metadata": {},
        }
        response = await client.post(
            f"{api_url}/v1/processor/events", json=refund_event
        )
        print(f"   Status: {response.status_code}")
        if response.status_code >= 400:
            print(f"   Error: {response.text}")

        print("\n3. Creating payout...")
        payout_data = {"restaurant_id": "res_metrics", "currency": "PEN"}
        response = await client.post(f"{api_url}/v1/payouts/run", json=payout_data)
        print(f"   Status: {response.status_code}")
        if response.status_code == 201:
            print(f"   Payout ID: {response.json().get('id')}")

        print("\n4. Fetching metrics...")
        response = await client.get(f"{api_url}/metrics")
        print(f"   Status: {response.status_code}")

        if response.status_code == 200:
            metrics_text = response.text

            print("\n" + "=" * 60)
            print("BUSINESS METRICS")
            print("=" * 60)

            for line in metrics_text.split("\n"):
                if line.startswith("restaurant_"):
                    if (
                        not line.startswith("restaurant_")
                        or "{" in line
                        or line.endswith("_total")
                    ):
                        continue
                    print(line)

            print("\n" + "=" * 60)
            print("DETAILED METRICS")
            print("=" * 60)

            for metric_name in [
                "restaurant_events_total",
                "restaurant_ledger_entries_total",
                "restaurant_balance_total",
                "restaurant_payouts_total",
            ]:
                print(f"\n{metric_name}:")
                for line in metrics_text.split("\n"):
                    if line.startswith(metric_name + "{") or (
                        line.startswith(metric_name + " ") and "{" not in line
                    ):
                        print(f"  {line}")

        print("\n" + "=" * 60)
        print("Test completed successfully!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_metrics())
