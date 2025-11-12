"""Health check endpoints for the Cooper API."""

from fastapi import APIRouter

from workflow.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health_check() -> dict[str, str]:
    """
    Health check endpoint.

    Returns:
        Status response indicating API is healthy
    """
    logger.debug("Health check (liveness) request received")
    return {"status": "healthy"}


@router.get("/ready")
async def readiness_check() -> dict[str, str]:
    """
    Readiness check endpoint.

    Indicates whether the API is ready to handle requests.

    Returns:
        Status response indicating API readiness
    """
    logger.debug("Readiness check request received")
    return {"status": "ready"}
