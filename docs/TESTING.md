# Testing Documentation

## Overview

This document describes the testing strategy and implementation for the Restaurant Ledger System.

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures (NullPool config)
├── test_sql_queries.py      # SQL queries Q1-Q4
├── integration/             # Integration tests (API + DB)
│   ├── test_processor_api.py      # Webhook processing (9 tests)
│   ├── test_restaurants_api.py    # Balance queries (6 tests)
│   └── test_payouts_api.py        # Payout generation (7 tests)
├── e2e/                     # End-to-end tests
│   └── test_complete_workflow.py  # Full workflows (3 tests)
└── utils/                   # Test utilities
    ├── factories.py         # Event factories
    └── helpers.py           # Test helpers
```

## Testing Strategy

### Integration Tests (API + Database)
- Test complete request/response cycle through FastAPI
- Use real PostgreSQL database with proper transactions
- Validate business logic, idempotency, and error handling
- **Cover all critical features**: idempotency, balance calculation, refund policy, concurrent payouts
- Tests repositories through API calls (more realistic than isolated unit tests)

### End-to-End Tests
- Test complete user workflows across multiple endpoints
- Validate entire system behavior from event processing to payouts
- Real-world scenario validation

**Design Decisions:**

1. **No Unit Tests**: Integration tests provide comprehensive coverage by testing through real API calls with actual database transactions. This approach:
   - Tests real behavior (not mocked behavior)
   - Validates database constraints and transactions
   - Avoids async session management complexity
   - Aligns with financial accuracy priority (PLAN.md §5)

2. **NullPool for asyncpg**: Configured in conftest.py to prevent connection reuse issues with asyncpg concurrent operations

3. **Automatic Cleanup Fixture**: Tests use an `autouse` fixture that truncates tables between tests to ensure isolation

## Running Tests

### All Tests with Coverage
```bash
docker-compose exec app python -m pytest tests/ --cov=app --cov-report=html --cov-report=term-missing
```

Open coverage report: `htmlcov/index.html`

### Specific Test Category
```bash
pytest tests/integration/
pytest tests/e2e/
```

### Specific Test File
```bash
pytest tests/integration/test_processor_api.py -v
```

### Idempotency Tests Only
```bash
pytest -m idempotency
```

### Concurrency Tests Only
```bash
pytest -m concurrency
```

## Test Markers

- `@pytest.mark.integration` - Integration tests (API endpoint tests)
- `@pytest.mark.e2e` - End-to-end tests (full system workflows)
- `@pytest.mark.slow` - Tests that take significant time
- `@pytest.mark.idempotency` - Tests focused on idempotent behavior
- `@pytest.mark.concurrency` - Tests for concurrent/race conditions

## Fixtures

### Database Fixtures
- `db_session` - Async database session for tests
- `client` - HTTP client for API testing

### Sample Data Fixtures
- `sample_restaurant_id` - Test restaurant ID
- `sample_event_id` - Test event ID
- `sample_charge_event_data` - Charge event payload
- `sample_refund_event_data` - Refund event payload
- `sample_payout_paid_event_data` - Payout paid event payload
- `past_datetime` - Datetime 3 days ago
- `future_datetime` - Datetime 1 day in the future

## Test Coverage

**Current: 77%**

- Critical paths covered:
  - ✅ Event processing with idempotency
  - ✅ Payout generation with row locking
  - ✅ Balance calculations (available/pending)
  - ✅ SQL queries Q1-Q4 (CTEs, window functions, anti-joins)
  - ✅ Refund policy (commission not refunded)
  - ✅ Multi-currency support
  - ✅ Concurrent operations

**29 tests total**: 22 integration + 3 e2e + 4 SQL queries

## Key Test Scenarios

### Idempotency (Priority #1)
- Duplicate event processing returns 200 OK (not 201)
- UNIQUE constraint prevents database duplicates
- Ledger entries created only once
- Concurrent duplicate requests handled correctly

### Balance Calculations (Priority #2)
- Available balance excludes future-dated entries (available_at)
- Pending balance includes future entries (7-day hold)
- Multi-currency support (PEN/USD)
- Correct commission deduction based on `fee_cents` provided by the event payload

### Refund Policy (Priority #3)
- refund_succeeded creates negative ledger entry
- Commission is NOT refunded (business rule)
- Balance correctly adjusted

### Concurrent Payouts (Priority #4)
- Row-level locking (FOR UPDATE) prevents race conditions
- Only one payout created per restaurant
- Insufficient balance properly handled

### SQL Queries (Priority #5)
- Q1: Restaurant balances with aggregation
- Q2: Top revenue with window functions (RANK)
- Q3: Payout eligibility with anti-join (NOT EXISTS)
- Q4: Data integrity checks (duplicates, orphans, invalid amounts)

### Event Processing
- charge_succeeded creates sale + commission entries
- refund_succeeded creates refund entry (negative amount)
- payout_paid updates payout status
- Auto-creation of restaurants on first event

## Test Utilities

### Factories
- `EventFactory` - Create test event payloads
- `RestaurantFactory` - Generate restaurant IDs
- `PayoutFactory` - Create payout data

### Helpers
- `process_events_batch` - Process multiple events sequentially
- `process_events_concurrent` - Process events concurrently
- `calculate_net_amount` - Calculate net after fees
- `format_currency` - Format cents to currency string

## Continuous Integration

Tests are designed to run in CI/CD pipelines:
- Fast execution (< 5 minutes total)
- Isolated test database
- Automatic cleanup after each test
- Parallel execution support

## Best Practices

1. **Isolation**: Each test is independent and can run in any order
2. **Clarity**: Test names describe what they test
3. **Coverage**: Both success and error cases tested
4. **Performance**: Minimal setup, fast execution
5. **Maintainability**: DRY principle with fixtures and factories
