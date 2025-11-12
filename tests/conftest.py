"""Pytest configuration and shared fixtures."""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment() -> None:
    """Set up test environment variables."""
    # Set minimal required environment variables for tests
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-api-key-for-testing")
    os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_with_minimum_32_characters")
    os.environ.setdefault("LOG_LEVEL", "INFO")
