"""
Structured logging configuration for the Template Service application.

Provides JSON-formatted logging with optional Loki integration.
"""

import json
import logging
import sys
from typing import Any

from workflow.config import Settings
from workflow.utils.request_context import get_request_id
from workflow.utils.user_context import get_user_context


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record as JSON with automatic context injection.

        Includes all standard fields plus any extra fields from record.__dict__.

        Auto-injection mechanism:
        - request_id: Retrieved from _request_id_var (contextvars) set by middleware
        - user_id: Retrieved from _user_context_var (contextvars) set at auth boundary

        This eliminates the need for manual extra={"request_id": ..., "user_id": ...}
        parameters in every log call. The context variables provide async-safe
        propagation throughout the entire request lifecycle.

        Supports token/cost tracking fields via extra parameter:
        - input_tokens, output_tokens, total_tokens
        - input_cost_usd, output_cost_usd, total_cost_usd

        Args:
            record: The log record to format

        Returns:
            JSON-formatted string with all fields serialized
        """
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Auto-inject request_id from contextvars (set by middleware)
        # The request_id is stored in _request_id_var by RequestIDMiddleware
        # and retrieved here for automatic inclusion in every log entry.
        # This enables end-to-end request tracing without manual logging.
        request_id = get_request_id()
        if request_id:
            log_data["request_id"] = request_id

        # Auto-inject user_id from contextvars (extracted from JWT sub claim)
        # The user_id is stored in _user_context_var at the JWT authentication boundary
        # (verify_bearer_token function) and retrieved here for automatic inclusion.
        # This enables multi-tenant filtering and user-specific debugging without
        # requiring manual extra={"user_id": ...} parameters in every log call.
        user_id = get_user_context()
        if user_id:
            log_data["user_id"] = user_id

        # Include all extra fields from the record (token/cost metrics, etc.)
        # Filter out standard LogRecord attributes
        standard_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "thread",
            "threadName",
            "exc_info",
            "exc_text",
            "stack_info",
            "taskName",
            "getMessage",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                log_data[key] = value

        return json.dumps(log_data)


def setup_logging(settings: Settings) -> None:
    """
    Configure logging for the application.

    Sets up console logging with appropriate format based on configuration.
    Supports both JSON and standard formats.

    Args:
        settings: Application settings containing logging configuration
    """
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, settings.log_level.upper()))

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.log_level.upper()))

    # Set formatter based on configuration
    if settings.log_format == "json":
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Log startup information
    logger.info(
        "Logging configured",
        extra={
            "log_level": settings.log_level,
            "log_format": settings.log_format,
            "environment": settings.environment,
        },
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
