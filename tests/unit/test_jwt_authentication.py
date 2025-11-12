"""
Unit tests for JWT bearer token authentication.

Tests the JWT verification dependency and token generation utilities
to ensure proper OpenAI-compatible authentication.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from workflow.api.dependencies import verify_bearer_token
from workflow.config import Settings


@pytest.fixture
def jwt_settings() -> Settings:
    """Create test settings with JWT configuration."""
    return Settings(
        anthropic_api_key="test-key-123",
        jwt_secret_key="test_secret_key_with_minimum_32_characters_required_for_testing",
        jwt_algorithm="HS256",
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
        "exp": datetime.now(tz=timezone.utc) - timedelta(hours=1),  # Expired 1 hour ago
    }
    return jwt.encode(
        payload,
        jwt_settings.jwt_secret_key,
        algorithm=jwt_settings.jwt_algorithm,
    )


@pytest.fixture
def invalid_signature_token() -> str:
    """Generate a token with invalid signature."""
    payload = {
        "sub": "test-client",
        "iat": datetime.now(tz=timezone.utc),
    }
    # Sign with wrong secret
    return jwt.encode(payload, "wrong_secret_key", algorithm="HS256")


class TestJWTVerification:
    """Test JWT token verification."""

    async def test_verify_valid_token(self, valid_token: str, jwt_settings: Settings) -> None:
        """Test verification of a valid token."""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=valid_token)

        with patch("workflow.api.dependencies.Settings", return_value=jwt_settings):
            payload = await verify_bearer_token(credentials, jwt_settings)

        assert payload["sub"] == "test-client"
        assert "iat" in payload

    async def test_verify_expired_token(self, expired_token: str, jwt_settings: Settings) -> None:
        """Test that expired tokens are rejected."""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired_token)

        with patch("workflow.api.dependencies.Settings", return_value=jwt_settings):
            with pytest.raises(HTTPException) as exc_info:
                await verify_bearer_token(credentials, jwt_settings)

        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    async def test_verify_invalid_signature(
        self, invalid_signature_token: str, jwt_settings: Settings
    ) -> None:
        """Test that tokens with invalid signatures are rejected."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=invalid_signature_token
        )

        with patch("workflow.api.dependencies.Settings", return_value=jwt_settings):
            with pytest.raises(HTTPException) as exc_info:
                await verify_bearer_token(credentials, jwt_settings)

        assert exc_info.value.status_code == 403
        assert "invalid" in exc_info.value.detail.lower()

    async def test_verify_malformed_token(self, jwt_settings: Settings) -> None:
        """Test that malformed tokens are rejected."""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not.a.valid.jwt")

        with patch("workflow.api.dependencies.Settings", return_value=jwt_settings):
            with pytest.raises(HTTPException) as exc_info:
                await verify_bearer_token(credentials, jwt_settings)

        assert exc_info.value.status_code == 403
        assert "invalid" in exc_info.value.detail.lower()

    async def test_verify_token_without_subject(self, jwt_settings: Settings) -> None:
        """Test that tokens are valid even without subject claim."""
        payload = {
            "iat": datetime.now(tz=timezone.utc),
        }
        token = jwt.encode(
            payload,
            jwt_settings.jwt_secret_key,
            algorithm=jwt_settings.jwt_algorithm,
        )

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch("workflow.api.dependencies.Settings", return_value=jwt_settings):
            result = await verify_bearer_token(credentials, jwt_settings)

        assert result is not None
        assert "iat" in result

    async def test_verify_token_with_custom_claims(self, jwt_settings: Settings) -> None:
        """Test that tokens with custom claims are properly decoded."""
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

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch("workflow.api.dependencies.Settings", return_value=jwt_settings):
            result = await verify_bearer_token(credentials, jwt_settings)

        assert result["sub"] == "premium-client"
        assert result["organization_id"] == "org-123"
        assert result["plan"] == "enterprise"


class TestJWTTokenGeneration:
    """Test JWT token generation utility."""

    def test_generate_basic_token(self, jwt_settings: Settings) -> None:
        """Test generating a basic token."""
        from scripts.generate_jwt import generate_token

        token = generate_token(
            secret_key=jwt_settings.jwt_secret_key,
            subject="test-client",
        )

        # Verify the token
        payload = jwt.decode(
            token,
            jwt_settings.jwt_secret_key,
            algorithms=[jwt_settings.jwt_algorithm],
        )

        assert payload["sub"] == "test-client"
        assert "iat" in payload
        assert "exp" not in payload  # No expiration

    def test_generate_token_with_expiration(self, jwt_settings: Settings) -> None:
        """Test generating a token with expiration."""
        from scripts.generate_jwt import generate_token

        # 24 hours in seconds
        expires_in = 86400
        token = generate_token(
            secret_key=jwt_settings.jwt_secret_key,
            subject="test-client",
            expires_in_seconds=expires_in,
        )

        # Verify the token
        payload = jwt.decode(
            token,
            jwt_settings.jwt_secret_key,
            algorithms=[jwt_settings.jwt_algorithm],
        )

        assert payload["sub"] == "test-client"
        assert "exp" in payload
        # Token should be valid (exp time is in future)
        assert payload["exp"] > datetime.now(tz=timezone.utc).timestamp()

    def test_generate_token_with_different_algorithm(self, jwt_settings: Settings) -> None:
        """Test generating a token with different algorithm."""
        from scripts.generate_jwt import generate_token

        token = generate_token(
            secret_key=jwt_settings.jwt_secret_key,
            subject="test-client",
            algorithm="HS256",
        )

        # Verify the token with HS256
        payload = jwt.decode(
            token,
            jwt_settings.jwt_secret_key,
            algorithms=["HS256"],
        )

        assert payload["sub"] == "test-client"


