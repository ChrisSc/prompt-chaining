"""Models listing endpoint for OpenAI-compatible API."""

from fastapi import APIRouter, Depends, Request, Response

from workflow.api.dependencies import verify_bearer_token
from workflow.api.limiter import limiter
from workflow.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["models"])


@router.get("/models", response_model=dict)
@limiter.limit("60/minute")
async def list_models(
    request: Request,
    response: Response,
    token: dict = Depends(verify_bearer_token),
) -> dict:
    """
    List available models.

    Returns a list of available models compatible with the OpenAI API.

    Args:
        request: FastAPI request object

    Returns:
        Dictionary containing list of available models
    """
    # Extract user info from JWT token
    user_subject = token.get("sub", "unknown")

    logger.info("Models list requested", extra={"user": user_subject})
    logger.debug(
        "Models list request details",
        extra={
            "user": user_subject,
            "client": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", "unknown"),
        },
    )

    # Get available models from app state
    settings = request.app.state.settings
    chain_config = settings.chain_config
    models = []

    if chain_config:
        # Use the analyze model as the primary model for this service
        models.append(
            {
                "id": settings.service_model_name,  # Display name from config
                "object": "model",
                "created": 1762232400,  # Unix timestamp for November 4, 2025
                "owned_by": "Christopher Scragg",
                "permission": {},
                "root": chain_config.analyze.model,  # Underlying Claude model from chain config
                "parent": {},
            }
        )

    logger.debug(f"Returning {len(models)} model(s)", extra={"model_count": len(models)})

    return {"object": "list", "data": models}
