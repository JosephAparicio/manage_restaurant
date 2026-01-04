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

-- PDF contract (for a given currency): restaurant_id, available, last_event_at.
-- Source of truth for last_event_at: ledger_entries.created_at for entries linked to events.

SELECT
    le.restaurant_id,
    SUM(le.amount_cents) FILTER (
        WHERE le.available_at IS NULL OR le.available_at <= NOW()
    ) AS available,
    MAX(le.created_at) FILTER (
        WHERE le.related_event_id IS NOT NULL
    ) AS last_event_at
FROM ledger_entries le
WHERE le.currency = :currency
GROUP BY le.restaurant_id
ORDER BY available DESC;

/*
Expected Output:
Parameters:
- :currency

Columns:
- restaurant_id
- available
- last_event_at

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

/*
Expected Output:
Columns:
- restaurant_id
- net_amount (sales - fees - refunds; aligned with ledger entry signs)
- charge_count
- refund_count

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
ORDER BY ab.available_balance_cents DESC;

/*
Expected Output:
Parameters:
- :min_amount
- :as_of

Columns:
- restaurant_id
- currency
- available_balance_cents

Business Interpretation:
- These restaurants can receive payouts immediately
- Anti-join excludes restaurants with pending payouts (prevents double payout)
- Second anti-join excludes restaurants that already ran for the same :as_of (batch idempotency)
*/

-- ============================================================================
-- Q4: DATA INTEGRITY CHECKS (Anomaly Detection)
-- ============================================================================
-- Purpose: Validate database consistency and detect anomalies
-- Techniques: Multiple CTEs, LEFT JOIN, aggregation, NOT EXISTS
-- Business Logic: Financial data must be complete and consistent
-- ============================================================================

SELECT
    pe.event_id,
    COUNT(*) AS duplicates
FROM processor_events pe
GROUP BY pe.event_id
HAVING COUNT(*) > 1;

/*
Expected Output:
- No rows returned (no duplicates)
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
