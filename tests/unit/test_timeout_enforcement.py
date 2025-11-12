"""Unit tests for timeout enforcement error handling and configuration.

Tests the StreamingTimeoutError exception and timeout configuration validation
in the config module.
"""

import pytest

from workflow.config import Settings
from workflow.utils.errors import StreamingTimeoutError, TemplateServiceError


class TestStreamingTimeoutError:
    """Test StreamingTimeoutError exception behavior."""

    def test_streaming_timeout_error_inherits_from_template_service_error(self):
        """Verify StreamingTimeoutError inherits from TemplateServiceError."""
        error = StreamingTimeoutError(phase="worker coordination", timeout_seconds=45)
        assert isinstance(error, TemplateServiceError)

    def test_streaming_timeout_error_attributes(self):
        """Verify StreamingTimeoutError stores phase and timeout_seconds."""
        phase = "worker coordination"
        timeout = 45

        error = StreamingTimeoutError(phase=phase, timeout_seconds=timeout)

        assert error.phase == phase
        assert error.timeout_seconds == timeout
        assert error.status_code == 504

    def test_streaming_timeout_error_message_format(self):
        """Verify StreamingTimeoutError generates proper message format."""
        error = StreamingTimeoutError(phase="worker coordination", timeout_seconds=45)

        expected_substring = "timed out during worker coordination phase after 45s"
        assert expected_substring in error.message

    def test_streaming_timeout_error_synthesis_phase(self):
        """Test StreamingTimeoutError with synthesis phase."""
        error = StreamingTimeoutError(phase="synthesis", timeout_seconds=30)

        assert error.phase == "synthesis"
        assert error.timeout_seconds == 30
        assert "synthesis phase" in error.message
        assert "30s" in error.message

    def test_streaming_timeout_error_code(self):
        """Verify error code is set correctly."""
        error = StreamingTimeoutError(phase="worker coordination", timeout_seconds=45)
        assert error.error_code == "STREAMING_TIMEOUT"

    def test_streaming_timeout_error_with_various_timeouts(self):
        """Test error with different timeout values."""
        for timeout in [1, 10, 30, 45, 60, 270]:
            error = StreamingTimeoutError(phase="test", timeout_seconds=timeout)
            assert error.timeout_seconds == timeout
            assert str(timeout) in error.message


class TestTimeoutConfigurationValidation:
    """Test timeout configuration validation in Settings."""

    def test_worker_coordination_timeout_default(self):
        """Verify worker coordination timeout has correct default."""
        settings = Settings(
            anthropic_api_key="test-key-" + "x" * 30,
            jwt_secret_key="test-secret-" + "x" * 30,
        )
        assert settings.worker_coordination_timeout == 45

    def test_synthesis_timeout_default(self):
        """Verify synthesis timeout has correct default."""
        settings = Settings(
            anthropic_api_key="test-key-" + "x" * 30,
            jwt_secret_key="test-secret-" + "x" * 30,
        )
        assert settings.synthesis_timeout == 30

    def test_worker_coordination_timeout_valid_values(self):
        """Verify valid range for worker coordination timeout (1-270)."""
        for timeout in [1, 10, 45, 100, 270]:
            settings = Settings(
                anthropic_api_key="test-key-" + "x" * 30,
                jwt_secret_key="test-secret-" + "x" * 30,
                worker_coordination_timeout=timeout,
            )
            assert settings.worker_coordination_timeout == timeout

    def test_synthesis_timeout_valid_values(self):
        """Verify valid range for synthesis timeout (1-270)."""
        for timeout in [1, 15, 30, 60, 270]:
            settings = Settings(
                anthropic_api_key="test-key-" + "x" * 30,
                jwt_secret_key="test-secret-" + "x" * 30,
                synthesis_timeout=timeout,
            )
            assert settings.synthesis_timeout == timeout

    def test_worker_coordination_timeout_too_low(self):
        """Verify worker coordination timeout rejects values < 1."""
        with pytest.raises(ValueError):
            Settings(
                anthropic_api_key="test-key-" + "x" * 30,
                jwt_secret_key="test-secret-" + "x" * 30,
                worker_coordination_timeout=0,
            )

    def test_worker_coordination_timeout_too_high(self):
        """Verify worker coordination timeout rejects values > 270."""
        with pytest.raises(ValueError):
            Settings(
                anthropic_api_key="test-key-" + "x" * 30,
                jwt_secret_key="test-secret-" + "x" * 30,
                worker_coordination_timeout=271,
            )

    def test_synthesis_timeout_too_low(self):
        """Verify synthesis timeout rejects values < 1."""
        with pytest.raises(ValueError):
            Settings(
                anthropic_api_key="test-key-" + "x" * 30,
                jwt_secret_key="test-secret-" + "x" * 30,
                synthesis_timeout=0,
            )

    def test_synthesis_timeout_too_high(self):
        """Verify synthesis timeout rejects values > 270."""
        with pytest.raises(ValueError):
            Settings(
                anthropic_api_key="test-key-" + "x" * 30,
                jwt_secret_key="test-secret-" + "x" * 30,
                synthesis_timeout=271,
            )

    def test_timeout_boundary_values(self):
        """Test timeout configuration at exact boundaries."""
        # Lower boundary
        settings_min = Settings(
            anthropic_api_key="test-key-" + "x" * 30,
            jwt_secret_key="test-secret-" + "x" * 30,
            worker_coordination_timeout=1,
            synthesis_timeout=1,
        )
        assert settings_min.worker_coordination_timeout == 1
        assert settings_min.synthesis_timeout == 1

        # Upper boundary
        settings_max = Settings(
            anthropic_api_key="test-key-" + "x" * 30,
            jwt_secret_key="test-secret-" + "x" * 30,
            worker_coordination_timeout=270,
            synthesis_timeout=270,
        )
        assert settings_max.worker_coordination_timeout == 270
        assert settings_max.synthesis_timeout == 270

    def test_independent_timeout_configuration(self):
        """Verify worker and synthesis timeouts are independent."""
        settings = Settings(
            anthropic_api_key="test-key-" + "x" * 30,
            jwt_secret_key="test-secret-" + "x" * 30,
            worker_coordination_timeout=120,
            synthesis_timeout=60,
        )
        assert settings.worker_coordination_timeout == 120
        assert settings.synthesis_timeout == 60


class TestErrorMessageFormatting:
    """Test error message formatting for various timeout scenarios."""

    def test_worker_coordination_timeout_message(self):
        """Verify worker coordination timeout message is descriptive."""
        error = StreamingTimeoutError(phase="worker coordination", timeout_seconds=45)
        message = error.message

        assert "Streaming operation" in message
        assert "timed out" in message
        assert "worker coordination" in message
        assert "45s" in message

    def test_synthesis_timeout_message(self):
        """Verify synthesis timeout message is descriptive."""
        error = StreamingTimeoutError(phase="synthesis", timeout_seconds=30)
        message = error.message

        assert "Streaming operation" in message
        assert "timed out" in message
        assert "synthesis" in message
        assert "30s" in message

    def test_error_message_with_different_phases(self):
        """Test error message with various phase names."""
        phases = ["worker coordination", "synthesis", "test phase"]

        for phase in phases:
            error = StreamingTimeoutError(phase=phase, timeout_seconds=50)
            assert phase in error.message

    def test_error_inherits_base_message_attribute(self):
        """Verify error message is stored in base class attribute."""
        error = StreamingTimeoutError(phase="test", timeout_seconds=45)
        assert hasattr(error, "message")
        assert error.message == str(error)
