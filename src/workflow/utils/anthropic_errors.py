"""
Anthropic SDK exception mapping utilities.

Maps Anthropic SDK exceptions to custom error classes for consistent error handling.
"""

from anthropic import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from workflow.utils.errors import (
    AnthropicConnectionError,
    AnthropicRateLimitError,
    AnthropicServerError,
    AnthropicTimeoutError,
    ExternalServiceError,
)
from workflow.utils.logging import get_logger

logger = get_logger(__name__)


def map_anthropic_exception(exc: Exception) -> Exception:
    """
    Map Anthropic SDK exception to custom error class.

    Converts Anthropic SDK exceptions to our custom error hierarchy for
    consistent error handling and retry logic.

    Args:
        exc: Exception from Anthropic SDK

    Returns:
        Mapped custom exception (or original if unmapped)
    """
    # Rate limit errors (429)
    if isinstance(exc, RateLimitError):
        logger.debug(
            "Mapping RateLimitError to AnthropicRateLimitError",
            extra={"original_error": str(exc)},
        )
        return AnthropicRateLimitError(message=str(exc))

    # Server errors (5xx)
    if isinstance(exc, InternalServerError):
        status_code = getattr(exc, "status_code", 500)
        logger.debug(
            "Mapping InternalServerError to AnthropicServerError",
            extra={"original_error": str(exc), "status_code": status_code},
        )
        return AnthropicServerError(message=str(exc), status_code=status_code)

    # Timeout errors
    if isinstance(exc, APITimeoutError):
        logger.debug(
            "Mapping APITimeoutError to AnthropicTimeoutError",
            extra={"original_error": str(exc)},
        )
        return AnthropicTimeoutError(message=str(exc))

    # Connection errors
    if isinstance(exc, APIConnectionError):
        logger.debug(
            "Mapping APIConnectionError to AnthropicConnectionError",
            extra={"original_error": str(exc)},
        )
        return AnthropicConnectionError(message=str(exc))

    # Generic API errors that might have status codes
    if isinstance(exc, APIError):
        status_code = getattr(exc, "status_code", None)

        # Check if it's a server error based on status code
        if status_code and status_code >= 500:
            logger.debug(
                "Mapping APIError (5xx) to AnthropicServerError",
                extra={"original_error": str(exc), "status_code": status_code},
            )
            return AnthropicServerError(message=str(exc), status_code=status_code)

        # Other API errors
        logger.debug(
            "Mapping APIError to ExternalServiceError",
            extra={"original_error": str(exc), "status_code": status_code},
        )
        return ExternalServiceError(
            message=str(exc),
            service_name="anthropic",
            status_code=status_code,
            error_code="API_ERROR",
        )

    # Unknown exception - return original
    logger.debug(
        f"No mapping for exception type {type(exc).__name__}, returning original",
        extra={"error_type": type(exc).__name__, "error": str(exc)},
    )
    return exc
