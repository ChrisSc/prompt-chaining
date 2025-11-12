"""
Custom exception hierarchy for the Template Service application.

Provides domain-specific exceptions for different error scenarios.
"""


class TemplateServiceError(Exception):
    """
    Base exception for all Template Service-specific errors.

    All application errors should inherit from this class.
    """

    def __init__(self, message: str, error_code: str | None = None) -> None:
        """
        Initialize a Template Service error.

        Args:
            message: Human-readable error message
            error_code: Optional error code for categorization
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__


class ConfigurationError(TemplateServiceError):
    """
    Raised when there's an error in application configuration.

    Typically thrown during startup when settings are invalid.
    """


class ValidationError(TemplateServiceError):
    """
    Raised when input validation fails.

    Indicates that provided data doesn't meet requirements.
    """


class RequestSizeError(ValidationError):
    """Raised when request body exceeds size limit."""

    def __init__(self, actual_size: int, max_size: int) -> None:
        """
        Initialize a request size error.

        Args:
            actual_size: Actual size of request body in bytes
            max_size: Maximum allowed size in bytes
        """
        message = (
            f"Request body size ({actual_size} bytes) exceeds maximum allowed ({max_size} bytes)"
        )
        super().__init__(message, error_code="REQUEST_TOO_LARGE")
        self.actual_size = actual_size
        self.max_size = max_size


class ExternalServiceError(TemplateServiceError):
    """
    Raised when an external service (e.g., Claude API) encounters an error.

    Wraps errors from third-party services with context.
    """

    def __init__(
        self,
        message: str,
        service_name: str,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        """
        Initialize an external service error.

        Args:
            message: Human-readable error message
            service_name: Name of the external service
            status_code: Optional HTTP status code
            error_code: Optional error code from the service
        """
        super().__init__(message, error_code)
        self.service_name = service_name
        self.status_code = status_code


class AgentError(TemplateServiceError):
    """
    Raised when an agent encounters an error.

    Indicates problems during agent initialization or execution.
    """

    def __init__(
        self,
        message: str,
        agent_name: str,
        error_code: str | None = None,
    ) -> None:
        """
        Initialize an agent error.

        Args:
            message: Human-readable error message
            agent_name: Name of the agent that encountered the error
            error_code: Optional error code
        """
        super().__init__(message, error_code)
        self.agent_name = agent_name


class SessionError(TemplateServiceError):
    """
    Raised when there's an error managing user sessions.

    Indicates problems with session creation, retrieval, or management.
    """


class StreamingTimeoutError(TemplateServiceError):
    """
    Raised when a streaming operation exceeds its configured timeout.

    Indicates that worker coordination or synthesis phases took too long to complete.
    """

    def __init__(self, phase: str, timeout_seconds: int) -> None:
        """
        Initialize a streaming timeout error.

        Args:
            phase: The phase that timed out (e.g., "worker coordination", "synthesis")
            timeout_seconds: The timeout duration in seconds
        """
        message = f"Streaming operation timed out during {phase} phase after {timeout_seconds}s"
        super().__init__(message, error_code="STREAMING_TIMEOUT")
        self.phase = phase
        self.timeout_seconds = timeout_seconds
        self.status_code = 504  # Gateway Timeout


class CircuitBreakerOpenError(TemplateServiceError):
    """
    Raised when circuit breaker is open and preventing calls.

    Indicates too many consecutive failures have occurred and the circuit is open
    to prevent further load on the failing service.
    """

    def __init__(self, service_name: str, failure_count: int) -> None:
        """
        Initialize a circuit breaker open error.

        Args:
            service_name: Name of the service with open circuit
            failure_count: Number of consecutive failures
        """
        message = f"Circuit breaker open for {service_name} after {failure_count} failures"
        super().__init__(message, error_code="CIRCUIT_BREAKER_OPEN")
        self.service_name = service_name
        self.failure_count = failure_count
        self.status_code = 503  # Service Unavailable


class RetryableAPIError(ExternalServiceError):
    """
    Base class for retryable external API errors.

    Indicates transient errors that may succeed on retry.
    """


class AnthropicRateLimitError(RetryableAPIError):
    """Raised when Anthropic API rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(
            message=message,
            service_name="anthropic",
            status_code=429,
            error_code="RATE_LIMIT_EXCEEDED",
        )


class AnthropicServerError(RetryableAPIError):
    """Raised when Anthropic API returns server error (5xx)."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(
            message=message,
            service_name="anthropic",
            status_code=status_code,
            error_code="API_SERVER_ERROR",
        )


class AnthropicTimeoutError(RetryableAPIError):
    """Raised when Anthropic API request times out."""

    def __init__(self, message: str = "API request timed out") -> None:
        super().__init__(
            message=message,
            service_name="anthropic",
            status_code=504,
            error_code="API_TIMEOUT",
        )


class AnthropicConnectionError(RetryableAPIError):
    """Raised when connection to Anthropic API fails."""

    def __init__(self, message: str = "Connection failed") -> None:
        super().__init__(
            message=message,
            service_name="anthropic",
            status_code=503,
            error_code="CONNECTION_ERROR",
        )
