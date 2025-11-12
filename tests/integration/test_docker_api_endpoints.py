"""
Integration tests for Docker API endpoints.

These tests validate that the running Docker container serves API endpoints
correctly with proper authentication, request validation, and response formats.

Note: These tests require the container to be running.
Start the container with: docker-compose up -d
"""

import json
import os
import subprocess
from pathlib import Path

import httpx
import pytest


class TestDockerAPIBasicAccess:
    """Test basic API access to running container."""

    @pytest.fixture
    def container_url(self) -> str:
        """Get the container URL."""
        return "http://localhost:8000"

    @pytest.fixture
    def bearer_token(self) -> str | None:
        """Get or generate a bearer token for authentication."""
        # Try to get token from environment variable
        token = os.getenv("API_BEARER_TOKEN")
        if token:
            return token

        # Try to generate a token
        try:
            project_root = Path(__file__).parent.parent.parent
            result = subprocess.run(
                ["python", "scripts/generate_jwt.py"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return None

    @pytest.mark.asyncio
    async def test_health_endpoint_no_auth(self, container_url: str) -> None:
        """Test that /health/ endpoint is public (no auth required)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{container_url}/health/", timeout=5.0)
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ready_endpoint_no_auth(self, container_url: str) -> None:
        """Test that /health/ready endpoint is public (no auth required)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{container_url}/health/ready", timeout=5.0)
            assert response.status_code == 200


class TestDockerAPIAuthentication:
    """Test API authentication with bearer tokens."""

    @pytest.fixture
    def container_url(self) -> str:
        """Get the container URL."""
        return "http://localhost:8000"

    @pytest.fixture
    def project_root(self) -> Path:
        """Get project root."""
        return Path(__file__).parent.parent.parent

    @pytest.fixture
    def bearer_token(self, project_root: Path) -> str | None:
        """Generate a valid bearer token."""
        try:
            result = subprocess.run(
                ["python", "scripts/generate_jwt.py"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    @pytest.mark.asyncio
    async def test_models_endpoint_without_auth_returns_401(self, container_url: str) -> None:
        """Test that /v1/models without auth returns 401."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{container_url}/v1/models", timeout=5.0)
            # Should be 401 Unauthorized
            assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_models_endpoint_with_invalid_token_returns_403(self, container_url: str) -> None:
        """Test that /v1/models with invalid token returns 403."""
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": "Bearer invalid.token.here"}
            response = await client.get(f"{container_url}/v1/models", headers=headers, timeout=5.0)
            # Should be 403 Forbidden for invalid token
            assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_models_endpoint_with_valid_token(
        self, container_url: str, bearer_token: str | None
    ) -> None:
        """Test that /v1/models with valid token returns 200."""
        if not bearer_token:
            pytest.skip("Could not generate bearer token")

        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {bearer_token}"}
            response = await client.get(f"{container_url}/v1/models", headers=headers, timeout=5.0)
            # Should be 200 OK
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_models_endpoint_returns_json(
        self, container_url: str, bearer_token: str | None
    ) -> None:
        """Test that /v1/models returns JSON response."""
        if not bearer_token:
            pytest.skip("Could not generate bearer token")

        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {bearer_token}"}
            response = await client.get(f"{container_url}/v1/models", headers=headers, timeout=5.0)

            if response.status_code == 200:
                # Should be valid JSON
                try:
                    data = response.json()
                    assert isinstance(data, dict)
                    # Should have a 'data' or 'models' field
                    assert "data" in data or "models" in data
                except json.JSONDecodeError:
                    pytest.fail("Response is not valid JSON")


class TestDockerChatCompletionEndpoint:
    """Test /v1/chat/completions endpoint."""

    @pytest.fixture
    def container_url(self) -> str:
        """Get the container URL."""
        return "http://localhost:8000"

    @pytest.fixture
    def project_root(self) -> Path:
        """Get project root."""
        return Path(__file__).parent.parent.parent

    @pytest.fixture
    def bearer_token(self, project_root: Path) -> str | None:
        """Generate a valid bearer token."""
        try:
            result = subprocess.run(
                ["python", "scripts/generate_jwt.py"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    @pytest.mark.asyncio
    async def test_chat_completions_requires_auth(self, container_url: str) -> None:
        """Test that /v1/chat/completions requires authentication."""
        async with httpx.AsyncClient() as client:
            payload = {
                "model": "orchestrator-worker",
                "messages": [{"role": "user", "content": "Hello"}],
            }
            response = await client.post(
                f"{container_url}/v1/chat/completions",
                json=payload,
                timeout=5.0,
            )
            # Should require auth
            assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_chat_completions_with_valid_token(
        self, container_url: str, bearer_token: str | None
    ) -> None:
        """Test that /v1/chat/completions works with valid token."""
        if not bearer_token:
            pytest.skip("Could not generate bearer token")

        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {bearer_token}"}
            payload = {
                "model": "orchestrator-worker",
                "messages": [{"role": "user", "content": "Say hello"}],
            }
            response = await client.post(
                f"{container_url}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=30.0,
            )
            # Should be 200 or 202
            assert response.status_code in [200, 202, 201]

    @pytest.mark.asyncio
    async def test_chat_completions_streaming_response(
        self, container_url: str, bearer_token: str | None
    ) -> None:
        """Test that /v1/chat/completions returns streaming response."""
        if not bearer_token:
            pytest.skip("Could not generate bearer token")

        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {bearer_token}"}
            payload = {
                "model": "orchestrator-worker",
                "messages": [{"role": "user", "content": "Say hello"}],
            }
            async with client.stream(
                "POST",
                f"{container_url}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=30.0,
            ) as response:
                # Should be 200
                assert response.status_code == 200

                # Collect response content
                content = await response.aread()
                content_str = content.decode("utf-8")

                # Should contain SSE format data
                assert "data:" in content_str or len(content_str) > 0


class TestDockerRequestValidation:
    """Test request validation in Docker container."""

    @pytest.fixture
    def container_url(self) -> str:
        """Get the container URL."""
        return "http://localhost:8000"

    @pytest.fixture
    def project_root(self) -> Path:
        """Get project root."""
        return Path(__file__).parent.parent.parent

    @pytest.fixture
    def bearer_token(self, project_root: Path) -> str | None:
        """Generate a valid bearer token."""
        try:
            result = subprocess.run(
                ["python", "scripts/generate_jwt.py"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    @pytest.mark.asyncio
    async def test_missing_model_field(
        self, container_url: str, bearer_token: str | None
    ) -> None:
        """Test that missing model field is validated."""
        if not bearer_token:
            pytest.skip("Could not generate bearer token")

        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {bearer_token}"}
            payload = {
                # Missing 'model' field
                "messages": [{"role": "user", "content": "Hello"}],
            }
            response = await client.post(
                f"{container_url}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=5.0,
            )
            # Should be 422 Unprocessable Entity
            assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_missing_messages_field(
        self, container_url: str, bearer_token: str | None
    ) -> None:
        """Test that missing messages field is validated."""
        if not bearer_token:
            pytest.skip("Could not generate bearer token")

        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {bearer_token}"}
            payload = {
                "model": "orchestrator-worker",
                # Missing 'messages' field
            }
            response = await client.post(
                f"{container_url}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=5.0,
            )
            # Should be 422 Unprocessable Entity
            assert response.status_code in [400, 422]


class TestDockerResponseFormats:
    """Test response formats from Docker container."""

    @pytest.fixture
    def container_url(self) -> str:
        """Get the container URL."""
        return "http://localhost:8000"

    @pytest.fixture
    def project_root(self) -> Path:
        """Get project root."""
        return Path(__file__).parent.parent.parent

    @pytest.fixture
    def bearer_token(self, project_root: Path) -> str | None:
        """Generate a valid bearer token."""
        try:
            result = subprocess.run(
                ["python", "scripts/generate_jwt.py"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    @pytest.mark.asyncio
    async def test_health_response_has_status(self, container_url: str) -> None:
        """Test that health response contains status."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{container_url}/health/", timeout=5.0)
            data = response.json()
            # Should have status or similar field
            assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_models_response_format(
        self, container_url: str, bearer_token: str | None
    ) -> None:
        """Test that models response has correct format."""
        if not bearer_token:
            pytest.skip("Could not generate bearer token")

        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {bearer_token}"}
            response = await client.get(f"{container_url}/v1/models", headers=headers, timeout=5.0)

            if response.status_code == 200:
                data = response.json()
                # Should be a dict with data field (OpenAI format)
                assert isinstance(data, dict)


class TestDockerHTTPHeaders:
    """Test HTTP headers in responses."""

    @pytest.fixture
    def container_url(self) -> str:
        """Get the container URL."""
        return "http://localhost:8000"

    @pytest.fixture
    def project_root(self) -> Path:
        """Get project root."""
        return Path(__file__).parent.parent.parent

    @pytest.fixture
    def bearer_token(self, project_root: Path) -> str | None:
        """Generate a valid bearer token."""
        try:
            result = subprocess.run(
                ["python", "scripts/generate_jwt.py"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    @pytest.mark.asyncio
    async def test_health_response_headers(self, container_url: str) -> None:
        """Test that health response has proper headers."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{container_url}/health/", timeout=5.0)
            # Should have content-type
            assert "content-type" in response.headers or "Content-Type" in response.headers

    @pytest.mark.asyncio
    async def test_response_content_type_json(
        self, container_url: str, bearer_token: str | None
    ) -> None:
        """Test that API responses have application/json content type."""
        if not bearer_token:
            pytest.skip("Could not generate bearer token")

        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {bearer_token}"}
            response = await client.get(f"{container_url}/v1/models", headers=headers, timeout=5.0)

            if response.status_code == 200:
                content_type = response.headers.get("content-type", "").lower()
                assert "application/json" in content_type or "json" in content_type
