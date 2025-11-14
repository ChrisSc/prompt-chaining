"""
Circuit breaker pattern and retry logic for external API calls.

Provides resilient API call handling with:
- Circuit breaker state management
- Exponential backoff retry logic
- Comprehensive error handling and logging
"""

import logging
from collections.abc import Callable
from enum import Enum
from time import time
from typing import Any, TypeVar

from tenacity import (
    after_log,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from workflow.config import Settings
from workflow.utils.errors import (
    AnthropicConnectionError,
    AnthropicRateLimitError,
    AnthropicServerError,
    AnthropicTimeoutError,
    CircuitBreakerOpenError,
)
from workflow.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, calls allowed
    OPEN = "open"  # Too many failures, calls blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker for external API calls.

    Prevents cascading failures by temporarily blocking calls to a failing service.
    Transitions between CLOSED -> OPEN -> HALF_OPEN -> CLOSED states based on
    success/failure rates.
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 3,
        timeout: int = 30,
        half_open_attempts: int = 1,
    ) -> None:
        """
        Initialize circuit breaker.

        Args:
            service_name: Name of the service being protected
            failure_threshold: Consecutive failures before opening circuit
            timeout: Seconds to wait before attempting half-open state
            half_open_attempts: Number of successful attempts needed to close circuit
        """
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.half_open_attempts = half_open_attempts

        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.recovery_attempt_count = 0
        self.consecutive_recovery_failures = 0
        self.max_recovery_attempts = 3  # Mark as unrecoverable after 3 recovery attempts fail

        logger.info(
            f"Circuit breaker initialized for {service_name}",
            extra={
                "service": service_name,
                "failure_threshold": failure_threshold,
                "timeout": timeout,
                "half_open_attempts": half_open_attempts,
            },
        )

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset from OPEN to HALF_OPEN."""
        if self.state != CircuitBreakerState.OPEN:
            return False

        if self.last_failure_time is None:
            return False

        elapsed = time() - self.last_failure_time
        return elapsed >= self.timeout

    def record_success(self) -> None:
        """Record successful call."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            logger.debug(
                f"Circuit breaker half-open success {self.success_count}/{self.half_open_attempts}",
                extra={
                    "service": self.service_name,
                    "success_count": self.success_count,
                    "required": self.half_open_attempts,
                },
            )

            if self.success_count >= self.half_open_attempts:
                # Close circuit - service recovered
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.last_failure_time = None
                # Reset recovery failure tracking on successful recovery
                self.consecutive_recovery_failures = 0

                logger.info(
                    f"Circuit breaker closed for {self.service_name} - service recovered",
                    extra={
                        "service": self.service_name,
                        "state": self.state.value,
                        "recovery_attempt_count": self.recovery_attempt_count,
                    },
                )
        else:
            # Normal operation - reset counters
            self.failure_count = 0
            self.success_count = 0

    def record_failure(self) -> None:
        """Record failed call and log at WARNING level for circuit breaker visibility."""
        self.last_failure_time = time()

        if self.state == CircuitBreakerState.HALF_OPEN:
            # Failed during test - reopen circuit
            self.state = CircuitBreakerState.OPEN
            self.failure_count += 1
            self.success_count = 0
            self.consecutive_recovery_failures += 1
            self.recovery_attempt_count += 1

            # Check if service is unrecoverable after multiple recovery attempts
            if self.consecutive_recovery_failures >= self.max_recovery_attempts:
                logger.critical(
                    f"Circuit breaker - service deemed unrecoverable for {self.service_name}",
                    extra={
                        "service": self.service_name,
                        "state": self.state.value,
                        "consecutive_recovery_failures": self.consecutive_recovery_failures,
                        "recovery_attempt_count": self.recovery_attempt_count,
                        "max_recovery_attempts": self.max_recovery_attempts,
                        "failure_count": self.failure_count,
                    },
                )
            else:
                logger.warning(
                    f"Circuit breaker reopened for {self.service_name} - half-open test failed",
                    extra={
                        "service": self.service_name,
                        "state": self.state.value,
                        "failure_count": self.failure_count,
                        "consecutive_recovery_failures": self.consecutive_recovery_failures,
                        "recovery_attempt_count": self.recovery_attempt_count,
                    },
                )
        else:
            # CLOSED state - count failures
            self.failure_count += 1

            # Log failure at WARNING level for visibility
            logger.warning(
                f"Circuit breaker failure recorded for {self.service_name}",
                extra={
                    "service": self.service_name,
                    "failure_count": self.failure_count,
                    "threshold": self.failure_threshold,
                },
            )

            if self.failure_count >= self.failure_threshold:
                # Open circuit
                self.state = CircuitBreakerState.OPEN
                logger.error(
                    f"Circuit breaker opened for {self.service_name} - threshold exceeded",
                    extra={
                        "service": self.service_name,
                        "state": self.state.value,
                        "failure_count": self.failure_count,
                        "threshold": self.failure_threshold,
                    },
                )

    def allow_request(self) -> bool:
        """
        Check if request should be allowed.

        Returns:
            True if request can proceed, False if circuit is open

        Raises:
            CircuitBreakerOpenError: If circuit is open and blocking calls
        """
        if self.state == CircuitBreakerState.CLOSED:
            return True

        if self.state == CircuitBreakerState.OPEN:
            # Check if we should attempt reset
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                logger.info(
                    f"Circuit breaker half-open for {self.service_name} - attempting recovery",
                    extra={"service": self.service_name, "state": self.state.value},
                )
                return True

            # Circuit still open - block request
            raise CircuitBreakerOpenError(
                service_name=self.service_name,
                failure_count=self.failure_count,
            )

        # HALF_OPEN - allow request
        return True


