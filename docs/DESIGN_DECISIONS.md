# ARCHITECTURE DECISION RECORDS (ADRs)
## Restaurant Ledger System - Design Decisions

This document records all significant architectural decisions made for this project, following the ADR format: Context → Decision → Consequences.

---

## TABLE OF CONTENTS

1. [ADR-001: Ledger-Based Balance (No Balance Column)](#adr-001-ledger-based-balance-no-balance-column)
2. [ADR-002: Database-Level Idempotency](#adr-002-database-level-idempotency)
3. [ADR-003: Commission NOT Refunded on Refunds](#adr-003-commission-not-refunded-on-refunds)
4. [ADR-004: Integer Money (BIGINT Cents)](#adr-004-integer-money-bigint-cents)
5. [ADR-005: Row Locking for Payout Generation](#adr-005-row-locking-for-payout-generation)
6. [ADR-006: Maturity Window Implementation](#adr-006-maturity-window-implementation)
7. [ADR-007: Async-First Architecture](#adr-007-async-first-architecture)
8. [ADR-008: No Triggers in Database](#adr-008-no-triggers-in-database)
9. [ADR-009: Foreign Keys with ON DELETE RESTRICT](#adr-009-foreign-keys-with-on-delete-restrict)
10. [ADR-010: HTTP Status Codes (201 vs 200)](#adr-010-http-status-codes-201-vs-200)

---

## ADR-001: Ledger-Based Balance (No Balance Column)

**Status:** ✅ Accepted

### Context

We need to track restaurant balances. There are two approaches:

**Option A: Mutable Balance Column**
```sql
CREATE TABLE restaurants (
    id VARCHAR(50) PRIMARY KEY,
    balance_cents BIGINT NOT NULL DEFAULT 0
);

-- Update balance on every transaction
UPDATE restaurants SET balance_cents = balance_cents + 12000 WHERE id = 'res_001';
```

**Option B: Ledger-Based (Calculated)**
```sql
-- Balance calculated on demand
SELECT SUM(amount_cents) FROM ledger_entries WHERE restaurant_id = 'res_001';
```

### Decision

**We chose Option B: Ledger-based balance calculation.**

Balance is NEVER stored in a column. It is ALWAYS calculated as:
```sql
SUM(ledger_entries.amount_cents)
```

### Consequences

**Positive:**
- ✅ **Immutability:** Ledger entries are never updated/deleted (audit trail)
- ✅ **Accuracy:** No balance drift (balance = source of truth)
- ✅ **Time travel:** Can calculate balance at any point in time
- ✅ **Audit compliance:** Every cent is traceable to its source event
- ✅ **Simpler concurrency:** No UPDATE conflicts (only INSERTs)

**Negative:**
- ❌ **Slower queries:** Must SUM on every balance check (~5-10ms with indexes)
- ❌ **More database load:** Cannot cache balance in DB

**Mitigation:**
- Use composite indexes on `(restaurant_id, currency)` for fast aggregation
- Add application-level caching (Redis) if needed for high-traffic scenarios
- Index-only scans make SUM queries very fast (milliseconds even with millions of rows)

**Scalability:**
- Horizontal scaling: Shard by restaurant_id
- Vertical scaling: PostgreSQL handles billions of rows efficiently with proper indexes
- Read replicas: Balance queries can run on replicas (no writes needed)

---

## ADR-002: Database-Level Idempotency

**Status:** ✅ Accepted

### Context

Webhook providers (Stripe, PayPal, etc.) may send duplicate events due to:
- Network retries
- Provider-side retries
- Race conditions

**Requirement from PDF:**
> Strong candidates enforce idempotency at the DB level (e.g., unique constraint on processor_events.event_id)

### Decision

**Enforce idempotency at DATABASE level using UNIQUE constraint:**

```sql
CREATE TABLE processor_events (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(50) NOT NULL UNIQUE,  -- ← Idempotency key
    ...
);

CREATE UNIQUE INDEX idx_processor_events_event_id 
    ON processor_events(event_id);
```

**Application handles IntegrityError:**
```python
try:
    await session.execute(insert(ProcessorEvent).values(event_id=...))
    await session.commit()
    return 201  # Created
except IntegrityError:
    await session.rollback()
    return 200  # Already processed
```

### Consequences

**Positive:**
- ✅ **Atomic guarantee:** Database enforces uniqueness (no race conditions)
- ✅ **Simple implementation:** No distributed locks needed
- ✅ **Fail-safe:** Even if application logic fails, DB prevents duplicates
- ✅ **Performance:** O(log n) UNIQUE index lookup (sub-millisecond)

**Negative:**
- ❌ **Throws exception:** Must catch and handle IntegrityError
- ❌ **Database coupling:** Idempotency logic tied to DB constraint

**Alternatives Rejected:**
- **Application-level check:** Race condition vulnerable
  ```python
  # BAD: Race condition between check and insert
  if await exists(event_id):
      return 200
  await insert(event_id)  # ← Two requests could both get here
  ```
- **Distributed lock (Redis):** Additional infrastructure, complexity
- **Application-level unique tracking:** Less reliable than DB constraint

**Atomicity:**
- UNIQUE constraint + transaction ensures atomic check-and-insert
- No partial state possible (either event is created or already exists)

---

## ADR-003: Commission NOT Refunded on Refunds

**Status:** ✅ Accepted

### Context

When a customer requests a refund, we must decide:
- Does the processor refund their commission?
- Does the restaurant get back the commission they paid?

**PDF Requirement:**
> Rule: define in the README whether the fee is refunded or not (and why)

### Decision

**Commission is NOT refunded when a refund occurs.**

**Example:**
- Customer pays 100 PEN (commission: 3.50 PEN = 3.5%)
- Restaurant receives 96.50 PEN
- Customer requests refund
- Restaurant returns 100 PEN to customer
- **Net effect: Restaurant loses 3.50 PEN (the commission)**

**Ledger entries:**
```sql
-- Initial sale
INSERT INTO ledger_entries VALUES ('res_001', +10000, 'sale');       -- +100.00
INSERT INTO ledger_entries VALUES ('res_001', -350, 'commission');    -- -3.50

-- Refund (only reverses sale, NOT commission)
INSERT INTO ledger_entries VALUES ('res_001', -10000, 'refund');      -- -100.00

-- Final balance: +10000 - 350 - 10000 = -350 (restaurant owes 3.50)
```

### Consequences

**Positive:**
- ✅ **Industry standard:** Stripe, PayPal, Square all retain commission on refunds
- ✅ **Fair to processor:** Processing costs were already incurred
- ✅ **Simpler logic:** No complex commission reversal calculations

**Negative:**
- ❌ **Restaurant absorbs cost:** Loses commission on refunded transactions
- ❌ **Potential confusion:** Must be clearly documented

**Business Rationale:**
- Processor already incurred costs (payment gateway fees, fraud checks, etc.)
- Processor provided the service of processing the payment
- Restaurant is responsible for customer satisfaction (refund reason)

**Documentation:**
- This decision MUST be documented in README.md (PDF requirement)
- Include example calculation for clarity

---

## ADR-004: Integer Money (BIGINT Cents)

**Status:** ✅ Accepted

### Context

**PDF Requirement:**
> Money & currency: amount and fee are integers in cents (no floats)

Two approaches for storing money:
- **Option A:** DECIMAL(10,2) or NUMERIC (stores exact decimals)
- **Option B:** BIGINT (stores cents as integers)

### Decision

**Store all amounts as BIGINT in cents (smallest currency unit).**

```sql
CREATE TABLE ledger_entries (
    amount_cents BIGINT NOT NULL,  -- 12000 = 120.00 PEN
    ...
);
```

**Conversion:**
```python
# Input: 120.45 PEN
amount_cents = int(120.45 * 100)  # 12045

# Output
amount_decimal = amount_cents / 100.0  # 120.45
```

### Consequences

**Positive:**
- ✅ **No floating-point errors:** `0.1 + 0.2 = 0.3` (not 0.30000000000000004)
- ✅ **Exact arithmetic:** All operations are integer math (accurate)
- ✅ **Performance:** Integer operations faster than DECIMAL/NUMERIC
- ✅ **Simpler queries:** `SUM(amount_cents)` always exact
- ✅ **Multi-currency friendly:** Different currencies have different "cents" (yen has 0 decimals)

**Negative:**
- ❌ **Conversion required:** Must multiply/divide by 100 at API boundaries
- ❌ **Human-unfriendly:** 12045 instead of 120.45 in database

**Database Support:**
- BIGINT range: ±9,223,372,036,854,775,807
- Max money: ±92,233,720,368,547,758.07 (92 trillion units)
- More than sufficient for any real-world financial system

**Atomicity:**
- Integer operations are atomic at database level
- No rounding errors in SUM operations

**Scalability:**
- Indexes on BIGINT are faster than DECIMAL/NUMERIC
- Smaller storage footprint (8 bytes vs 16 bytes for NUMERIC)

---

## ADR-005: Row Locking for Payout Generation

**Status:** ✅ Accepted

### Context

**Problem:** Race condition in payout generation

**Scenario:**
1. Request A: Calculate balance = 15000 (above threshold)
2. Request B: Calculate balance = 15000 (above threshold)
3. Both create payout for same restaurant
4. **Result:** Double payout (CRITICAL BUG)

### Decision

**Use PostgreSQL row-level locking (`SELECT ... FOR UPDATE`):**

```sql
-- Lock ledger rows during balance calculation
SELECT 
    restaurant_id,
    SUM(amount_cents) as available_balance
FROM ledger_entries
WHERE restaurant_id = ?
  AND currency = ?
  AND (available_at IS NULL OR available_at <= NOW())
FOR UPDATE;  -- ← Locks these rows until transaction ends
```

**SQLAlchemy implementation:**
```python
async with session.begin():
    result = await session.execute(
        select(func.sum(LedgerEntry.amount_cents))
        .where(LedgerEntry.restaurant_id == restaurant_id)
        .with_for_update()  # ← Row lock
    )
    balance = result.scalar() or 0
    
    if balance >= min_amount:
        # Create payout (still locked)
        payout = await create_payout(...)
        entry = await create_ledger_entry(...)
    
    # Commit releases lock
```

### Consequences

**Positive:**
- ✅ **Prevents double payouts:** Only ONE process can calculate balance at a time
- ✅ **Built-in PostgreSQL:** No external locks needed
- ✅ **Automatic release:** Lock released on commit/rollback
- ✅ **Deadlock detection:** PostgreSQL detects and resolves deadlocks

**Negative:**
- ❌ **Concurrency reduced:** Only one payout per restaurant at a time
- ❌ **Lock wait time:** Second request waits until first completes

**Alternatives Rejected:**
- **Application-level lock:** Not safe across multiple instances
- **Redis distributed lock:** Additional infrastructure
- **Optimistic locking:** Requires retry logic, more complex

**Performance Impact:**
- Minimal: Payout generation is async background task (not user-facing)
- Lock duration: <100ms (balance calculation + insert)
- Trade-off: Safety > Speed for financial operations

**Atomicity:**
- Transaction ensures all-or-nothing: balance check + payout creation + ledger entry
- Lock prevents interleaving of concurrent payout generations

---

## ADR-006: Maturity Window Implementation

**Status:** ✅ Accepted

### Context

**Maturity Window:** Money is "held" for X days before becoming available for payout.

**Use Case:**
- Prevent payouts for transactions that might get refunded
- Similar to Stripe's "rolling reserve" or "payout schedule"
- Example: Sales must wait 7 days before payout

### Decision

**Add `available_at` column to `ledger_entries`:**

```sql
CREATE TABLE ledger_entries (
    ...
    available_at TIMESTAMPTZ,  -- NULL = immediately available
    ...
);

-- Partial index for efficiency
CREATE INDEX idx_ledger_available_at 
    ON ledger_entries(available_at) 
    WHERE available_at IS NOT NULL;
```

**Balance queries:**
```sql
-- Available balance (can be paid out NOW)
SELECT SUM(amount_cents)
FROM ledger_entries
WHERE restaurant_id = ?
  AND (available_at IS NULL OR available_at <= NOW());

-- Pending balance (not yet matured)
SELECT SUM(amount_cents)
FROM ledger_entries
WHERE restaurant_id = ?
  AND available_at > NOW();
```

### Consequences

**Positive:**
- ✅ **Flexible:** Different maturity periods per entry type
- ✅ **Simple queries:** Single WHERE clause filters by maturity
- ✅ **NULL = available:** Most entries are immediately available (no value needed)
- ✅ **Partial index:** Only indexes future maturity dates (efficient)

**Negative:**
- ❌ **Additional complexity:** Balance calculation has two modes (available vs total)
- ❌ **Clock dependency:** Requires accurate system time

**Configuration:**
```python
# Example maturity policies
MATURITY_POLICIES = {
    "sale": timedelta(days=7),       # Sales mature in 7 days
    "commission": timedelta(days=0), # Immediate
    "refund": timedelta(days=0),     # Immediate
    "payout_reserve": timedelta(days=0)  # Immediate
}

# On insert
available_at = datetime.utcnow() + MATURITY_POLICIES[entry_type]
```

**Scalability:**
- Partial index keeps index small (only ~10% of entries have maturity dates)
- Query performance remains fast (index-only scan)

---

## ADR-007: Async-First Architecture

**Status:** ✅ Accepted

### Context

**PDF Requirements:**
- FastAPI (modern Python async framework)
- Payout generation must be asynchronous

**Choice:**
- **Option A:** Mix sync + async (psycopg2 + asyncio)
- **Option B:** Async all the way (asyncpg + SQLAlchemy async)

### Decision

**Use async for ALL database operations:**

```python
# Database
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from asyncpg import create_pool

# Endpoints
@app.post("/v1/processor/events")
async def process_event(event: EventPayload, session: AsyncSession = Depends(get_session)):
    result = await event_service.process_event(event, session)
    return result

# Services
class EventService:
    async def process_event(self, event: EventPayload, session: AsyncSession):
        await session.execute(...)
        await session.commit()

# Repositories
class LedgerRepository:
    async def get_balance(self, restaurant_id: str) -> int:
        result = await self.session.execute(...)
        return result.scalar()
```

### Consequences

**Positive:**
- ✅ **Non-blocking:** Handles thousands of concurrent requests
- ✅ **Better resource usage:** Single thread handles multiple requests
- ✅ **FastAPI native:** No context switching between sync/async
- ✅ **Modern Python:** Leverages latest async features

**Negative:**
- ❌ **Learning curve:** Async/await requires understanding event loop
- ❌ **Debugging harder:** Stack traces more complex
- ❌ **Library limitations:** Must use async-compatible libraries

**Stack:**
- **Database driver:** asyncpg (fastest PostgreSQL driver for Python)
- **ORM:** SQLAlchemy 2.0 async
- **HTTP client:** httpx.AsyncClient (for tests)
- **Background tasks:** FastAPI BackgroundTasks

**Atomicity:**
- Async does NOT affect transaction atomicity
- Database transactions work identically in async context
- `async with session.begin()` ensures ACID properties

**Scalability:**
- Async enables vertical scaling (more requests per instance)
- Lower memory footprint (no thread-per-request)
- Easier horizontal scaling (stateless instances)

---

## ADR-008: No Triggers in Database

**Status:** ✅ Accepted

### Context

Should we use database triggers for automatic ledger entry creation?

**Option A: Database Triggers**
```sql
CREATE TRIGGER auto_create_ledger_entries
AFTER INSERT ON processor_events
FOR EACH ROW
EXECUTE FUNCTION create_ledger_entries();
```

**Option B: Application Logic**
```python
async def process_event(event):
    # Insert event
    await insert_event(event)
    # Create ledger entries
    await create_ledger_entries(event)
```

### Decision

**All business logic in application layer. NO database triggers.**

### Consequences

**Positive:**
- ✅ **Testability:** Unit tests don't need database
- ✅ **Clarity:** All logic visible in Python code
- ✅ **Debugging:** Stack traces show execution flow
- ✅ **Flexibility:** Easy to modify logic without ALTER TRIGGER
- ✅ **Versioning:** Logic changes tracked in Git, not DB dumps

**Negative:**
- ❌ **More code:** Must explicitly call functions
- ❌ **Potential inconsistency:** Developer could forget to create ledger entries

**Safeguards:**
- Comprehensive integration tests ensure ledger entries are created
- Database foreign keys prevent orphaned entries
- Code reviews catch missing logic

**Exceptions:**
- **updated_at triggers:** Acceptable for timestamp management
  ```sql
  CREATE TRIGGER update_restaurants_updated_at
  BEFORE UPDATE ON restaurants
  FOR EACH ROW
  EXECUTE FUNCTION update_timestamp();
  ```

---

## ADR-009: Foreign Keys with ON DELETE RESTRICT

**Status:** ✅ Accepted

### Context

What should happen if someone tries to delete a restaurant with existing events?

**Options:**
- `ON DELETE CASCADE` → Delete all related records
- `ON DELETE SET NULL` → Set foreign keys to NULL
- `ON DELETE RESTRICT` → Prevent deletion (raise error)

### Decision

**Use `ON DELETE RESTRICT` for ALL foreign keys:**

```sql
CREATE TABLE processor_events (
    restaurant_id VARCHAR(50) NOT NULL,
    CONSTRAINT fk_restaurant
        FOREIGN KEY (restaurant_id) 
        REFERENCES restaurants(id) 
        ON DELETE RESTRICT  -- ← Prevents deletion
);
```

### Consequences

**Positive:**
- ✅ **Data safety:** Cannot accidentally delete restaurants with transactions
- ✅ **Audit integrity:** Financial records are immutable
- ✅ **Explicit deletion:** Must handle deletion explicitly (soft delete)
- ✅ **Prevents orphans:** No dangling foreign keys

**Negative:**
- ❌ **Cannot delete:** Must implement soft delete for restaurants
- ❌ **Migration complexity:** Requires careful planning for data cleanup

**Soft Delete Pattern:**
```sql
-- Instead of DELETE
DELETE FROM restaurants WHERE id = 'res_001';  -- ← Fails with RESTRICT

-- Use soft delete
UPDATE restaurants SET is_active = FALSE WHERE id = 'res_001';
```

**Rationale:**
- Financial data should NEVER be deleted
- Regulatory compliance (audit trails)
- Historical analysis requires complete data

---

## ADR-010: HTTP Status Codes (201 vs 200)

**Status:** ✅ Accepted

### Context

**PDF Requirement:**
> Recommended: 201 when newly processed, 200 when already processed (or justify your choice)

How should we indicate idempotent event processing?

### Decision

**Use different status codes for new vs duplicate events:**

| Status | Meaning | Response Body |
|--------|---------|---------------|
| **201 Created** | Event processed for first time | Full event details |
| **200 OK** | Event already processed (idempotent) | Existing event details |

**Implementation:**
```python
try:
    await session.execute(insert(ProcessorEvent).values(...))
    await session.commit()
    return JSONResponse(status_code=201, content={...})
except IntegrityError:
    await session.rollback()
    existing = await get_event(event_id)
    return JSONResponse(status_code=200, content={...})
```

### Consequences

**Positive:**
- ✅ **Client awareness:** Client knows if event was new or duplicate
- ✅ **Debugging:** Logs show idempotent requests
- ✅ **Monitoring:** Can track duplicate event rate
- ✅ **Standard HTTP:** 201 = resource created, 200 = success (no creation)

**Negative:**
- ❌ **Client must handle:** Some clients may only expect 201 from POST
- ❌ **Slightly more complex:** Need to differentiate in response

**Alternative Approaches:**
- **Always 200:** Simpler, but loses information
- **409 Conflict:** Could indicate duplicate, but feels like error
- **Custom header:** `X-Idempotency: true` (more complex)

**Justification:**
- RESTful semantics: POST creates resource → 201
- Idempotent repeat of same POST → resource already exists → 200
- Client can take action based on status (e.g., don't log "duplicate" as error)

---

## SUMMARY OF KEY DECISIONS

| ADR | Decision | Impact | Status |
|-----|----------|--------|--------|
| ADR-001 | Ledger-based balance (no column) | High | ✅ Implemented |
| ADR-002 | DB-level idempotency (UNIQUE) | High | ✅ Implemented |
| ADR-003 | Commission NOT refunded | Medium | ✅ Documented |
| ADR-004 | BIGINT cents (no floats) | High | ✅ Implemented |
| ADR-005 | Row locking (FOR UPDATE) | High | ✅ Implemented |
| ADR-006 | Maturity window (available_at) | Medium | ✅ Implemented |
| ADR-007 | Async-first architecture | High | ✅ Implemented |
| ADR-008 | No database triggers | Medium | ✅ Implemented |
| ADR-009 | ON DELETE RESTRICT | Medium | ✅ Implemented |
| ADR-010 | 201 vs 200 status codes | Low | ✅ Implemented |
| ADR-011 | Custom exception hierarchy | High | ✅ Implemented |

---

## ADR-011: Custom Exception Hierarchy with Global Handler

**Status:** ✅ Implemented

### Context

How should the API handle and communicate errors consistently across all endpoints?

**Option A: FastAPI HTTPException Only**
```python
from fastapi import HTTPException
raise HTTPException(status_code=404, detail="Restaurant not found")
```

**Option B: Custom Exception Hierarchy**
```python
from app.exceptions import RestaurantNotFoundException
raise RestaurantNotFoundException(restaurant_id="res_001")
```

### Decision

**Implement custom exception hierarchy with global exception handlers.**

**Structure:**
```python
# app/exceptions.py
class BaseAPIException(Exception):
    status_code: int
    error_code: str
    message: str
    details: dict
    
class ValidationException(BaseAPIException):  # 422
class BusinessException(BaseAPIException):     # 409
class NotFoundException(BaseAPIException):     # 404
class SystemException(BaseAPIException):       # 500
```

**Global Handler:**
```python
# app/main.py
@app.exception_handler(BaseAPIException)
async def api_exception_handler(request, exc):
    return ErrorResponse(
        error=ErrorDetail(
            code=exc.error_code,
            message=exc.message,
            details=exc.details
        )
    )
```

### Consequences

**Positive:**
- ✅ **Consistent responses:** All errors follow `ErrorResponse` schema
- ✅ **Machine-readable:** Error codes enable programmatic error handling
- ✅ **Type safety:** Custom exceptions are strongly typed
- ✅ **Testability:** Easy to test specific exception types
- ✅ **Centralized logging:** All errors logged with context
- ✅ **OpenAPI documentation:** Error schemas automatically documented

**Negative:**
- ❌ **More code:** Requires exception classes and handlers (~150 LOC)
- ❌ **Learning curve:** Team must know which exceptions to use

**Implementation Details:**

Domain-specific exceptions:
- `RestaurantNotFoundException` → 404 with `restaurant_id` in details
- `InsufficientBalanceException` → 409 with balance details
- `InvalidEventTypeException` → 422 with `event_type` in details
- `DuplicateEventException` → 409 with `idempotent=true` flag
- `DatabaseException` → 500 with operation details

**Example Response:**
```json
{
  "success": false,
  "error": {
    "code": "RESTAURANT_NOT_FOUND",
    "message": "Restaurant not found: res_123",
    "details": {
      "restaurant_id": "res_123"
    }
  },
  "meta": {
    "timestamp": "2025-12-31T10:30:00Z",
    "path": "/v1/restaurants/res_123/balance"
  }
}
```

**Rationale:**
- Consistent error responses improve client experience
- Machine-readable error codes enable programmatic handling
- Centralized handlers ensure logging consistency
- Type-safe exceptions prevent typos in error codes

---

## DOCUMENT MAINTENANCE

- **When to add ADR:** Significant architectural or design decision
- **Format:** Context → Decision → Consequences
- **Status:** Proposed → Accepted → Implemented → Superseded
- **Review:** ADRs are living documents, update as system evolves

---

## Related Documents

- [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - Schema implementing these decisions

