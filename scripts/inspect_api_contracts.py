import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx


def _pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)


async def _request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    json_body: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
) -> None:
    url = f"{client.base_url}{path}"
    print("\n" + "=" * 80)
    print(f"{method} {url}")

    if params:
        print("\nQuery params:")
        print(_pretty(params))

    if json_body is not None:
        print("\nRequest JSON:")
        print(_pretty(json_body))

    response = await client.request(method, path, json=json_body, params=params)

    print(f"\nStatus: {response.status_code}")
    content_type = response.headers.get("content-type", "")
    print(f"Content-Type: {content_type}")

    if "application/json" in content_type:
        try:
            print("\nResponse JSON:")
            print(_pretty(response.json()))
        except Exception:
            print("\nResponse (raw):")
            print(response.text)
    else:
        print("\nResponse (raw):")
        text = response.text
        print(text[:4000] + ("\n... (truncated)" if len(text) > 4000 else ""))


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect request/response payloads for the API endpoints"
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--restaurant-id",
        type=str,
        default="res_001",
        help="Restaurant id to use for balance and events (default: res_001)",
    )
    parser.add_argument(
        "--currency",
        type=str,
        default="PEN",
        help="Currency code (default: PEN)",
    )
    parser.add_argument(
        "--amount-cents",
        type=int,
        default=12000,
        help="Charge amount in cents (default: 12000)",
    )
    parser.add_argument(
        "--fee-cents",
        type=int,
        default=600,
        help="Fee amount in cents (default: 600)",
    )
    parser.add_argument(
        "--min-amount",
        type=int,
        default=5000,
        help="Minimum payout amount in cents (default: 5000)",
    )
    parser.add_argument(
        "--event-occurred-days-ago",
        type=int,
        default=10,
        help="How many days in the past to set occurred_at (default: 10). Useful to pass maturity window.",
    )

    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    occurred_at_dt = datetime.now(timezone.utc) - timedelta(
        days=args.event_occurred_days_ago
    )
    occurred_at = (
        occurred_at_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )

    event_id = f"evt_inspect_{int(datetime.now(timezone.utc).timestamp())}"

    charge_event = {
        "event_id": event_id,
        "event_type": "charge_succeeded",
        "occurred_at": occurred_at,
        "restaurant_id": args.restaurant_id,
        "currency": args.currency,
        "amount_cents": args.amount_cents,
        "fee_cents": args.fee_cents,
        "metadata": {"reservation_id": "rsv_987", "payment_id": "pay_456"},
    }

    payout_as_of = datetime.now(timezone.utc).date().isoformat()
    payout_run = {
        "currency": args.currency,
        "as_of": payout_as_of,
        "min_amount": args.min_amount,
    }

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        await _request(client, "GET", "/health")
        await _request(client, "GET", "/metrics")

        await _request(client, "POST", "/v1/processor/events", json_body=charge_event)
        await _request(client, "POST", "/v1/processor/events", json_body=charge_event)

        await _request(
            client,
            "GET",
            f"/v1/restaurants/{args.restaurant_id}/balance",
            params={"currency": args.currency},
        )

        await _request(client, "POST", "/v1/payouts/run", json_body=payout_run)

        print(
            "\n" + "=" * 80 + "\n"
            "Note: /v1/payouts/run executes asynchronously and returns 202 immediately. "
            "This script does not attempt to fetch a payout id."
        )


if __name__ == "__main__":
    asyncio.run(main())
