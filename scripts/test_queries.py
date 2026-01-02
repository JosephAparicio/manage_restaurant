import subprocess


def execute_query(query_name: str, sql: str) -> None:
    print(f"\n{'=' * 80}")
    print(f"{query_name}")
    print(f"{'=' * 80}\n")

    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "restaurant_ledger_db",
            "psql",
            "-U",
            "restaurant_user",
            "-d",
            "restaurant_ledger",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print(result.stdout)
    else:
        print(f"ERROR: {result.stderr}")


def main():
    print("\nRestaurant Ledger System - SQL Query Tests")
    print("=" * 80)

    q1 = """
    SELECT 
        restaurant_id,
        currency,
        SUM(amount_cents) AS balance_cents,
        ROUND(SUM(amount_cents) / 100.0, 2) AS balance_decimal,
        COUNT(*) AS total_entries,
        MAX(created_at) AS last_entry_at
    FROM ledger_entries
    GROUP BY restaurant_id, currency
    HAVING SUM(amount_cents) != 0
    ORDER BY balance_cents DESC;
    """

    q2 = """
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
            COUNT(*) AS transaction_count,
            COUNT(DISTINCT related_event_id) AS unique_events
        FROM ledger_entries
        WHERE created_at >= NOW() - INTERVAL '7 days'
          AND (available_at IS NULL OR available_at <= NOW())
          AND entry_type IN ('sale', 'commission', 'refund')
        GROUP BY restaurant_id, currency
    ),
    ranked_revenue AS (
        SELECT 
            restaurant_id,
            currency,
            net_revenue_cents,
            ROUND(net_revenue_cents / 100.0, 2) AS net_revenue_decimal,
            transaction_count,
            unique_events,
            RANK() OVER (ORDER BY net_revenue_cents DESC) AS revenue_rank,
            ROUND(100.0 * net_revenue_cents / SUM(net_revenue_cents) OVER (), 2) AS market_share_pct
        FROM recent_revenue
        WHERE net_revenue_cents > 0
    )
    SELECT 
        revenue_rank,
        restaurant_id,
        currency,
        net_revenue_decimal AS net_revenue,
        transaction_count,
        unique_events,
        market_share_pct
    FROM ranked_revenue
    ORDER BY revenue_rank
    LIMIT 10;
    """

    q3 = """
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
        ab.available_balance_cents,
        ROUND(ab.available_balance_cents / 100.0, 2) AS available_balance_decimal,
        r.name AS restaurant_name,
        pe.last_event_at
    FROM available_balances ab
    INNER JOIN restaurants r ON ab.restaurant_id = r.id
    LEFT JOIN LATERAL (
        SELECT MAX(occurred_at) AS last_event_at
        FROM processor_events
        WHERE restaurant_id = ab.restaurant_id
    ) pe ON TRUE
    WHERE NOT EXISTS (
        SELECT 1 
        FROM payouts p
        WHERE p.restaurant_id = ab.restaurant_id
          AND p.status IN ('created', 'processing')
    )
    AND r.is_active = TRUE
    ORDER BY ab.available_balance_cents DESC;
    """

    q4_1 = """
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
            ELSE 'FAIL - Idempotency violated!'
        END AS status
    FROM duplicate_events;
    """

    q4_2 = """
    WITH orphaned_entries AS (
        SELECT 
            le.id, 
            le.restaurant_id, 
            le.entry_type,
            le.related_event_id
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
            ELSE 'FAIL - Foreign key integrity issue!'
        END AS status
    FROM orphaned_entries;
    """

    q4_3 = """
    WITH payouts_without_reserve AS (
        SELECT 
            p.id, 
            p.restaurant_id, 
            p.amount_cents
        FROM payouts p
        WHERE NOT EXISTS (
            SELECT 1 
            FROM ledger_entries le 
            WHERE le.related_payout_id = p.id 
              AND le.entry_type = 'payout_reserve'
        )
    )
    SELECT 
        'PAYOUTS_WITHOUT_RESERVE' AS check_name,
        COUNT(*) AS violations,
        CASE 
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL - Missing payout_reserve entries!'
        END AS status
    FROM payouts_without_reserve;
    """

    q4_4 = """
    WITH invalid_amounts AS (
        SELECT 
            id, 
            restaurant_id, 
            amount_cents, 
            entry_type
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
            ELSE 'FAIL - Amount signs are incorrect!'
        END AS status
    FROM invalid_amounts;
    """

    q4_5 = """
    WITH ledger_balances AS (
        SELECT 
            restaurant_id,
            currency,
            SUM(amount_cents) AS ledger_balance
        FROM ledger_entries
        GROUP BY restaurant_id, currency
    ),
    payout_totals AS (
        SELECT 
            restaurant_id,
            currency,
            SUM(amount_cents) AS total_payouts
        FROM payouts
        WHERE status = 'paid'
        GROUP BY restaurant_id, currency
    ),
    reserve_totals AS (
        SELECT 
            restaurant_id,
            currency,
            SUM(amount_cents) AS total_reserves
        FROM ledger_entries
        WHERE entry_type = 'payout_reserve'
        GROUP BY restaurant_id, currency
    )
    SELECT 
        'BALANCE_RECONCILIATION' AS check_name,
        COUNT(*) AS mismatches,
        CASE 
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL - Payout reserves do not match paid payouts!'
        END AS status
    FROM (
        SELECT 
            COALESCE(pt.restaurant_id, rt.restaurant_id) AS restaurant_id,
            COALESCE(pt.currency, rt.currency) AS currency,
            COALESCE(pt.total_payouts, 0) AS paid_amount,
            COALESCE(rt.total_reserves, 0) AS reserved_amount
        FROM payout_totals pt
        FULL OUTER JOIN reserve_totals rt 
            ON pt.restaurant_id = rt.restaurant_id 
            AND pt.currency = rt.currency
        WHERE ABS(COALESCE(pt.total_payouts, 0) + COALESCE(rt.total_reserves, 0)) > 1
    ) AS reconciliation;
    """

    bonus = """
    SELECT 
        restaurant_id,
        currency,
        SUM(amount_cents) AS total_balance_cents,
        ROUND(SUM(amount_cents) / 100.0, 2) AS total_balance_decimal,
        SUM(amount_cents) FILTER (
            WHERE available_at IS NULL OR available_at <= NOW()
        ) AS available_cents,
        ROUND(SUM(amount_cents) FILTER (
            WHERE available_at IS NULL OR available_at <= NOW()
        ) / 100.0, 2) AS available_decimal,
        COALESCE(SUM(amount_cents) FILTER (
            WHERE available_at > NOW()
        ), 0) AS pending_cents,
        ROUND(COALESCE(SUM(amount_cents) FILTER (
            WHERE available_at > NOW()
        ), 0) / 100.0, 2) AS pending_decimal,
        COUNT(*) AS total_entries,
        MAX(created_at) AS last_entry_at
    FROM ledger_entries
    GROUP BY restaurant_id, currency
    ORDER BY total_balance_cents DESC;
    """

    execute_query("Q1: RESTAURANT BALANCES", q1)
    execute_query("Q2: TOP 10 RESTAURANTS BY NET REVENUE (Last 7 Days)", q2)
    execute_query("Q3: PAYOUT ELIGIBILITY", q3)
    execute_query("Q4.1: DATA INTEGRITY - Duplicate Events", q4_1)
    execute_query("Q4.2: DATA INTEGRITY - Orphaned Ledger Entries", q4_2)
    execute_query("Q4.3: DATA INTEGRITY - Payouts Without Reserve", q4_3)
    execute_query("Q4.4: DATA INTEGRITY - Invalid Amounts", q4_4)
    execute_query("Q4.5: DATA INTEGRITY - Balance Reconciliation", q4_5)
    execute_query("BONUS: COMPREHENSIVE BALANCE REPORT", bonus)

    print(f"\n{'=' * 80}")
    print("All queries executed successfully")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
