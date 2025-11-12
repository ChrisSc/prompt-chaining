"""
Unit tests for security headers middleware.

Tests the middleware logic in isolation, verifying that security headers are
correctly added to responses under various conditions.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator_worker.config import Settings
from orchestrator_worker.middleware.security_headers import security_headers_middleware


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings for security headers middleware."""
    return Settings(
        anthropic_api_key="test-key-123",
        jwt_secret_key="test_secret_key_with_minimum_32_characters_required_for_testing",
    )


@pytest.fixture
def mock_request():
    """Create a mock FastAPI Request."""
    request = MagicMock()
    request.url.scheme = "http"
    request.headers = {}
    request.app.state.settings = None  # Will be set per test
    return request


@pytest.fixture
def mock_https_request():
    """Create a mock FastAPI Request with HTTPS scheme."""
    request = MagicMock()
    request.url.scheme = "https"
    request.headers = {}
    request.app.state.settings = None
    return request


@pytest.fixture
def mock_call_next():
    """Create a mock call_next function that returns a response."""
    response = MagicMock()
    response.headers = {}
    return AsyncMock(return_value=response)


@pytest.fixture
def mock_call_next_with_response():
    """Create a mock call_next that returns a response with headers dict."""

    async def next_handler(request):
        response = MagicMock()
        response.headers = {}
        response.status_code = 200
        response.body = "test"
        return response

    return next_handler


class TestSecurityHeadersPresence:
    """Test that security headers are present in responses."""

    @pytest.mark.asyncio
    async def test_all_security_headers_present_http(
        self, mock_request, mock_call_next, test_settings
    ) -> None:
        """Test that all security headers are present in HTTP response."""
        mock_request.url.scheme = "http"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "X-Content-Type-Options" in result.headers
        assert "X-Frame-Options" in result.headers
        assert "X-XSS-Protection" in result.headers

    @pytest.mark.asyncio
    async def test_all_security_headers_present_https(
        self, mock_https_request, mock_call_next
    ) -> None:
        """Test that all security headers including HSTS are present in HTTPS response."""
        mock_https_request.url.scheme = "https"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_https_request, mock_call_next)

        assert "X-Content-Type-Options" in result.headers
        assert "X-Frame-Options" in result.headers
        assert "X-XSS-Protection" in result.headers
        assert "Strict-Transport-Security" in result.headers

    @pytest.mark.asyncio
    async def test_content_type_options_header_present(self, mock_request, mock_call_next) -> None:
        """Test X-Content-Type-Options header is present."""
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "X-Content-Type-Options" in result.headers

    @pytest.mark.asyncio
    async def test_frame_options_header_present(self, mock_request, mock_call_next) -> None:
        """Test X-Frame-Options header is present."""
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "X-Frame-Options" in result.headers

    @pytest.mark.asyncio
    async def test_xss_protection_header_present(self, mock_request, mock_call_next) -> None:
        """Test X-XSS-Protection header is present."""
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "X-XSS-Protection" in result.headers


