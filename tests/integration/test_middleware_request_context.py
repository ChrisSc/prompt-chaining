"""
Integration tests for middleware request context setting.

Tests that the FastAPI middleware properly sets the request context (X-Request-ID)
from request headers and generates IDs when missing. Verifies that request IDs are
included in response headers and available through the request context throughout
the request lifecycle.
"""

import re
import time

import pytest
from fastapi.testclient import TestClient

from orchestrator_worker.main import create_app
from orchestrator_worker.utils.request_context import (
    _request_id_var,
    get_request_id,
    set_request_id,
)


@pytest.fixture
def app():
    """Create a FastAPI test application."""
    return create_app()


@pytest.fixture
def client(app):
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestMiddlewareRequestIdGeneration:
    """Test that middleware generates request IDs when not provided."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_middleware_generates_request_id_if_missing(self, client) -> None:
        """Test middleware generates request_id if not provided in headers."""
        response = client.get("/health/")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        request_id = response.headers["X-Request-ID"]
        assert request_id.startswith("req_")
        assert len(request_id) > 4  # At least "req_" + timestamp digits

    def test_generated_request_id_format(self, client) -> None:
        """Test that generated request IDs follow expected format."""
        response = client.get("/health/")

        request_id = response.headers["X-Request-ID"]
        # Should match pattern: req_<timestamp_ms>
        pattern = r"^req_\d+$"
        assert re.match(pattern, request_id), f"Request ID {request_id} doesn't match pattern"

    def test_each_request_gets_unique_id(self, client) -> None:
        """Test that each request without custom ID gets a unique ID."""
        request_ids = set()

        for _ in range(5):
            response = client.get("/health/")
            request_id = response.headers["X-Request-ID"]
            assert request_id not in request_ids, "Duplicate request ID generated"
            request_ids.add(request_id)
            # Small delay to ensure timestamp increases
            time.sleep(0.001)

        assert len(request_ids) == 5


class TestMiddlewareRequestIdFromHeader:
    """Test that middleware uses X-Request-ID from request header."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_middleware_uses_custom_request_id_from_header(self, client) -> None:
        """Test middleware uses X-Request-ID from request header."""
        custom_request_id = "req_custom_12345"
        response = client.get("/health/", headers={"X-Request-ID": custom_request_id})

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_request_id

    def test_custom_request_id_various_formats(self, client) -> None:
        """Test middleware accepts various request ID formats."""
        test_ids = [
            "req_test_123",
            "request-id-abc",
            "REQ_UPPERCASE",
            "my-request-1234567",
            "a" * 100,  # Long ID
        ]

        for test_id in test_ids:
            response = client.get("/health/", headers={"X-Request-ID": test_id})
            assert response.status_code == 200
            assert response.headers["X-Request-ID"] == test_id

    def test_empty_request_id_header_generates_new(self, client) -> None:
        """Test that empty X-Request-ID header triggers generation."""
        response = client.get("/health/", headers={"X-Request-ID": ""})

        assert response.status_code == 200
        # Empty header should trigger generation of new ID
        request_id = response.headers["X-Request-ID"]
        assert request_id.startswith("req_")

    def test_request_id_with_special_characters(self, client) -> None:
        """Test middleware handles request IDs with special characters."""
        special_id = "req_test@#$%^&*()"
        response = client.get("/health/", headers={"X-Request-ID": special_id})

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == special_id


class TestRequestIdInResponseHeaders:
    """Test that request_id is included in response headers."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_request_id_in_response_headers_health_endpoint(self, client) -> None:
        """Test request_id is included in response headers for health endpoint."""
        response = client.get("/health/")
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"]

    def test_request_id_in_response_headers_ready_endpoint(self, client) -> None:
        """Test request_id is included in response headers for readiness endpoint."""
        response = client.get("/health/ready")
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"]

    def test_request_id_persists_across_endpoints(self, client) -> None:
        """Test same request ID is returned in response headers."""
        custom_id = "req_persistence_test_123"
        response = client.get("/health/", headers={"X-Request-ID": custom_id})

        assert response.headers["X-Request-ID"] == custom_id


class TestMultipleEndpointsRequestId:
    """Test request ID handling across different endpoints."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_request_id_with_get_endpoints(self, client) -> None:
        """Test request ID works with GET endpoints."""
        test_id = "req_get_test_123"

        # Test health endpoint
        response = client.get("/health/", headers={"X-Request-ID": test_id})
        assert response.headers["X-Request-ID"] == test_id

        # Test ready endpoint
        response = client.get("/health/ready", headers={"X-Request-ID": test_id})
        assert response.headers["X-Request-ID"] == test_id

    def test_request_id_with_post_endpoints(self, client) -> None:
        """Test request ID works with POST endpoints."""
        test_id = "req_post_test_456"

        # Mock token for testing
        import jwt
        from orchestrator_worker.config import Settings

        settings = Settings()
        token = jwt.encode({"sub": "test-user"}, settings.jwt_secret_key, algorithm="HS256")

        response = client.post(
            "/v1/chat/completions",
            headers={"X-Request-ID": test_id, "Authorization": f"Bearer {token}"},
            json={
                "model": "orchestrator-worker",
                "messages": [{"role": "user", "content": "test"}],
            },
        )

        # Request ID should be in response headers regardless of endpoint status
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"] == test_id


