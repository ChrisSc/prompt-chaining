"""
Request size validation middleware.

Validates incoming request body size before processing.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from orchestrator_worker.utils.logging import get_logger

logger = get_logger(__name__)


async def request_size_validator(request: Request, call_next):  # type: ignore
    """Middleware to validate request body size.

    Checks Content-Length header against configured maximum.
    Returns 413 Payload Too Large if exceeded.
    Skips health endpoints.

    Args:
        request: FastAPI Request object
        call_next: Next middleware/route handler

    Returns:
        Response from next middleware/route handler or 413 error response
    """
    # Skip validation for GET requests (no body) and health endpoints
    if request.method == "GET":
        return await call_next(request)

    if request.url.path.startswith("/health/"):
        return await call_next(request)

    # Get settings from app state
    settings = request.app.state.settings

    # Get Content-Length header
    content_length_header = request.headers.get("content-length")

    # If no Content-Length header, allow request to proceed
    # FastAPI's body parsing will handle size limits
    if content_length_header is None:
        return await call_next(request)

    try:
        content_length = int(content_length_header)
    except ValueError:
        # Invalid Content-Length header, allow request to proceed
        return await call_next(request)

    # Check if content length exceeds maximum
    if content_length > settings.max_request_body_size:
        logger.warning(
            "Request body too large",
            extra={
                "actual_size": content_length,
                "max_size": settings.max_request_body_size,
                "path": request.url.path,
                "method": request.method,
            },
        )
        return JSONResponse(
            status_code=413,  # Payload Too Large
            content={
                "error": "request_too_large",
                "message": f"Request body size ({content_length} bytes) exceeds maximum allowed ({settings.max_request_body_size} bytes)",
                "actual_size_bytes": content_length,
                "max_size_bytes": settings.max_request_body_size,
            },
        )

    # Log successful validation at DEBUG level
    logger.debug(
        "Request size validation passed",
        extra={
            "content_length": content_length,
            "max_size": settings.max_request_body_size,
            "path": request.url.path,
            "method": request.method,
        },
    )

    return await call_next(request)
