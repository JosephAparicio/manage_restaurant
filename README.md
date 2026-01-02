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
- **PostgreSQL 15+** with asyncpg
- **SQLAlchemy 2.0** (async ORM)
- **Alembic** for migrations
- **pytest** for testing
- **Prometheus** for metrics

---

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Docker (optional)

### Installation

```bash
# Clone repository
git clone <repository-url>
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

The repository includes 103 sample events for testing:
- 74 events in PEN (nuevo sol)
- 26 events in USD (dollars)
- Mix of charge_succeeded, refund_succeeded, payout_paid

```bash
# Load events from JSONL file (required by PDF specification)
python -m scripts.load_events --file events/events.jsonl --url http://localhost:8000

# Expected output: 103 events processed
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
docker exec -e PGPASSWORD=restaurant_pass_dev restaurant_ledger_db psql -U restaurant_user -d restaurant_ledger -c "TRUNCATE TABLE ledger_entries, processor_events, payouts, restaurants RESTART IDENTITY CASCADE;"; docker exec restaurant_ledger_api python -m pytest tests/ --cov=app --cov-report=html --cov-report=term-missing
```

Open coverage report: `htmlcov/index.html`

**Manual Testing (Alternative):**
```bash
# 1. Start application
docker-compose up

# 2. Load sample events
python -m scripts.load_events --file events/events.jsonl --url http://localhost:8000

# 3. Test API manually via docs
open http://localhost:8000/docs

# 4. Run SQL validation queries
python -m scripts.test_queries
```

**Automated Tests (Needs fixing):**
```bash
# All tests (currently failing due to async session conflicts)
pytest

# Integration tests only
pytest tests/integration/ -v

# E2E tests only  
pytest tests/e2e/ -v
```

**Test Status:**
- ✅ Application functional (validated via manual testing and sample data)
- ⏳ Automated tests need refactoring for proper async session isolation

---

## API Endpoints

### POST /v1/processor/events
Process webhook events (idempotent: 201 first time, 200 if duplicate)

**Request:**
```json
{
  "event_id": "evt_charge_001",
  "event_type": "charge_succeeded",
  "restaurant_id": "res_001",
  "amount": 10000,
  "fee": 300,
  "timestamp": "2025-12-31T10:00:00Z"
}
```

### GET /v1/restaurants/{id}/balance
Get calculated balance from ledger

### POST /v1/restaurants/{id}/payouts
Generate payout (async background task)

### GET /v1/health
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

## AI Tools Usage

**Tool:** GitHub Copilot with Claude Sonnet 4.5

**Development Approach:**
- AI was used as a coding assistant to accelerate syntax and boilerplate generation
- All architectural decisions, design patterns, and business logic were developer-guided
- Developer maintained control over: schema design, idempotency strategy, testing priorities, and all technical trade-offs
- All AI suggestions were reviewed, validated, and corrected by the developer
- The developer ensured code quality, adherence to best practices, and requirement compliance

**Disclosure:** This project was developed with AI assistance as recommended in the challenge guidelines. The AI served as a productivity tool while the developer retained full responsibility for all technical decisions and implementation quality.

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
app/
  db/
    repositories/   # Data access layer
  services/         # Business logic
  schemas/          # Pydantic schemas
docs/
  DESIGN_DECISIONS.md      # ADRs
  ARCHITECTURE_STRATEGY.md # Complete architecture
  database/                # DB design docs
sql/
  schema.sql      # DDL
  indexes.sql     # Indexes
  queries.sql     # Q1-Q4
tests/
  integration/    # Integration tests
  unit/           # Unit tests
  e2e/            # End-to-end tests
PLAN.md           # Development plan
README.md         # This file
```

---

## SQL Queries (Q1-Q4)

Advanced PostgreSQL queries demonstrating:
- **Q1:** Top 10 restaurants by volume (CTEs, window functions)
- **Q2:** Restaurants never refunded (anti-join with NOT EXISTS)
- **Q3:** Payment velocity analysis (LAG, date arithmetic)
- **Q4:** Commission accuracy check (HAVING, aggregates)

**File:** [`sql/queries.sql`](sql/queries.sql) (384 lines)

---

## Documentation

- **[PLAN.md](PLAN.md)** - Development plan (schema, idempotency, endpoints, payouts, testing, trade-offs)
- **[docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md)** - 10 Architecture Decision Records
- **[docs/ARCHITECTURE_STRATEGY.md](docs/ARCHITECTURE_STRATEGY.md)** - Complete

---
**Last Updated:** January 1, 2026