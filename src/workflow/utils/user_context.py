"""
User context management using contextvars for async-safe user tracking.

This module provides context variables for storing and retrieving user identity
across async operations without manual parameter passing. The user_id is extracted
from JWT authentication (sub claim) and automatically propagated throughout the
request lifecycle.

Usage Pattern:
    1. JWT authentication extracts user_id from token's sub claim
    2. set_user_context(user_id) stores in context variable
    3. get_user_context() retrieves from anywhere in call stack
    4. JSONFormatter auto-injects into all logs
    5. ChainState includes user_id for workflow tracking

Benefits:
    - Async-safe: Automatic isolation per request via contextvars
    - Zero boilerplate: No manual parameter passing needed
    - Multi-tenant support: Filter logs and metrics by user
    - Security auditing: Track all user actions for compliance
"""

from contextvars import ContextVar

# Define ContextVar for user_id with string | None type
_user_context_var: ContextVar[str | None] = ContextVar("user_context", default=None)


def set_user_context(user_id: str) -> None:
    """
    Set the current user ID in context for automatic propagation.

    Stores the user ID in the context variable so it can be retrieved
    from any async operation within the same async context. This is typically
    called at the JWT authentication boundary after extracting the sub claim.

    The stored user_id is automatically injected into:
    - All log entries via JSONFormatter
    - LangGraph ChainState for workflow tracking
    - Any code that calls get_user_context()

    Args:
        user_id: The user identifier to store (typically from JWT sub claim)

    Example:
        >>> set_user_context("alice@example.com")
        >>> # All subsequent logs will include user_id field automatically
    """
    _user_context_var.set(user_id)


def get_user_context() -> str | None:
    """
    Get the current user ID from context.

    Retrieves the user ID from the context variable. Returns None if
    no user ID has been set in the current context (e.g., unauthenticated
    requests or before authentication occurs).

    This function is called by:
    - JSONFormatter to auto-inject user_id into logs
    - Workflow initialization to populate ChainState
    - Any code needing to access the current user identity

    Returns:
        The stored user ID (from JWT sub claim), or None if not set

    Example:
        >>> user_id = get_user_context()
        >>> if user_id:
        ...     print(f"Processing request for user: {user_id}")
    """
    return _user_context_var.get()
