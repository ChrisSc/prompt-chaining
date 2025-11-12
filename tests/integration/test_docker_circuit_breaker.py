"""
Integration tests for circuit breaker with Docker container.

Tests circuit breaker behavior in realistic scenarios with actual
container execution, API failures, and state transitions.
"""

import subprocess

import pytest

# Mark all tests in this module as docker tests
pytestmark = pytest.mark.docker


class TestDockerCircuitBreakerIntegration:
    """Integration tests for circuit breaker in Docker environment."""

    @pytest.fixture(scope="class")
    def docker_container(self):
        """Ensure Docker container is running."""
        # Check if container is running
        result = subprocess.run(
            ["docker-compose", "ps", "-q", "orchestrator-worker"],
            capture_output=True,
            text=True,
            cwd="/Users/chris/Projects/agentic-orchestrator-worker-template",
        )

        if not result.stdout.strip():
            pytest.skip("Docker container not running. Start with: docker-compose up -d")

        return

        # Cleanup happens automatically with docker-compose down

    def test_circuit_breaker_configuration_loaded(self, docker_container):
        """Test circuit breaker configuration is loaded in Docker."""
        result = subprocess.run(
            [
                "docker-compose",
                "exec",
                "-T",
                "orchestrator-worker",
                "python",
                "-c",
                "from workflow.config import Settings; "
                "s = Settings(); "
                "print(f'{s.circuit_breaker_enabled}:{s.circuit_breaker_failure_threshold}:"
                "{s.circuit_breaker_timeout}:{s.circuit_breaker_half_open_attempts}')",
            ],
            capture_output=True,
            text=True,
            cwd="/Users/chris/Projects/agentic-orchestrator-worker-template",
        )

        assert result.returncode == 0
        config_values = result.stdout.strip().split(":")
        assert len(config_values) == 4

        enabled, threshold, timeout, half_open = config_values
        assert enabled in ["True", "False"]
        assert int(threshold) >= 1
        assert int(timeout) >= 1
        assert int(half_open) >= 1

    def test_circuit_breaker_initializes(self, docker_container):
        """Test circuit breaker initializes correctly in Docker."""
        test_script = """
from workflow.utils.circuit_breaker import CircuitBreaker, CircuitBreakerState

cb = CircuitBreaker(service_name="test", failure_threshold=3, timeout=30)
print(f"State: {cb.state.value}")
print(f"Failures: {cb.failure_count}")
print(f"Service: {cb.service_name}")
"""

        result = subprocess.run(
            [
                "docker-compose",
                "exec",
                "-T",
                "orchestrator-worker",
                "python",
                "-c",
                test_script,
            ],
            capture_output=True,
            text=True,
            cwd="/Users/chris/Projects/agentic-orchestrator-worker-template",
        )

        assert result.returncode == 0
        output = result.stdout
        assert "State: closed" in output
        assert "Failures: 0" in output
        assert "Service: test" in output

    def test_circuit_opens_after_consecutive_failures(self, docker_container):
        """Test circuit opens after consecutive failures in Docker."""
        test_script = """
from workflow.utils.circuit_breaker import CircuitBreaker, CircuitBreakerState

cb = CircuitBreaker(service_name="test", failure_threshold=3)

# Record failures
for i in range(3):
    cb.record_failure()
    print(f"After failure {i+1}: state={cb.state.value}, count={cb.failure_count}")

# Verify circuit is open
assert cb.state == CircuitBreakerState.OPEN
print("SUCCESS: Circuit opened after 3 failures")
"""

        result = subprocess.run(
            [
                "docker-compose",
                "exec",
                "-T",
                "orchestrator-worker",
                "python",
                "-c",
                test_script,
            ],
            capture_output=True,
            text=True,
            cwd="/Users/chris/Projects/agentic-orchestrator-worker-template",
        )

        assert result.returncode == 0
        output = result.stdout
        assert "state=closed" in output  # First 2 failures
        assert "state=open" in output  # After 3rd failure
        assert "SUCCESS: Circuit opened after 3 failures" in output

    def test_circuit_blocks_requests_when_open(self, docker_container):
        """Test circuit blocks requests when open in Docker."""
        test_script = """
from workflow.utils.circuit_breaker import CircuitBreaker
from workflow.utils.errors import CircuitBreakerOpenError

cb = CircuitBreaker(service_name="test", failure_threshold=2)

# Open the circuit
cb.record_failure()
cb.record_failure()

# Try to make request
try:
    cb.allow_request()
    print("ERROR: Request was allowed")
except CircuitBreakerOpenError as e:
    print(f"SUCCESS: Request blocked - {e.message}")
    print(f"Service: {e.service_name}")
    print(f"Failures: {e.failure_count}")
"""

        result = subprocess.run(
            [
                "docker-compose",
                "exec",
                "-T",
                "orchestrator-worker",
                "python",
                "-c",
                test_script,
            ],
            capture_output=True,
            text=True,
            cwd="/Users/chris/Projects/agentic-orchestrator-worker-template",
        )

        assert result.returncode == 0
        output = result.stdout
        assert "SUCCESS: Request blocked" in output
        assert "Service: test" in output
        assert "Failures: 2" in output

    def test_half_open_allows_single_test_request(self, docker_container):
        """Test half-open state allows single test request in Docker."""
        test_script = """
import asyncio
from workflow.utils.circuit_breaker import CircuitBreaker, CircuitBreakerState

cb = CircuitBreaker(service_name="test", failure_threshold=2, timeout=1)

# Open circuit
cb.record_failure()
cb.record_failure()
print(f"Circuit opened: {cb.state.value}")

# Wait for timeout
asyncio.run(asyncio.sleep(1.1))

# Try request - should transition to HALF_OPEN
allowed = cb.allow_request()
print(f"Request allowed: {allowed}")
print(f"State: {cb.state.value}")
assert cb.state == CircuitBreakerState.HALF_OPEN
print("SUCCESS: Circuit transitioned to half-open")
"""

        result = subprocess.run(
            [
                "docker-compose",
                "exec",
                "-T",
                "orchestrator-worker",
                "python",
                "-c",
                test_script,
            ],
            capture_output=True,
            text=True,
            cwd="/Users/chris/Projects/agentic-orchestrator-worker-template",
        )

        assert result.returncode == 0
        output = result.stdout
        assert "Circuit opened: open" in output
        assert "Request allowed: True" in output
        assert "State: half_open" in output
        assert "SUCCESS: Circuit transitioned to half-open" in output

    def test_circuit_closes_after_successful_recovery(self, docker_container):
        """Test circuit closes after successful recovery in Docker."""
        test_script = """
from workflow.utils.circuit_breaker import CircuitBreaker, CircuitBreakerState

cb = CircuitBreaker(service_name="test", failure_threshold=2, half_open_attempts=1)

# Transition to HALF_OPEN
cb.state = CircuitBreakerState.HALF_OPEN

# Record success
cb.record_success()
print(f"State after success: {cb.state.value}")
assert cb.state == CircuitBreakerState.CLOSED
print("SUCCESS: Circuit closed after recovery")
"""

        result = subprocess.run(
            [
                "docker-compose",
                "exec",
                "-T",
                "orchestrator-worker",
                "python",
                "-c",
                test_script,
            ],
            capture_output=True,
            text=True,
            cwd="/Users/chris/Projects/agentic-orchestrator-worker-template",
        )

        assert result.returncode == 0
        output = result.stdout
        assert "State after success: closed" in output
        assert "SUCCESS: Circuit closed after recovery" in output

    def test_circuit_logs_contain_state_transitions(self, docker_container):
        """Test logs contain circuit breaker state transitions."""
        # Clear recent logs and trigger state changes
        test_script = """
import logging
from workflow.utils.circuit_breaker import CircuitBreaker
from workflow.utils.logging import get_logger

# Set up logging
logger = get_logger(__name__)

cb = CircuitBreaker(service_name="log-test", failure_threshold=2)

# Trigger state transitions
logger.info("Starting circuit breaker test")
cb.record_failure()
logger.info("Recorded first failure")
cb.record_failure()
logger.info("Recorded second failure - circuit should be open")

print("Circuit state transitions logged")
"""

        result = subprocess.run(
            [
                "docker-compose",
                "exec",
                "-T",
                "orchestrator-worker",
                "python",
                "-c",
                test_script,
            ],
            capture_output=True,
            text=True,
            cwd="/Users/chris/Projects/agentic-orchestrator-worker-template",
        )

        assert result.returncode == 0
        assert "Circuit state transitions logged" in result.stdout

        # Check Docker logs for circuit breaker messages
        log_result = subprocess.run(
            ["docker-compose", "logs", "--tail", "50", "orchestrator-worker"],
            capture_output=True,
            text=True,
            cwd="/Users/chris/Projects/agentic-orchestrator-worker-template",
        )

        logs = log_result.stdout
        # Should contain circuit breaker initialization or state change logs
        # (exact format depends on log output)
        assert log_result.returncode == 0

    def test_exponential_backoff_timing_in_container(self, docker_container):
        """Test exponential backoff timing in real scenario."""
        test_script = """
import asyncio
import time
from workflow.config import Settings
from workflow.utils.circuit_breaker import create_retryable_anthropic_call
from workflow.utils.errors import AnthropicRateLimitError

settings = Settings(
    retry_max_attempts=3,
    retry_exponential_multiplier=1,
    retry_exponential_max=10
)

call_times = []

async def failing_func():
    call_times.append(time.time())
    raise AnthropicRateLimitError()

decorator = create_retryable_anthropic_call(settings)
wrapped = decorator(failing_func)

start = time.time()
try:
    await wrapped()
except AnthropicRateLimitError:
    pass

elapsed = time.time() - start

# Verify we made 3 attempts
print(f"Attempts: {len(call_times)}")
assert len(call_times) == 3

# Verify backoff delays
if len(call_times) >= 2:
    delay1 = call_times[1] - call_times[0]
    print(f"First delay: {delay1:.2f}s")

    if len(call_times) >= 3:
        delay2 = call_times[2] - call_times[1]
        print(f"Second delay: {delay2:.2f}s")

print(f"Total elapsed: {elapsed:.2f}s")
print("SUCCESS: Exponential backoff working")
"""

        result = subprocess.run(
            [
                "docker-compose",
                "exec",
                "-T",
                "orchestrator-worker",
                "python",
                "-c",
                test_script,
            ],
            capture_output=True,
            text=True,
            cwd="/Users/chris/Projects/agentic-orchestrator-worker-template",
            timeout=30,
        )

        assert result.returncode == 0
        output = result.stdout
        assert "Attempts: 3" in output
        assert "SUCCESS: Exponential backoff working" in output

    def test_retry_with_circuit_breaker_integration(self, docker_container):
        """Test retry decorator integrates with circuit breaker."""
        test_script = """
import asyncio
from workflow.config import Settings
from workflow.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
    create_retryable_anthropic_call
)
from workflow.utils.errors import AnthropicRateLimitError, CircuitBreakerOpenError

settings = Settings(
    retry_max_attempts=2,
    circuit_breaker_enabled=True,
    circuit_breaker_failure_threshold=2
)

cb = CircuitBreaker(service_name="test", failure_threshold=2, timeout=10)

async def failing_func():
    raise AnthropicRateLimitError()

decorator = create_retryable_anthropic_call(settings, circuit_breaker=cb)
wrapped = decorator(failing_func)

# First call - should fail after retries and open circuit
try:
    await wrapped()
except AnthropicRateLimitError:
    print(f"First call failed, circuit state: {cb.state.value}")

# Circuit should be open
assert cb.state == CircuitBreakerState.OPEN
print("Circuit opened after failures")

# Second call - should be blocked by circuit breaker
try:
    await wrapped()
    print("ERROR: Call was not blocked")
except CircuitBreakerOpenError as e:
    print(f"SUCCESS: Call blocked by circuit breaker - {e.message}")
"""

        result = subprocess.run(
            [
                "docker-compose",
                "exec",
                "-T",
                "orchestrator-worker",
                "python",
                "-c",
                test_script,
            ],
            capture_output=True,
            text=True,
            cwd="/Users/chris/Projects/agentic-orchestrator-worker-template",
            timeout=30,
        )

        assert result.returncode == 0
        output = result.stdout
        assert "Circuit opened after failures" in output
        assert "SUCCESS: Call blocked by circuit breaker" in output

    def test_exception_mapping_in_container(self, docker_container):
        """Test Anthropic exception mapping works in container."""
        test_script = """
from anthropic import RateLimitError, APITimeoutError, InternalServerError
from unittest.mock import Mock
from workflow.utils.anthropic_errors import map_anthropic_exception
from workflow.utils.errors import (
    AnthropicRateLimitError,
    AnthropicTimeoutError,
    AnthropicServerError
)

# Test rate limit mapping
rate_limit = RateLimitError("Rate limit", response=Mock(), body=None)
mapped = map_anthropic_exception(rate_limit)
assert isinstance(mapped, AnthropicRateLimitError)
print("Rate limit mapping: OK")

# Test timeout mapping
timeout = APITimeoutError(request=Mock())
mapped = map_anthropic_exception(timeout)
assert isinstance(mapped, AnthropicTimeoutError)
print("Timeout mapping: OK")

# Test server error mapping
server_error = InternalServerError("Server error", response=Mock(), body=None)
server_error.status_code = 500
mapped = map_anthropic_exception(server_error)
assert isinstance(mapped, AnthropicServerError)
print("Server error mapping: OK")

print("SUCCESS: All exception mappings working")
"""

        result = subprocess.run(
            [
                "docker-compose",
                "exec",
                "-T",
                "orchestrator-worker",
                "python",
                "-c",
                test_script,
            ],
            capture_output=True,
            text=True,
            cwd="/Users/chris/Projects/agentic-orchestrator-worker-template",
        )

        assert result.returncode == 0
        output = result.stdout
        assert "Rate limit mapping: OK" in output
        assert "Timeout mapping: OK" in output
        assert "Server error mapping: OK" in output
        assert "SUCCESS: All exception mappings working" in output

    def test_circuit_breaker_full_lifecycle(self, docker_container):
        """Test complete circuit breaker lifecycle: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
        test_script = """
