"""Authentication dependencies for FastAPI endpoints.

Provides JWT bearer token verification for securing API endpoints.
"""

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from workflow.config import Settings
from workflow.utils.circuit_breaker import CircuitBreaker
from workflow.utils.logging import get_logger
from workflow.utils.user_context import set_user_context

logger = get_logger(__name__)

# HTTPBearer security scheme
security = HTTPBearer()


# Global circuit breaker instance for Anthropic API calls
def _init_circuit_breaker() -> CircuitBreaker:
    """Initialize circuit breaker with settings from the config."""
    settings = Settings()
    return CircuitBreaker(
        service_name="anthropic",
        failure_threshold=settings.circuit_breaker_failure_threshold,
        timeout=settings.circuit_breaker_timeout,
        half_open_attempts=settings.circuit_breaker_half_open_attempts,
    )


circuit_breaker = _init_circuit_breaker()


async def verify_bearer_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(lambda: Settings()),
) -> dict:
    """
    Verify JWT bearer token from Authorization header.

    Extracts Bearer token from Authorization header, validates JWT signature,
    and returns decoded token payload.

    Args:
        credentials: HTTPAuthorizationCredentials from Authorization header
        settings: Application settings containing JWT configuration

    Returns:
        Decoded JWT token payload as dictionary

    Raises:
        HTTPException: 401 if token is missing or expired
        HTTPException: 403 if token signature is invalid
    """
    token = credentials.credentials

    # Validate JWT_SECRET_KEY is properly configured (security critical)
    if not settings.jwt_secret_key or len(settings.jwt_secret_key) < 32:
        logger.critical(
            "JWT_SECRET_KEY is missing or too short - authentication system compromised",
            extra={
                "key_length": len(settings.jwt_secret_key) if settings.jwt_secret_key else 0,
                "minimum_length": 32,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Authentication system misconfigured",
        )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )

        # Store user context at the authentication boundary for automatic propagation
        # The user_id is extracted from the JWT "sub" claim and stored in a ContextVar.
        # This enables:
        # 1. Automatic injection into all logs via JSONFormatter (no manual logging)
        # 2. Propagation to LangGraph ChainState for workflow tracking
        # 3. Multi-tenant filtering and user-specific debugging across the entire request
        user_id = payload.get("sub", "unknown")
        set_user_context(user_id)

        logger.debug(
            "JWT token verified successfully",
            extra={"subject": user_id},
        )
        return payload

    except jwt.ExpiredSignatureError as exc:
        logger.warning("JWT token verification failed: token expired")
        raise HTTPException(
            status_code=401,
            detail="Token has expired",
        ) from exc

    except jwt.InvalidTokenError as exc:
        logger.warning(
            "JWT token verification failed: invalid token",
            extra={"error": str(exc)},
        )
        raise HTTPException(
            status_code=403,
            detail="Invalid authentication credentials",
        ) from exc

    except Exception as exc:
        logger.error(
            "Unexpected error during JWT verification",
            extra={"error": str(exc)},
        )
        raise HTTPException(
            status_code=403,
            detail="Authentication verification failed",
        ) from exc
