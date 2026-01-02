import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

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
            query = text("""
                SELECT 
                    restaurant_id,
                    currency,
                    SUM(amount_cents) AS balance_cents,
                    COUNT(*) AS total_entries
                FROM ledger_entries
                GROUP BY restaurant_id, currency
                HAVING SUM(amount_cents) != 0
                ORDER BY balance_cents DESC
            """)
            
            result = await session.execute(query)
            rows = result.fetchall()
            
            assert len(rows) > 0, "Should have at least one restaurant with balance"
            
            first_row = rows[0]
            assert first_row.restaurant_id == sample_charge_event_data["restaurant_id"]
            assert first_row.currency == "PEN"
            assert first_row.balance_cents == 9750  # 10000 - 250 commission
            assert first_row.total_entries == 2  # sale + commission

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
            query = text("""
                WITH recent_revenue AS (
                    SELECT 
                        restaurant_id,
                        currency,
                        SUM(CASE 
                            WHEN entry_type = 'sale' THEN amount_cents
                            WHEN entry_type = 'commission' THEN amount_cents
                            WHEN entry_type = 'refund' THEN amount_cents
                            ELSE 0
                        END) AS net_revenue_cents,
                        COUNT(*) AS transaction_count
                    FROM ledger_entries
                    WHERE created_at >= NOW() - INTERVAL '7 days'
                      AND entry_type IN ('sale', 'commission', 'refund')
                    GROUP BY restaurant_id, currency
                )
                SELECT 
                    restaurant_id,
                    currency,
                    net_revenue_cents,
                    transaction_count,
                    RANK() OVER (ORDER BY net_revenue_cents DESC) AS revenue_rank
                FROM recent_revenue
                WHERE net_revenue_cents > 0
                ORDER BY revenue_rank
                LIMIT 10
            """)
            
            result = await session.execute(query)
            rows = result.fetchall()
            
            assert len(rows) >= 2, "Should have at least 2 restaurants"
            
            assert rows[0].revenue_rank == 1
            assert rows[0].net_revenue_cents > rows[1].net_revenue_cents
            
            for i, row in enumerate(rows):
                assert row.revenue_rank == i + 1

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
                .where(LedgerEntry.restaurant_id == sample_charge_event_data["restaurant_id"])
                .values(available_at=None)
            )
            await session.commit()
        
        async with AsyncSessionLocal() as session:
            query = text("""
                WITH available_balances AS (
                    SELECT 
                        restaurant_id,
                        currency,
                        SUM(amount_cents) AS available_balance_cents
                    FROM ledger_entries
                    WHERE (available_at IS NULL OR available_at <= NOW())
                    GROUP BY restaurant_id, currency
                    HAVING SUM(amount_cents) >= 10000
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
                      AND p.status IN ('created', 'processing')
                )
                AND r.is_active = TRUE
                ORDER BY ab.available_balance_cents DESC
            """)
            
            result = await session.execute(query)
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
            # Q4.1: Check for duplicate event_ids
            query_duplicates = text("""
                WITH duplicate_events AS (
                    SELECT 
                        event_id, 
                        COUNT(*) AS duplicates
                    FROM processor_events
                    GROUP BY event_id
                    HAVING COUNT(*) > 1
                )
                SELECT 
                    'DUPLICATE_EVENTS' AS check_name,
                    COUNT(*) AS violations,
                    CASE 
                        WHEN COUNT(*) = 0 THEN 'PASS'
                        ELSE 'FAIL'
                    END AS status
                FROM duplicate_events
            """)
            
            result = await session.execute(query_duplicates)
            check = result.fetchone()
            
            assert check.violations == 0, "Should have no duplicate events"
            assert check.status == "PASS"
            
            # Q4.2: Check for orphaned ledger entries
            query_orphaned = text("""
                WITH orphaned_entries AS (
                    SELECT le.id
                    FROM ledger_entries le
                    LEFT JOIN processor_events pe ON le.related_event_id = pe.event_id
                    WHERE pe.id IS NULL 
                      AND le.entry_type IN ('sale', 'commission', 'refund')
                      AND le.related_event_id IS NOT NULL
                )
                SELECT 
                    'ORPHANED_LEDGER_ENTRIES' AS check_name,
                    COUNT(*) AS violations,
                    CASE 
                        WHEN COUNT(*) = 0 THEN 'PASS'
                        ELSE 'FAIL'
                    END AS status
                FROM orphaned_entries
            """)
            
            result = await session.execute(query_orphaned)
            check = result.fetchone()
            
            assert check.violations == 0, "Should have no orphaned entries"
            assert check.status == "PASS"
            
            # Q4.4: Check for invalid amounts
            query_invalid_amounts = text("""
                WITH invalid_amounts AS (
                    SELECT id
                    FROM ledger_entries
                    WHERE (entry_type = 'sale' AND amount_cents < 0)
                       OR (entry_type = 'commission' AND amount_cents > 0)
                       OR (entry_type = 'refund' AND amount_cents > 0)
                       OR (entry_type = 'payout_reserve' AND amount_cents > 0)
                )
                SELECT 
                    'INVALID_AMOUNTS' AS check_name,
                    COUNT(*) AS violations,
                    CASE 
                        WHEN COUNT(*) = 0 THEN 'PASS'
                        ELSE 'FAIL'
                    END AS status
                FROM invalid_amounts
            """)
            
            result = await session.execute(query_invalid_amounts)
            check = result.fetchone()
            
            assert check.violations == 0, "Should have no invalid amounts"
            assert check.status == "PASS"
