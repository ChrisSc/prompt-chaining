# JWT Authentication

This document describes the JWT (JSON Web Token) authentication system for the Prompt Chaining API.

## Overview

The API uses JWT bearer tokens for authentication on all protected endpoints. Clients must include a valid JWT token in the `Authorization` header to access the service.

```bash
Authorization: Bearer <jwt_token>
```

## Quick Start

### Generate a Token

Use the included token generation script:

```bash
# Generate token (no expiration)
export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)

# Generate token that expires in 7 days
export API_BEARER_TOKEN=$(python scripts/generate_jwt.py --expires-in 7d)

# Generate token with custom subject
export API_BEARER_TOKEN=$(python scripts/generate_jwt.py --subject "my-service")
```

### Use Token in Requests

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "prompt-chaining",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## Configuration

JWT authentication is configured via environment variables in `.env`:

### Required

**`JWT_SECRET_KEY`** (required)
- Secret key for signing and verifying tokens
- Minimum 32 characters (recommended: 32-64 characters)
- Must be kept secure and never committed to version control
- Generate a secure key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Optional

**`JWT_ALGORITHM`** (default: `HS256`)
- Algorithm for token signing
- Supported: `HS256` (HMAC with SHA-256)
- Only change if you have specific cryptographic requirements

## Token Generation

### Using `generate_jwt.py`

The `scripts/generate_jwt.py` script generates JWT tokens for testing and deployment.

#### Arguments

- `--secret TEXT` - JWT secret key (defaults to `JWT_SECRET_KEY` environment variable)
- `--subject TEXT` - JWT subject claim (default: `client`)
- `--expires-in TEXT` - Token expiration time (format: `30d`, `24h`, `3600s`; default: no expiration)
- `--algorithm TEXT` - JWT signing algorithm (default: `HS256`)

#### Expiration Format

Supported time units:
- `s` - seconds (e.g., `3600s`)
- `m` - minutes (e.g., `30m`)
- `h` - hours (e.g., `24h`)
- `d` - days (e.g., `7d`)
- `w` - weeks (e.g., `4w`)

#### Examples

```bash
# No expiration
python scripts/generate_jwt.py

# 7-day expiration
python scripts/generate_jwt.py --expires-in 7d

# 1-hour expiration
python scripts/generate_jwt.py --expires-in 1h

# Custom subject
python scripts/generate_jwt.py --subject "analytics-service"

# Custom subject with expiration
python scripts/generate_jwt.py --subject "my-client" --expires-in 30d

# Custom secret (for testing)
python scripts/generate_jwt.py --secret "my-test-secret-key-32-characters!"
```

#### Exit Codes

- `0` - Success (token printed to stdout)
- `1` - Configuration error (JWT_SECRET_KEY missing or invalid)
- `2` - Invalid arguments

## Token Structure

JWT tokens consist of three parts separated by dots: `header.payload.signature`

### Header

```json
{
  "alg": "HS256",
  "typ": "JWT"
}
```

### Payload

```json
{
  "sub": "client",
  "iat": 1234567890,
  "exp": 1234654290
}
```

**Standard Claims:**

| Claim | Description |
|-------|-------------|
| `sub` | Subject (typically client identifier) |
| `iat` | Issued at timestamp (seconds since epoch) |
| `exp` | Expiration timestamp (optional, seconds since epoch) |

### Signature

HMAC-SHA256 hash of header and payload, signed with `JWT_SECRET_KEY`.

## API Endpoints

### Protected Endpoints

All endpoints under `/v1/*` require JWT authentication:

- `POST /v1/chat/completions` - Stream chat completions (requires bearer token)
- `GET /v1/models` - List available models (requires bearer token)

### Public Endpoints

These endpoints do not require authentication:

- `GET /health/` - Liveness check
- `GET /health/ready` - Readiness check

## Error Responses

### 401 Unauthorized

**Missing Token**

```json
{
  "detail": "Not authenticated"
}
```

**Expired Token**

```json
{
  "detail": "Token has expired"
}
```

**Invalid Format**

```json
{
  "detail": "Invalid authentication credentials"
}
```

### 403 Forbidden

**Invalid Signature**

```json
{
  "detail": "Invalid authentication credentials"
}
```

**Malformed Token**

```json
{
  "detail": "Invalid authentication credentials"
}
```

### 500 Internal Server Error

**Misconfigured JWT_SECRET_KEY**

```json
{
  "detail": "Authentication system misconfigured"
}
```

This error occurs when:
- `JWT_SECRET_KEY` is not set
- `JWT_SECRET_KEY` is less than 32 characters

## Implementation Details

### Token Verification

The `verify_bearer_token()` dependency in `src/workflow/api/dependencies.py` handles token verification:

1. Extracts Bearer token from `Authorization` header
2. Validates `JWT_SECRET_KEY` is properly configured
3. Decodes JWT signature using the secret key
4. Returns decoded token payload

### Token Payload Extraction

Access token claims in endpoint handlers:

