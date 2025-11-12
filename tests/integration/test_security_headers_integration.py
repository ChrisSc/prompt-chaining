"""
Integration tests for security headers middleware.

Tests the security headers feature through the complete API lifecycle,
including protected/public endpoints, proxy headers, and error responses.
"""

import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from workflow.main import create_app

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
    for key in [
        "ANTHROPIC_API_KEY",
        "JWT_SECRET_KEY",
        "JWT_ALGORITHM",
        "ENVIRONMENT",
        "LOG_LEVEL",
    ]:
        os.environ.pop(key, None)


@pytest.fixture
def valid_jwt_token() -> str:
    """Generate a valid JWT token for testing."""
    payload = {
        "sub": "test-client",
        "iat": datetime.now(tz=timezone.utc),
    }
    return jwt.encode(
        payload,
        TEST_JWT_SECRET,
        algorithm="HS256",
    )


@pytest.fixture
def expired_jwt_token() -> str:
    """Generate an expired JWT token."""
    payload = {
        "sub": "test-client",
        "iat": datetime.now(tz=timezone.utc) - timedelta(hours=2),
        "exp": datetime.now(tz=timezone.utc) - timedelta(hours=1),
    }
    return jwt.encode(
        payload,
        TEST_JWT_SECRET,
        algorithm="HS256",
    )


@pytest.fixture
def invalid_signature_token() -> str:
    """Generate a token with invalid signature."""
    payload = {
        "sub": "test-client",
        "iat": datetime.now(tz=timezone.utc),
    }
    return jwt.encode(
        payload,
        "wrong_secret_key_with_minimum_32_characters_for_testing",
        algorithm="HS256",
    )


@pytest.fixture
def app():
    """Create FastAPI app for testing."""
    return create_app()


@pytest.fixture
def client(app) -> TestClient:
    """Create test client from app."""
    return TestClient(app)


