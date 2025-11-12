"""Authentication dependencies for FastAPI endpoints.

Provides JWT bearer token verification for securing API endpoints.
"""

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from orchestrator_worker.config import Settings
from orchestrator_worker.utils.logging import get_logger

logger = get_logger(__name__)

# HTTPBearer security scheme
security = HTTPBearer()


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
        logger.debug(
            "JWT token verified successfully",
            extra={"subject": payload.get("sub", "unknown")},
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
