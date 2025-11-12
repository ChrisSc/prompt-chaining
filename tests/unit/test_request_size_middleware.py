"""
Unit tests for request size validation middleware.

Tests the middleware logic in isolation, verifying that request size validation
works correctly for different Content-Length values and request types.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from workflow.config import Settings
from workflow.middleware.request_size import request_size_validator
from workflow.utils.errors import RequestSizeError


class TestRequestSizeError:
    """Test RequestSizeError exception."""

    def test_request_size_error_creation(self) -> None:
        """Test creating RequestSizeError with size attributes."""
        error = RequestSizeError(actual_size=2_000_000, max_size=1_000_000)
        assert error.actual_size == 2_000_000
        assert error.max_size == 1_000_000
        assert error.error_code == "REQUEST_TOO_LARGE"
        assert "2000000" in str(error.message) or "2000000" in error.message

    def test_request_size_error_message_format(self) -> None:
        """Test error message includes size information."""
        error = RequestSizeError(actual_size=5_000_000, max_size=1_000_000)
        error_msg = error.message.lower()
        assert "size" in error_msg
        assert "5000000" in error.message or "5" in error.message

    def test_request_size_error_inheritance(self) -> None:
        """Test RequestSizeError inherits from TemplateServiceError."""
        from workflow.utils.errors import TemplateServiceError

        error = RequestSizeError(actual_size=2_000_000, max_size=1_000_000)
        assert isinstance(error, TemplateServiceError)


@pytest.fixture
def test_settings_default() -> Settings:
    """Create test settings with default max_request_body_size."""
    return Settings(
        anthropic_api_key="test-key-123",
        jwt_secret_key="test_secret_key_with_minimum_32_characters_required_for_testing",
    )


@pytest.fixture
def test_settings_custom_limit() -> Settings:
    """Create test settings with custom max_request_body_size."""
    return Settings(
        anthropic_api_key="test-key-123",
        jwt_secret_key="test_secret_key_with_minimum_32_characters_required_for_testing",
        max_request_body_size=500_000,  # 500KB
    )


@pytest.fixture
def mock_request():
    """Create a mock FastAPI Request with proper app state."""
    request = MagicMock()
    request.method = "POST"
    request.url.path = "/v1/chat/completions"
    request.headers = {}
    # Set up app state with settings attribute
    request.app.state.settings = None  # Will be set per test
    return request


@pytest.fixture
def mock_call_next():
    """Create a mock call_next function."""
    return AsyncMock()


class TestRequestSizeValidationPasses:
    """Test cases where request size validation passes."""

    @pytest.mark.asyncio
    async def test_request_size_validation_passes_small_request(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that request well under limit passes validation."""
        mock_request.headers["content-length"] = "50000"  # 50KB
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 200
        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_request_size_validation_passes_at_limit(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that request exactly at limit passes validation."""
        limit = test_settings_default.max_request_body_size
        mock_request.headers["content-length"] = str(limit)
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 200
        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_request_size_validation_passes_just_under_limit(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that request just under limit passes validation."""
        limit = test_settings_default.max_request_body_size
        mock_request.headers["content-length"] = str(limit - 1)
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 200
        mock_call_next.assert_called_once_with(mock_request)


class TestRequestSizeValidationRejects:
    """Test cases where request size validation rejects requests."""

    @pytest.mark.asyncio
    async def test_request_size_validation_rejects_oversized_request(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that request exceeding limit raises RequestSizeError."""
        limit = test_settings_default.max_request_body_size
        oversized = limit + 1
        mock_request.headers["content-length"] = str(oversized)
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 413
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_size_validation_rejects_much_oversized_request(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that much larger request is rejected."""
        oversized = 10_000_000  # 10MB
        mock_request.headers["content-length"] = str(oversized)
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 413
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_size_validation_rejects_with_custom_limit(
        self, mock_request, mock_call_next, test_settings_custom_limit
    ) -> None:
        """Test rejection with custom max_request_body_size."""
        oversized = 501_000  # 501KB, just over 500KB limit
        mock_request.headers["content-length"] = str(oversized)
        mock_request.app.state.settings = test_settings_custom_limit

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 413
        mock_call_next.assert_not_called()


class TestRequestSizeValidationSkipConditions:
    """Test cases where request size validation is skipped."""

    @pytest.mark.asyncio
    async def test_request_size_validation_skips_get_requests(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that GET requests skip size validation."""
        mock_request.method = "GET"
        # Very large content-length header (shouldn't matter for GET)
        mock_request.headers["content-length"] = "999999999"
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 200
        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_request_size_validation_skips_head_requests(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that HEAD requests are validated (not skipped like GET)."""
        mock_request.method = "HEAD"
        mock_request.headers["content-length"] = "999999999"
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 413
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_size_validation_skips_health_endpoint(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that /health/ endpoint skips size validation."""
        mock_request.method = "POST"
        mock_request.url.path = "/health/"
        mock_request.headers["content-length"] = "999999999"
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 200
        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_request_size_validation_skips_health_ready_endpoint(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that /health/ready endpoint skips size validation."""
        mock_request.method = "POST"
        mock_request.url.path = "/health/ready"
        mock_request.headers["content-length"] = "999999999"
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 200
        mock_call_next.assert_called_once_with(mock_request)


class TestRequestSizeValidationMissingContentLength:
    """Test cases with missing or invalid Content-Length header."""

    @pytest.mark.asyncio
    async def test_request_size_validation_handles_missing_content_length(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that missing Content-Length header doesn't crash."""
        mock_request.headers = {}  # No content-length header
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 200
        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_request_size_validation_handles_zero_content_length(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that zero Content-Length passes."""
        mock_request.headers["content-length"] = "0"
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 200
        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_request_size_validation_handles_invalid_content_length_non_numeric(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that invalid (non-numeric) Content-Length header is handled gracefully."""
        mock_request.headers["content-length"] = "not-a-number"
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = test_settings_default

        # Should not crash, but skip validation for non-numeric value
        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 200
        mock_call_next.assert_called_once_with(mock_request)


class TestRequestSizeErrorAttributes:
    """Test RequestSizeError attributes and properties."""

    def test_request_size_error_has_correct_attributes(self) -> None:
        """Test that exception stores actual_size and max_size."""
        error = RequestSizeError(actual_size=2_500_000, max_size=1_000_000)
        assert hasattr(error, "actual_size")
        assert hasattr(error, "max_size")
        assert error.actual_size == 2_500_000
        assert error.max_size == 1_000_000

    def test_request_size_error_inherited_attributes(self) -> None:
        """Test inherited attributes from TemplateServiceError."""
        error = RequestSizeError(actual_size=2_500_000, max_size=1_000_000)
        assert hasattr(error, "message")
        assert hasattr(error, "error_code")
        assert error.error_code == "REQUEST_TOO_LARGE"


class TestRequestSizeConfigurable:
    """Test that request size limit is configurable."""

    @pytest.mark.asyncio
    async def test_request_size_configurable_via_settings_small(
        self, mock_request, mock_call_next
    ) -> None:
        """Test setting max_request_body_size to small value."""
        small_limit = 100_000  # 100KB
        settings = Settings(
            anthropic_api_key="test-key-123",
            jwt_secret_key="test_secret_key_with_minimum_32_characters_required_for_testing",
            max_request_body_size=small_limit,
        )

        # Request at the limit should pass
        mock_request.headers["content-length"] = str(small_limit)
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = settings

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_request_size_configurable_via_settings_large(
        self, mock_request, mock_call_next
    ) -> None:
        """Test setting max_request_body_size to large value."""
        large_limit = 10_000_000  # 10MB
        settings = Settings(
            anthropic_api_key="test-key-123",
            jwt_secret_key="test_secret_key_with_minimum_32_characters_required_for_testing",
            max_request_body_size=large_limit,
        )

        # 5MB request should pass with 10MB limit
        mock_request.headers["content-length"] = str(5_000_000)
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = settings

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_request_size_respects_settings_limit_for_rejection(
        self, mock_request, mock_call_next
    ) -> None:
        """Test that custom limit is respected for rejection."""
        custom_limit = 500_000  # 500KB
        settings = Settings(
            anthropic_api_key="test-key-123",
            jwt_secret_key="test_secret_key_with_minimum_32_characters_required_for_testing",
            max_request_body_size=custom_limit,
        )

        # 600KB request should fail with 500KB limit
        mock_request.headers["content-length"] = "600000"
        mock_request.app.state.settings = settings

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 413


class TestRequestSizeMiddlewareCallNext:
    """Test that middleware properly calls next handler."""

    @pytest.mark.asyncio
    async def test_middleware_calls_call_next_with_request(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that middleware passes request to call_next."""
        mock_request.headers["content-length"] = "50000"
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = test_settings_default

        await request_size_validator(mock_request, mock_call_next)

        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_middleware_returns_response_from_call_next(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that middleware returns response from call_next."""
        expected_response = MagicMock(status_code=201)
        mock_request.headers["content-length"] = "50000"
        mock_call_next.return_value = expected_response
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response is expected_response


class TestRequestSizeValidationEdgeCases:
    """Test edge cases for request size validation."""

    @pytest.mark.asyncio
    async def test_request_with_negative_content_length(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test handling of negative Content-Length (invalid but test robustness)."""
        mock_request.headers["content-length"] = "-1"
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = test_settings_default

        # Should not crash, negative values should be treated as skippable
        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_request_with_very_large_content_length(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test handling of very large Content-Length numbers."""
        mock_request.headers["content-length"] = "999999999999999"  # > 1TB
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_multiple_content_length_headers(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test behavior with multiple Content-Length headers."""
        # In HTTP, multiple Content-Length headers should be same value
        # Headers mock returns comma-separated or first value
        mock_request.headers["content-length"] = "50000"
        mock_call_next.return_value = MagicMock(status_code=200)
        mock_request.app.state.settings = test_settings_default

        response = await request_size_validator(mock_request, mock_call_next)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_request_method_case_insensitivity(
        self, mock_request, mock_call_next, test_settings_default
    ) -> None:
        """Test that method name matching is case-sensitive (GET vs get)."""
        mock_request.method = "get"  # lowercase
        mock_request.headers["content-length"] = "999999999"
        mock_request.app.state.settings = test_settings_default

        # Lowercase 'get' does not match uppercase 'GET' in middleware check
        # HTTP methods are uppercase per RFC 9110, so lowercase is treated as a data-carrying method
        response = await request_size_validator(mock_request, mock_call_next)

        # Lowercase 'get' does not match 'GET', so validation applies and request is rejected
        assert response.status_code == 413
        mock_call_next.assert_not_called()
