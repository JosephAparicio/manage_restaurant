#!/bin/bash
set -e

echo "=========================================="
echo "Restaurant Ledger & Payout System - Startup"
echo "=========================================="

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
until python -c "import asyncpg; import asyncio; asyncio.run(asyncpg.connect('$DATABASE_URL'.replace('+asyncpg', '')))" 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "PostgreSQL is up - executing migrations"

# Run Alembic migrations
alembic upgrade head

echo "Migrations completed successfully"
echo "=========================================="
echo "Starting FastAPI application on port 8000"
echo "=========================================="

# Start FastAPI with uvicorn
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
