import asyncio
import subprocess

import httpx


async def seed_payouts():
    api_url = "http://localhost:8000"
    timeout = 30.0

    print("Starting payout generation via API...\n")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{api_url}/v1/payouts/run",
            json={"currency": "PEN", "as_of": "2025-12-27", "min_amount": 10000},
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 202:
            print("Payout batch initiated")
        else:
            error = response.text[:200]
            print(f"Failed - {response.status_code}: {error}")

    print("\n--- Verification ---")

    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "restaurant_ledger_db",
            "psql",
            "-U",
            "restaurant_user",
            "-d",
            "restaurant_ledger",
            "-c",
            "SELECT restaurant_id, amount_cents, status FROM payouts ORDER BY id;",
        ],
        capture_output=True,
        text=True,
    )
    print("\nPayouts created:")
    print(result.stdout)

    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "restaurant_ledger_db",
            "psql",
            "-U",
            "restaurant_user",
            "-d",
            "restaurant_ledger",
            "-c",
            "SELECT COUNT(*) as payout_reserve_count FROM ledger_entries WHERE entry_type = 'payout_reserve';",
        ],
        capture_output=True,
        text=True,
    )
    print("Payout reserve entries:")
    print(result.stdout)


if __name__ == "__main__":
    asyncio.run(seed_payouts())
