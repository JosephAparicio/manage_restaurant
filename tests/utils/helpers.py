import asyncio
from typing import List

from httpx import AsyncClient


async def process_events_batch(
    client: AsyncClient,
    events: List[dict],
) -> List[dict]:
    """Process multiple events and return their responses."""
    responses = []
    for event in events:
        response = await client.post("/v1/processor/events", json=event)
        responses.append(response.json())
    return responses


async def process_events_concurrent(
    client: AsyncClient,
    events: List[dict],
) -> List[dict]:
    """Process multiple events concurrently."""
    tasks = [client.post("/v1/processor/events", json=event) for event in events]
    responses = await asyncio.gather(*tasks)
    return [r.json() for r in responses]


def calculate_net_amount(amount_cents: int, fee_cents: int) -> int:
    """Calculate net amount after fee deduction."""
    return amount_cents - fee_cents


def format_currency(amount_cents: int, currency: str = "PEN") -> str:
    """Format cents to currency string."""
    amount = amount_cents / 100
    return f"{currency} {amount:.2f}"
