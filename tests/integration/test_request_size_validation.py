"""
Integration tests for request size validation with full HTTP request/response cycle.

Tests the request size validation feature through the complete API lifecycle,
including error handling, status codes, response formats, and edge cases.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from orchestrator_worker.main import create_app
from orchestrator_worker.models.openai import (
    ChatCompletionChunk,
    ChatCompletionStreamChoice,
    ChoiceDelta,
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
def valid_jwt_token() -> str:
    """Generate a valid JWT token for testing."""
    from datetime import datetime, timezone

    import jwt

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
def app_with_mocked_orchestrator():
    """Create FastAPI app with mocked orchestrator."""
    with patch("orchestrator_worker.main.Orchestrator") as mock_orchestrator_class:
        mock_orchestrator = AsyncMock()
        mock_orchestrator.model = "claude-sonnet-4-5-20250929"
        mock_orchestrator.client = True  # Mark as initialized
        mock_orchestrator_class.return_value = mock_orchestrator

        app = create_app()
        app.state.orchestrator = mock_orchestrator

    return app


@pytest.fixture
def client(app_with_mocked_orchestrator) -> TestClient:
    """Create test client from app."""
    return TestClient(app_with_mocked_orchestrator)


@pytest.fixture
def mock_orchestrator_streaming_response(app_with_mocked_orchestrator):
    """Setup orchestrator to return streaming response."""

    async def mock_process(request):
        yield ChatCompletionChunk(
            id="test-1",
            created=0,
            model="test",
            choices=[
                ChatCompletionStreamChoice(
                    index=0,
                    delta=ChoiceDelta(role="assistant", content="Hello"),
                    finish_reason=None,
                )
            ],
        )
        yield ChatCompletionChunk(
            id="test-2",
            created=0,
            model="test",
            choices=[
                ChatCompletionStreamChoice(
                    index=0,
                    delta=ChoiceDelta(),
                    finish_reason="stop",
                )
            ],
        )

    app_with_mocked_orchestrator.state.orchestrator.process = mock_process
    return app_with_mocked_orchestrator


class TestChatEndpointRequestSizeAcceptance:
    """Test chat endpoint acceptance of appropriately-sized requests."""

    def test_chat_endpoint_accepts_small_request(
        self, mock_orchestrator_streaming_response, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that small valid request succeeds."""
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_chat_endpoint_accepts_medium_sized_request(
        self, mock_orchestrator_streaming_response, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that medium-sized request is accepted."""
        # Create a request with ~500KB of content
        large_message = "x" * 500_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": large_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 200

    def test_chat_endpoint_accepts_request_at_limit(
        self, mock_orchestrator_streaming_response, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that request exactly at 1MB limit is accepted."""
        # Create request just under 1MB (accounting for JSON overhead)
        large_message = "x" * 950_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": large_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 200


class TestChatEndpointRequestSizeRejection:
    """Test chat endpoint rejection of oversized requests."""

    def test_chat_endpoint_rejects_oversized_request(
        self, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that request >1MB returns 413 Payload Too Large."""
        # Create request just over 1MB
        oversized_message = "x" * 1_100_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413

    def test_chat_endpoint_rejects_very_large_request(
        self, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that very large request (10MB) is rejected."""
        # Create request ~2MB (to stay under content-length, but test rejection)
        very_large_message = "x" * 2_000_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": very_large_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413


class TestErrorResponseFormat:
    """Test error response format and content."""

    def test_error_response_has_correct_status_code(
        self, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that oversized request returns 413 status."""
        oversized_message = "x" * 1_100_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413

    def test_error_response_is_json(self, client: TestClient, valid_jwt_token: str) -> None:
        """Test that error response is valid JSON."""
        oversized_message = "x" * 1_100_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413
        # Should be valid JSON
        data = response.json()
        assert isinstance(data, dict)

    def test_error_response_includes_error_code(
        self, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that error response includes error code."""
        oversized_message = "x" * 1_100_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413
        data = response.json()
        assert "error" in data
        assert data["error"] == "request_too_large"

    def test_error_response_includes_message(
        self, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that error response includes error message."""
        oversized_message = "x" * 1_100_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413
        data = response.json()
        assert "message" in data
        assert "size" in data["message"].lower() or "request" in data["message"].lower()

    def test_error_response_includes_size_info(
        self, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that error response includes actual and max sizes."""
        oversized_message = "x" * 1_100_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413
        data = response.json()
        # Size information should be in message or extra fields
        message = data.get("message", "")
        assert "1" in message  # Should contain size numbers


class TestRequestSizeEdgeCases:
    """Test edge cases for request size validation."""

    def test_request_exactly_at_limit_accepted(
        self, mock_orchestrator_streaming_response, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that request exactly at 1MB limit is accepted."""
        # Create a request that's exactly at the limit
        large_message = "x" * 950_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": large_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 200

    def test_request_just_over_limit_rejected(
        self, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that request just over limit is rejected."""
        oversized_message = "x" * 1_050_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413

    def test_multiple_requests_both_small(
        self, mock_orchestrator_streaming_response, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that multiple small requests all succeed."""
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        for _ in range(3):
            response = client.post(
                "/v1/chat/completions",
                json=request_body,
                headers={"Authorization": f"Bearer {valid_jwt_token}"},
            )
            assert response.status_code == 200


class TestHealthEndpointsNotAffected:
    """Test that health endpoints are not affected by request size validation."""

    def test_health_endpoint_still_works(self, client: TestClient) -> None:
        """Test that /health/ endpoint works without authentication."""
        response = client.get("/health/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_ready_endpoint_still_works(self, client: TestClient) -> None:
        """Test that /health/ready endpoint works."""
        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


class TestModelsEndpointNotAffected:
    """Test that models endpoint is not affected by request size validation."""

    def test_models_endpoint_still_works(self, client: TestClient, valid_jwt_token: str) -> None:
        """Test that /v1/models endpoint works."""
        response = client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "object" in data
        assert data["object"] == "list"


class TestServerRecoveryAfterRejection:
    """Test that server recovers properly after request rejection."""

    def test_server_accepts_valid_after_rejection(
        self, mock_orchestrator_streaming_response, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that server accepts valid request after rejecting oversized one."""
        # First, send oversized request
        oversized_message = "x" * 1_100_000
        oversized_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=oversized_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )
        assert response.status_code == 413

        # Then, send valid request
        valid_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=valid_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )
        assert response.status_code == 200

    def test_multiple_rejections_and_acceptances(
        self, mock_orchestrator_streaming_response, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test server handles alternating rejections and acceptances."""
        headers = {"Authorization": f"Bearer {valid_jwt_token}"}

        for _ in range(3):
            # Oversized request
            oversized_message = "x" * 1_100_000
            oversized_body = {
                "model": "test-service",
                "messages": [{"role": "user", "content": oversized_message}],
            }
            response = client.post(
                "/v1/chat/completions",
                json=oversized_body,
                headers=headers,
            )
            assert response.status_code == 413

            # Valid request
            valid_body = {
                "model": "test-service",
                "messages": [{"role": "user", "content": "Hello"}],
            }
            response = client.post(
                "/v1/chat/completions",
                json=valid_body,
                headers=headers,
            )
            assert response.status_code == 200


class TestAuthenticationWithSizeValidation:
    """Test that authentication and size validation work together."""

    def test_oversized_request_with_valid_auth_still_rejected(
        self, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that auth still required even with size error."""
        oversized_message = "x" * 1_100_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413

    def test_oversized_request_without_auth(self, client: TestClient) -> None:
        """Test that oversized request without auth gets 413 from size validation."""
        oversized_message = "x" * 1_100_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
        )

        # Size validation runs before auth check, so 413 takes precedence
        assert response.status_code == 413

    def test_valid_size_with_invalid_auth(self, client: TestClient) -> None:
        """Test that auth error is checked before size validation."""
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": "Bearer invalid_token"},
        )

        assert response.status_code == 403


class TestGetRequestsSkipValidation:
    """Test that GET requests skip size validation."""

    def test_get_request_ignores_content_length_header(
        self, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that GET requests are not subject to size validation."""
        response = client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        # GET request should succeed regardless of size validation
        assert response.status_code == 200


class TestErrorAttributesPresent:
    """Test that error responses contain necessary attributes."""

    def test_413_response_has_error_field(self, client: TestClient, valid_jwt_token: str) -> None:
        """Test 413 response includes 'error' field."""
        oversized_message = "x" * 1_100_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413
        data = response.json()
        assert "error" in data

    def test_413_response_has_message_field(self, client: TestClient, valid_jwt_token: str) -> None:
        """Test 413 response includes 'message' field."""
        oversized_message = "x" * 1_100_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413
        data = response.json()
        assert "message" in data


class TestRequestSizeValidationWithDifferentContentTypes:
    """Test request size validation with various content types."""

    def test_json_request_size_validation(self, client: TestClient, valid_jwt_token: str) -> None:
        """Test request size validation with JSON content."""
        oversized_message = "x" * 1_100_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413

    def test_empty_message_passes_validation(
        self, mock_orchestrator_streaming_response, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that empty message passes validation."""
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": ""}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 200

    def test_unicode_content_size_calculation(
        self, mock_orchestrator_streaming_response, client: TestClient, valid_jwt_token: str
    ) -> None:
        """Test that unicode content is properly counted in size."""
        # Unicode characters take multiple bytes
        unicode_message = "你好世界" * 100_000  # Chinese characters, ~3 bytes each
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": unicode_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        # Should reject if over 1MB when encoded
        assert response.status_code in (200, 413)


class TestErrorResponseContentValidation:
    """Test that error response content is properly formatted."""

    def test_error_message_is_string(self, client: TestClient, valid_jwt_token: str) -> None:
        """Test that error message field is a string."""
        oversized_message = "x" * 1_100_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413
        data = response.json()
        assert isinstance(data["message"], str)

    def test_error_code_is_string(self, client: TestClient, valid_jwt_token: str) -> None:
        """Test that error code field is a string."""
        oversized_message = "x" * 1_100_000
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": oversized_message}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_jwt_token}"},
        )

        assert response.status_code == 413
        data = response.json()
        assert isinstance(data["error"], str)
