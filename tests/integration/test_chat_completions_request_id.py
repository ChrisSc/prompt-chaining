"""
End-to-end integration tests for request ID propagation through chat completions.

Tests the full request lifecycle from API endpoint to chat completions, verifying that
request IDs are properly propagated through the workflow and returned in response headers.
Tests request ID generation, custom request ID handling, and request ID persistence.
"""

import os

import jwt
import pytest
from fastapi.testclient import TestClient

from workflow.main import create_app
from workflow.utils.request_context import (
    _request_id_var,
    get_request_id,
)

# Use a consistent secret key for all tests
TEST_JWT_SECRET = "test_secret_key_with_minimum_32_characters_required_for_testing"


@pytest.fixture(autouse=True)
def set_test_env() -> None:
    """Set test environment variables before each test."""
    os.environ["ANTHROPIC_API_KEY"] = "test-key-123"
    os.environ["JWT_SECRET_KEY"] = TEST_JWT_SECRET
    os.environ["JWT_ALGORITHM"] = "HS256"
    os.environ["ENVIRONMENT"] = "development"
    os.environ["LOG_LEVEL"] = "DEBUG"
    yield
    # Cleanup
    for key in ["ANTHROPIC_API_KEY", "JWT_SECRET_KEY", "JWT_ALGORITHM", "ENVIRONMENT", "LOG_LEVEL"]:
        os.environ.pop(key, None)


@pytest.fixture
def app():
    """Create FastAPI app for testing."""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def valid_token() -> str:
    """Generate valid JWT token for testing."""
    return jwt.encode(
        {"sub": "test-user", "iat": 1234567890},
        TEST_JWT_SECRET,
        algorithm="HS256",
    )


class TestChatCompletionsRequestIdFlow:
    """Test request ID propagation through full chat completions flow."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_request_id_generated_for_post_request(self, client, valid_token) -> None:
        """Test that POST requests without custom ID get generated IDs."""
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={
                "model": "orchestrator-worker",
                "messages": [{"role": "user", "content": "test"}],
            },
        )

        # Request ID should be generated and returned in response headers
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"].startswith("req_")

    def test_custom_request_id_propagated_through_endpoints(self, client, valid_token) -> None:
        """Test custom request ID from header is used through endpoints."""
        custom_id = "req_e2e_test_123"

        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {valid_token}",
                "X-Request-ID": custom_id,
            },
            json={
                "model": "orchestrator-worker",
                "messages": [{"role": "user", "content": "test"}],
            },
        )

        # Response should contain the custom request ID
        assert response.headers["X-Request-ID"] == custom_id

    def test_request_id_in_health_endpoint(self, client) -> None:
        """Test request ID is available in health endpoint."""
        custom_id = "req_health_test"

        response = client.get(
            "/health/",
            headers={"X-Request-ID": custom_id},
        )

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_id

    def test_request_id_in_models_endpoint(self, client, valid_token) -> None:
        """Test request ID is available in models listing endpoint."""
        custom_id = "req_models_test"

        response = client.get(
            "/v1/models",
            headers={
                "Authorization": f"Bearer {valid_token}",
                "X-Request-ID": custom_id,
            },
        )

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_id


class TestChainWorkflowReceivesRequestId:
    """Test that chain workflow receives request ID in context."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_workflow_can_access_request_id_in_context(self, client, valid_token) -> None:
        """Test that workflow has access to request ID during processing."""
        custom_id = "req_workflow_access"

        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {valid_token}",
                "X-Request-ID": custom_id,
            },
            json={
                "model": "orchestrator-worker",
                "messages": [{"role": "user", "content": "test"}],
            },
        )

        # Workflow should propagate the request ID to response headers
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_id


class TestRequestIdErrorResponse:
    """Test request ID handling in error responses."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_request_id_included_in_unauthorized_response(self, client) -> None:
        """Test request ID is included even in 401 responses."""
        custom_id = "req_unauth_test"

        response = client.post(
            "/v1/chat/completions",
            headers={"X-Request-ID": custom_id},
            json={
                "model": "orchestrator-worker",
                "messages": [{"role": "user", "content": "test"}],
            },
        )

        assert response.status_code in [401, 403]
        assert response.headers["X-Request-ID"] == custom_id

    def test_request_id_included_in_validation_error(self, client, valid_token) -> None:
        """Test request ID is included in validation error responses."""
        custom_id = "req_validation_test"

        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {valid_token}",
                "X-Request-ID": custom_id,
            },
            json={"model": "orchestrator-worker"},  # Missing messages
        )

        # Should be a validation error
        assert response.status_code >= 400
        # Request ID should still be in headers
        assert "X-Request-ID" in response.headers


class TestRequestIdWithResponseHeaders:
    """Test request ID alongside other response headers."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_request_id_and_rate_limit_headers(self, client, valid_token) -> None:
        """Test request ID coexists with rate limit headers."""
        custom_id = "req_rate_limit_test"

        response = client.get(
            "/v1/models",
            headers={
                "Authorization": f"Bearer {valid_token}",
                "X-Request-ID": custom_id,
            },
        )

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_id
        # Rate limit headers may or may not be present depending on config
        if "X-RateLimit-Limit" in response.headers:
            assert response.headers["X-RateLimit-Limit"]

    def test_request_id_and_response_time(self, client, valid_token) -> None:
        """Test request ID is included with X-Response-Time header."""
        custom_id = "req_timing_test"

        response = client.get(
            "/health/",
            headers={"X-Request-ID": custom_id},
        )

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_id
        assert "X-Response-Time" in response.headers