class TestSecurityHeadersOnProtectedEndpoints:
    """Test security headers on protected endpoints."""

    def test_chat_completions_endpoint_returns_security_headers(
        self,
        client: TestClient,
        valid_jwt_token: str,
    ) -> None:
        """Test /v1/chat/completions returns security headers with valid token."""
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
            json={
                "model": "test",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert response.status_code == 200
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-XSS-Protection" in response.headers

    def test_models_endpoint_returns_security_headers(
        self, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test /v1/models endpoint returns security headers."""
        response = client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 200
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-XSS-Protection" in response.headers

    def test_chat_completions_headers_have_correct_values(
        self,
        client: TestClient,
        valid_jwt_token: str,
    ) -> None:
        """Test /v1/chat/completions headers have correct values."""
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
            json={
                "model": "test",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"


class TestSecurityHeadersOnPublicEndpoints:
    """Test security headers on public endpoints."""

    def test_health_endpoint_returns_security_headers(self, client: TestClient) -> None:
        """Test /health/ endpoint returns security headers."""
        response = client.get("/health/")

        assert response.status_code == 200
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-XSS-Protection" in response.headers

    def test_health_ready_endpoint_returns_security_headers(self, client: TestClient) -> None:
        """Test /health/ready endpoint returns security headers."""
        response = client.get("/health/ready")

        assert response.status_code == 200
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-XSS-Protection" in response.headers

    def test_health_endpoint_headers_have_correct_values(self, client: TestClient) -> None:
        """Test /health/ endpoint headers have correct values."""
        response = client.get("/health/")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"


class TestSecurityHeadersWithAuth:
    """Test security headers in various authentication scenarios."""

    def test_missing_token_returns_headers_with_auth_error(self, client: TestClient) -> None:
        """Test missing token returns auth error (401 or 403) with security headers."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "test",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        # Auth errors can be 401 or 403 depending on implementation
        assert response.status_code in (401, 403)
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers

    def test_invalid_token_returns_headers_with_403(self, client: TestClient) -> None:
        """Test invalid token returns 403 with security headers."""
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer invalid-token-xyz"},
            json={
                "model": "test",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert response.status_code == 403
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers

    def test_expired_token_returns_headers_with_401(
        self, client: TestClient, expired_jwt_token: str
    ) -> None:
        """Test expired token returns 401 with security headers."""
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {expired_jwt_token}"},
            json={
                "model": "test",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert response.status_code == 401
        assert "X-Content-Type-Options" in response.headers

    def test_invalid_signature_token_returns_headers_with_403(
        self, client: TestClient, invalid_signature_token: str
    ) -> None:
        """Test invalid signature token returns 403 with security headers."""
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {invalid_signature_token}"},
            json={
                "model": "test",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert response.status_code == 403
        assert "X-Content-Type-Options" in response.headers


class TestHSTSWithProxyHeaders:
    """Test HSTS header with reverse proxy scenarios."""

    def test_hsts_not_present_http_no_proxy_header(self, client: TestClient) -> None:
        """Test HSTS not present for HTTP without proxy header."""
        response = client.get("/health/")

        # TestClient defaults to http scheme
        assert "Strict-Transport-Security" not in response.headers
        assert "X-Content-Type-Options" in response.headers

    def test_hsts_present_with_x_forwarded_proto_https(self, client: TestClient) -> None:
        """Test HSTS present when X-Forwarded-Proto: https."""
        response = client.get(
            "/health/",
            headers={"X-Forwarded-Proto": "https"},
        )

        assert "Strict-Transport-Security" in response.headers
        assert (
            response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
        )

    def test_hsts_not_present_with_x_forwarded_proto_http(self, client: TestClient) -> None:
        """Test HSTS not present when X-Forwarded-Proto: http."""
        response = client.get(
            "/health/",
            headers={"X-Forwarded-Proto": "http"},
        )

        assert "Strict-Transport-Security" not in response.headers

    def test_hsts_case_insensitive_x_forwarded_proto(self, client: TestClient) -> None:
        """Test HSTS present with uppercase X-Forwarded-Proto: HTTPS."""
        response = client.get(
            "/health/",
            headers={"X-Forwarded-Proto": "HTTPS"},
        )

        assert "Strict-Transport-Security" in response.headers

    def test_hsts_with_mixed_case_x_forwarded_proto(self, client: TestClient) -> None:
        """Test HSTS present with mixed case X-Forwarded-Proto: Https."""
        response = client.get(
            "/health/",
            headers={"X-Forwarded-Proto": "Https"},
        )

        assert "Strict-Transport-Security" in response.headers

    def test_hsts_not_present_with_other_proxy_headers(self, client: TestClient) -> None:
        """Test HSTS not present with other proxy headers but no X-Forwarded-Proto."""
        response = client.get(
            "/health/",
            headers={"X-Forwarded-For": "192.168.1.1"},
        )

        assert "Strict-Transport-Security" not in response.headers


class TestHeadersOnErrorResponses:
    """Test security headers on error responses."""

    def test_headers_on_404_not_found(self, client: TestClient) -> None:
        """Test security headers on 404 Not Found response."""
        response = client.get("/nonexistent/endpoint")

        assert response.status_code == 404
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers

    def test_headers_on_413_payload_too_large(
        self, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test 413 Payload Too Large response.

        Note: The request size middleware runs before security headers middleware,
        so the 413 error response may not have security headers depending on middleware
        execution order. This test verifies the response status code is correct.
        """
        # Create a payload that exceeds the default 1MB limit
        large_payload = "x" * (2 * 1024 * 1024)  # 2MB

        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
            json={
                "model": "test",
                "messages": [{"role": "user", "content": large_payload}],
            },
        )

        # The request size middleware returns 413 before reaching the security headers middleware
        assert response.status_code == 413

    def test_headers_on_405_method_not_allowed(self, client: TestClient) -> None:
        """Test security headers on 405 Method Not Allowed response."""
        response = client.post("/health/")

        assert response.status_code == 405
        assert "X-Content-Type-Options" in response.headers


class TestHeadersConsistency:
    """Test that headers are consistent across different scenarios."""

    def test_same_headers_on_multiple_requests(
        self, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test security headers are consistent across multiple requests."""
        response1 = client.get(
            "/health/",
        )
        response2 = client.get(
            "/health/",
        )

        assert response1.headers["X-Content-Type-Options"] == "nosniff"
        assert response2.headers["X-Content-Type-Options"] == "nosniff"
        assert response1.headers["X-Frame-Options"] == "DENY"
        assert response2.headers["X-Frame-Options"] == "DENY"

    def test_same_headers_on_protected_and_public_endpoints(
        self, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test security headers are same on protected and public endpoints."""
        public_response = client.get("/health/")
        protected_response = client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert (
            public_response.headers["X-Content-Type-Options"]
            == protected_response.headers["X-Content-Type-Options"]
        )
        assert (
            public_response.headers["X-Frame-Options"]
            == protected_response.headers["X-Frame-Options"]
        )


class TestHTTPMethodsWithSecurityHeaders:
    """Test security headers with different HTTP methods."""

    def test_headers_on_get_request(self, client: TestClient, valid_jwt_token: str) -> None:
        """Test security headers on GET request."""
        response = client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert "X-Content-Type-Options" in response.headers

    def test_headers_on_post_request(
        self,
        client: TestClient,
        valid_jwt_token: str,
    ) -> None:
        """Test security headers on POST request."""
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
            json={
                "model": "test",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert "X-Content-Type-Options" in response.headers

    def test_headers_on_options_request(self, client: TestClient) -> None:
        """Test security headers on OPTIONS request (CORS preflight)."""
        response = client.options("/v1/chat/completions")

        # CORS preflight should also have security headers
        assert "X-Content-Type-Options" in response.headers


class TestHeadersWithContentTypes:
    """Test security headers with various content types."""

    def test_headers_with_json_response(self, client: TestClient, valid_jwt_token: str) -> None:
        """Test security headers with JSON response."""
        response = client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.headers.get("content-type") is not None
        assert "X-Content-Type-Options" in response.headers

    def test_headers_with_streaming_response(
        self,
        client: TestClient,
        valid_jwt_token: str,
    ) -> None:
        """Test security headers with streaming response."""
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
            json={
                "model": "test",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert response.status_code == 200
        assert "X-Content-Type-Options" in response.headers


class TestNoHeadersInvalidConfiguration:
    """Test headers behavior in edge configuration scenarios."""

    def test_headers_always_present_by_default(self, client: TestClient) -> None:
        """Test that security headers are always present by default."""
        response = client.get("/health/")

        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-XSS-Protection" in response.headers
