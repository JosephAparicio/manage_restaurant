from enum import Enum


class EventType(str, Enum):
    CHARGE_SUCCEEDED = "charge_succeeded"
    REFUND_SUCCEEDED = "refund_succeeded"
    PAYOUT_PAID = "payout_paid"


class EntryType(str, Enum):
    SALE = "sale"
    COMMISSION = "commission"
    REFUND = "refund"
    PAYOUT_RESERVE = "payout_reserve"


class PayoutStatus(str, Enum):
    CREATED = "created"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"
