"""
Rate limiting configuration using SlowAPI.

This module initializes the rate limiter with JWT-based identification for user-specific
rate limiting, falling back to IP-based limiting for unauthenticated requests.
"""

import os

import jwt
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from workflow.utils.logging import get_logger

logger = get_logger(__name__)


def get_jwt_subject_or_ip(request: Request) -> str:
    """
    Extract rate limit key from JWT subject or fall back to IP address.

    This function provides user-specific rate limiting by extracting the 'sub' claim
    from the JWT bearer token. If no valid token is present, it falls back to IP-based
    rate limiting.

    Extraction Logic:
    1. Check for Authorization header with Bearer token
    2. Decode JWT and extract 'sub' claim (no signature verification for key function)
    3. Return formatted key: "user_{subject}"
    4. On any failure (missing token, invalid JWT, etc.), fall back to IP: "ip_{address}"

    Args:
        request: FastAPI Request object containing headers and client information

    Returns:
        str: Formatted rate limit key:
            - "user_{subject}" for authenticated requests with valid JWT
            - "ip_{client_ip}" for unauthenticated or invalid token requests

    Example:
        Valid JWT with sub="user123" -> "user_user123"
        No token or invalid token -> "ip_192.168.1.1"

    Note:
        This function does NOT verify JWT signatures for performance reasons.
        Token verification happens separately in authentication middleware.
        This function only extracts the subject for rate limit key purposes.
    """
    try:
        # Extract Authorization header
        auth_header = request.headers.get("Authorization", "")

        # Check for Bearer token format
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix

            # Decode JWT without verification (verification happens in auth middleware)
            # We only need the 'sub' claim for rate limiting purposes
            payload = jwt.decode(token, options={"verify_signature": False})

            # Extract subject claim
            subject = payload.get("sub")
            if subject:
                key = f"user_{subject}"
                logger.debug(
                    "Rate limit key resolved",
                    extra={
                        "key": key,
                        "type": "jwt_subject",
                        "subject": subject,
                        "path": str(request.url.path),
                    },
                )
                return key

    except (jwt.DecodeError, jwt.InvalidTokenError, KeyError, ValueError) as exc:
        # Any JWT decoding error falls through to IP-based fallback
        logger.debug(
            "JWT decoding failed for rate limit key, using IP fallback",
            extra={
                "error": type(exc).__name__,
                "path": str(request.url.path),
            },
        )

    # Fallback to IP-based rate limiting
    ip = get_remote_address(request)
    key = f"ip_{ip}"
    logger.debug(
        "Rate limit key resolved",
        extra={
            "key": key,
            "type": "ip_address",
            "ip": ip,
            "path": str(request.url.path),
        },
    )
    return key


# Initialize SlowAPI Limiter with JWT-based key function
# See documentation/slowapi/03_FASTAPI_GUIDE.md lines 18-38
limiter = Limiter(
    key_func=get_jwt_subject_or_ip,
    default_limits=["100/hour"],
    headers_enabled=True,  # Include X-RateLimit-* headers in responses
    enabled=os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true",  # Disable in tests
)


def get_limiter_status() -> dict[str, str | bool]:
    """
    Get a structured dump of the rate limiter's current configuration and status.

    Returns a dictionary with all relevant rate limiter configuration suitable for logging
    as structured extra fields. Useful for monitoring and debugging rate limiting behavior.

    Returns:
        Dictionary containing:
        - enabled: Whether rate limiting is active (bool)
        - default_limit: Default rate limit string (e.g., "100/hour")
        - chat_completions_limit: Rate limit for chat completions endpoint
        - models_limit: Rate limit for models endpoint
        - key_function_type: Type of key function used (jwt-based)
    """
    from workflow.config import Settings

    settings = Settings()

    return {
        "enabled": limiter.enabled,
        "default_limit": settings.rate_limit_default,
        "chat_completions_limit": settings.rate_limit_chat_completions,
        "models_limit": settings.rate_limit_models,
        "key_function_type": "jwt-based",
    }