class TestExpirationParsing:
    """Test expiration string parsing utility."""

    def test_parse_seconds(self) -> None:
        """Test parsing expiration in seconds."""
        from scripts.generate_jwt import parse_expiration

        assert parse_expiration("3600") == 3600
        assert parse_expiration("86400") == 86400

    def test_parse_seconds_with_suffix(self) -> None:
        """Test parsing expiration with 's' suffix."""
        from scripts.generate_jwt import parse_expiration

        assert parse_expiration("3600s") == 3600
        assert parse_expiration("60s") == 60

    def test_parse_minutes(self) -> None:
        """Test parsing expiration in minutes."""
        from scripts.generate_jwt import parse_expiration

        assert parse_expiration("60m") == 3600  # 60 minutes = 3600 seconds
        assert parse_expiration("30m") == 1800

    def test_parse_hours(self) -> None:
        """Test parsing expiration in hours."""
        from scripts.generate_jwt import parse_expiration

        assert parse_expiration("24h") == 86400  # 24 hours = 86400 seconds
        assert parse_expiration("1h") == 3600

    def test_parse_days(self) -> None:
        """Test parsing expiration in days."""
        from scripts.generate_jwt import parse_expiration

        assert parse_expiration("30d") == 2592000  # 30 days
        assert parse_expiration("1d") == 86400

    def test_parse_weeks(self) -> None:
        """Test parsing expiration in weeks."""
        from scripts.generate_jwt import parse_expiration

        assert parse_expiration("1w") == 604800  # 1 week
        assert parse_expiration("4w") == 2419200  # 4 weeks

    def test_parse_invalid_format(self) -> None:
        """Test parsing invalid expiration format."""
        from scripts.generate_jwt import parse_expiration

        with pytest.raises(ValueError):
            parse_expiration("invalid")

        with pytest.raises(ValueError):
            parse_expiration("10x")

        with pytest.raises(ValueError):
            parse_expiration("abcd")


class TestOpenAICompatibility:
    """Test OpenAI API compatibility of JWT authentication."""

    def test_bearer_token_format(self, valid_token: str) -> None:
        """Test that tokens follow OpenAI Bearer token format."""
        # Bearer token should be a valid JWT
        assert "." in valid_token  # JWT has 3 parts separated by dots
        parts = valid_token.split(".")
        assert len(parts) == 3  # header.payload.signature

    def test_authorization_header_format(self, valid_token: str) -> None:
        """Test Authorization header follows OpenAI format."""
        auth_header = f"Bearer {valid_token}"

        # Parse the header
        scheme, credentials = auth_header.split(" ", 1)
        assert scheme == "Bearer"
        assert credentials == valid_token
        assert "." in credentials  # JWT format

    async def test_401_on_missing_token(self) -> None:
        """Test 401 response for missing token (OpenAI compatible)."""
        from fastapi.security import HTTPBearer

        security = HTTPBearer()

        # Mock a request without Bearer token
        from unittest.mock import MagicMock

        request = MagicMock()
        request.headers = {}

        with pytest.raises(Exception):
            # HTTPBearer will raise an exception when no credentials found
            await security(request)

    async def test_403_on_invalid_token(self, jwt_settings: Settings) -> None:
        """Test 403 response for invalid token (OpenAI compatible)."""
        invalid_token = "invalid.token.here"
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=invalid_token)

        with patch("workflow.api.dependencies.Settings", return_value=jwt_settings):
            with pytest.raises(HTTPException) as exc_info:
                await verify_bearer_token(credentials, jwt_settings)

        # OpenAI returns 403 for invalid credentials
        assert exc_info.value.status_code == 403

    async def test_403_on_unexpected_error(self, jwt_settings: Settings) -> None:
        """Test 403 response for unexpected errors during verification."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid.format.token"
        )

        # Mock jwt.decode to raise an unexpected exception
        with patch("workflow.api.dependencies.jwt.decode") as mock_decode:
            mock_decode.side_effect = RuntimeError("Unexpected error")

            with pytest.raises(HTTPException) as exc_info:
                await verify_bearer_token(credentials, jwt_settings)

        # Should return 403 for any verification failure
        assert exc_info.value.status_code == 403
        assert "verification failed" in exc_info.value.detail.lower()


class TestJWTSecurityBestPractices:
    """Test JWT security best practices are followed."""

    def test_secret_key_minimum_length(self) -> None:
        """Test that secret key has minimum length."""
        # This should enforce minimum 32 characters in Settings
        with pytest.raises(Exception):
            Settings(
                anthropic_api_key="test",
                jwt_secret_key="short",  # Less than 32 characters
            )

    def test_hs256_algorithm_default(self) -> None:
        """Test that HS256 is the default algorithm."""
        settings = Settings(
            anthropic_api_key="test",
            jwt_secret_key="test_secret_key_with_minimum_32_characters_for_testing",
        )
        assert settings.jwt_algorithm == "HS256"

    def test_token_does_not_expose_secret(self, jwt_settings: Settings) -> None:
        """Test that JWT token does not expose the secret key."""
        from scripts.generate_jwt import generate_token

        token = generate_token(
            secret_key=jwt_settings.jwt_secret_key,
            subject="test",
        )

        # The secret should not appear in the token
        assert jwt_settings.jwt_secret_key not in token

        # Decode to verify it contains what we expect
        payload = jwt.decode(
            token,
            jwt_settings.jwt_secret_key,
            algorithms=["HS256"],
        )
        assert payload["sub"] == "test"
