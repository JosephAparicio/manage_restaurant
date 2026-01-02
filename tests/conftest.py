import asyncio
import sys
from typing import AsyncGenerator
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.pool import NullPool

from app.main import app
from app.db.session import engine

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(scope="session", autouse=True)
def configure_db_for_tests():
    engine.pool = NullPool(engine.pool._creator)
    yield


@pytest.fixture(scope="function")
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_restaurant_id() -> str:
    return "res_test_001"


@pytest.fixture
def sample_event_id() -> str:
    return "evt_test_001"


@pytest.fixture
def sample_charge_event_data(sample_restaurant_id: str, sample_event_id: str) -> dict:
    return {
        "event_id": sample_event_id,
        "event_type": "charge_succeeded",
        "restaurant_id": sample_restaurant_id,
        "amount_cents": 10000,
        "fee_cents": 250,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "currency": "PEN",
    }


@pytest.fixture
def sample_refund_event_data(sample_restaurant_id: str) -> dict:
    return {
        "event_id": "evt_refund_001",
        "event_type": "refund_succeeded",
        "restaurant_id": sample_restaurant_id,
        "amount_cents": 5000,
        "fee_cents": 0,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "currency": "PEN",
    }


@pytest.fixture
def sample_payout_paid_event_data(sample_restaurant_id: str) -> dict:
    return {
        "event_id": "evt_payout_001",
        "event_type": "payout_paid",
        "restaurant_id": sample_restaurant_id,
        "amount_cents": 8000,
        "fee_cents": 0,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "currency": "PEN",
        "metadata": {"payout_id": 1},
    }


@pytest.fixture
def past_datetime() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=3)


@pytest.fixture
def future_datetime() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=1)
