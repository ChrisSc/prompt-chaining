"""Pytest configuration and fixtures for performance tests."""

import os
import subprocess

import pytest


@pytest.fixture(scope="session")
def api_key():
    """Get ANTHROPIC_API_KEY from environment."""
    return os.getenv("ANTHROPIC_API_KEY")


@pytest.fixture(scope="session")
def jwt_token(api_key):
    """Generate a valid JWT token for testing."""
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    try:
        result = subprocess.run(
            ["python", "scripts/generate_jwt.py"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            pytest.skip("Failed to generate JWT token")
    except Exception as e:
        pytest.skip(f"Could not generate JWT token: {e}")


@pytest.fixture(scope="session")
def server_running():
    """Check if dev server is running."""
    try:
        import requests

        response = requests.get("http://localhost:8000/health/", timeout=2)
        if response.status_code == 200:
            return True
    except Exception:
        pass
    return False


@pytest.fixture
def headers(jwt_token):
    """Create request headers with JWT token."""
    if not jwt_token:
        pytest.skip("JWT token not available")
    return {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def test_messages():
    """Provide test messages for benchmarking."""
    return [
        "What is artificial intelligence and how does it work?",
        "Explain machine learning in simple terms",
        "How do neural networks process information?",
        "What are the benefits and risks of AI?",
        "Describe the future of AI technology",
    ]
