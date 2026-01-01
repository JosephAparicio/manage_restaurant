# API ENDPOINTS DOCUMENTATION
## Restaurant Ledger System

RESTful API endpoints for financial reconciliation and settlement.

---

## TABLE OF CONTENTS

1. [Base Configuration](#base-configuration)
2. [Core Endpoints](#core-endpoints)
   - [POST /v1/processor/events](#post-v1processorevents)
   - [GET /v1/restaurants/{id}/balance](#get-v1restaurantsidbalance)
   - [POST /v1/payouts/run](#post-v1payoutsrun)
   - [GET /v1/payouts/{id}](#get-v1payoutsid)
3. [Additional Endpoints](#additional-endpoints)
4. [Error Handling](#error-handling)
5. [Testing Examples](#testing-examples)

---

## BASE CONFIGURATION

**Base URL:** `http://localhost:8000`

**Default Port:** `8000`

**API Prefix:** `/v1`

---

## CORE ENDPOINTS

### POST /v1/processor/events

Process payment processor events with idempotency guarantee.

**Purpose:** Ingest events from payment processor (idempotent by `event_id`)

**Supported Event Types:**
- `charge_succeeded` - Money received from processor
- `refund_succeeded` - Money returned to customer
- `payout_paid` - Payout confirmation

**Request:**
```http
POST /v1/processor/events
Content-Type: application/json

{
  "event_id": "evt_001",
  "event_type": "charge_succeeded",
  "restaurant_id": "res_001",
  "amount_cents": 12000,
  "fee_cents": 300,
  "occurred_at": "2025-01-15T10:00:00Z",
  "currency": "PEN"
}
```

**Response - First Time (201 Created):**
```json
{
  "event_id": "evt_001",
  "event_type": "charge_succeeded",
  "restaurant_id": "res_001",
  "amount_cents": 12000,
  "fee_cents": 300,
  "occurred_at": "2025-01-15T10:00:00Z",
  "currency": "PEN",
  "idempotent": false,
  "meta": {
    "timestamp": "2025-01-15T10:00:01Z",
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**Response - Duplicate (200 OK):**
```json
{
  "event_id": "evt_001",
  "event_type": "charge_succeeded",
  "restaurant_id": "res_001",
  "amount_cents": 12000,
  "fee_cents": 300,
  "occurred_at": "2025-01-15T10:00:00Z",
  "currency": "PEN",
  "idempotent": true,
  "meta": {
    "timestamp": "2025-01-15T10:05:01Z",
    "request_id": "660f9500-f39c-52e5-b827-557766551111"
  }
}
```

**Key Features:**
- ✅ Idempotent by `event_id` (UNIQUE database constraint)
- ✅ First call returns 201, duplicate calls return 200
- ✅ Creates ledger entries automatically
- ✅ Field `idempotent` indicates if event was already processed

---

### GET /v1/restaurants/{id}/balance

Query available and pending balance for a specific restaurant.

**Purpose:** Retrieve current balance information including last event timestamp

**Request:**
```http
GET /v1/restaurants/res_001/balance?currency=PEN
```

**Query Parameters:**
- `currency` (optional): Currency code (default: `PEN`)

**Response (200 OK):**
```json
{
  "restaurant_id": "res_001",
  "currency": "PEN",
  "available_cents": 50000,
  "pending_cents": 12000,
  "total_cents": 62000,
  "last_event_at": "2025-01-15T14:30:00Z",
  "meta": {
    "timestamp": "2025-01-15T15:00:00Z",
    "request_id": "770fa611-g49d-63f6-c938-668877662222"
  }
}
```

**Field Descriptions:**
- `available_cents`: Balance available for payout (matured funds)
- `pending_cents`: Balance pending maturation (with maturity window)
- `total_cents`: Sum of available + pending
- `last_event_at`: Timestamp of last processed event for this restaurant (nullable)

**Balance Calculation:**
- Calculated in real-time from `ledger_entries` table
- No mutable balance column (ledger-based approach)
- Uses database indexes for performance

---

### POST /v1/payouts/run

Trigger asynchronous batch process to generate payouts for restaurants.

**Purpose:** Start background task to create payouts for eligible restaurants

**Request:**
```http
POST /v1/payouts/run
Content-Type: application/json

{
  "restaurant_id": "res_001",
  "currency": "PEN"
}
```

**Response (202 Accepted):**
```json
{
  "message": "Payout process initiated",
  "restaurant_id": "res_001"
}
```

**Process Details:**
- ✅ Returns immediately with HTTP 202 Accepted
- ✅ Executes asynchronously using FastAPI BackgroundTasks
- ✅ Does not block the request

**Business Rules:**
- Minimum payout amount: 100.00 PEN (10,000 centavos)
- Cannot create payout if pending payout exists
- Only uses available balance (matured funds)

**Error Responses:**

**409 Conflict - Insufficient Balance:**
```json
{
  "success": false,
  "error": {
    "code": "PAYOUT_INSUFFICIENT_BALANCE",
    "message": "Insufficient balance for payout",
    "details": {
      "restaurant_id": "res_001",
      "available_cents": 5000,
      "required_cents": 10000
    }
  },
  "meta": {
    "timestamp": "2025-01-15T15:00:00Z",
    "path": "/v1/payouts/run"
  }
}
```

**409 Conflict - Pending Payout Exists:**
```json
{
  "success": false,
  "error": {
    "code": "PAYOUT_ALREADY_PENDING",
    "message": "Cannot create payout while another is pending",
    "details": {
      "restaurant_id": "res_001"
    }
  },
  "meta": {
    "timestamp": "2025-01-15T15:00:00Z",
    "path": "/v1/payouts/run"
  }
}
```

---

### GET /v1/payouts/{id}

Retrieve details and status of a specific payout.

**Purpose:** Query payout information by ID

**Request:**
```http
GET /v1/payouts/123
```

**Response (200 OK):**
```json
{
  "id": 123,
  "restaurant_id": "res_001",
  "amount_cents": 50000,
  "currency": "PEN",
  "status": "created",
  "created_at": "2025-01-15T15:00:00Z",
  "paid_at": null,
  "meta": {
    "timestamp": "2025-01-15T15:05:00Z",
    "request_id": "990gc833-i69f-85h8-e150-880099884444"
  }
}
```

**Payout Statuses:**
- `created` - Payout created, pending processing
- `processing` - Being sent to bank
- `paid` - Successfully completed
- `failed` - Payout failed

**Error Response (404 Not Found):**
```json
{
  "success": false,
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Payout not found: 123",
    "details": {
      "payout_id": 123
    }
  },
  "meta": {
    "timestamp": "2025-01-15T15:05:00Z",
    "path": "/v1/payouts/123"
  }
}
```

---

## ADDITIONAL ENDPOINTS

### GET /health

System health check endpoint.

**Request:**
```http
GET /health
```

**Response (200 OK):**
```json
{
  "status": "healthy"
}
```

---

## ERROR HANDLING

All error responses follow a consistent structure:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {
      "field": "additional context"
    }
  },
  "meta": {
    "timestamp": "2025-01-15T15:00:00Z",
    "path": "/v1/endpoint/path"
  }
}
```

### Error Codes Reference

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 422 | `VALIDATION_ERROR` | Invalid input data |
| 422 | `EVENT_INVALID_TYPE` | Unknown event type |
| 404 | `RESOURCE_NOT_FOUND` | Resource not found |
| 404 | `RESTAURANT_NOT_FOUND` | Restaurant ID not found |
| 409 | `PAYOUT_INSUFFICIENT_BALANCE` | Insufficient balance for payout |
| 409 | `PAYOUT_ALREADY_PENDING` | Pending payout already exists |
| 500 | `DATABASE_ERROR` | Database operation failed |
| 500 | `INTERNAL_ERROR` | Unexpected internal error |

### Global Exception Handler

The API uses a global exception handler that catches all `BaseAPIException` instances and formats them consistently. Unhandled exceptions return a generic 500 error without exposing internal details.

---

## TESTING EXAMPLES

### cURL Commands

**1. Process Event:**
```bash
curl -X POST http://localhost:8000/v1/processor/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt_001",
    "event_type": "charge_succeeded",
    "restaurant_id": "res_001",
    "amount_cents": 12000,
    "fee_cents": 300,
    "occurred_at": "2025-01-15T10:00:00Z",
    "currency": "PEN"
  }'
```

**2. Query Balance:**
```bash
curl http://localhost:8000/v1/restaurants/res_001/balance?currency=PEN
```

**3. Generate Payout (Async):**
```bash
curl -X POST http://localhost:8000/v1/payouts/run \
  -H "Content-Type: application/json" \
  -d '{
    "restaurant_id": "res_001",
    "currency": "PEN"
  }'
```

**4. Get Payout Details:**
```bash
curl http://localhost:8000/v1/payouts/1
```

**5. Health Check:**
```bash
curl http://localhost:8000/health
```

### Python httpx Examples

```python
import httpx
import asyncio

async def test_endpoints():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Process event
        response = await client.post(
            "/v1/processor/events",
            json={
                "event_id": "evt_001",
                "event_type": "charge_succeeded",
                "restaurant_id": "res_001",
                "amount_cents": 12000,
                "fee_cents": 300,
                "occurred_at": "2025-01-15T10:00:00Z",
                "currency": "PEN"
            }
        )
        print(f"Event: {response.status_code}")
        
        # Query balance
        response = await client.get("/v1/restaurants/res_001/balance")
        print(f"Balance: {response.json()}")
        
        # Generate payout
        response = await client.post(
            "/v1/payouts/run",
            json={"restaurant_id": "res_001", "currency": "PEN"}
        )
        print(f"Payout: {response.json()}")

asyncio.run(test_endpoints())
```

---

## TECHNICAL NOTES

### Idempotency

**POST /v1/processor/events** is idempotent by design:
- UNIQUE constraint on `event_id` in database
- Duplicate events return 200 OK instead of 201 Created
- Field `idempotent: true` indicates duplicate detection
- No side effects on duplicate calls (ledger entries not duplicated)

### Asynchronous Processing

**POST /v1/payouts/run** executes asynchronously:
- Uses FastAPI `BackgroundTasks` for non-blocking execution
- Returns HTTP 202 Accepted immediately
- Actual payout generation happens in background

### Money Handling

All monetary amounts are represented as integers (cents):
- Type: `BIGINT` in database
- Format: Amount in smallest currency unit (centavos for PEN)
- Example: 100.50 PEN = 10050 cents
- Avoids floating-point precision errors

### Balance Calculation

Balance is calculated in real-time from ledger entries:
- No mutable balance column in `restaurants` table
- Query uses database aggregation (`SUM`)
- Optimized with composite index on `(restaurant_id, currency)`
- Maturity window handled by `available_at` timestamp filter

### Timestamps

All timestamps are:
- Stored as `TIMESTAMPTZ` (timezone-aware)
- Generated server-side using PostgreSQL `func.now()`
- Returned in ISO 8601 format with timezone
- Example: `2025-01-15T10:00:00Z`

---

## API VERSIONING

Current version: **v1**

The API uses URL versioning (`/v1/...`) to maintain backward compatibility. Future major changes will increment the version number (`/v2/...`).
