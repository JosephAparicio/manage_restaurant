# ARCHITECTURE & IMPLEMENTATION STRATEGY
## Restaurant Ledger Microservice

Strategic architectural approach for financial reconciliation system with guaranteed idempotency.

---

## TABLE OF CONTENTS

1. [Core Requirements Analysis](#1-core-requirements-analysis)
2. [Architecture Principles](#2-architecture-principles)
3. [Design Patterns](#3-design-patterns)
4. [Database Strategy](#4-database-strategy)
5. [API Design](#5-api-design)
6. [Error Handling](#6-error-handling)
7. [Security & Performance](#7-security--performance)

---

## 1. CORE REQUIREMENTS ANALYSIS

### 1.1 Business Context

Financial reconciliation and settlement system for restaurants requiring:
- **Zero data loss:** Every cent must be traceable
- **Zero duplication:** Idempotent webhook processing
- **Complete audit trail:** Immutable ledger
- **ACID transactions:** Atomic event processing

### 1.2 Critical Success Factors

| Factor | Weight | Strategy |
|--------|--------|----------|
| **Idempotency** | 35% | DB-level UNIQUE constraint on event_id |
| **SQL Mastery** | 25% | Advanced queries (CTEs, window functions, anti-joins) |
| **Code Quality** | 20% | Layered architecture, SOLID principles, type hints |
| **Async Robustness** | 10% | AsyncPG, non-blocking operations |
| **Tests & Docs** | 10% | pytest-asyncio, comprehensive ADRs |

### 1.3 Technical Stack

**Core:**
- Python 3.11+ with FastAPI (async only)
- PostgreSQL 15+ with asyncpg
- SQLAlchemy 2.0 (async ORM)
- Alembic for migrations

**Testing:**
- pytest + pytest-asyncio
- httpx.AsyncClient
- Factory pattern for test data

**Critical Constraints:**
- No floats for money (BIGINT cents only)
- No mutable balance column (calculated from ledger)
- No blocking operations in async context
- English only (code, comments, docs)

---

## 2. ARCHITECTURE PRINCIPLES

### 2.1 Layered Architecture

Clear separation of concerns with dependency flow:

```
API Layer (Controllers)
  ↓ depends on
Service Layer (Business Logic)
  ↓ depends on
Repository Layer (Data Access)
  ↓ depends on
Model Layer (ORM)
```

**Key Rules:**
- API layer: HTTP concerns only (validation, responses, status codes)
- Service layer: Business logic and transaction orchestration
- Repository layer: Database operations and query optimization
- Model layer: Data structures and relationships

**Benefits:**
- Testability: Mock lower layers in tests
- Maintainability: Changes localized to single layer
- Clarity: Single responsibility per layer

### 2.2 Immutability First

**Financial Data:**
- `processor_events` table: INSERT only (no UPDATE/DELETE)
- `ledger_entries` table: INSERT only (no UPDATE/DELETE)
- Balance: ALWAYS calculated, NEVER stored

**Mutable Data:**
- `payouts` table: Status updates only (amounts immutable)
- `restaurants` table: Metadata updates only

**Why:**
- Complete audit trail
- Time-travel balance calculation
- Simplified concurrency (no UPDATE conflicts)

### 2.3 Database-Level Guarantees

**Idempotency:**
- UNIQUE constraint on `processor_events.event_id`
- Duplicate webhooks return 200 OK (not 201)
- No application-level locks needed

**Referential Integrity:**
- Foreign keys with ON DELETE RESTRICT
- Prevents orphaned records
- Enforces data consistency

**Data Validation:**
- CHECK constraints for business rules
- NOT NULL for required fields
- Proper column types (BIGINT for money, TIMESTAMPTZ for dates)

---

## 3. DESIGN PATTERNS

### 3.1 Repository Pattern

**Purpose:** Isolate data access from business logic

**Structure:**
- Abstract base repository with common CRUD operations
- Concrete repositories per domain entity (Event, Ledger, Payout)
- Custom domain queries in respective repositories

**Benefits:**
- Testability: Mock repositories in service tests
- Flexibility: Swap database without changing services
- Single responsibility for data operations

### 3.2 Dependency Injection

**Purpose:** Decouple dependencies, enable testing

**Implementation:**
- FastAPI `Depends()` for automatic injection
- Database sessions via `async with` context manager
- Service instances created per request

**Benefits:**
- Easy to test (inject mocks)
- Explicit dependencies
- Automatic cleanup (context managers)

### 3.3 Unit of Work (Transaction Management)

**Purpose:** Atomic operations across multiple entities

**Pattern:**
- Begin transaction before processing
- Perform all operations within transaction scope
- Automatic commit on success, rollback on exception

**Example Flow:**
1. INSERT processor_event (may raise IntegrityError if duplicate)
2. INSERT ledger_entries (multiple rows)
3. Commit both or rollback both

### 3.4 Strategy Pattern (Event Handlers)

**Purpose:** Handle different event types without if/else chains

**Implementation:**
- Abstract EventHandler interface
- Concrete handlers per event type (ChargeHandler, RefundHandler, PayoutHandler)
- Factory dictionary mapping event_type → Handler class

**Benefits:**
- Open/Closed Principle (add new types without modifying existing)
- Testability (test handlers independently)
- Clarity (each handler has single responsibility)

---

## 4. DATABASE STRATEGY

### 4.1 Schema Design

**Core Tables:**
1. `restaurants` - Master data (mutable metadata)
2. `processor_events` - Webhook log (immutable, UNIQUE on event_id)
3. `ledger_entries` - Financial ledger (immutable, balance source)
4. `payouts` - Settlement records (status mutable, amounts immutable)

**Money Handling:**
- BIGINT for all amounts (cents, not decimals)
- Max value: ~92 quadrillion currency units (more than sufficient)
- No floating-point rounding errors

**Timestamps:**
- TIMESTAMPTZ (timezone-aware)
- `created_at` for audit trail
- `occurred_at` for business events
- `available_at` for maturity window

### 4.2 Index Strategy

**Performance Critical Indexes:**
- `processor_events.event_id` (UNIQUE, idempotency)
- `ledger_entries(restaurant_id, currency)` (balance calculation)
- `ledger_entries(available_at)` (maturity window filter)
- `payouts(restaurant_id, status)` (payout queries)

**Partial Indexes:**
- `payouts WHERE status='pending'` (active payouts only)

**Rationale:**
- Balance queries frequent (sub-5ms target with index)
- Payout queries filter by status (partial index reduces size)

### 4.3 Constraints as Documentation

**Business Rules Enforced:**
- `CHECK (amount_cents >= 0)` - No negative gross amounts
- `CHECK (currency ~ '^[A-Z]{3}$')` - ISO 4217 format
- `CHECK (event_type IN (...))` - Valid event types only
- `CHECK (status IN (...))` - Valid payout statuses only

**Benefits:**
- Database rejects invalid data
- Rules documented in schema
- Independent of application logic

---

## 5. API DESIGN

### 5.1 Response Standards

**Success Response Structure:**
```
{
  "success": true,
  "data": { ... },
  "meta": {
    "timestamp": "ISO8601",
    "request_id": "uuid"
  }
}
```

**Error Response Structure:**
```
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description",
    "details": { ... }
  },
  "meta": { ... }
}
```

### 5.2 HTTP Status Codes

| Status | Use Case |
|--------|----------|
| 200 OK | Successful read, idempotent write |
| 201 Created | New resource created |
| 202 Accepted | Async task started |
| 400 Bad Request | Invalid input |
| 404 Not Found | Resource doesn't exist |
| 409 Conflict | Business rule violation |
| 422 Unprocessable Entity | Validation failed |
| 500 Internal Server Error | Unexpected error |

### 5.3 Idempotency Response

**First Request (201):**
- Process event
- Create ledger entries
- Return 201 Created

**Duplicate Request (200):**
- Detect duplicate via UNIQUE constraint
- Return 200 OK with `"idempotent": true`
- No side effects

**Why 200 not 201:**
- 201 = "resource created"
- 200 = "request successful, but resource already existed"
- Semantic correctness

---

## 6. ERROR HANDLING

### 6.1 Exception Hierarchy

**Base Exception:** `BaseAPIException`
- `ValidationException` (422) - Invalid input
- `BusinessException` (409) - Rule violation
- `NotFoundException` (404) - Resource not found
- `SystemException` (500) - Internal error

**Custom Exceptions:**
- `InsufficientBalanceException` - Payout below minimum
- `RestaurantNotFoundException` - Invalid restaurant_id
- `InvalidEventTypeException` - Unknown event type
- `DatabaseException` - DB connection/query failure

### 6.2 Error Code Taxonomy

**Format:** `DOMAIN_ENTITY_ERROR_TYPE`

**Examples:**
- `EVENT_INVALID_TYPE` - Unknown event type
- `PAYOUT_INSUFFICIENT_BALANCE` - Balance too low
- `LEDGER_BALANCE_CALCULATION_FAILED` - Balance query error
- `VALIDATION_MISSING_FIELD` - Required field absent

**Benefits:**
- Machine-readable error codes
- Consistent error structure
- Easy to document and test

### 6.3 Global Exception Handler

**Middleware Approach:**
- Catch all `BaseAPIException` instances
- Format error response consistently
- Log errors with context (request_id, stack trace)
- Return appropriate HTTP status

**Unhandled Exceptions:**
- Catch-all for unexpected errors
- Return 500 with generic message
- Log full stack trace
- Never expose internal details to client

---

## 7. SECURITY & PERFORMANCE

### 7.1 Security Measures

**Input Validation:**
- Pydantic schemas with strict types
- Regex validation for IDs and currency codes
- Range validation for amounts

**SQL Injection Prevention:**
- Parameterized queries (SQLAlchemy ORM)
- No raw SQL string concatenation
- Validated enums for types/statuses

**Rate Limiting (Future):**
- Per-IP limits on public endpoints
- Per-restaurant limits on payout generation
- Prevents abuse and DoS

**Authentication (Out of Scope):**
- JWT tokens in production
- Not implemented in technical challenge
- Architecture supports future addition

### 7.2 Performance Optimizations

**Database:**
- Connection pooling (async engine with pool size)
- Strategic indexes on hot paths
- Query optimization (avoid N+1 with joins/subqueries)

**API:**
- Async all the way (non-blocking I/O)
- Background tasks for long operations (payout generation)
- Response compression (gzip for large payloads)

**Caching (Future):**
- Redis for balance caching (invalidate on ledger write)
- Not implemented initially (premature optimization)

**Monitoring (Future):**
- Query execution time logging
- Endpoint latency tracking
- Connection pool metrics

---

## RELATED DOCUMENTS

- [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) - 10 Architecture Decision Records
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - Complete schema specification

---

**Conclusion:** This architecture balances production-grade practices with pragmatic simplicity. We use proven patterns (layered architecture, repository, DI) while avoiding over-engineering (no event sourcing, CQRS, or message queues). The result: professional, testable, maintainable code.