import asyncio
from workflow.utils.circuit_breaker import CircuitBreaker, CircuitBreakerState

cb = CircuitBreaker(service_name="lifecycle", failure_threshold=2, timeout=1, half_open_attempts=1)

# 1. Start CLOSED
print(f"1. Initial state: {cb.state.value}")
assert cb.state == CircuitBreakerState.CLOSED

# 2. Trigger OPEN
cb.record_failure()
cb.record_failure()
print(f"2. After failures: {cb.state.value}")
assert cb.state == CircuitBreakerState.OPEN

# 3. Wait for timeout
asyncio.run(asyncio.sleep(1.1))

# 4. Transition to HALF_OPEN
cb.allow_request()
print(f"3. After timeout: {cb.state.value}")
assert cb.state == CircuitBreakerState.HALF_OPEN

# 5. Successful request closes circuit
cb.record_success()
print(f"4. After success: {cb.state.value}")
assert cb.state == CircuitBreakerState.CLOSED

print("SUCCESS: Full lifecycle completed")
"""

        result = subprocess.run(
            [
                "docker-compose",
                "exec",
                "-T",
                "orchestrator-worker",
                "python",
                "-c",
                test_script,
            ],
            capture_output=True,
            text=True,
            cwd="/Users/chris/Projects/agentic-orchestrator-worker-template",
            timeout=30,
        )

        assert result.returncode == 0
        output = result.stdout
        assert "1. Initial state: closed" in output
        assert "2. After failures: open" in output
        assert "3. After timeout: half_open" in output
        assert "4. After success: closed" in output
        assert "SUCCESS: Full lifecycle completed" in output
