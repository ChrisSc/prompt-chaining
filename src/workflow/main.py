"""
Main FastAPI application for the Template Service.

Sets up the application with all routes, middleware, and startup/shutdown logic.
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi.errors import RateLimitExceeded

from workflow.api.dependencies import circuit_breaker
from workflow.api.health import router as health_router
from workflow.api.limiter import get_limiter_status, limiter
from workflow.api.v1.chat import router as chat_router
from workflow.api.v1.models import router as models_router
from workflow.chains.graph import build_chain_graph
from workflow.config import Settings
from workflow.middleware.request_size import request_size_validator
from workflow.middleware.security_headers import security_headers_middleware
from workflow.utils.errors import (
    RequestSizeError,
    StreamingTimeoutError,
    TemplateServiceError,
)
from workflow.utils.logging import get_logger, setup_logging
from workflow.utils.request_context import set_request_id

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore
    """
    Manage application lifecycle.

    Handles startup and shutdown events for chain graph initialization.

    Args:
        app: FastAPI application instance

    Yields:
        Control during application runtime
    """
    # Startup
    logger.info("Application starting up")
    try:
        # Initialize chain graph for prompt-chaining workflow
        settings = app.state.settings
        chain_graph = build_chain_graph(settings.chain_config)
        app.state.chain_graph = chain_graph
        logger.info(
            "LangGraph chain graph initialized and compiled",
            extra={
                "analyze_model": settings.chain_analyze_model,
                "process_model": settings.chain_process_model,
                "synthesize_model": settings.chain_synthesize_model,
            },
        )

        # Log circuit breaker state dump
        cb_state_dump = circuit_breaker.get_state_dump()
        logger.info(
            "Circuit breaker initialized with state dump",
            extra={
                "step": "initialization",
                "service": "anthropic",
                **cb_state_dump,
            },
        )

        # Log rate limiter status
        limiter_status = get_limiter_status()
        logger.info(
            "Rate limiter initialized with status",
            extra={
                "step": "initialization",
                "component": "rate_limiter",
                **limiter_status,
            },
        )
    except Exception as exc:
        logger.critical(
            "Failed to initialize chain graph - application cannot start",
            extra={
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        raise

    yield

    # Shutdown
    logger.info("Application shutting down")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    # Load settings
    try:
        settings = Settings()
    except Exception as exc:
        # Cannot use logger yet - settings failed to load
        import sys

        print(f"CRITICAL: Failed to load settings: {exc}", file=sys.stderr)
        raise

    # Setup logging
    setup_logging(settings)

    # Log critical error if validation failed during settings load
    try:
        # Settings loaded successfully - validate critical fields
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        if not settings.jwt_secret_key:
            raise ValueError("JWT_SECRET_KEY is required")
    except ValueError as exc:
        logger.critical(
            f"Configuration validation failed: {exc}",
            extra={
                "error": str(exc),
                "error_type": type(exc).__name__,
                "validation_field": str(exc),
            },
            exc_info=True,
        )
        raise

    logger.info(
        "Creating FastAPI application",
        extra={
            "environment": settings.environment,
            "api_title": settings.api_title,
        },
    )

    # Create application
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description="Prompt Chaining workflow platform with OpenAI-compatible API",
        lifespan=lifespan,
    )

    # Store settings in app state
    app.state.settings = settings

    # Attach rate limiter to app state
    app.state.limiter = limiter

    # Add request ID and timing middleware (added first, executes last)
    @app.middleware("http")
    async def add_request_tracking(request: Request, call_next):  # type: ignore
        """Add request tracking with streaming-aware timing."""
        # Get request ID from header, or generate if missing or empty
        request_id = request.headers.get("X-Request-ID", "").strip()
        if not request_id:
            request_id = f"req_{int(time.time() * 1000)}"

        # Store request ID in context for propagation through async operations
        set_request_id(request_id)
        logger.debug("Request context set", extra={"request_id": request_id})

        start_time = time.time()

        response = await call_next(request)

        # For streaming, this measures "time to first byte"
        first_byte_time = time.time() - start_time

        response.headers["X-Request-ID"] = request_id

        is_streaming = isinstance(response, StreamingResponse)
        if is_streaming:
            response.headers["X-First-Byte-Time"] = str(first_byte_time)
            logger.info(
                "Streaming response initiated",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "first_byte_time": first_byte_time,
                },
            )
        else:
            response.headers["X-Response-Time"] = str(first_byte_time)
            logger.info(
                "Response completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "response_time": first_byte_time,
                },
            )

        return response

    # Add request size validation middleware
    app.middleware("http")(request_size_validator)

    # Add security headers middleware
    if settings.enable_security_headers:
        app.middleware("http")(security_headers_middleware)

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    # Add error handling
    @app.exception_handler(TemplateServiceError)
    async def workflow_error_handler(request: Request, exc: TemplateServiceError):  # type: ignore
        """Handle template service-specific exceptions."""
        logger.error(
            f"Template service error: {exc.message}",
            extra={
                "error_code": exc.error_code,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": exc.error_code,
                "message": exc.message,
            },
        )

    @app.exception_handler(RequestSizeError)
    async def request_size_error_handler(request: Request, exc: RequestSizeError) -> JSONResponse:  # type: ignore
        """Handle request size validation errors."""
        logger.warning(
            "Request body too large",
            extra={
                "actual_size": exc.actual_size,
                "max_size": exc.max_size,
                "path": str(request.url.path),
                "method": request.method,
            },
        )
        return JSONResponse(
            status_code=413,  # Payload Too Large
            content={
                "error": "request_too_large",
                "message": exc.message,
                "actual_size_bytes": exc.actual_size,
                "max_size_bytes": exc.max_size,
            },
        )

    @app.exception_handler(StreamingTimeoutError)
    async def streaming_timeout_error_handler(
        request: Request, exc: StreamingTimeoutError
    ) -> JSONResponse:  # type: ignore
        """Handle streaming timeout errors."""
        logger.error(
            f"Streaming timeout: {exc.message}",
            extra={
                "phase": exc.phase,
                "timeout_seconds": exc.timeout_seconds,
                "path": str(request.url.path),
                "method": request.method,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "streaming_timeout",
                "message": exc.message,
                "phase": exc.phase,
                "timeout_seconds": exc.timeout_seconds,
            },
        )

    @app.middleware("http")
    async def log_rate_limit_headers(request: Request, call_next):  # type: ignore
        """
        Middleware to log rate limit information for all requests.

        Provides debug visibility into rate limiting behavior across all endpoints.
        """
        response = await call_next(request)

        # Extract rate limit info from response headers
        limit = response.headers.get("X-RateLimit-Limit")
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")

        if limit and remaining:
            log_level = "warning" if response.status_code == 429 else "debug"
            log_fn = logger.warning if log_level == "warning" else logger.debug

            log_fn(
                "Rate limit checkpoint",
                extra={
                    "path": str(request.url.path),
                    "method": request.method,
                    "client": request.client.host if request.client else "unknown",
                    "status": response.status_code,
                    "limit": limit,
                    "remaining": remaining,
                    "reset": reset,
                },
            )

        return response

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:  # type: ignore
        """
        Handle rate limit exceeded errors.

        Returns HTTP 429 with Retry-After header indicating when client can retry.
        Follows slowapi documentation for custom error handlers.
        """
        logger.warning(
            "Rate limit exceeded",
            extra={
                "client": request.client.host if request.client else "unknown",
                "path": str(request.url.path),
                "method": request.method,
                "limit": str(exc.detail),
            },
        )
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": "60"},
            content={"detail": str(exc.detail)},
        )

    # Register routers
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(models_router)

    logger.info("FastAPI application created successfully")

    return app


# Create the application instance for running with FastAPI CLI
app = create_app()