class TestHSTSConditionalLogic:
    """Test HSTS header conditional logic."""

    @pytest.mark.asyncio
    async def test_hsts_added_for_https_scheme(self, mock_https_request, mock_call_next) -> None:
        """Test HSTS header is added when request.url.scheme == https."""
        mock_https_request.url.scheme = "https"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_https_request, mock_call_next)

        assert "Strict-Transport-Security" in result.headers

    @pytest.mark.asyncio
    async def test_hsts_added_for_x_forwarded_proto_https(
        self, mock_request, mock_call_next
    ) -> None:
        """Test HSTS header is added when X-Forwarded-Proto: https."""
        mock_request.url.scheme = "http"
        mock_request.headers["X-Forwarded-Proto"] = "https"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "Strict-Transport-Security" in result.headers

    @pytest.mark.asyncio
    async def test_hsts_not_added_for_http_scheme(self, mock_request, mock_call_next) -> None:
        """Test HSTS header is NOT added when request.url.scheme == http."""
        mock_request.url.scheme = "http"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "Strict-Transport-Security" not in result.headers

    @pytest.mark.asyncio
    async def test_hsts_not_added_for_x_forwarded_proto_http(
        self, mock_request, mock_call_next
    ) -> None:
        """Test HSTS header is NOT added when X-Forwarded-Proto: http."""
        mock_request.url.scheme = "http"
        mock_request.headers["X-Forwarded-Proto"] = "http"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "Strict-Transport-Security" not in result.headers

    @pytest.mark.asyncio
    async def test_hsts_case_insensitive_x_forwarded_proto_https(
        self, mock_request, mock_call_next
    ) -> None:
        """Test HSTS added when X-Forwarded-Proto is 'HTTPS' (uppercase)."""
        mock_request.url.scheme = "http"
        mock_request.headers["X-Forwarded-Proto"] = "HTTPS"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "Strict-Transport-Security" in result.headers

    @pytest.mark.asyncio
    async def test_hsts_case_insensitive_x_forwarded_proto_https_mixed_case(
        self, mock_request, mock_call_next
    ) -> None:
        """Test HSTS added when X-Forwarded-Proto is 'Https' (mixed case)."""
        mock_request.url.scheme = "http"
        mock_request.headers["X-Forwarded-Proto"] = "Https"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "Strict-Transport-Security" in result.headers

    @pytest.mark.asyncio
    async def test_hsts_scheme_takes_precedence_over_x_forwarded_proto(
        self, mock_https_request, mock_call_next
    ) -> None:
        """Test HTTPS scheme takes precedence when X-Forwarded-Proto is http."""
        mock_https_request.url.scheme = "https"
        mock_https_request.headers["X-Forwarded-Proto"] = "http"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_https_request, mock_call_next)

        # HSTS should be added because direct scheme is https
        assert "Strict-Transport-Security" in result.headers


class TestHeaderValues:
    """Test exact header values match specification."""

    @pytest.mark.asyncio
    async def test_content_type_options_exact_value(self, mock_request, mock_call_next) -> None:
        """Test X-Content-Type-Options has exact value 'nosniff'."""
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert result.headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_frame_options_exact_value(self, mock_request, mock_call_next) -> None:
        """Test X-Frame-Options has exact value 'DENY'."""
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert result.headers["X-Frame-Options"] == "DENY"

    @pytest.mark.asyncio
    async def test_xss_protection_exact_value(self, mock_request, mock_call_next) -> None:
        """Test X-XSS-Protection has exact value '1; mode=block'."""
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert result.headers["X-XSS-Protection"] == "1; mode=block"

    @pytest.mark.asyncio
    async def test_hsts_exact_value(self, mock_https_request, mock_call_next) -> None:
        """Test Strict-Transport-Security has exact value."""
        mock_https_request.url.scheme = "https"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_https_request, mock_call_next)

        assert result.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


