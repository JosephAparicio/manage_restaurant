import asyncio
import argparse
import json
from pathlib import Path
from typing import List, Dict, Any, cast
import httpx


class EventLoader:
    def __init__(self, api_url: str, timeout: float = 30.0):
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.endpoint = f"{self.api_url}/v1/processor/events"

    async def load_events_from_file(self, file_path: Path) -> Dict[str, Any]:
        if not file_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        events = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    events.append(event)
                except json.JSONDecodeError as e:
                    print(f"Warning: JSON decode error at line {line_num}: {e}")

        print(f"Loaded {len(events)} events from {file_path.name}")
        return await self.send_events(events)

    async def send_events(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        stats: Dict[str, Any] = {
            "total": len(events),
            "success": 0,
            "failed": 0,
            "duplicate": 0,
            "errors": [],
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            print(f"\nSending {len(events)} events to {self.endpoint}")
            print("-" * 60)

            for idx, event in enumerate(events, 1):
                event_id = event.get("event_id", "unknown")
                event_type = event.get("event_type", "unknown")

                try:
                    response = await client.post(
                        self.endpoint,
                        json=event,
                        headers={"Content-Type": "application/json"},
                    )

                    if response.status_code == 201:
                        stats["success"] += 1
                        print(
                            f"[{idx}/{len(events)}] SUCCESS: {event_id} ({event_type})"
                        )
                    elif response.status_code == 200:
                        stats["duplicate"] += 1
                        print(
                            f"[{idx}/{len(events)}] DUPLICATE: {event_id} ({event_type})"
                        )
                    else:
                        stats["failed"] += 1
                        error_detail = response.text[:100]
                        print(
                            f"[{idx}/{len(events)}] FAILED: {event_id} - {response.status_code}: {error_detail}"
                        )
                        stats["errors"].append(
                            {
                                "event_id": event_id,
                                "status": response.status_code,
                                "detail": error_detail,
                            }
                        )

                except httpx.RequestError as e:
                    stats["failed"] += 1
                    print(
                        f"[{idx}/{len(events)}] ERROR: {event_id} - Connection error: {str(e)}"
                    )
                    stats["errors"].append({"event_id": event_id, "error": str(e)})

                await asyncio.sleep(0.1)

        return stats

    def print_summary(self, stats: Dict[str, Any]):
        """Prints loading results summary.

        Args:
            stats: Dictionary containing statistics from the loading process.
        """
        print("\n" + "=" * 60)
        print("LOADING SUMMARY")
        print("=" * 60)
        print(f"Total events:     {stats['total']}")
        print(f"Successful:       {stats['success']}")
        print(f"Duplicates:       {stats['duplicate']}")
        print(f"Failed:           {stats['failed']}")

        if stats["errors"]:
            print(f"\nWarning: {len(stats['errors'])} errors detected")


async def main():
    """Main function to load events from JSONL file to API."""
    parser = argparse.ArgumentParser(description="Load events from JSONL file to API")
    parser.add_argument(
        "--file", type=str, required=True, help="Path to JSONL file containing events"
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds (default: 30)",
    )

    args = parser.parse_args()
    file_path = Path(args.file)

    print(f"\nConfiguration:")
    print(f"  File:     {file_path}")
    print(f"  API URL:  {args.url}")
    print(f"  Timeout:  {args.timeout}s")

    loader = EventLoader(api_url=args.url, timeout=args.timeout)

    try:
        stats = await loader.load_events_from_file(file_path)
        loader.print_summary(stats)

        if stats["failed"] > 0:
            exit(1)
        exit(0)

    except FileNotFoundError as e:
        print(f"\nError: {e}")
        exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
