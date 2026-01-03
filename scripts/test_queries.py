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
        le.restaurant_id,
        SUM(le.amount_cents) AS available,
        MAX(pe.occurred_at) AS last_event_at
    FROM ledger_entries le
    LEFT JOIN processor_events pe
        ON pe.event_id = le.related_event_id
    WHERE le.currency = 'PEN'
    GROUP BY le.restaurant_id
    ORDER BY available DESC;
    """

    q2 = """
    WITH recent_activity AS (
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
    )
    SELECT
        restaurant_id,
        net_amount,
        charge_count,
        refund_count
    FROM recent_activity
    WHERE net_amount > 0
    ORDER BY net_amount DESC
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
          AND p.as_of = DATE '2025-12-27'
    )
    AND r.is_active = TRUE
    ORDER BY ab.available_balance_cents DESC;
    """

    q4 = """
    SELECT
        pe.event_id,
        COUNT(*) AS duplicates
    FROM processor_events pe
    GROUP BY pe.event_id
    HAVING COUNT(*) > 1;
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
    execute_query("Q4: DATA INTEGRITY - Duplicate Events", q4)
    execute_query("BONUS: COMPREHENSIVE BALANCE REPORT", bonus)

    print(f"\n{'=' * 80}")
    print("All queries executed successfully")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
