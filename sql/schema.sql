-- ============================================================================
-- Restaurant Ledger System - Database Schema
-- ============================================================================
-- Database: PostgreSQL 15+
-- Purpose: Financial ledger with idempotency guarantees
-- Features: Immutable ledger, row locking, maturity window, multi-currency
-- ============================================================================

-- Drop existing tables (for clean setup)
DROP TABLE IF EXISTS ledger_entries CASCADE;
DROP TABLE IF EXISTS payouts CASCADE;
DROP TABLE IF EXISTS processor_events CASCADE;
DROP TABLE IF EXISTS restaurants CASCADE;

-- ============================================================================
-- TABLE 1: restaurants
-- ============================================================================
-- Purpose: Master data for restaurant entities
-- Mutability: Mutable (metadata only)
-- ============================================================================

CREATE TABLE restaurants (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB,
    
    CONSTRAINT check_restaurant_id_format 
        CHECK (id ~ '^res_[a-zA-Z0-9_-]+$')
);

-- Comments
COMMENT ON TABLE restaurants IS 'Master data for restaurant entities';
COMMENT ON COLUMN restaurants.id IS 'Restaurant identifier from processor (e.g., "res_001")';
COMMENT ON COLUMN restaurants.name IS 'Restaurant display name';
COMMENT ON COLUMN restaurants.is_active IS 'Soft delete flag';
COMMENT ON COLUMN restaurants.metadata IS 'Additional processor-specific fields (JSONB)';

-- ============================================================================
-- TABLE 2: processor_events
-- ============================================================================
-- Purpose: Webhook event log (idempotency tracking)
-- Mutability: Immutable
-- Key Feature: UNIQUE constraint on event_id enforces idempotency
-- ============================================================================

CREATE TABLE processor_events (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(50) NOT NULL UNIQUE,
    event_type VARCHAR(50) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    restaurant_id VARCHAR(50) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'PEN',
    amount_cents BIGINT NOT NULL,
    fee_cents BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB,
    
    CONSTRAINT fk_restaurant
        FOREIGN KEY (restaurant_id) 
        REFERENCES restaurants(id) 
        ON DELETE RESTRICT,
    
    CONSTRAINT check_event_type 
        CHECK (event_type IN ('charge_succeeded', 'refund_succeeded', 'payout_paid')),
    
    CONSTRAINT check_currency 
        CHECK (currency ~ '^[A-Z]{3}$'),
    
    CONSTRAINT check_amount_cents_positive 
        CHECK (amount_cents >= 0),
    
    CONSTRAINT check_fee_cents_positive 
        CHECK (fee_cents >= 0)
);

-- Comments
COMMENT ON TABLE processor_events IS 'Immutable log of webhook events (idempotency guarantee via UNIQUE event_id)';
COMMENT ON COLUMN processor_events.event_id IS 'External event identifier from processor (idempotency key)';
COMMENT ON COLUMN processor_events.event_type IS 'Event classification: charge_succeeded, refund_succeeded, payout_paid';
COMMENT ON COLUMN processor_events.occurred_at IS 'Timestamp when event occurred (from processor)';
COMMENT ON COLUMN processor_events.amount_cents IS 'Gross amount in cents (always positive, integers only)';
COMMENT ON COLUMN processor_events.fee_cents IS 'Processor commission in cents (always positive)';
COMMENT ON COLUMN processor_events.created_at IS 'When API received the event (may differ from occurred_at)';
COMMENT ON COLUMN processor_events.metadata IS 'Raw webhook payload for debugging and audit';

-- ============================================================================
-- TABLE 3: ledger_entries
-- ============================================================================
-- Purpose: Financial ledger (double-entry inspired, immutable)
-- Mutability: Immutable (INSERT only, no UPDATE/DELETE)
-- Key Feature: Balance = SUM(amount_cents) - never stored in column
-- ============================================================================