def create_retryable_anthropic_call(
    settings: Settings,
    circuit_breaker: CircuitBreaker | None = None,
) -> Callable:
    """
    Create a retry decorator for Anthropic API calls.

    Uses tenacity for exponential backoff retry logic with:
    - Maximum retry attempts from settings
    - Exponential backoff with jitter
    - Retry on transient errors only
    - Logging of retry attempts and sleep durations

    Args:
        settings: Application settings
        circuit_breaker: Optional circuit breaker to check before calls

    Returns:
        Retry decorator function
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator to wrap async function with retry logic."""

        @retry(
            stop=stop_after_attempt(settings.retry_max_attempts),
            wait=wait_random_exponential(
                multiplier=settings.retry_exponential_multiplier,
                max=settings.retry_exponential_max,
            ),
            retry=retry_if_exception_type(
                (
                    AnthropicRateLimitError,
                    AnthropicServerError,
                    AnthropicTimeoutError,
                    AnthropicConnectionError,
                )
            ),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            after=after_log(logger, logging.DEBUG),
        )
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Wrapper function with circuit breaker check."""
            # Check circuit breaker if enabled
            if circuit_breaker and settings.circuit_breaker_enabled:
                circuit_breaker.allow_request()

            try:
                result = await func(*args, **kwargs)

                # Record success
                if circuit_breaker and settings.circuit_breaker_enabled:
                    circuit_breaker.record_success()

                return result

            except (
                AnthropicRateLimitError,
                AnthropicServerError,
                AnthropicTimeoutError,
                AnthropicConnectionError,
            ) as exc:
                # Record failure for retryable errors
                if circuit_breaker and settings.circuit_breaker_enabled:
                    circuit_breaker.record_failure()

                logger.warning(
                    f"Retryable error in {func.__name__}: {exc}",
                    extra={
                        "function": func.__name__,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
                raise

            except Exception as exc:
                # Non-retryable error - don't record as circuit breaker failure
                logger.error(
                    f"Non-retryable error in {func.__name__}: {exc}",
                    extra={
                        "function": func.__name__,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
                raise

        return wrapper

    return decorator
