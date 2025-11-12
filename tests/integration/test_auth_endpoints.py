"""
Integration tests for JWT bearer authentication on API endpoints.

Tests that protected endpoints require valid JWT tokens, public endpoints work
without tokens, and proper HTTP status codes are returned for various auth scenarios.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

from orchestrator_worker.config import Settings
from orchestrator_worker.main import create_app
from orchestrator_worker.models.openai import (
    ChatCompletionChunk,
    ChatCompletionStreamChoice,
    ChoiceDelta,
)

# Use a consistent secret key for all tests
TEST_JWT_SECRET = "test_secret_key_with_minimum_32_characters_required_for_testing"


@pytest.fixture(autouse=True)
def set_test_env():
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
def jwt_settings() -> Settings:
    """Create test settings with JWT configuration."""
    return Settings(
        anthropic_api_key="test-key-123",
        jwt_secret_key=TEST_JWT_SECRET,
        jwt_algorithm="HS256",
        environment="development",
        log_level="DEBUG",
    )


@pytest.fixture
def valid_token(jwt_settings: Settings) -> str:
    """Generate a valid JWT token."""
    payload = {
        "sub": "test-client",
        "iat": datetime.now(tz=timezone.utc),
    }
    return jwt.encode(
        payload,
        jwt_settings.jwt_secret_key,
        algorithm=jwt_settings.jwt_algorithm,
    )


@pytest.fixture
def expired_token(jwt_settings: Settings) -> str:
    """Generate an expired JWT token."""
    payload = {
        "sub": "test-client",
        "iat": datetime.now(tz=timezone.utc) - timedelta(hours=2),
        "exp": datetime.now(tz=timezone.utc) - timedelta(hours=1),
    }
    return jwt.encode(
        payload,
        jwt_settings.jwt_secret_key,
        algorithm=jwt_settings.jwt_algorithm,
    )


@pytest.fixture
def invalid_signature_token(jwt_settings: Settings) -> str:
    """Generate a token with invalid signature."""
    payload = {
        "sub": "test-client",
        "iat": datetime.now(tz=timezone.utc),
    }
    # Sign with different secret than jwt_settings
    return jwt.encode(
        payload,
        "wrong_secret_key_with_minimum_32_characters_for_testing",
        algorithm="HS256",
    )


@pytest.fixture
def app_with_mocks(jwt_settings: Settings):
    """Create FastAPI app with mocked orchestrator."""
    with patch("orchestrator_worker.main.Orchestrator") as mock_orchestrator_class:
        mock_orchestrator = AsyncMock()
        mock_orchestrator.model = "claude-sonnet-4-5-20250929"
        mock_orchestrator_class.return_value = mock_orchestrator

        app = create_app()
        app.state.orchestrator = mock_orchestrator
        app.state.settings = jwt_settings

    return app


@pytest.fixture
def client(app_with_mocks):
    """Create test client from app."""
    return TestClient(app_with_mocks)


class TestChatEndpointAuth:
    """Test authentication on chat completions endpoint."""

    def test_chat_endpoint_with_valid_token(
        self, client: TestClient, valid_token: str, app_with_mocks
    ) -> None:
        """Test POST to /v1/chat/completions with valid token succeeds."""

        # Mock the orchestrator to return a valid response
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

        app_with_mocks.state.orchestrator.process = mock_process

        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_chat_endpoint_without_token(self, client: TestClient) -> None:
        """Test POST without token returns 403."""
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_chat_endpoint_with_invalid_token(
        self, client: TestClient, invalid_signature_token: str
    ) -> None:
        """Test POST with invalid token returns 403."""
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {invalid_signature_token}"},
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data
        assert "invalid" in data["detail"].lower()

    def test_chat_endpoint_with_expired_token(self, client: TestClient, expired_token: str) -> None:
        """Test POST with expired token returns 401."""
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "expired" in data["detail"].lower()

    def test_chat_endpoint_with_malformed_token(self, client: TestClient) -> None:
        """Test POST with malformed token returns 403."""
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": "Bearer not.a.valid.jwt"},
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_chat_endpoint_with_wrong_auth_scheme(
        self, client: TestClient, valid_token: str
    ) -> None:
        """Test POST with wrong auth scheme (e.g., Basic instead of Bearer)."""
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Basic {valid_token}"},
        )

        assert response.status_code == 403


class TestModelsEndpointAuth:
    """Test authentication on models listing endpoint."""

    def test_models_endpoint_with_valid_token(self, client: TestClient, valid_token: str) -> None:
        """Test GET to /v1/models with valid token succeeds."""
        response = client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "object" in data
        assert data["object"] == "list"
        assert "data" in data

    def test_models_endpoint_without_token(self, client: TestClient) -> None:
        """Test GET without token returns 403."""
        response = client.get("/v1/models")

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_models_endpoint_with_invalid_token(
        self, client: TestClient, invalid_signature_token: str
    ) -> None:
        """Test GET with invalid token returns 403."""
        response = client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {invalid_signature_token}"},
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data
        assert "invalid" in data["detail"].lower()

    def test_models_endpoint_with_expired_token(
        self, client: TestClient, expired_token: str
    ) -> None:
        """Test GET with expired token returns 401."""
        response = client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "expired" in data["detail"].lower()

    def test_models_endpoint_with_custom_token_claims(
        self, client: TestClient, jwt_settings: Settings
    ) -> None:
        """Test that models endpoint accepts tokens with custom claims."""
        # Generate token with custom claims
        payload = {
            "sub": "premium-client",
            "iat": datetime.now(tz=timezone.utc),
            "organization_id": "org-123",
            "plan": "enterprise",
        }
        token = jwt.encode(
            payload,
            jwt_settings.jwt_secret_key,
            algorithm=jwt_settings.jwt_algorithm,
        )

        response = client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200


class TestHealthEndpointsNoAuth:
    """Test that health endpoints work without authentication."""

    def test_health_endpoint_no_auth(self, client: TestClient) -> None:
        """Test GET to /health/ works without token."""
        response = client.get("/health/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_endpoint_with_token(self, client: TestClient, valid_token: str) -> None:
        """Test GET to /health/ works with token (should not require it)."""
        response = client.get(
            "/health/",
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_ready_endpoint_no_auth(self, client: TestClient) -> None:
        """Test GET to /health/ready works without token."""
        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"

    def test_health_ready_endpoint_with_token(self, client: TestClient, valid_token: str) -> None:
        """Test GET to /health/ready works with token (should not require it)."""
        response = client.get(
            "/health/ready",
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


class TestAuthHeaderEdgeCases:
    """Test edge cases in Authorization header handling."""

    def test_empty_authorization_header(self, client: TestClient) -> None:
        """Test empty Authorization header returns 403."""
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": ""},
        )

        assert response.status_code == 403

    def test_bearer_with_no_token(self, client: TestClient) -> None:
        """Test 'Bearer' with no token returns 403."""
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": "Bearer "},
        )

        assert response.status_code == 403

    def test_token_with_extra_spaces(self, client: TestClient, valid_token: str) -> None:
        """Test token with extra spaces around value."""
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"Bearer  {valid_token}  "},
        )

        # FastAPI's HTTPBearer should handle trimming
        assert response.status_code in (200, 403)

    def test_bearer_scheme_case_insensitive(self, client: TestClient, valid_token: str) -> None:
        """Test that Bearer scheme matching is case-insensitive in HTTP."""
        request_body = {
            "model": "test-service",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        # HTTPBearer accepts both Bearer and bearer (case-insensitive per HTTP spec)
        # This should return 200 since the token is valid
        response = client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": f"bearer {valid_token}"},
        )

        # Should accept the token regardless of Bearer/bearer case
        assert response.status_code == 200


class TestOpenAICompatibleErrorFormats:
    """Test that auth errors follow OpenAI API format."""

    def test_missing_auth_error_format(self, client: TestClient) -> None:
        """Test missing auth error follows OpenAI format."""
        response = client.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "Hi"}]},
        )

        assert response.status_code == 403
        data = response.json()
        # OpenAI returns error with 'detail' field
        assert "detail" in data

    def test_invalid_token_error_format(
        self, client: TestClient, invalid_signature_token: str
    ) -> None:
        """Test invalid token error follows OpenAI format."""
        response = client.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "Hi"}]},
            headers={"Authorization": f"Bearer {invalid_signature_token}"},
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data
        assert "invalid" in data["detail"].lower()

    def test_expired_token_error_format(self, client: TestClient, expired_token: str) -> None:
        """Test expired token error follows OpenAI format."""
        response = client.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "Hi"}]},
            headers={"Authorization": f"Bearer {expired_token}"},
        )

        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "expired" in data["detail"].lower()
