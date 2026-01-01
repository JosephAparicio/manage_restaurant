import logging
import re
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.exceptions import BaseAPIException, RestaurantNotFoundException
from app.schemas.common import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


async def api_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Global handler for custom API exceptions.

    Returns structured error response with status code and error details.
    """
    assert isinstance(exc, BaseAPIException)
    logger.warning(
        f"API Exception: {exc.error_code} - {exc.message}",
        extra={
            "error_code": exc.error_code,
            "path": request.url.path,
            "method": request.method,
            "details": exc.details,
        },
    )

    error_response = ErrorResponse(
        error=ErrorDetail(
            code=exc.error_code,
            message=exc.message,
            details=exc.details if exc.details else None,
        ),
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": request.url.path,
        },
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(exclude_none=True),
    )


async def integrity_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Handle database integrity constraint violations.

    Detects foreign key violations for restaurants table and converts to
    RestaurantNotFoundException with proper error code.
    """
    assert isinstance(exc, IntegrityError)
    error_message = str(exc.orig).lower()

    if "foreign key constraint" in error_message and "restaurants" in error_message:
        restaurant_id_match = re.search(r"res_\w+", str(exc.orig))
        restaurant_id = (
            restaurant_id_match.group(0) if restaurant_id_match else "unknown"
        )

        api_exception = RestaurantNotFoundException(restaurant_id=restaurant_id)
        return await api_exception_handler(request, api_exception)

    logger.warning(
        "Database integrity error",
        extra={
            "error": str(exc.orig),
            "path": request.url.path,
            "method": request.method,
        },
    )

    error_response = ErrorResponse(
        error=ErrorDetail(
            code="INTEGRITY_ERROR",
            message="Database constraint violation",
        ),
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": request.url.path,
        },
    )

    return JSONResponse(
        status_code=409, content=error_response.model_dump(exclude_none=True)
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Catch-all handler for unexpected errors.

    Returns generic 500 error without exposing internal details.
    """
    logger.error(
        f"Unhandled exception: {type(exc).__name__}",
        exc_info=exc,
        extra={
            "path": request.url.path,
            "method": request.method,
        },
    )

    error_response = ErrorResponse(
        error=ErrorDetail(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
        ),
        meta={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": request.url.path,
        },
    )

    return JSONResponse(
        status_code=500, content=error_response.model_dump(exclude_none=True)
    )


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all global exception handlers to the FastAPI application.

    Handlers are registered in order of specificity:
    1. Custom API exceptions (BaseAPIException)
    2. Database integrity errors (IntegrityError)
    3. Unhandled exceptions (Exception)
    """
    app.add_exception_handler(
        BaseAPIException,
        api_exception_handler,
    )
    app.add_exception_handler(
        IntegrityError,
        integrity_error_handler,
    )
    app.add_exception_handler(Exception, unhandled_exception_handler)