class TestMiddlewareExecution:
    """Test middleware execution and response handling."""

    @pytest.mark.asyncio
    async def test_middleware_calls_call_next(self, mock_request, mock_call_next) -> None:
        """Test middleware calls call_next with the request."""
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        await security_headers_middleware(mock_request, mock_call_next)

        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_middleware_returns_response(self, mock_request, mock_call_next) -> None:
        """Test middleware returns the response from call_next."""
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert result is response

    @pytest.mark.asyncio
    async def test_middleware_preserves_status_code(self, mock_request, mock_call_next) -> None:
        """Test middleware doesn't modify response status code."""
        response = MagicMock()
        response.headers = {}
        response.status_code = 200
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_middleware_preserves_response_body(self, mock_request, mock_call_next) -> None:
        """Test middleware doesn't modify response body."""
        response = MagicMock()
        response.headers = {}
        response.body = b"test response body"
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert result.body == b"test response body"

    @pytest.mark.asyncio
    async def test_middleware_with_json_content_type(self, mock_request, mock_call_next) -> None:
        """Test middleware works with JSON content type."""
        response = MagicMock()
        response.headers = {"content-type": "application/json"}
        response.status_code = 200
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        # Verify security headers were added
        assert "X-Content-Type-Options" in result.headers
        # And original header preserved
        assert result.headers["content-type"] == "application/json"

    @pytest.mark.asyncio
    async def test_middleware_with_streaming_response(self, mock_request, mock_call_next) -> None:
        """Test middleware works with streaming responses."""
        response = MagicMock()
        response.headers = {}
        response.status_code = 200
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "X-Content-Type-Options" in result.headers

    @pytest.mark.asyncio
    async def test_middleware_with_error_response(self, mock_request, mock_call_next) -> None:
        """Test middleware adds headers to error responses."""
        response = MagicMock()
        response.headers = {}
        response.status_code = 500
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        # Headers should still be added even for error responses
        assert "X-Content-Type-Options" in result.headers
        assert result.status_code == 500

    @pytest.mark.asyncio
    async def test_middleware_with_redirect_response(self, mock_request, mock_call_next) -> None:
        """Test middleware works with redirect responses."""
        response = MagicMock()
        response.headers = {"location": "http://example.com"}
        response.status_code = 302
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "X-Content-Type-Options" in result.headers
        assert result.headers["location"] == "http://example.com"

    @pytest.mark.asyncio
    async def test_middleware_with_404_response(self, mock_request, mock_call_next) -> None:
        """Test middleware adds headers to 404 responses."""
        response = MagicMock()
        response.headers = {}
        response.status_code = 404
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "X-Content-Type-Options" in result.headers
        assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_middleware_with_401_response(self, mock_request, mock_call_next) -> None:
        """Test middleware adds headers to 401 Unauthorized responses."""
        response = MagicMock()
        response.headers = {}
        response.status_code = 401
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "X-Content-Type-Options" in result.headers
        assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_middleware_with_403_response(self, mock_request, mock_call_next) -> None:
        """Test middleware adds headers to 403 Forbidden responses."""
        response = MagicMock()
        response.headers = {}
        response.status_code = 403
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "X-Content-Type-Options" in result.headers
        assert result.status_code == 403


class TestMissingXForwardedProtoHeader:
    """Test behavior when X-Forwarded-Proto header is missing."""

    @pytest.mark.asyncio
    async def test_hsts_not_added_when_x_forwarded_proto_missing_http(
        self, mock_request, mock_call_next
    ) -> None:
        """Test HSTS not added when X-Forwarded-Proto header is missing and scheme is http."""
        mock_request.url.scheme = "http"
        # Don't set X-Forwarded-Proto header
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "Strict-Transport-Security" not in result.headers

    @pytest.mark.asyncio
    async def test_hsts_added_when_x_forwarded_proto_missing_but_scheme_https(
        self, mock_https_request, mock_call_next
    ) -> None:
        """Test HSTS added when X-Forwarded-Proto missing but scheme is https."""
        mock_https_request.url.scheme = "https"
        # Don't set X-Forwarded-Proto header
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_https_request, mock_call_next)

        assert "Strict-Transport-Security" in result.headers

    @pytest.mark.asyncio
    async def test_hsts_not_added_when_x_forwarded_proto_empty_string(
        self, mock_request, mock_call_next
    ) -> None:
        """Test HSTS not added when X-Forwarded-Proto is empty string."""
        mock_request.url.scheme = "http"
        mock_request.headers["X-Forwarded-Proto"] = ""
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "Strict-Transport-Security" not in result.headers

    @pytest.mark.asyncio
    async def test_hsts_not_added_when_x_forwarded_proto_has_spaces(
        self, mock_request, mock_call_next
    ) -> None:
        """Test HSTS not added when X-Forwarded-Proto has unexpected value with spaces."""
        mock_request.url.scheme = "http"
        mock_request.headers["X-Forwarded-Proto"] = " https "
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        # The implementation uses .lower() but doesn't strip, so " https " != "https"
        assert "Strict-Transport-Security" not in result.headers


