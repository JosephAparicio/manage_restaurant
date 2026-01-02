from prometheus_client import Counter, Gauge

events_total = Counter(
    "restaurant_events_total", "Total events processed", ["event_type"]
)

ledger_entries_total = Counter(
    "restaurant_ledger_entries_total", "Total ledger entries created", ["entry_type"]
)

balance_total = Gauge(
    "restaurant_balance_total", "Current total balance across all accounts"
)

payouts_total = Counter(
    "restaurant_payouts_total", "Total payouts executed", ["status"]
)
