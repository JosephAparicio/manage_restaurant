-- ============================================================================
-- Restaurant Ledger System - SQL Query Deliverables (Q1-Q4)
-- ============================================================================
-- Purpose: Demonstrate SQL proficiency for technical challenge evaluation
-- Features: Aggregations, CTEs, Window Functions, Joins, Anti-joins, Intervals
-- ============================================================================

-- ============================================================================
-- Q1: RESTAURANT BALANCES (Aggregation)
-- ============================================================================
-- Purpose: Calculate current balance for all restaurants
-- Techniques: GROUP BY, SUM aggregation, HAVING clause
-- Business Logic: Balance = SUM(ledger_entries.amount_cents)
-- ============================================================================

SELECT 
    restaurant_id,
    currency,
    SUM(amount_cents) AS balance_cents,
    ROUND(SUM(amount_cents) / 100.0, 2) AS balance_decimal,
    COUNT(*) AS total_entries,
    MAX(created_at) AS last_entry_at
FROM ledger_entries
GROUP BY restaurant_id, currency
HAVING SUM(amount_cents) != 0  -- Exclude zero balances
ORDER BY balance_cents DESC;

/*
Expected Output:
+--------------+----------+---------------+-----------------+---------------+-------------------------+
| restaurant_id| currency | balance_cents | balance_decimal | total_entries | last_entry_at           |
+--------------+----------+---------------+-----------------+---------------+-------------------------+
| res_001      | PEN      | 11400         | 114.00          | 3             | 2025-12-20 15:30:00+00  |
| res_002      | PEN      | -600          | -6.00           | 2             | 2025-12-21 10:00:00+00  |
+--------------+----------+---------------+-----------------+---------------+-------------------------+

Business Interpretation:
- res_001: +114.00 PEN available (positive balance)
- res_002: -6.00 PEN owed (negative balance, commission absorbed on refund)
*/

-- ============================================================================
-- Q2: TOP 10 RESTAURANTS BY NET REVENUE (Last 7 Days)
-- ============================================================================
-- Purpose: Rank restaurants by revenue with window functions
-- Techniques: CTE, INTERVAL, CASE aggregation, Window Function (RANK)
-- Business Logic: Revenue = sales - commissions - refunds
-- ============================================================================

WITH recent_revenue AS (
    SELECT 
        restaurant_id,
        currency,
        -- Calculate net revenue (sales - commissions - refunds)
        SUM(CASE 
            WHEN entry_type = 'sale' THEN amount_cents
            WHEN entry_type = 'commission' THEN amount_cents  -- Already negative
            WHEN entry_type = 'refund' THEN amount_cents      -- Already negative
            ELSE 0
        END) AS net_revenue_cents,
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT related_event_id) AS unique_events
    FROM ledger_entries
    WHERE created_at >= NOW() - INTERVAL '7 days'
      AND (available_at IS NULL OR available_at <= NOW())  -- Only matured entries
      AND entry_type IN ('sale', 'commission', 'refund')   -- Exclude payout_reserve
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
    WHERE net_revenue_cents > 0  -- Only profitable restaurants
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

/*
Expected Output:
+--------------+---------------+----------+--------------+-------------------+--------------+------------------+
| revenue_rank | restaurant_id | currency | net_revenue  | transaction_count | unique_events| market_share_pct |
+--------------+---------------+----------+--------------+-------------------+--------------+------------------+
| 1            | res_005       | PEN      | 285.00       | 30                | 10           | 35.50            |
| 2            | res_003       | PEN      | 171.00       | 18                | 6            | 21.30            |
| 3            | res_001       | PEN      | 114.00       | 12                | 4            | 14.20            |
+--------------+---------------+----------+--------------+-------------------+--------------+------------------+

Business Interpretation:
- res_005: Top performer with 35.5% market share
- Shows transaction count and unique events (detect bulk vs individual sales)
- Market share helps identify concentration risk
*/