class TestHeadersOnVariousEndpoints:
    """Test security headers on different endpoint types."""

    @pytest.mark.asyncio
    async def test_headers_on_health_endpoint(self, mock_request, mock_call_next) -> None:
        """Test security headers on /health/ endpoint."""
        mock_request.url.path = "/health/"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "X-Content-Type-Options" in result.headers
        assert "X-Frame-Options" in result.headers

    @pytest.mark.asyncio
    async def test_headers_on_models_endpoint(self, mock_request, mock_call_next) -> None:
        """Test security headers on /v1/models endpoint."""
        mock_request.url.path = "/v1/models"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "X-Content-Type-Options" in result.headers

    @pytest.mark.asyncio
    async def test_headers_on_chat_completions_endpoint(self, mock_request, mock_call_next) -> None:
        """Test security headers on /v1/chat/completions endpoint."""
        mock_request.url.path = "/v1/chat/completions"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        assert "X-Content-Type-Options" in result.headers


class TestMultipleHeadersPreservation:
    """Test that middleware preserves existing headers."""

    @pytest.mark.asyncio
    async def test_middleware_preserves_existing_headers(
        self, mock_request, mock_call_next
    ) -> None:
        """Test that middleware preserves existing response headers."""
        response = MagicMock()
        response.headers = {"custom-header": "custom-value"}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        # Existing header should be preserved
        assert result.headers["custom-header"] == "custom-value"
        # Security headers should be added
        assert "X-Content-Type-Options" in result.headers

    @pytest.mark.asyncio
    async def test_middleware_overwrites_security_headers_if_present(
        self, mock_request, mock_call_next
    ) -> None:
        """Test that middleware overwrites security headers if already present."""
        response = MagicMock()
        response.headers = {"X-Content-Type-Options": "sniff"}  # Wrong value
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        # Should overwrite with correct value
        assert result.headers["X-Content-Type-Options"] == "nosniff"


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_middleware_with_none_headers(self, mock_request) -> None:
        """Test middleware handles response with headers set to empty dict."""
        response = MagicMock()
        response.headers = {}

        async def call_next_fn(req):
            return response

        result = await security_headers_middleware(mock_request, call_next_fn)

        assert "X-Content-Type-Options" in result.headers

    @pytest.mark.asyncio
    async def test_hsts_with_mixed_case_x_forwarded_proto_and_http_scheme(
        self, mock_request, mock_call_next
    ) -> None:
        """Test HSTS logic with X-Forwarded-Proto HTTPS and http scheme."""
        mock_request.url.scheme = "http"
        mock_request.headers["X-Forwarded-Proto"] = "HTTPS"
        response = MagicMock()
        response.headers = {}
        mock_call_next.return_value = response

        result = await security_headers_middleware(mock_request, mock_call_next)

        # X-Forwarded-Proto takes priority when set to https
        assert "Strict-Transport-Security" in result.headers

    @pytest.mark.asyncio
    async def test_headers_unchanged_across_multiple_calls(
        self, mock_request, mock_call_next
    ) -> None:
        """Test that security header values remain consistent across calls."""
        response1 = MagicMock()
        response1.headers = {}
        mock_call_next.return_value = response1

        result1 = await security_headers_middleware(mock_request, mock_call_next)
        header_value_1 = result1.headers["X-Content-Type-Options"]

        response2 = MagicMock()
        response2.headers = {}
        mock_call_next.return_value = response2

        result2 = await security_headers_middleware(mock_request, mock_call_next)
        header_value_2 = result2.headers["X-Content-Type-Options"]

        assert header_value_1 == header_value_2
        assert header_value_1 == "nosniff"
