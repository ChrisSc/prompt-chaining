"""
Unit tests for circuit breaker functionality.

Tests the CircuitBreaker state machine, retry logic, error handling,
and integration with tenacity decorators.
"""

import asyncio
from time import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from anthropic import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from workflow.config import Settings
from workflow.utils.anthropic_errors import map_anthropic_exception
from workflow.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
    create_retryable_anthropic_call,
)
from workflow.utils.errors import (
    AnthropicConnectionError,
    AnthropicRateLimitError,
    AnthropicServerError,
    AnthropicTimeoutError,
    CircuitBreakerOpenError,
    ExternalServiceError,
)


class TestCircuitBreakerState:
    """Test CircuitBreaker state machine."""

    def test_initial_state_is_closed(self):
        """Test circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker(service_name="test-service")
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0
        assert cb.last_failure_time is None

    def test_closed_state_allows_requests(self):
        """Test CLOSED state allows requests through."""
        cb = CircuitBreaker(service_name="test-service")
        assert cb.allow_request() is True

    def test_failure_threshold_triggers_open(self):
        """Test circuit opens after failure threshold reached."""
        cb = CircuitBreaker(service_name="test-service", failure_threshold=3)

        # Record failures
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 1

        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 2

        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.failure_count == 3

    def test_open_state_blocks_requests(self):
        """Test OPEN state blocks requests with CircuitBreakerOpenError."""
        cb = CircuitBreaker(service_name="test-service", failure_threshold=2)

        # Trigger OPEN state
        cb.record_failure()
        cb.record_failure()

        assert cb.state == CircuitBreakerState.OPEN

        # Verify request is blocked
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            cb.allow_request()

        error = exc_info.value
        assert error.service_name == "test-service"
        assert error.failure_count == 2
        assert error.status_code == 503

    def test_timeout_allows_half_open_transition(self):
        """Test timeout transitions OPEN to HALF_OPEN."""
        cb = CircuitBreaker(
            service_name="test-service", failure_threshold=2, timeout=1  # 1 second timeout
        )

        # Trigger OPEN state
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        # Immediately try - should still be blocked
        with pytest.raises(CircuitBreakerOpenError):
            cb.allow_request()

        # Wait for timeout
        asyncio.run(asyncio.sleep(1.1))

        # Should transition to HALF_OPEN and allow request
        assert cb.allow_request() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_allows_single_test_request(self):
        """Test HALF_OPEN state allows test request."""
        cb = CircuitBreaker(service_name="test-service", failure_threshold=2, timeout=1)

        # Trigger OPEN state
        cb.record_failure()
        cb.record_failure()

        # Manually transition to HALF_OPEN for testing
        cb.state = CircuitBreakerState.HALF_OPEN

        # Should allow request
        assert cb.allow_request() is True

    def test_successful_request_in_half_open_closes_circuit(self):
        """Test successful request in HALF_OPEN closes circuit."""
        cb = CircuitBreaker(
            service_name="test-service",
            failure_threshold=2,
            timeout=1,
            half_open_attempts=1,
        )

        # Manually set to HALF_OPEN
        cb.state = CircuitBreakerState.HALF_OPEN

        # Record success
        cb.record_success()

        # Should transition to CLOSED
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0
        assert cb.last_failure_time is None

    def test_failed_request_in_half_open_reopens_circuit(self):
        """Test failed request in HALF_OPEN reopens circuit."""
        cb = CircuitBreaker(service_name="test-service", failure_threshold=2, timeout=1)

        # Manually set to HALF_OPEN
        cb.state = CircuitBreakerState.HALF_OPEN

        # Record failure
        cb.record_failure()

        # Should transition back to OPEN
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.failure_count == 1

    def test_multiple_successes_required_in_half_open(self):
        """Test circuit requires multiple successful attempts to close."""
        cb = CircuitBreaker(
            service_name="test-service",
            failure_threshold=2,
            timeout=1,
            half_open_attempts=3,  # Require 3 successes
        )

        # Manually set to HALF_OPEN
        cb.state = CircuitBreakerState.HALF_OPEN

        # First success - should stay HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreakerState.HALF_OPEN
        assert cb.success_count == 1

        # Second success - should stay HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreakerState.HALF_OPEN
        assert cb.success_count == 2

        # Third success - should close circuit
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.success_count == 0
        assert cb.failure_count == 0

    def test_success_in_closed_state_resets_counters(self):
        """Test success in CLOSED state resets failure count."""
        cb = CircuitBreaker(service_name="test-service", failure_threshold=3)

        # Record some failures
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

        # Record success
        cb.record_success()

        # Counters should reset
        assert cb.failure_count == 0
        assert cb.success_count == 0


class TestErrorClasses:
    """Test error class creation and attributes."""

    def test_anthropic_rate_limit_error_creation(self):
        """Test AnthropicRateLimitError attributes."""
        error = AnthropicRateLimitError(message="Rate limit exceeded")
        assert error.message == "Rate limit exceeded"
        assert error.service_name == "anthropic"
        assert error.status_code == 429
        assert error.error_code == "RATE_LIMIT_EXCEEDED"

    def test_anthropic_rate_limit_error_default_message(self):
        """Test AnthropicRateLimitError default message."""
        error = AnthropicRateLimitError()
        assert error.message == "Rate limit exceeded"
        assert error.status_code == 429

    def test_anthropic_server_error_creation(self):
        """Test AnthropicServerError attributes."""
        error = AnthropicServerError(message="Internal server error", status_code=502)
        assert error.message == "Internal server error"
        assert error.service_name == "anthropic"
        assert error.status_code == 502
        assert error.error_code == "API_SERVER_ERROR"

    def test_anthropic_server_error_default_status(self):
        """Test AnthropicServerError default status code."""
        error = AnthropicServerError(message="Server error")
        assert error.status_code == 500

    def test_anthropic_timeout_error_creation(self):
        """Test AnthropicTimeoutError attributes."""
        error = AnthropicTimeoutError(message="Request timed out")
        assert error.message == "Request timed out"
        assert error.service_name == "anthropic"
        assert error.status_code == 504
        assert error.error_code == "API_TIMEOUT"

    def test_anthropic_timeout_error_default_message(self):
        """Test AnthropicTimeoutError default message."""
        error = AnthropicTimeoutError()
        assert error.message == "API request timed out"

    def test_anthropic_connection_error_creation(self):
        """Test AnthropicConnectionError attributes."""
        error = AnthropicConnectionError(message="Connection failed")
        assert error.message == "Connection failed"
        assert error.service_name == "anthropic"
        assert error.status_code == 503
        assert error.error_code == "CONNECTION_ERROR"

    def test_anthropic_connection_error_default_message(self):
        """Test AnthropicConnectionError default message."""
        error = AnthropicConnectionError()
        assert error.message == "Connection failed"

    def test_circuit_breaker_open_error_creation(self):
        """Test CircuitBreakerOpenError attributes."""
        error = CircuitBreakerOpenError(service_name="test-service", failure_count=5)
        assert error.service_name == "test-service"
        assert error.failure_count == 5
        assert error.status_code == 503
        assert error.error_code == "CIRCUIT_BREAKER_OPEN"
        assert "test-service" in error.message
        assert "5 failures" in error.message


class TestExceptionMapping:
    """Test Anthropic exception mapping."""

    def test_map_rate_limit_error(self):
        """Test mapping RateLimitError to AnthropicRateLimitError."""
        original = RateLimitError("Rate limit hit", response=Mock(), body=None)
        mapped = map_anthropic_exception(original)

        assert isinstance(mapped, AnthropicRateLimitError)
        assert mapped.service_name == "anthropic"
        assert mapped.status_code == 429

    def test_map_internal_server_error(self):
        """Test mapping InternalServerError to AnthropicServerError."""
        original = InternalServerError("Server error", response=Mock(), body=None)
        original.status_code = 500
        mapped = map_anthropic_exception(original)

        assert isinstance(mapped, AnthropicServerError)
        assert mapped.service_name == "anthropic"
        assert mapped.status_code == 500

    def test_map_timeout_error(self):
        """Test mapping APITimeoutError to AnthropicTimeoutError."""
        original = APITimeoutError(request=Mock())
        mapped = map_anthropic_exception(original)

        assert isinstance(mapped, AnthropicTimeoutError)
        assert mapped.service_name == "anthropic"
        assert mapped.status_code == 504

    def test_map_connection_error(self):
        """Test mapping APIConnectionError to AnthropicConnectionError."""
        original = APIConnectionError(message="Connection lost", request=Mock())
        mapped = map_anthropic_exception(original)

        assert isinstance(mapped, AnthropicConnectionError)
        assert mapped.service_name == "anthropic"
        assert mapped.status_code == 503

    def test_map_api_error_with_5xx_status(self):
        """Test mapping APIError with 5xx status to AnthropicServerError."""
        # APIError constructor takes message, request, body
        mock_request = Mock()
        original = APIError("API error", request=mock_request, body=None)
        # Set status_code directly on exception instance
        object.__setattr__(original, "status_code", 502)
        mapped = map_anthropic_exception(original)

        assert isinstance(mapped, AnthropicServerError)
        assert mapped.status_code == 502

    def test_map_api_error_with_non_5xx_status(self):
        """Test mapping APIError with non-5xx status to ExternalServiceError."""
        mock_request = Mock()
        original = APIError("API error", request=mock_request, body=None)
        # Set status_code directly on exception instance
        object.__setattr__(original, "status_code", 400)
        mapped = map_anthropic_exception(original)

        assert isinstance(mapped, ExternalServiceError)
        assert mapped.status_code == 400

    def test_map_unknown_exception_returns_original(self):
        """Test unmapped exception is returned unchanged."""
        original = ValueError("Unknown error")
        mapped = map_anthropic_exception(original)

        assert mapped is original
        assert isinstance(mapped, ValueError)

    def test_error_details_preserved_in_mapping(self):
        """Test error details are preserved during mapping."""
        original = RateLimitError("Rate limit: 100 req/min", response=Mock(), body=None)
        mapped = map_anthropic_exception(original)

        assert "Rate limit: 100 req/min" in str(mapped)


class TestRetryDecorator:
    """Test retry decorator with circuit breaker integration."""

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit_error(self):
        """Test retry decorator retries on rate limit error."""
        settings = Settings(retry_max_attempts=3)
        mock_func = AsyncMock(
            side_effect=[
                AnthropicRateLimitError(),
                AnthropicRateLimitError(),
                "success",
            ]
        )

        decorator = create_retryable_anthropic_call(settings)
        wrapped = decorator(mock_func)

        result = await wrapped()

        assert result == "success"
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self):
        """Test retry decorator retries on server error (5xx)."""
        settings = Settings(retry_max_attempts=3)
        mock_func = AsyncMock(
            side_effect=[
                AnthropicServerError("Server error", status_code=502),
                AnthropicServerError("Server error", status_code=503),
                "success",
            ]
        )

        decorator = create_retryable_anthropic_call(settings)
        wrapped = decorator(mock_func)

        result = await wrapped()

        assert result == "success"
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_timeout_error(self):
        """Test retry decorator retries on timeout error."""
        settings = Settings(retry_max_attempts=3)
        mock_func = AsyncMock(
            side_effect=[
                AnthropicTimeoutError(),
                "success",
            ]
        )

        decorator = create_retryable_anthropic_call(settings)
        wrapped = decorator(mock_func)

        result = await wrapped()

        assert result == "success"
        assert mock_func.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self):
        """Test retry decorator retries on connection error."""
        settings = Settings(retry_max_attempts=3)
        mock_func = AsyncMock(
            side_effect=[
                AnthropicConnectionError(),
                "success",
            ]
        )

        decorator = create_retryable_anthropic_call(settings)
        wrapped = decorator(mock_func)

        result = await wrapped()

        assert result == "success"
        assert mock_func.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_fails_on_non_retryable_errors(self):
        """Test retry decorator doesn't retry non-retryable errors."""
        settings = Settings(retry_max_attempts=3)
        mock_func = AsyncMock(side_effect=ValueError("Invalid input"))

        decorator = create_retryable_anthropic_call(settings)
        wrapped = decorator(mock_func)

        with pytest.raises(ValueError, match="Invalid input"):
            await wrapped()

        # Should only be called once (no retries)
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self):
        """Test exponential backoff with timing verification."""
        settings = Settings(
            retry_max_attempts=3,
            retry_exponential_multiplier=1,
            retry_exponential_max=10,
        )
        mock_func = AsyncMock(
            side_effect=[
                AnthropicRateLimitError(),
                AnthropicRateLimitError(),
                "success",
            ]
        )

        decorator = create_retryable_anthropic_call(settings)
        wrapped = decorator(mock_func)

        start_time = time()
        result = await wrapped()
        elapsed = time() - start_time

        assert result == "success"
        # With exponential backoff and random jitter, timing is variable
        # Just verify it took some time (not instantaneous)
        assert elapsed >= 0.1  # At least 100ms with retries
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_max_attempts_limit_respected(self):
        """Test max attempts limit is respected."""
        from tenacity import RetryError

        settings = Settings(
            retry_max_attempts=3,  # 3 attempts total
            retry_exponential_multiplier=0.5,  # Minimum allowed
            retry_exponential_max=5,  # Minimum allowed
        )
        mock_func = AsyncMock(side_effect=AnthropicRateLimitError())

        decorator = create_retryable_anthropic_call(settings)
        wrapped = decorator(mock_func)

        # After max attempts, tenacity raises RetryError wrapping the original
        with pytest.raises(RetryError):
            await wrapped()

        # stop_after_attempt(3) means try 3 times total
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration_with_retry(self):
        """Test circuit breaker integrates with retry logic."""
        settings = Settings(
            retry_max_attempts=4,  # 4 attempts total
            retry_exponential_multiplier=0.5,  # Minimum allowed
            retry_exponential_max=5,  # Minimum allowed
            circuit_breaker_enabled=True,
            circuit_breaker_failure_threshold=3,  # Open after 3 failures
        )
        cb = CircuitBreaker(service_name="test", failure_threshold=3, timeout=10)

        mock_func = AsyncMock(side_effect=AnthropicRateLimitError())

        decorator = create_retryable_anthropic_call(settings, circuit_breaker=cb)
        wrapped = decorator(mock_func)

        # First attempt - circuit breaker opens after 3 failures,
        # 4th retry attempt gets blocked by circuit breaker
        with pytest.raises(CircuitBreakerOpenError):
            await wrapped()

        # Circuit breaker opened after 3 failures
        # 4th attempt was blocked before reaching mock_func
        assert mock_func.call_count == 3
        assert cb.state == CircuitBreakerState.OPEN

        # Next attempt should also be blocked by circuit breaker
        with pytest.raises(CircuitBreakerOpenError):
            await wrapped()

        # Call count should still be 3 (blocked before execution)
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_circuit_breaker_records_success(self):
        """Test circuit breaker records successful calls."""
        settings = Settings(circuit_breaker_enabled=True)
        cb = CircuitBreaker(service_name="test")

        mock_func = AsyncMock(return_value="success")

        decorator = create_retryable_anthropic_call(settings, circuit_breaker=cb)
        wrapped = decorator(mock_func)

        result = await wrapped()

        assert result == "success"
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_disabled(self):
        """Test circuit breaker can be disabled."""
        settings = Settings(circuit_breaker_enabled=False)
        cb = CircuitBreaker(service_name="test", failure_threshold=1)

        # Open the circuit
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        mock_func = AsyncMock(return_value="success")

        # Even though circuit is open, should work when disabled
        decorator = create_retryable_anthropic_call(settings, circuit_breaker=cb)
        wrapped = decorator(mock_func)

        result = await wrapped()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_with_mixed_errors(self):
        """Test retry handles mixed retryable and non-retryable errors."""
        settings = Settings(retry_max_attempts=4)
        mock_func = AsyncMock(
            side_effect=[
                AnthropicRateLimitError(),  # Retry
                AnthropicServerError("Server error"),  # Retry
                ValueError("Bad input"),  # Don't retry
            ]
        )

        decorator = create_retryable_anthropic_call(settings)
        wrapped = decorator(mock_func)

        with pytest.raises(ValueError, match="Bad input"):
            await wrapped()

        # Should have tried 3 times before hitting non-retryable
        assert mock_func.call_count == 3


