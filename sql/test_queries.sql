-- ============================================================================
-- Test Queries - Validación del sistema implementado
-- ============================================================================

-- Query 1: Balance total por restaurante
SELECT 
    restaurant_id,
    currency,
    SUM(amount_cents) AS balance_cents,
    ROUND(SUM(amount_cents) / 100.0, 2) AS balance_decimal,
    COUNT(*) AS total_entries
FROM ledger_entries
GROUP BY restaurant_id, currency
ORDER BY balance_cents DESC;

-- Query 2: Desglose de entradas por tipo
SELECT 
    restaurant_id,
    entry_type,
    COUNT(*) AS entry_count,
    SUM(amount_cents) AS total_cents,
    ROUND(SUM(amount_cents) / 100.0, 2) AS total_decimal
FROM ledger_entries
GROUP BY restaurant_id, entry_type
ORDER BY restaurant_id, entry_type;

-- Query 3: Balance disponible vs bloqueado (maturity date)
SELECT 
    restaurant_id,
    currency,
    SUM(CASE WHEN available_at IS NULL OR available_at <= NOW() 
        THEN amount_cents ELSE 0 END) AS available_balance_cents,
    SUM(CASE WHEN available_at > NOW() 
        THEN amount_cents ELSE 0 END) AS locked_balance_cents,
    SUM(amount_cents) AS total_balance_cents
FROM ledger_entries
GROUP BY restaurant_id, currency
ORDER BY restaurant_id;

-- Query 4: Eventos procesados por restaurante
SELECT 
    r.id,
    r.name,
    COUNT(pe.id) AS total_events,
    SUM(CASE WHEN pe.event_type = 'charge_succeeded' THEN 1 ELSE 0 END) AS charges,
    SUM(CASE WHEN pe.event_type = 'refund_succeeded' THEN 1 ELSE 0 END) AS refunds,
    SUM(CASE WHEN pe.event_type = 'payout_paid' THEN 1 ELSE 0 END) AS payouts
FROM restaurants r
LEFT JOIN processor_events pe ON r.id = pe.restaurant_id
GROUP BY r.id, r.name
ORDER BY total_events DESC;

-- Query 5: Verificar idempotencia (NO debe haber duplicados)
SELECT 
    event_id, 
    COUNT(*) AS duplicates
FROM processor_events
GROUP BY event_id
HAVING COUNT(*) > 1;

-- Query 6: Verificar integridad referencial (ledger_entries → processor_events)
SELECT 
    le.id AS ledger_id,
    le.related_event_id,
    le.entry_type,
    pe.event_id AS found_event
FROM ledger_entries le
LEFT JOIN processor_events pe ON le.related_event_id = pe.event_id
WHERE le.related_event_id IS NOT NULL
  AND pe.event_id IS NULL;

-- Query 7: Revenue neto por restaurante (sales - commissions)
SELECT 
    restaurant_id,
    currency,
    SUM(CASE WHEN entry_type = 'sale' THEN amount_cents ELSE 0 END) AS gross_sales_cents,
    SUM(CASE WHEN entry_type = 'commission' THEN amount_cents ELSE 0 END) AS commission_cents,
    SUM(CASE WHEN entry_type = 'sale' OR entry_type = 'commission' THEN amount_cents ELSE 0 END) AS net_revenue_cents,
    ROUND(SUM(CASE WHEN entry_type = 'sale' OR entry_type = 'commission' THEN amount_cents ELSE 0 END) / 100.0, 2) AS net_revenue_decimal
FROM ledger_entries
GROUP BY restaurant_id, currency
ORDER BY net_revenue_cents DESC;

-- Query 8: Última actividad por restaurante
SELECT 
    r.id,
    r.name,
    r.created_at AS restaurant_created,
    pe.last_event,
    pe.last_event_type
FROM restaurants r
LEFT JOIN LATERAL (
    SELECT 
        occurred_at AS last_event,
        event_type AS last_event_type
    FROM processor_events
    WHERE restaurant_id = r.id
    ORDER BY occurred_at DESC
    LIMIT 1
) pe ON TRUE
ORDER BY r.id;