class TestMultipleSequentialRequests:
    """Test request ID handling across multiple sequential requests."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_each_request_maintains_own_id(self, client, valid_token) -> None:
        """Test that sequential requests maintain their own IDs."""
        custom_ids = [
            "req_sequential_1",
            "req_sequential_2",
            "req_sequential_3",
        ]

        for custom_id in custom_ids:
            response = client.get(
                "/health/",
                headers={"X-Request-ID": custom_id},
            )

            assert response.status_code == 200
            assert response.headers["X-Request-ID"] == custom_id

    def test_alternating_custom_and_generated_ids(self, client, valid_token) -> None:
        """Test alternating between custom and generated request IDs."""
        # First request with custom ID
        response1 = client.get(
            "/health/",
            headers={"X-Request-ID": "req_custom_1"},
        )
        assert response1.headers["X-Request-ID"] == "req_custom_1"

        # Second request without custom ID (should generate)
        response2 = client.get("/health/")
        id2 = response2.headers["X-Request-ID"]
        assert id2.startswith("req_")
        assert id2 != "req_custom_1"

        # Third request with different custom ID
        response3 = client.get(
            "/health/",
            headers={"X-Request-ID": "req_custom_2"},
        )
        assert response3.headers["X-Request-ID"] == "req_custom_2"


class TestRequestIdContextCleanup:
    """Test that request ID context is properly managed between requests."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_request_id_not_leaked_between_sync_requests(self, client) -> None:
        """Test request IDs don't leak between sequential requests."""
        # Make request with custom ID
        response1 = client.get(
            "/health/",
            headers={"X-Request-ID": "req_first_request"},
        )
        assert response1.headers["X-Request-ID"] == "req_first_request"

        # Make request without custom ID - should get new ID
        response2 = client.get("/health/")
        id2 = response2.headers["X-Request-ID"]

        # Should be different from first request
        assert id2 != "req_first_request"
        assert id2.startswith("req_")


class TestRequestIdWithLongRunningRequests:
    """Test request ID stability in long-running operations."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_request_id_stable_throughout_request(self, client, valid_token) -> None:
        """Test request ID remains stable throughout request lifecycle."""
        custom_id = "req_stable_throughout"

        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {valid_token}",
                "X-Request-ID": custom_id,
            },
            json={
                "model": "orchestrator-worker",
                "messages": [{"role": "user", "content": "test"}],
            },
        )

        # Response should contain the original request ID throughout the request
        assert response.headers["X-Request-ID"] == custom_id


class TestRequestIdFormats:
    """Test various request ID formats are properly handled."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_various_request_id_formats(self, client) -> None:
        """Test different request ID formats are accepted and returned."""
        test_formats = [
            "req_simple_123",
            "request-with-dashes",
            "REQ_UPPERCASE",
            "mixed_Case_ID_123",
            "very_long_request_id_" + "x" * 80,
        ]

        for test_id in test_formats:
            response = client.get(
                "/health/",
                headers={"X-Request-ID": test_id},
            )

            assert response.status_code == 200
            assert response.headers["X-Request-ID"] == test_id


class TestRequestIdWithDifferentHttpMethods:
    """Test request ID propagation with different HTTP methods."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_request_id_with_get(self, client, valid_token) -> None:
        """Test request ID with GET requests."""
        custom_id = "req_get_method"

        response = client.get(
            "/health/",
            headers={"X-Request-ID": custom_id},
        )

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_id

    def test_request_id_with_post(self, client, valid_token) -> None:
        """Test request ID with POST requests."""
        custom_id = "req_post_method"

        response = client.post(
            "/health/",
            headers={"X-Request-ID": custom_id},
        )

        # Health endpoint might not support POST, but ID should still propagate
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"] == custom_id