class TestLoggingCallbacks:
    """Test logging callbacks for retry and circuit breaker."""

    @pytest.mark.asyncio
    async def test_retry_logs_attempts(self):
        """Test retry decorator logs retry attempts."""
        settings = Settings(retry_max_attempts=2)
        mock_func = AsyncMock(
            side_effect=[
                AnthropicRateLimitError(),
                "success",
            ]
        )

        with patch("workflow.utils.circuit_breaker.logger") as mock_logger:
            decorator = create_retryable_anthropic_call(settings)
            wrapped = decorator(mock_func)

            await wrapped()

            # Should log warning about retryable error
            assert mock_logger.warning.called

    @pytest.mark.asyncio
    async def test_circuit_breaker_logs_state_changes(self):
        """Test circuit breaker logs state transitions."""
        with patch("workflow.utils.circuit_breaker.logger") as mock_logger:
            cb = CircuitBreaker(service_name="test", failure_threshold=2)

            # Should log initialization
            assert mock_logger.info.called

            # Trigger state change to OPEN
            cb.record_failure()
            cb.record_failure()

            # Should log error when opening
            assert mock_logger.error.called


class TestCircuitBreakerHelpers:
    """Test circuit breaker helper methods."""

    def test_should_attempt_reset_returns_false_when_closed(self):
        """Test _should_attempt_reset returns False in CLOSED state."""
        cb = CircuitBreaker(service_name="test")
        assert cb._should_attempt_reset() is False

    def test_should_attempt_reset_returns_false_when_half_open(self):
        """Test _should_attempt_reset returns False in HALF_OPEN state."""
        cb = CircuitBreaker(service_name="test")
        cb.state = CircuitBreakerState.HALF_OPEN
        assert cb._should_attempt_reset() is False

    def test_should_attempt_reset_returns_false_without_failure_time(self):
        """Test _should_attempt_reset returns False without last_failure_time."""
        cb = CircuitBreaker(service_name="test")
        cb.state = CircuitBreakerState.OPEN
        cb.last_failure_time = None
        assert cb._should_attempt_reset() is False

    def test_should_attempt_reset_returns_false_before_timeout(self):
        """Test _should_attempt_reset returns False before timeout elapsed."""
        cb = CircuitBreaker(service_name="test", timeout=10)
        cb.state = CircuitBreakerState.OPEN
        cb.last_failure_time = time()
        assert cb._should_attempt_reset() is False

    def test_should_attempt_reset_returns_true_after_timeout(self):
        """Test _should_attempt_reset returns True after timeout."""
        cb = CircuitBreaker(service_name="test", timeout=1)
        cb.state = CircuitBreakerState.OPEN
        cb.last_failure_time = time() - 2  # 2 seconds ago

        assert cb._should_attempt_reset() is True
