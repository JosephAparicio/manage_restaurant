import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import AsyncSessionLocal  # type: ignore
from sqlalchemy import text


async def reset_database():
    """Resets the database completely.

    Performs the following operations:
        1. Truncates all tables
        2. Resets sequences and IDs
        3. Clears audit data

    Returns:
        bool: True if reset was successful, False otherwise.
    """
    print("Starting database reset...")
    print("-" * 60)

    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("SET session_replication_role = 'replica';"))

            tables = [
                ("payouts", "Payouts"),
                ("ledger_entries", "Ledger Entries"),
                ("processor_events", "Processor Events"),
                ("restaurants", "Restaurants"),
            ]

            for table_name, display_name in tables:
                await session.execute(
                    text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE;")
                )
                print(f"Truncated table: {display_name}")

            await session.execute(text("SET session_replication_role = 'origin';"))

            await session.commit()
            print("-" * 60)
            print("Database reset successful")
            print("\nCurrent state:")

            for table_name, display_name in tables:
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")
                )
                count = result.scalar()
                print(f"  {display_name}: {count} records")

            return True

        except Exception as e:
            await session.rollback()
            print(f"\nError during reset: {e}")
            return False


async def confirm_reset() -> bool:
    """Prompts user for confirmation before resetting database.

    Returns:
        bool: True if user confirms, False otherwise.
    """
    print("\nWARNING: This operation will delete ALL data")
    print("Only use in development/testing environments")
    print("\nDo you want to continue? (yes/no): ", end="")

    response = input().strip().lower()
    return response in ["yes", "y"]


async def main():
    """Main function to reset database."""
    print("\n" + "=" * 60)
    print("DATABASE RESET")
    print("=" * 60)

    if not await confirm_reset():
        print("\nOperation cancelled by user")
        exit(0)

    success = await reset_database()

    if success:
        print("\nReset complete. Database is clean.")
        exit(0)
    else:
        print("\nReset failed. Check logs for details.")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
