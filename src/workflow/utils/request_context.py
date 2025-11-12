"""
Request context management using contextvars.

Provides context variables for tracking request state across async operations.
Enables propagation of request IDs through the entire request lifecycle including
API calls to external services.
"""

from contextvars import ContextVar

# Define ContextVar for request_id with string | None type
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(request_id: str) -> None:
    """
    Set the current request ID in context.

    Stores the request ID in the context variable so it can be retrieved
    from any async operation within the same async context.

    Args:
        request_id: The request ID to store in context
    """
    _request_id_var.set(request_id)


def get_request_id() -> str | None:
    """
    Get the current request ID from context.

    Retrieves the request ID from the context variable. Returns None if
    no request ID has been set in the current context.

    Returns:
        The stored request ID, or None if not set
    """
    return _request_id_var.get()