-- ============================================================================
-- Q3: PAYOUT ELIGIBILITY (Filtering + Anti-Join)
-- ============================================================================
-- Purpose: Find restaurants eligible for payout (no pending payouts)
-- Techniques: NOT EXISTS (anti-join), HAVING clause, aggregate filtering
-- Business Logic: Eligible if balance >= min_amount AND no pending payouts
-- ============================================================================

WITH available_balances AS (
    SELECT 
        restaurant_id,
        currency,
        SUM(amount_cents) AS available_balance_cents
    FROM ledger_entries
    WHERE (available_at IS NULL OR available_at <= NOW())  -- Only matured funds
    GROUP BY restaurant_id, currency
    HAVING SUM(amount_cents) >= 10000  -- Minimum payout: 100.00 currency
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

/*
Expected Output:
+---------------+----------+------------------------+---------------------------+------------------+-------------------------+
| restaurant_id | currency | available_balance_cents| available_balance_decimal | restaurant_name  | last_event_at           |
+---------------+----------+------------------------+---------------------------+------------------+-------------------------+
| res_005       | PEN      | 28500                  | 285.00                    | Restaurant Five  | 2025-12-30 12:00:00+00  |
| res_003       | PEN      | 17100                  | 171.00                    | Restaurant Three | 2025-12-30 11:30:00+00  |
| res_001       | PEN      | 11400                  | 114.00                    | Restaurant One   | 2025-12-30 10:00:00+00  |
+---------------+----------+------------------------+---------------------------+------------------+-------------------------+

Business Interpretation:
- These restaurants can receive payouts immediately
- Anti-join excludes restaurants with pending payouts (prevents double payout)
- LATERAL join optimizes last_event_at lookup
*/

-- ============================================================================
-- Q4: DATA INTEGRITY CHECKS (Anomaly Detection)
-- ============================================================================
-- Purpose: Validate database consistency and detect anomalies
-- Techniques: Multiple CTEs, LEFT JOIN, aggregation, NOT EXISTS
-- Business Logic: Financial data must be complete and consistent
-- ============================================================================

-- Check 4.1: Duplicate event_ids (should be ZERO)
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
        WHEN COUNT(*) = 0 THEN '✓ PASS'
        ELSE '✗ FAIL - Idempotency violated!'
    END AS status
FROM duplicate_events;

-- Check 4.2: Orphaned ledger entries (no related event)
WITH orphaned_entries AS (
    SELECT 
        le.id, 
        le.restaurant_id, 
        le.entry_type,
        le.related_event_id
    FROM ledger_entries le
    LEFT JOIN processor_events pe ON le.related_event_id = pe.event_id
    WHERE pe.id IS NULL 
      AND le.entry_type IN ('sale', 'commission', 'refund')  -- These MUST have event
      AND le.related_event_id IS NOT NULL  -- If specified, must exist
)
SELECT 
    'ORPHANED_LEDGER_ENTRIES' AS check_name,
    COUNT(*) AS violations,
    CASE 
        WHEN COUNT(*) = 0 THEN '✓ PASS'
        ELSE '✗ FAIL - Foreign key integrity issue!'
    END AS status
FROM orphaned_entries;

-- Check 4.3: Payouts without payout_reserve entry
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
        WHEN COUNT(*) = 0 THEN '✓ PASS'
        ELSE '✗ FAIL - Missing payout_reserve entries!'
    END AS status
FROM payouts_without_reserve;

-- Check 4.4: Invalid amounts (negative sales, positive commissions)
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
        WHEN COUNT(*) = 0 THEN '✓ PASS'
        ELSE '✗ FAIL - Amount signs are incorrect!'
    END AS status
FROM invalid_amounts;

-- Check 4.5: Balance reconciliation (ledger vs payouts)
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
        SUM(amount_cents) AS total_reserves  -- Should be negative
    FROM ledger_entries
    WHERE entry_type = 'payout_reserve'
    GROUP BY restaurant_id, currency
)
SELECT 
    'BALANCE_RECONCILIATION' AS check_name,
    COUNT(*) AS mismatches,
    CASE 
        WHEN COUNT(*) = 0 THEN '✓ PASS'
        ELSE '✗ FAIL - Payout reserves do not match paid payouts!'
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
    WHERE ABS(COALESCE(pt.total_payouts, 0) + COALESCE(rt.total_reserves, 0)) > 1  -- Allow 1 cent rounding
) AS reconciliation;

