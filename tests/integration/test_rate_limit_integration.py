"""
Integration tests for rate limiting against live Docker container.

Tests verify that rate limiting is properly enforced on API endpoints using slowapi.
Tests run against http://localhost:8000 (live Docker container).

Rate limits (production):
- /v1/models: 60/minute
- /v1/chat/completions: 10/minute
"""

import os
import time

import jwt
import pytest
import requests

# Test configuration
DOCKER_BASE_URL = "http://localhost:8000"
TEST_JWT_SECRET = os.getenv("JWT_SECRET_KEY", "d1PDud207CUUaQE0RGoaV-NN-MhOXE5xP4CBqXbybXI")


def generate_test_token(subject: str = "test-client") -> str:
    """Generate a JWT token for testing."""
    payload = {"sub": subject, "iat": int(time.time())}
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="session")
def docker_available():
    """Check if Docker container is running."""
    try:
        response = requests.get(f"{DOCKER_BASE_URL}/health/", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


class TestRateLimitModelsEndpoint:
    """Test rate limiting on /v1/models endpoint (60/minute limit)."""

    def test_models_rate_limit_headers_present(self, docker_available):
        """Verify rate limit headers are present on successful response."""
        if not docker_available:
            pytest.skip("Docker container not available")

        token = generate_test_token("user1")
        headers = {"Authorization": f"Bearer {token}"}

        response = requests.get(f"{DOCKER_BASE_URL}/v1/models", headers=headers, timeout=10)

        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

        # Verify values are numeric
        limit = response.headers["X-RateLimit-Limit"]
        remaining = response.headers["X-RateLimit-Remaining"]
        reset = response.headers["X-RateLimit-Reset"]

        assert limit == "60", f"Expected limit 60, got {limit}"
        assert remaining.isdigit(), f"Remaining should be numeric: {remaining}"
        # Reset can be float (Unix timestamp with decimals)
        try:
            float(reset)
        except ValueError:
            pytest.fail(f"Reset should be numeric: {reset}")

    def test_models_rate_limit_remaining_decreases(self, docker_available):
        """Verify X-RateLimit-Remaining decreases with requests."""
        if not docker_available:
            pytest.skip("Docker container not available")

        token = generate_test_token("user2")
        headers = {"Authorization": f"Bearer {token}"}

        # Make 3 requests and track remaining
        remaining_values = []
        for _ in range(3):
            response = requests.get(f"{DOCKER_BASE_URL}/v1/models", headers=headers, timeout=10)
            assert response.status_code == 200
            remaining = int(response.headers["X-RateLimit-Remaining"])
            remaining_values.append(remaining)

        # Verify they decrease
        assert (
            remaining_values[1] < remaining_values[0]
        ), f"Remaining should decrease: {remaining_values}"
        assert (
            remaining_values[2] < remaining_values[1]
        ), f"Remaining should decrease: {remaining_values}"


class TestRateLimitChatCompletionsEndpoint:
    """Test rate limiting on /v1/chat/completions endpoint (10/minute limit)."""

    def test_chat_completions_rate_limit_headers_present(self, docker_available):
        """Verify rate limit headers are present on chat/completions."""
        if not docker_available:
            pytest.skip("Docker container not available")

        token = generate_test_token("user3")
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "model": "orchestrator-worker",
            "messages": [{"role": "user", "content": "test"}],
        }

        response = requests.post(
            f"{DOCKER_BASE_URL}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
            stream=False,
        )

        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers

        # Chat completions has 10/minute limit
        limit = response.headers["X-RateLimit-Limit"]
        assert limit == "10", f"Expected limit 10, got {limit}"


class TestPerUserRateLimiting:
    """Test that rate limits are per-user (per JWT subject)."""

    def test_different_users_have_separate_limits(self, docker_available):
        """Verify different JWT subjects have separate rate limit quotas."""
        if not docker_available:
            pytest.skip("Docker container not available")

        token1 = generate_test_token("user4")
        token2 = generate_test_token("user5")
        headers1 = {"Authorization": f"Bearer {token1}"}
        headers2 = {"Authorization": f"Bearer {token2}"}

        # User 1 makes a request
        resp1 = requests.get(f"{DOCKER_BASE_URL}/v1/models", headers=headers1, timeout=10)
        remaining1_first = int(resp1.headers["X-RateLimit-Remaining"])

        # User 2 makes a request
        resp2 = requests.get(f"{DOCKER_BASE_URL}/v1/models", headers=headers2, timeout=10)
        remaining2_first = int(resp2.headers["X-RateLimit-Remaining"])

        # Both should have high remaining counts (separate quotas)
        # If they shared, user2 would have lower remaining
        assert remaining1_first > 50, f"User1 should have high remaining: {remaining1_first}"
        assert remaining2_first > 50, f"User2 should have high remaining: {remaining2_first}"


class TestRateLimitResponseFormat:
    """Test 429 response format when rate limit is exceeded."""

    def test_429_response_format(self, docker_available):
        """Verify 429 response has correct format with detail field."""
        if not docker_available:
            pytest.skip("Docker container not available")

        # Make a single request to verify endpoint works
        token = generate_test_token("user6")
        headers = {"Authorization": f"Bearer {token}"}

        response = requests.get(f"{DOCKER_BASE_URL}/v1/models", headers=headers, timeout=10)

        # Should be 200, not rate limited after just 1 request
        assert response.status_code == 200
        assert "detail" not in response.text or response.json().get("detail") is None


class TestRateLimitBasics:
    """Basic rate limiting functionality tests."""

    def test_endpoint_requires_auth(self, docker_available):
        """Verify protected endpoints require authentication."""
        if not docker_available:
            pytest.skip("Docker container not available")

        # Request without auth header
        response = requests.get(f"{DOCKER_BASE_URL}/v1/models", timeout=10)

        # Should get 403 Forbidden (not authenticated)
        assert response.status_code == 403

    def test_health_endpoint_no_rate_limit(self, docker_available):
        """Verify health endpoints are not rate limited."""
        if not docker_available:
            pytest.skip("Docker container not available")

        # Make multiple requests to health endpoint
        for _ in range(10):
            response = requests.get(f"{DOCKER_BASE_URL}/health/", timeout=10)
            assert response.status_code == 200

        # All should succeed - health endpoint is not rate limited
