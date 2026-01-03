import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date

from app.db.session import AsyncSessionLocal
from app.db.models import LedgerEntry


@pytest.mark.asyncio
class TestSQLQueries:
    async def test_q1_restaurant_balances(
        self,
        client,
        sample_charge_event_data: dict,
    ) -> None:
        await client.post("/v1/processor/events", json=sample_charge_event_data)

        async with AsyncSessionLocal() as session:
            query = text(
                """
                SELECT 
                    le.restaurant_id,
                    SUM(le.amount_cents) AS available,
                    MAX(pe.occurred_at) AS last_event_at
                FROM ledger_entries le
                LEFT JOIN processor_events pe
                    ON pe.event_id = le.related_event_id
                WHERE le.currency = :currency
                GROUP BY le.restaurant_id
                ORDER BY available DESC
            """
            )

            result = await session.execute(query, {"currency": "PEN"})
            rows = result.fetchall()

            assert len(rows) > 0, "Should have at least one restaurant with balance"

            first_row = rows[0]
            assert first_row.restaurant_id == sample_charge_event_data["restaurant_id"]
            assert first_row.available == 9750  # 10000 - 250 commission
            assert first_row.last_event_at is not None

    async def test_q2_top_restaurants_revenue(
        self,
        client,
        sample_charge_event_data: dict,
    ) -> None:
        event1 = sample_charge_event_data.copy()
        event1["event_id"] = "evt_q2_001"
        event1["amount_cents"] = 50000
        event1["fee_cents"] = 1250
        await client.post("/v1/processor/events", json=event1)

        event2 = sample_charge_event_data.copy()
        event2["event_id"] = "evt_q2_002"
        event2["restaurant_id"] = "res_q2_002"
        event2["amount_cents"] = 30000
        event2["fee_cents"] = 750
        await client.post("/v1/processor/events", json=event2)

        async with AsyncSessionLocal() as session:
            query = text(
                """
                SELECT 
                    restaurant_id,
                    currency,
                    SUM(CASE
                        WHEN entry_type IN ('sale', 'commission', 'refund') THEN amount_cents
                        ELSE 0
                    END) AS net_amount,
                    COUNT(*) FILTER (WHERE entry_type = 'sale') AS charge_count,
                    COUNT(*) FILTER (WHERE entry_type = 'refund') AS refund_count
                FROM ledger_entries
                WHERE created_at >= NOW() - INTERVAL '7 days'
                  AND entry_type IN ('sale', 'commission', 'refund')
                GROUP BY restaurant_id, currency
                HAVING SUM(CASE
                    WHEN entry_type IN ('sale', 'commission', 'refund') THEN amount_cents
                    ELSE 0
                END) > 0
                ORDER BY net_amount DESC
                LIMIT 10
            """
            )

            result = await session.execute(query)
            rows = result.fetchall()

            assert len(rows) >= 2, "Should have at least 2 restaurants"

            assert rows[0].net_amount > rows[1].net_amount
            assert rows[0].charge_count >= 1

    async def test_q3_payout_eligibility(
        self,
        client,
        sample_charge_event_data: dict,
    ) -> None:
        event = sample_charge_event_data.copy()
        event["event_id"] = "evt_q3_001"
        event["amount_cents"] = 20000
        event["fee_cents"] = 500
        await client.post("/v1/processor/events", json=event)

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(LedgerEntry)
                .where(
                    LedgerEntry.restaurant_id
                    == sample_charge_event_data["restaurant_id"]
                )
                .values(available_at=None)
            )
            await session.commit()

        async with AsyncSessionLocal() as session:
            query = text(
                """
                WITH available_balances AS (
                    SELECT 
                        restaurant_id,
                        currency,
                        SUM(amount_cents) AS available_balance_cents
                    FROM ledger_entries
                    WHERE (available_at IS NULL OR available_at <= NOW())
                    GROUP BY restaurant_id, currency
                    HAVING SUM(amount_cents) >= :min_amount
                )
                SELECT 
                    ab.restaurant_id,
                    ab.currency,
                    ab.available_balance_cents
                FROM available_balances ab
                INNER JOIN restaurants r ON ab.restaurant_id = r.id
                WHERE NOT EXISTS (
                    SELECT 1 
                    FROM payouts p
                    WHERE p.restaurant_id = ab.restaurant_id
                      AND p.currency = ab.currency
                      AND p.status IN ('created', 'processing')
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM payouts p
                    WHERE p.restaurant_id = ab.restaurant_id
                      AND p.currency = ab.currency
                      AND p.as_of = :as_of
                )
                AND r.is_active = TRUE
                ORDER BY ab.available_balance_cents DESC
            """
            )

            result = await session.execute(
                query,
                {
                    "min_amount": 10000,
                    "as_of": date(2025, 12, 27),
                },
            )
            rows = result.fetchall()

            # Validate: Should find eligible restaurant
            assert len(rows) > 0, "Should have at least one eligible restaurant"

            eligible = rows[0]
            assert eligible.restaurant_id == sample_charge_event_data["restaurant_id"]
            assert eligible.available_balance_cents >= 10000

    async def test_q4_data_integrity_checks(
        self,
        client,
        sample_charge_event_data: dict,
    ) -> None:
        await client.post("/v1/processor/events", json=sample_charge_event_data)

        async with AsyncSessionLocal() as session:
            query_duplicates = text(
                """
                SELECT
                    pe.event_id,
                    COUNT(*) AS duplicates
                FROM processor_events pe
                GROUP BY pe.event_id
                HAVING COUNT(*) > 1
            """
            )

            result = await session.execute(query_duplicates)
            rows = result.fetchall()
            assert len(rows) == 0, "Should have no duplicate events"