/*
Expected Output (All checks should PASS):
+---------------------------+------------+--------+
| check_name                | violations | status |
+---------------------------+------------+--------+
| DUPLICATE_EVENTS          | 0          | ✓ PASS |
| ORPHANED_LEDGER_ENTRIES   | 0          | ✓ PASS |
| PAYOUTS_WITHOUT_RESERVE   | 0          | ✓ PASS |
| INVALID_AMOUNTS           | 0          | ✓ PASS |
| BALANCE_RECONCILIATION    | 0          | ✓ PASS |
+---------------------------+------------+--------+

Business Interpretation:
- All integrity checks pass → Database is consistent
- If any check fails → Critical bug that needs immediate attention
- Run these checks periodically (daily cron job recommended)
*/

-- ============================================================================
-- BONUS: COMPREHENSIVE BALANCE REPORT (Available vs Pending)
-- ============================================================================
-- Purpose: Show pending vs available balance for all restaurants
-- Techniques: FILTER clause, conditional aggregation
-- Business Logic: Maturity window separates pending from available funds
-- ============================================================================

SELECT 
    restaurant_id,
    currency,
    -- Total balance (all entries)
    SUM(amount_cents) AS total_balance_cents,
    ROUND(SUM(amount_cents) / 100.0, 2) AS total_balance_decimal,
    
    -- Available balance (matured funds)
    SUM(amount_cents) FILTER (
        WHERE available_at IS NULL OR available_at <= NOW()
    ) AS available_cents,
    ROUND(SUM(amount_cents) FILTER (
        WHERE available_at IS NULL OR available_at <= NOW()
    ) / 100.0, 2) AS available_decimal,
    
    -- Pending balance (not yet matured)
    COALESCE(SUM(amount_cents) FILTER (
        WHERE available_at > NOW()
    ), 0) AS pending_cents,
    ROUND(COALESCE(SUM(amount_cents) FILTER (
        WHERE available_at > NOW()
    ), 0) / 100.0, 2) AS pending_decimal,
    
    -- Metadata
    COUNT(*) AS total_entries,
    MAX(created_at) AS last_entry_at
FROM ledger_entries
GROUP BY restaurant_id, currency
ORDER BY total_balance_cents DESC;

/*
Expected Output:
+---------------+----------+-------------------+----------------------+------------------+-------------------+---------------+-----------------+---------------+-------------------------+
| restaurant_id | currency | total_balance_cents| total_balance_decimal| available_cents  | available_decimal | pending_cents | pending_decimal | total_entries | last_entry_at           |
+---------------+----------+-------------------+----------------------+------------------+-------------------+---------------+-----------------+---------------+-------------------------+
| res_001       | PEN      | 11400             | 114.00               | 11400            | 114.00            | 0             | 0.00            | 3             | 2025-12-20 15:30:00+00  |
| res_002       | PEN      | 23400             | 234.00               | 11400            | 114.00            | 12000         | 120.00          | 4             | 2025-12-28 10:00:00+00  |
+---------------+----------+-------------------+----------------------+------------------+-------------------+---------------+-----------------+---------------+-------------------------+

Business Interpretation:
- res_001: All funds available (no maturity window)
- res_002: 114.00 available now, 120.00 pending (matures in future)
- This matches the PDF's expected JSON response format
*/

-- ============================================================================
-- END OF QUERIES
-- ============================================================================

-- Performance tip: Run EXPLAIN ANALYZE on these queries to verify index usage
-- Example: EXPLAIN ANALYZE <paste query here>;
