from typing import Any, Optional


class BaseAPIException(Exception):
    """
    Base exception for all API errors.

    Provides consistent structure with status_code, error_code, and details.
    """

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        if error_code:
            self.error_code = error_code
        self.details = details or {}


class ValidationException(BaseAPIException):
    """Invalid input data (HTTP 422)."""

    status_code = 422
    error_code = "VALIDATION_ERROR"


class BusinessException(BaseAPIException):
    """Business rule violation (HTTP 409)."""

    status_code = 409
    error_code = "BUSINESS_RULE_VIOLATION"


class NotFoundException(BaseAPIException):
    """Resource not found (HTTP 404)."""

    status_code = 404
    error_code = "RESOURCE_NOT_FOUND"


class SystemException(BaseAPIException):
    """Internal system error (HTTP 500)."""

    status_code = 500
    error_code = "SYSTEM_ERROR"


# Domain-specific exceptions
class InsufficientBalanceException(BusinessException):
    """Payout amount exceeds available balance."""

    error_code = "PAYOUT_INSUFFICIENT_BALANCE"

    def __init__(self, restaurant_id: str, available: int, required: int):
        super().__init__(
            message=f"Insufficient balance for payout",
            details={
                "restaurant_id": restaurant_id,
                "available_cents": available,
                "required_cents": required,
            },
        )


class PendingPayoutException(BusinessException):
    """Cannot create payout while another is pending."""

    error_code = "PAYOUT_ALREADY_PENDING"

    def __init__(self, restaurant_id: str):
        super().__init__(
            message=f"Cannot create payout while another is pending",
            details={"restaurant_id": restaurant_id},
        )


class RestaurantNotFoundException(NotFoundException):
    """Restaurant ID not found in database."""

    error_code = "RESTAURANT_NOT_FOUND"

    def __init__(self, restaurant_id: str):
        super().__init__(
            message=f"Restaurant not found: {restaurant_id}",
            details={"restaurant_id": restaurant_id},
        )


class InvalidEventTypeException(ValidationException):
    """Unknown or unsupported event type."""

    error_code = "EVENT_INVALID_TYPE"

    def __init__(self, event_type: str):
        super().__init__(
            message=f"Invalid event type: {event_type}",
            details={"event_type": event_type},
        )


class DatabaseException(SystemException):
    """Database connection or query failure."""

    error_code = "DATABASE_ERROR"

    def __init__(self, message: str, operation: Optional[str] = None):
        super().__init__(
            message=message, details={"operation": operation} if operation else {}
        )


class DuplicateEventException(BusinessException):
    """Event already processed (idempotency check)."""

    error_code = "EVENT_DUPLICATE"

    def __init__(self, event_id: str):
        super().__init__(
            message=f"Event already processed: {event_id}",
            details={"event_id": event_id, "idempotent": True},
        )