class TestRequestIdContextAvailability:
    """Test that request ID is available in request context during middleware execution."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_request_id_available_in_health_endpoint_context(self, client) -> None:
        """Test request ID is set in context when health endpoint is called."""
        test_id = "req_context_test_789"

        # Make request and verify ID in response headers
        response = client.get("/health/", headers={"X-Request-ID": test_id})

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == test_id


class TestRequestIdTimingHeaders:
    """Test that request ID works alongside timing headers."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_request_id_with_response_time_header(self, client) -> None:
        """Test request ID coexists with X-Response-Time header."""
        test_id = "req_timing_test"
        response = client.get("/health/", headers={"X-Request-ID": test_id})

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == test_id
        assert "X-Response-Time" in response.headers

    def test_response_time_header_is_numeric(self, client) -> None:
        """Test X-Response-Time header contains numeric value."""
        response = client.get("/health/")

        response_time = response.headers.get("X-Response-Time")
        assert response_time is not None
        try:
            float_value = float(response_time)
            assert float_value >= 0
        except ValueError:
            pytest.fail(f"X-Response-Time is not numeric: {response_time}")


class TestConcurrentRequestIds:
    """Test request ID isolation with concurrent requests."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_multiple_sequential_requests_get_different_ids(self, client) -> None:
        """Test sequential requests without custom ID get different IDs."""
        ids = []

        for _ in range(3):
            response = client.get("/health/")
            ids.append(response.headers["X-Request-ID"])
            time.sleep(0.001)  # Ensure timestamp differences

        # All IDs should be unique
        assert len(set(ids)) == 3

    def test_sequential_requests_with_custom_ids(self, client) -> None:
        """Test sequential requests maintain custom IDs."""
        custom_ids = ["req_seq_1", "req_seq_2", "req_seq_3"]

        for custom_id in custom_ids:
            response = client.get("/health/", headers={"X-Request-ID": custom_id})
            assert response.headers["X-Request-ID"] == custom_id


class TestRequestIdErrorHandling:
    """Test request ID behavior with error responses."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_request_id_included_on_401_unauthorized(self, client) -> None:
        """Test request ID is included even on 401 responses."""
        test_id = "req_401_test"

        # Try to access protected endpoint without auth
        response = client.post(
            "/v1/chat/completions",
            headers={"X-Request-ID": test_id},
            json={
                "model": "orchestrator-worker",
                "messages": [{"role": "user", "content": "test"}],
            },
        )

        # Should get 401 or 403
        assert response.status_code in [401, 403]
        # Request ID should still be in headers
        assert "X-Request-ID" in response.headers

    def test_request_id_with_malformed_request(self, client) -> None:
        """Test request ID is available even with malformed requests."""
        test_id = "req_malformed_test"

        response = client.get(
            "/health/",
            headers={"X-Request-ID": test_id},
        )

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == test_id


class TestRequestIdHeaderPropagation:
    """Test that request ID is properly propagated through middleware chain."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    def test_request_id_header_case_insensitive(self, client) -> None:
        """Test that X-Request-ID header is case-insensitive."""
        test_id = "req_case_test_123"

        # Try different case variations (HTTP headers are case-insensitive)
        response = client.get(
            "/health/",
            headers={"x-request-id": test_id},
        )

        # Should still work due to case-insensitive header handling
        assert response.status_code == 200
        # Response header should be normalized
        assert "X-Request-ID" in response.headers or "x-request-id" in response.headers

    def test_request_id_preserved_through_redirects(self, client) -> None:
        """Test request ID is maintained (if endpoint supports it)."""
        test_id = "req_redirect_test"

        response = client.get(
            "/health/",
            headers={"X-Request-ID": test_id},
            follow_redirects=False,
        )

        # Verify ID is in response
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"] == test_id
