#!/usr/bin/env python3
"""
Generate JWT bearer tokens for Template Service API authentication.

This utility generates valid JWT tokens signed with the JWT_SECRET_KEY from
your environment configuration. The generated tokens can be used as Bearer
tokens in the Authorization header when calling API endpoints.

Usage:
    # Generate token with default settings (no expiration)
    python scripts/generate_jwt.py

    # Generate token that expires in 30 days
    python scripts/generate_jwt.py --expires-in 30d

    # Generate token with custom subject
    python scripts/generate_jwt.py --subject "my-client"

    # Generate token with custom secret
    python scripts/generate_jwt.py --secret "your-secret-key"

    # Generate token and save to environment
    export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)

Exit codes:
    0: Success
    1: Configuration error (missing JWT_SECRET_KEY)
    2: Invalid arguments
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import jwt


def parse_expiration(expires_str: str) -> int | None:
    """
    Parse expiration string to seconds from now.

    Args:
        expires_str: Expiration time (e.g., "30d", "24h", "3600s")

    Returns:
        Seconds from now, or None if invalid format

    Raises:
        ValueError: If format is invalid
    """
    if not expires_str:
        return None

    expires_str = expires_str.strip()

    # Try to parse with unit suffix
    if expires_str[-1].isdigit():
        # Pure number, treat as seconds
        try:
            return int(expires_str)
        except ValueError as exc:
            raise ValueError(f"Invalid expiration format: {expires_str}") from exc

    unit = expires_str[-1].lower()
    try:
        value = int(expires_str[:-1])
    except ValueError as exc:
        raise ValueError(f"Invalid expiration format: {expires_str}") from exc

    unit_to_seconds = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }

    if unit not in unit_to_seconds:
        raise ValueError(
            f"Invalid unit '{unit}'. Supported units: s(econds), m(inutes), "
            "h(ours), d(ays), w(eeks)"
        )

    return value * unit_to_seconds[unit]


def generate_token(
    secret_key: str,
    subject: str = "client",
    expires_in_seconds: int | None = None,
    algorithm: str = "HS256",
) -> str:
    """
    Generate a JWT token.

    Args:
        secret_key: JWT secret key for signing
        subject: JWT subject claim (typically client identifier)
        expires_in_seconds: Token expiration time in seconds (None = no expiration)
        algorithm: JWT signing algorithm (default: HS256)

    Returns:
        Encoded JWT token as string
    """
    now = datetime.now(tz=timezone.utc)
    payload: dict = {
        "sub": subject,
        "iat": now,
    }

    # Add expiration if specified
    if expires_in_seconds is not None:
        exp_time = now + timedelta(seconds=expires_in_seconds)
        payload["exp"] = exp_time

    token = jwt.encode(payload, secret_key, algorithm=algorithm)
    return token


def main() -> int:
    """
    Parse arguments and generate JWT token.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        description="Generate JWT bearer tokens for Template Service API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--secret",
        type=str,
        default=None,
        help="JWT secret key (defaults to JWT_SECRET_KEY environment variable)",
    )
    parser.add_argument(
        "--subject",
        type=str,
        default="client",
        help="JWT subject claim (default: client)",
    )
    parser.add_argument(
        "--expires-in",
        type=str,
        default=None,
        help='Token expiration time (e.g., "30d", "24h", "3600s"). '
        "Default: no expiration",
    )
    parser.add_argument(
        "--algorithm",
        type=str,
        default="HS256",
        help="JWT signing algorithm (default: HS256)",
    )

    args = parser.parse_args()

    # Get secret key from argument or environment
    secret_key = args.secret or os.getenv("JWT_SECRET_KEY")
    if not secret_key:
        print(
            "ERROR: JWT_SECRET_KEY not found in environment",
            file=sys.stderr,
        )
        print(
            "\nTo set up JWT_SECRET_KEY:",
            file=sys.stderr,
        )
        print(
            '  1. Generate a secret: python -c "import secrets; '
            'print(secrets.token_urlsafe(32))"',
            file=sys.stderr,
        )
        print("  2. Add to .env file: JWT_SECRET_KEY=<generated_secret>", file=sys.stderr)
        print(
            "\nOr pass directly: python scripts/generate_jwt.py "
            '--secret "your-secret-here"',
            file=sys.stderr,
        )
        return 1

    # Validate secret key length
    if len(secret_key) < 32:
        print(
            f"WARNING: JWT_SECRET_KEY is only {len(secret_key)} characters. "
            "Minimum recommended: 32 characters",
            file=sys.stderr,
        )

    # Parse expiration if provided
    expires_in_seconds: int | None = None
    if args.expires_in:
        try:
            expires_in_seconds = parse_expiration(args.expires_in)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    # Generate token
    try:
        token = generate_token(
            secret_key=secret_key,
            subject=args.subject,
            expires_in_seconds=expires_in_seconds,
            algorithm=args.algorithm,
        )
        print(token)
        return 0

    except Exception as exc:
        print(f"ERROR: Failed to generate token: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
