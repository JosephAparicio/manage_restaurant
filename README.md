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
docker-compose up -d db

# Or manually
createdb restaurant_ledger

# Run migrations
alembic upgrade head

# Load test data (optional)
python scripts/load_events.py events/events.jsonl
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
# All tests
pytest

# Integration tests only
pytest tests/integration/ -v

# With coverage
pytest --cov=app --cov-report=html

# Specific test
pytest tests/integration/test_idempotency.py -v
```

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

This project is being developed with AI assistance as disclosed per challenge requirements.

**Tool:** Claude Sonnet 4.5 (via GitHub Copilot Agent)

**Current usage:** Planning and design phase - database schema, architecture decisions, documentation structure

All AI suggestions are reviewed and validated. Design decisions based on production experience with financial systems.

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
- **[docs/ARCHITECTURE_STRATEGY.md](docs/ARCHITECTURE_STRATEGY.md)** - Complete architecture guide
- **[docs/database/](docs/database/)** - Database design documentation

---

**Last Updated:** December 31, 2025