CREATE TABLE ledger_entries (
    id BIGSERIAL PRIMARY KEY,
    restaurant_id VARCHAR(50) NOT NULL,
    amount_cents BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'PEN',
    entry_type VARCHAR(50) NOT NULL,
    description TEXT,
    related_event_id VARCHAR(100),
    related_payout_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    available_at TIMESTAMPTZ,
    
    CONSTRAINT fk_restaurant
        FOREIGN KEY (restaurant_id) 
        REFERENCES restaurants(id) 
        ON DELETE RESTRICT,
    
    CONSTRAINT fk_processor_event
        FOREIGN KEY (related_event_id) 
        REFERENCES processor_events(event_id) 
        ON DELETE RESTRICT,
    
    CONSTRAINT fk_payout
        FOREIGN KEY (related_payout_id) 
        REFERENCES payouts(id) 
        ON DELETE RESTRICT,
    
    CONSTRAINT check_entry_type 
        CHECK (entry_type IN ('sale', 'commission', 'refund', 'payout_reserve')),
    
    CONSTRAINT check_currency 
        CHECK (currency ~ '^[A-Z]{3}$')
);

-- Comments
COMMENT ON TABLE ledger_entries IS 'Immutable financial ledger - balance calculated as SUM(amount_cents)';
COMMENT ON COLUMN ledger_entries.amount_cents IS 'Can be negative for debits (commission: -600, payout_reserve: -11400). Credits are positive (sale: +12000)';
COMMENT ON COLUMN ledger_entries.entry_type IS 'Entry classification: sale (credit), commission (debit), refund (debit), payout_reserve (debit)';
COMMENT ON COLUMN ledger_entries.description IS 'Human-readable description for debugging and audit';
COMMENT ON COLUMN ledger_entries.related_event_id IS 'Source event (NULL for payout_reserve entries)';
COMMENT ON COLUMN ledger_entries.related_payout_id IS 'Related payout (NULL for event-based entries)';
COMMENT ON COLUMN ledger_entries.available_at IS 'Maturity date - NULL means immediately available. Used for pending vs available balance';

-- ============================================================================
-- TABLE 4: payouts
-- ============================================================================
-- Purpose: Settlement records (mutable status only)
-- Mutability: Mutable (status transitions: created → processing → paid/failed)
-- Key Feature: Status machine with CHECK constraint for data integrity
-- ============================================================================

CREATE TABLE payouts (
    id BIGSERIAL PRIMARY KEY,
    restaurant_id VARCHAR(50) NOT NULL,
    amount_cents BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'PEN',
    status VARCHAR(50) NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at TIMESTAMPTZ,
    failure_reason TEXT,
    metadata JSONB,
    
    CONSTRAINT fk_restaurant
        FOREIGN KEY (restaurant_id) 
        REFERENCES restaurants(id) 
        ON DELETE RESTRICT,
    
    CONSTRAINT check_status 
        CHECK (status IN ('created', 'processing', 'paid', 'failed')),
    
    CONSTRAINT check_currency 
        CHECK (currency ~ '^[A-Z]{3}$'),
    
    CONSTRAINT check_amount_cents_positive 
        CHECK (amount_cents > 0),
    
    CONSTRAINT check_paid_at_with_status
        CHECK (
            (status = 'paid' AND paid_at IS NOT NULL) OR
            (status != 'paid' AND paid_at IS NULL)
        )
);

-- Comments
COMMENT ON TABLE payouts IS 'Settlement records - status is mutable (created → processing → paid/failed)';
COMMENT ON COLUMN payouts.status IS 'Payout state: created, processing, paid, failed';
COMMENT ON COLUMN payouts.amount_cents IS 'Payout amount (always positive, money OUT)';
COMMENT ON COLUMN payouts.paid_at IS 'Timestamp when transfer completed (NULL until status=paid)';
COMMENT ON COLUMN payouts.failure_reason IS 'Error message if status=failed';
COMMENT ON COLUMN payouts.metadata IS 'Bank account, transfer reference, processor response';

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================

-- Verify tables were created
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
