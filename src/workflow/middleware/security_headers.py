"""
Security headers middleware.

Adds security headers to all responses to protect against common web vulnerabilities.
"""

from fastapi import Request

from workflow.utils.logging import get_logger

logger = get_logger(__name__)


async def security_headers_middleware(request: Request, call_next) -> None:  # type: ignore
    """Middleware to add security headers to all responses.

    Adds the following headers to all responses:
    - X-Content-Type-Options: nosniff (always)
    - X-Frame-Options: DENY (always)
    - X-XSS-Protection: 1; mode=block (always)
    - Strict-Transport-Security: max-age=31536000; includeSubDomains (HTTPS only)

    The HSTS header is only added for HTTPS requests to avoid issues with HTTP-only
    environments. Detection includes both direct HTTPS and reverse proxy scenarios
    (via X-Forwarded-Proto header).

    Args:
        request: FastAPI Request object
        call_next: Next middleware/route handler

    Returns:
        Response with security headers added
    """
    response = await call_next(request)

    # Add security headers that apply to all requests
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Add HSTS header only for HTTPS requests
    # Check both direct HTTPS and X-Forwarded-Proto header (reverse proxy support)
    is_https = (
        request.url.scheme == "https"
        or request.headers.get("X-Forwarded-Proto", "").lower() == "https"
    )

    if is_https:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        logger.debug(
            "Security headers applied with HSTS",
            extra={
                "path": str(request.url.path),
                "scheme": request.url.scheme,
                "forwarded_proto": request.headers.get("X-Forwarded-Proto"),
            },
        )
    else:
        logger.debug(
            "Security headers applied (HSTS skipped for HTTP)",
            extra={
                "path": str(request.url.path),
                "scheme": request.url.scheme,
            },
        )

    return response
