# Restaurant Ledger Microservice

Financial reconciliation system with guaranteed idempotency and ledger-based balance calculation.

---

## Table of Contents

- [Overview](#overview)
- [Technology Stack](#technology-stack)
- [Setup](#setup)
- [How to Run Tests](#how-to-run-tests)
- [API Endpoints](#api-endpoints)
- [Database Schema](#database-schema)
- [Refund Policy](#refund-policy)
- [Idempotency Guarantee](#idempotency-guarantee)
- [Balance Calculation](#balance-calculation)
- [AI Tools Usage](#ai-tools-usage)
- [Decisions](#decisions)
- [Limitations](#limitations)
- [Project Structure](#project-structure)
- [SQL Queries](#sql-queries-q1-q4)
- [Documentation](#documentation)

---

## Overview

Microservice that processes payment processor webhooks, maintains an immutable ledger, and generates payouts for restaurant accounts.

**Key Features:**
- Database-level idempotency (UNIQUE constraint on event_id)
- Ledger-based accounting (balance calculated, never stored)
- Async payout generation with row locking
- Advanced SQL queries (CTEs, window functions, anti-joins)

---

## Technology Stack

- **Python 3.11+** with FastAPI (async)
- **PostgreSQL 17** with asyncpg
- **SQLAlchemy 2.0** (async ORM)
- **Alembic** for migrations
- **pytest** for testing
- **Prometheus** for metrics

---

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 17
- Docker (optional)

### Installation

```bash
# Clone repository
git clone https://github.com/JosephAparicio/manage_restaurant.git
cd manage_restaurant

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your database credentials
```

### Database Setup

```bash
# Using Docker
docker-compose up --build

# Run migrations
docker-compose exec app alembic upgrade head
```

### Load Sample Data

The repository includes 100 sample events for testing:
- 100 events in PEN
- Mix of charge_succeeded, refund_succeeded, payout_paid

```bash
# Load events from JSONL file (required by PDF specification)
python -m scripts.load_events --file events/events.jsonl --url http://localhost:8000

# Expected output: 100 events processed
```

**Optional: Additional data population**

```bash
# Generate payouts for restaurants with available balance
python -m scripts.seed_payouts

# Run SQL validation queries (Q1-Q4 from deliverables)
python -m scripts.test_queries
```

### Run Application

```bash
# Development
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**API Documentation:** http://localhost:8000/docs

---

## How to Run Tests

```bash
docker-compose exec app alembic upgrade head
docker-compose exec app python -m pytest tests/ --cov=app --cov-report=html --cov-report=term-missing
```

Open coverage report: `htmlcov/index.html`

**Manual Testing (Alternative):**
```bash
# 1. Start application
docker-compose up

# 2. Load sample events
python -m scripts.load_events --file events/events.jsonl --url http://localhost:8000

# 3. Test Prometheus metrics
python scripts/test_metrics.py

# 4. Run SQL validation queries
python -m scripts.test_queries
```

**Test Coverage:**
- ✅ **29 tests total**: 22 integration + 3 e2e + 4 SQL queries
- ✅ **77% coverage** (710 statements)
- ✅ **All critical paths tested**: idempotency, balance calculation, refunds, concurrent payouts

---

## API Endpoints

### Notes about the PDF vs this API

The PDF uses example field names like `amount` and `fee`. This service uses explicit cent-based names to avoid ambiguity:

- `amount` (PDF) → `amount_cents` (API)
- `fee` (PDF) → `fee_cents` (API)
- `timestamp` (PDF examples) → `occurred_at` (API)

The PDF examples are treated as illustrative. This repository keeps the same data types and semantics (integer amounts in cents, no floats), while using more explicit field names.

This API also includes a `meta` object in responses for traceability:
- `meta.timestamp`: server-side response time in ISO 8601
 - `meta.request_id`: unique identifier useful for debugging/log correlation

### POST /v1/processor/events
Process webhook events (idempotent: 201 first time, 200 if duplicate)

**Request:**
```json
{
  "event_id": "evt_charge_001",
  "event_type": "charge_succeeded",
  "restaurant_id": "res_001",
  "amount_cents": 10000,
  "fee_cents": 300,
  "metadata": {
    "reservation_id": "rsv_987",
    "payment_id": "pay_456"
  },
  "occurred_at": "2025-12-31T10:00:00Z",
  "currency": "PEN"
}
```

### GET /v1/restaurants/{id}/balance
Get calculated balance from ledger

**Response fields (implementation contract):**
- `available_cents`: matured funds available for payout (integer cents)
- `pending_cents`: not-yet-matured funds (integer cents)
- `total_cents`: `available_cents + pending_cents` (integer cents)
- `last_event_at`: server-side timestamp when the most recent processor event was recorded/processed for this restaurant (nullable)
- `meta`: traceability metadata (see above)

### POST /v1/payouts/run
Run payout generation for all restaurants in a currency as of a given date (async background task)

**Request fields (implementation contract):**
- `currency`: ISO 4217 currency code (default `PEN`)
- `as_of`: date used for payout run idempotency and reporting
- `min_amount`: minimum eligible available balance (integer cents)

This endpoint is asynchronous and returns HTTP 202 immediately.

### GET /v1/payouts/{payout_id}

**Response fields (implementation contract):**
- `id`: payout identifier (integer)
- `restaurant_id`: restaurant identifier
- `currency`: ISO 4217 currency code
- `amount_cents`: payout amount (integer cents)
- `status`: `created | processing | paid | failed`
- `created_at`, `paid_at`: timestamps
- `items`: breakdown line items with:
  - `item_type`: category (e.g. `net_sales`, `fees`, `refunds`)
  - `amount_cents`: signed integer cents (credits positive, debits negative)
- `meta`: traceability metadata (see above)

### GET /health
Health check

### GET /metrics
Prometheus metrics endpoint:

**Business Metrics:**
- `restaurant_events_total{event_type}` - Events by type
- `restaurant_ledger_entries_total{entry_type}` - Ledger entries by type
- `restaurant_balance_total` - Current total balance (PEN cents)
- `restaurant_payouts_total{status}` - Payouts by status

**HTTP Metrics:** Auto-instrumented (requests, latency, status codes)

---

## Database Schema

**4 Core Tables:**
- `restaurants` - Master restaurant data
- `processor_events` - Webhook log (UNIQUE constraint on event_id)
- `ledger_entries` - Immutable ledger (balance source)
- `payouts` - Payout records

**Files:** [`sql/schema.sql`](sql/schema.sql) | [`sql/indexes.sql`](sql/indexes.sql)  
**Complete design:** [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md)

---

## Refund Policy

**When a charge is refunded, the commission is NOT refunded to the restaurant.**

**Rationale:**
- Industry standard (Stripe, PayPal), work already performed, prevents abuse

**Example:** Charge $100 → Restaurant gets $95 | Refund $100 → Restaurant owes $5.30

**Complete justification:** [ADR-003: Commission NOT Refunded](docs/DESIGN_DECISIONS.md#adr-003-commission-not-refunded-on-refunds)

---

## Idempotency Guarantee

**How it works:** Database-level UNIQUE constraint on `processor_events.event_id`

**Flow:**
1. Receive webhook → Try INSERT into processor_events
2. Success → Create ledger entries → Return 201
3. Unique violation → Already processed → Return 200

**Why database-level?** Race condition safe, no Redis needed, mathematically impossible to duplicate

**Complete explanation:** [ADR-002: Database-Level Idempotency](docs/DESIGN_DECISIONS.md#adr-002-database-level-idempotency)

---

## Balance Calculation

**Balance is ALWAYS calculated from ledger, never stored.**

**Why?** Absolute correctness over performance, complete audit trail, simpler concurrency

**Trade-off:** Slightly slower reads (< 5ms with indexes)

**Complete explanation:** [ADR-001: Ledger-Based Balance](docs/DESIGN_DECISIONS.md#adr-001-ledger-based-balance-no-balance-column)

---

## 5.3 Query performance (short answers)

**Which indexes did you add and what query benefits from each?**
- `idx_processor_events_event_id` (UNIQUE): idempotency for `POST /v1/processor/events`.
- `idx_ledger_restaurant_currency`: speeds up balance aggregation for `GET /v1/restaurants/{id}/balance`.
- `idx_ledger_available_at` (partial): speeds up maturity-window filtering (available vs pending funds).
- `idx_payouts_pending` (partial): speeds up payout eligibility checks (avoid duplicate pending payouts).
- `idx_payouts_as_of`: speeds up payout batch idempotency checks by `(currency, as_of)`.

**What would become slow at scale without indexes?**
- Balance reads would degrade into full scans over `ledger_entries`.
- Idempotency checks would be slower and less reliable under concurrency without the UNIQUE index.
- Payout eligibility and pending-payout checks would degrade as `payouts` grows.
- Maturity-window filters would degrade as `ledger_entries` grows.

**How do you prevent double-processing under concurrency (idempotency + payouts)?**
- Events: DB UNIQUE constraint on `processor_events.event_id`.
- Payout runs: DB UNIQUE constraint on `(restaurant_id, currency, as_of)` plus pending payout checks per `(restaurant_id, currency)`.

---
## AI Tools Usage

**Tool:** GitHub Copilot with Claude Sonnet 4.5

**Development Approach:**
- AI was used as a coding assistant to accelerate syntax and boilerplate generation
- All architectural decisions, design patterns, and business logic were developer-guided
- Developer maintained control over: schema design, idempotency strategy, testing priorities, and all technical trade-offs
- All AI suggestions were reviewed, validated, and corrected by the developer
- The developer ensured code quality, adherence to best practices, and requirement compliance

**Disclosure:** This project was developed with AI assistance. The AI served as a productivity tool while the developer retained full responsibility for all technical decisions and implementation quality.

---

## Decisions

**Key technical decisions made during development:**

1. **Calculated balance (not stored)** - Correctness over performance | [ADR-001](docs/DESIGN_DECISIONS.md#adr-001-ledger-based-balance-no-balance-column)
2. **DB-level idempotency** - UNIQUE constraint, no Redis | [ADR-002](docs/DESIGN_DECISIONS.md#adr-002-database-level-idempotency)
3. **Commission not refunded** - Industry standard | [ADR-003](docs/DESIGN_DECISIONS.md#adr-003-commission-not-refunded-on-refunds)
4. **BIGINT for money** - Cents as integers (no floats) | [ADR-004](docs/DESIGN_DECISIONS.md#adr-004-integer-money-bigint-cents)
5. **Row locking for payouts** - SELECT FOR UPDATE prevents overdraft | [ADR-005](docs/DESIGN_DECISIONS.md#adr-005-row-locking-for-payout-generation)
6. **Async-first** - All endpoints async | [ADR-007](docs/DESIGN_DECISIONS.md#adr-007-async-first-architecture)
7. **No database triggers** - Logic in application | [ADR-008](docs/DESIGN_DECISIONS.md#adr-008-no-triggers-in-database)

**Complete ADRs:** [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md)

---

## Limitations

**Current limitations (technical challenge scope):**
1. No authentication (production needs JWT)
2. No retry logic (production needs Celery)
3. Single DB instance (production needs read replicas)
4. No rate limiting (production needs throttling)
5. No webhook signature verification (production needs HMAC)

**Complete analysis:** [PLAN.md Section 6](PLAN.md#6-known-trade-offs--out-of-scope)

---

## Project Structure

```
app/                 # Application package (FastAPI app, routers, services)
  api/               # HTTP layer (routers, request/response handling)
    v1/              # Versioned API endpoints
  core/              # Settings and shared enums
  db/                # Persistence layer (models, repositories, session)
    models/          # SQLAlchemy ORM models
    repositories/    # Database access methods
  schemas/           # Pydantic schemas (validation + API contracts)
  services/          # Business logic (event processing, ledger, payouts)
docs/                # Architecture notes, API docs, DB design rationale
sql/                 # Raw SQL deliverables (schema, indexes, queries)
scripts/             # Local tooling (load dataset, run queries, seed helpers)
tests/               # Integration/E2E tests
  integration/       # API + DB integration tests
  e2e/               # End-to-end workflows
  utils/             # Test helpers/factories
alembic/             # Database migrations
events/              # Dataset (JSONL)
```

---

## SQL Queries (Q1-Q4)
Advanced PostgreSQL queries demonstrating:
- **Q1:** Restaurant balances by currency
- **Q2:** Top 10 restaurants by net revenue (last 7 days)
- **Q3:** Payout eligibility (min amount + idempotency by as_of)
- **Q4:** Data integrity checks

**File:** [`sql/queries.sql`](sql/queries.sql)

---

## Documentation

- **[PLAN.md](PLAN.md)** - Development plan (schema, idempotency, endpoints, payouts, testing, trade-offs)
- **[docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md)** - 10 Architecture Decision Records
- **[docs/ARCHITECTURE_STRATEGY.md](docs/ARCHITECTURE_STRATEGY.md)** - Complete

---
**Last Updated:** January 3, 2026