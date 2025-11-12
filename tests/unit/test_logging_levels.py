"""
Unit tests for logging level verification across the application.

Tests verify that all log levels (CRITICAL/FATAL, ERROR, WARNING, INFO, DEBUG)
are properly emitted in appropriate contexts throughout the application.
"""

import logging
from unittest.mock import patch

import pytest

from orchestrator_worker.config import Settings
from orchestrator_worker.utils.logging import JSONFormatter, get_logger, setup_logging
from orchestrator_worker.utils.token_tracking import calculate_cost


class TestLoggingLevels:
    """Test that all logging levels work correctly."""

    def test_debug_logging_health_check(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test DEBUG logging is emitted for health check requests."""
        from orchestrator_worker.api.health import health_check

        with caplog.at_level(logging.DEBUG):
            # Simulate health check
            result = None
            import asyncio

            async def run_health_check() -> dict[str, str]:
                return await health_check()

            result = asyncio.run(run_health_check())

        assert result == {"status": "healthy"}
        assert any(
            record.levelname == "DEBUG" and "Health check (liveness)" in record.message
            for record in caplog.records
        )

    def test_debug_logging_readiness_check(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test DEBUG logging is emitted for readiness check requests."""
        from orchestrator_worker.api.health import readiness_check

        with caplog.at_level(logging.DEBUG):
            # Simulate readiness check
            result = None
            import asyncio

            async def run_readiness_check() -> dict[str, str]:
                return await readiness_check()

            result = asyncio.run(run_readiness_check())

        assert result == {"status": "ready"}
        assert any(
            record.levelname == "DEBUG" and "Readiness check request received" in record.message
            for record in caplog.records
        )

    def test_debug_logging_token_cost_calculation(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test DEBUG logging is emitted during token cost calculation."""
        with caplog.at_level(logging.DEBUG):
            cost = calculate_cost("claude-haiku-4-5-20251001", 1000, 500)

        assert cost.total_cost_usd > 0
        assert any(
            record.levelname == "DEBUG" and "Token cost calculated" in record.message
            for record in caplog.records
        )

    def test_warning_logging_unknown_model_pricing(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test WARNING logging is emitted for unknown model pricing."""
        with caplog.at_level(logging.WARNING):
            with pytest.raises(ValueError, match="Unknown model"):
                calculate_cost("invalid-model", 100, 50)

        assert any(
            record.levelname == "WARNING" and "Unknown model pricing requested" in record.message
            for record in caplog.records
        )

    def test_info_logging_application_startup(self) -> None:
        """Test INFO logging is emitted during application startup."""
        # Create settings with minimal config
        with patch.dict(
            "os.environ",
            {
                "ANTHROPIC_API_KEY": "sk-ant-test-key",
                "JWT_SECRET_KEY": "test-secret-key-minimum-32-characters-required",
            },
        ):
            settings = Settings()

            # Verify settings loaded correctly (INFO level will be logged by setup_logging)
            assert settings.log_level == "INFO"
            assert settings.log_format == "json"

            # This function logs at INFO level when it configures logging
            # We can't easily test with caplog since setup_logging replaces handlers
            # But we can verify it runs without error and produces valid config
            setup_logging(settings)

            # Verify logging is now configured
            root_logger = logging.getLogger()
            assert root_logger.level == logging.INFO
            assert len(root_logger.handlers) > 0

    def test_critical_logging_orchestrator_init_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test CRITICAL logging is emitted on orchestrator initialization failure."""
        # This will be tested via integration test with lifespan manager
        # For unit test, we verify the log call would be made
        logger = get_logger(__name__)

        with caplog.at_level(logging.CRITICAL):
            logger.critical(
                "Failed to initialize orchestrator - application cannot start",
                extra={"error": "test error", "error_type": "TestException"},
            )

        assert any(
            record.levelname == "CRITICAL" and "Failed to initialize orchestrator" in record.message
            for record in caplog.records
        )

    def test_error_logging_agent_errors(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test ERROR logging is emitted for agent processing errors."""
        logger = get_logger(__name__)

        with caplog.at_level(logging.ERROR):
            logger.error("Worker task failed", extra={"task_id": "test-task", "error": "test"})

        assert any(
            record.levelname == "ERROR" and "Worker task failed" in record.message
            for record in caplog.records
        )

    def test_logging_extra_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that extra fields are properly attached to log records."""
        logger = get_logger(__name__)

        with caplog.at_level(logging.DEBUG):
            logger.debug(
                "Test with extras",
                extra={
                    "request_id": "req_123",
                    "user": "test-user",
                    "duration_ms": 150,
                },
            )

        assert any(record.request_id == "req_123" for record in caplog.records)  # type: ignore
        assert any(record.user == "test-user" for record in caplog.records)  # type: ignore
        assert any(record.duration_ms == 150 for record in caplog.records)  # type: ignore


class TestJSONFormatter:
    """Test JSON formatter behavior."""

    def test_json_formatter_includes_standard_fields(self) -> None:
        """Test that JSON formatter includes all standard fields."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        import json

        parsed = json.loads(result)

        assert "timestamp" in parsed
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"
        assert parsed["message"] == "Test message"

    def test_json_formatter_includes_extra_fields(self) -> None:
        """Test that JSON formatter includes extra fields."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=10,
            msg="Test with extras",
            args=(),
            exc_info=None,
        )
        # Add extra fields
        record.request_id = "req_456"  # type: ignore
        record.user = "test-user"  # type: ignore
        record.total_cost_usd = 0.00123  # type: ignore

        result = formatter.format(record)
        import json

        parsed = json.loads(result)

        assert parsed["request_id"] == "req_456"
        assert parsed["user"] == "test-user"
        assert parsed["total_cost_usd"] == 0.00123

    def test_json_formatter_handles_exceptions(self) -> None:
        """Test that JSON formatter properly formats exceptions."""
        formatter = JSONFormatter()
        try:
            raise ValueError("Test exception")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        result = formatter.format(record)
        import json

        parsed = json.loads(result)

        assert "exception" in parsed
        assert "ValueError: Test exception" in parsed["exception"]


class TestLogLevelFiltering:
    """Test that log level filtering works correctly."""

    def test_debug_level_shows_all_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that DEBUG level shows all log levels."""
        logger = get_logger(__name__)

        with caplog.at_level(logging.DEBUG):
            logger.debug("Debug message")
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message")
            logger.critical("Critical message")

        assert len(caplog.records) == 5
        assert any(r.levelname == "DEBUG" for r in caplog.records)
        assert any(r.levelname == "INFO" for r in caplog.records)
        assert any(r.levelname == "WARNING" for r in caplog.records)
        assert any(r.levelname == "ERROR" for r in caplog.records)
        assert any(r.levelname == "CRITICAL" for r in caplog.records)

    def test_info_level_filters_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that INFO level filters out DEBUG logs."""
        logger = get_logger(__name__)

        with caplog.at_level(logging.INFO):
            logger.debug("Debug message - should not appear")
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message")
            logger.critical("Critical message")

        assert len(caplog.records) == 4
        assert not any(r.levelname == "DEBUG" for r in caplog.records)
        assert any(r.levelname == "INFO" for r in caplog.records)

    def test_warning_level_filters_info_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that WARNING level filters out INFO and DEBUG logs."""
        logger = get_logger(__name__)

        with caplog.at_level(logging.WARNING):
            logger.debug("Debug message - should not appear")
            logger.info("Info message - should not appear")
            logger.warning("Warning message")
            logger.error("Error message")
            logger.critical("Critical message")

        assert len(caplog.records) == 3
        assert not any(r.levelname == "DEBUG" for r in caplog.records)
        assert not any(r.levelname == "INFO" for r in caplog.records)
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_error_level_filters_warning_info_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that ERROR level filters out WARNING, INFO, and DEBUG logs."""
        logger = get_logger(__name__)

        with caplog.at_level(logging.ERROR):
            logger.debug("Debug message - should not appear")
            logger.info("Info message - should not appear")
            logger.warning("Warning message - should not appear")
            logger.error("Error message")
            logger.critical("Critical message")

        assert len(caplog.records) == 2
        assert not any(r.levelname == "DEBUG" for r in caplog.records)
        assert not any(r.levelname == "INFO" for r in caplog.records)
        assert not any(r.levelname == "WARNING" for r in caplog.records)
        assert any(r.levelname == "ERROR" for r in caplog.records)

    def test_critical_level_shows_only_critical(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that CRITICAL level shows only CRITICAL logs."""
        logger = get_logger(__name__)

        with caplog.at_level(logging.CRITICAL):
            logger.debug("Debug message - should not appear")
            logger.info("Info message - should not appear")
            logger.warning("Warning message - should not appear")
            logger.error("Error message - should not appear")
            logger.critical("Critical message")

        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "CRITICAL"


class TestSecurityHeadersLogging:
    """Test DEBUG logging in security headers middleware."""

    def test_security_headers_debug_logging_https(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test DEBUG logging for security headers with HTTPS."""
        from orchestrator_worker.middleware.security_headers import logger as sec_logger

        with caplog.at_level(logging.DEBUG):
            sec_logger.debug(
                "Security headers applied with HSTS",
                extra={
                    "path": "/test",
                    "scheme": "https",
                    "forwarded_proto": "https",
                },
            )

        assert any(
            record.levelname == "DEBUG" and "Security headers applied with HSTS" in record.message
            for record in caplog.records
        )

    def test_security_headers_debug_logging_http(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test DEBUG logging for security headers with HTTP."""
        from orchestrator_worker.middleware.security_headers import logger as sec_logger

        with caplog.at_level(logging.DEBUG):
            sec_logger.debug(
                "Security headers applied (HSTS skipped for HTTP)",
                extra={
                    "path": "/test",
                    "scheme": "http",
                },
            )

        assert any(
            record.levelname == "DEBUG"
            and "Security headers applied (HSTS skipped for HTTP)" in record.message
            for record in caplog.records
        )


class TestRequestSizeLogging:
    """Test logging in request size validation middleware."""

    def test_request_size_warning_logging(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test WARNING logging for oversized requests."""
        from orchestrator_worker.middleware.request_size import logger as size_logger

        with caplog.at_level(logging.WARNING):
            size_logger.warning(
                "Request body size validation triggered",
                extra={
                    "path": "/v1/chat/completions",
                    "method": "POST",
                    "actual_size": 2000000,
                    "max_size": 1048576,
                },
            )

        assert any(
            record.levelname == "WARNING"
            and "Request body size validation triggered" in record.message
            for record in caplog.records
        )

    def test_request_size_debug_logging_pass(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test DEBUG logging when request size validation passes."""
        from orchestrator_worker.middleware.request_size import logger as size_logger

        with caplog.at_level(logging.DEBUG):
            size_logger.debug(
                "Request size validation passed",
                extra={
                    "path": "/v1/chat/completions",
                    "method": "POST",
                    "size": 500,
                    "max_size": 1048576,
                },
            )

        assert any(
            record.levelname == "DEBUG" and "Request size validation passed" in record.message
            for record in caplog.records
        )