```python
from fastapi import Depends
from workflow.api.dependencies import verify_bearer_token

@router.post("/v1/chat/completions")
async def create_chat_completion(
    token: dict = Depends(verify_bearer_token),
):
    # Access token claims
    user_subject = token.get("sub", "unknown")
    issued_at = token.get("iat")
    expires_at = token.get("exp")

    # Use in logging or request validation
    logger.info(f"Request from {user_subject}")
```

## Security Best Practices

### Development

1. Generate a strong `JWT_SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

2. Store in `.env` (which is gitignored):
```bash
echo 'JWT_SECRET_KEY=<generated_key>' >> .env
```

3. Never commit `.env` to version control

### Production

1. **Use environment variables** - Set `JWT_SECRET_KEY` via infrastructure (AWS Secrets Manager, HashiCorp Vault, etc.)

2. **Rotate keys regularly** - Plan for periodic key rotation:
   - Generate new key
   - Update environment
   - Invalidate old tokens if needed

3. **Use HTTPS** - Always transmit tokens over encrypted connections

4. **Implement token expiration**:
   ```bash
   python scripts/generate_jwt.py --expires-in 7d  # 7-day expiration
   ```

5. **Monitor token usage**:
   - Log all authentication attempts (both success and failure)
   - Alert on repeated failed authentication attempts
   - Track token issuance and expiration

6. **Token storage**:
   - Store tokens securely on client side (don't expose in logs)
   - Use secure HTTP-only cookies if possible
   - Never store tokens in localStorage or browser cookies visible to JavaScript

### Checking Token Validity

Decode and inspect a token (for debugging only):

```bash
# Decode token (without verification)
python -c "
import jwt
import json
token = 'your.jwt.token'
decoded = jwt.decode(token, options={'verify_signature': False})
print(json.dumps(decoded, indent=2, default=str))
"
```

## Troubleshooting

### "JWT_SECRET_KEY not found" Error

**Problem:** `generate_jwt.py` script fails with `JWT_SECRET_KEY not found`

**Solution:**
```bash
# Generate a secret
SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# Add to .env
echo "JWT_SECRET_KEY=$SECRET" >> .env

# Source environment
source .env

# Verify
echo $JWT_SECRET_KEY
```

### "Token has expired" Error

**Problem:** API returns 401 "Token has expired"

**Solution:** Generate a new token with longer expiration:
```bash
python scripts/generate_jwt.py --expires-in 30d
```

### "Invalid authentication credentials" Error

**Problem:** API returns 403 with valid-looking token

**Possible causes:**
- Token was signed with different `JWT_SECRET_KEY`
- Token signature is corrupted
- Token has been tampered with

**Solution:**
1. Verify `JWT_SECRET_KEY` matches the one used to generate token
2. Generate a fresh token:
```bash
export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)
```
3. Check server logs for details

### Rate Limiting & 429 Errors

**Problem:** API returns 429 Too Many Requests

**Solution:**
- Implement retry logic with exponential backoff
- Contact administrator to adjust rate limits if needed
- See `CLAUDE.md` configuration section for rate limit settings

## Testing

### Using curl

```bash
# Generate token
TOKEN=$(python scripts/generate_jwt.py)

# Make authenticated request
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "prompt-chaining",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 100
  }'
```

### Using Python

```python
import requests
import subprocess

# Generate token
token_result = subprocess.run(
    ["python", "scripts/generate_jwt.py"],
    capture_output=True,
    text=True,
    check=True
)
token = token_result.stdout.strip()

# Make request
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    headers=headers,
    json={
        "model": "prompt-chaining",
        "messages": [{"role": "user", "content": "Hello"}]
    }
)

print(response.status_code)
print(response.json())
```

### Using httpx (Async)

```python
import httpx
import subprocess

# Generate token
token_result = subprocess.run(
    ["python", "scripts/generate_jwt.py"],
    capture_output=True,
    text=True,
    check=True
)
token = token_result.stdout.strip()

async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model": "prompt-chaining",
            "messages": [{"role": "user", "content": "Hello"}]
        }
    )
    print(response.status_code)
```

## Advanced Configuration

### Changing JWT Algorithm

By default, the API uses `HS256` (HMAC with SHA-256). To use a different algorithm:

1. Update `.env`:
```bash
JWT_ALGORITHM=HS512
```

2. Generate token with matching algorithm:
```bash
python scripts/generate_jwt.py --algorithm HS512
```

**Note:** Only change algorithms if you have specific security requirements. `HS256` is recommended for most use cases.

### Programmatic Token Generation

Use the `generate_token()` function from `scripts/generate_jwt.py`:

```python
from scripts.generate_jwt import generate_token
from datetime import timedelta

# Generate token with 7-day expiration
token = generate_token(
    secret_key="your-secret-key",
    subject="my-client",
    expires_in_seconds=int(timedelta(days=7).total_seconds()),
    algorithm="HS256"
)

print(token)  # Print JWT token
```

## Related Documentation

- **CLAUDE.md** - Configuration reference and quick setup
- **ARCHITECTURE.md** - System architecture and request flow
- **README.md** - Project overview and deployment instructions

## Support

For issues or questions about JWT authentication:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review server logs for authentication errors
3. Verify `JWT_SECRET_KEY` is properly configured
4. Generate a fresh token and retry the request
