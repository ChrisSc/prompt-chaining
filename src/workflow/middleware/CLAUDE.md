# Middleware Layer: Request Interception, Context Management, Request ID Propagation

**Location**: `src/workflow/middleware/`

**Purpose**: Request-level interception patterns, context variable initialization, request tracking, size validation, and security headers management.

## Navigation

- **Parent**: See `../../CLAUDE.md` for project overview
- **Related Files**:
  - `../api/CLAUDE.md` - API endpoints and authentication integration
  - `../utils/CLAUDE.md` - Logging standards and context variable utilities
  - `../chains/CLAUDE.md` - Workflow execution that uses propagated context

---

## Request ID Propagation Architecture

Request IDs enable end-to-end tracing of requests through the entire system. The middleware layer is responsible for generating or extracting request IDs at the request boundary and propagating them through contextvars.

**Request ID Lifecycle**

1. **Generation/Extraction** (middleware boundary)
   - Check for `X-Request-ID` header in incoming request
   - If present: Use header value (client-provided trace ID)
   - If absent: Generate new ID via `generate_request_id()` (timestamp-based)

2. **Context Storage** (contextvars)
   - Store request ID in Python contextvars via `set_request_id()`
   - Async-safe: Each concurrent request gets isolated context

3. **Automatic Injection** (JSONFormatter)
   - All logs automatically receive `request_id` field from contextvars
   - No manual logging required—JSONFormatter handles injection

4. **External Propagation** (API calls)
   - Request ID forwarded to Anthropic API via `extra_headers` parameter
   - Enables correlation of Claude logs with application logs

**Code Reference**: `src/workflow/middleware.py` contains the request ID middleware implementation.

## Middleware Stack Order

FastAPI executes middleware in LIFO order (last registered, first executed on request). Stack is:

```
1. RequestIDMiddleware       - Generate/extract request ID, store in contextvars
2. RequestSizeMiddleware     - Validate request body size
3. RateLimitMiddleware       - SlowAPI rate limit enforcement (from api/limiter.py)
4. AuthenticationMiddleware  - Bearer token verification (from api/dependencies.py)
5. [Endpoint Handler]        - Route to handler (chat/completions, models, health)
```

On response: Executed in reverse order (AuthenticationMiddleware → RateLimitMiddleware → RequestSizeMiddleware → RequestIDMiddleware).

## Request ID Middleware Pattern

**Responsibility**: Generate or extract request ID and store in contextvars.

**Reference**: `src/workflow/middleware.py:RequestIDMiddleware`

**Pattern**:

```python
from starlette.middleware.base import BaseHTTPMiddleware
from workflow.utils.request_context import set_request_id, generate_request_id

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Extract from header or generate new
        request_id = request.headers.get("X-Request-ID") or generate_request_id()

        # Store in contextvars for downstream access
        set_request_id(request_id)

        # Add to response headers for client tracking
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response
```

**Timing**: Runs before any endpoint handler. Ensures request_id is available to all downstream code (authentication, logging, workflow steps).

**Contextvars Integration**: `set_request_id()` stores the ID in Python's contextvars, making it accessible to:
- All logs via JSONFormatter (automatic injection)
- Workflow steps that call `get_request_id()`
- External API calls via `extra_headers` parameter

## Request Size Validation Middleware

**Responsibility**: Validate request body size and reject oversized requests.

**Reference**: `src/workflow/middleware.py:RequestSizeMiddleware`

**Pattern**:

```python
class RequestSizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Check Content-Length header
        content_length = request.headers.get("content-length")

        if content_length and int(content_length) > self.max_size:
            logger.warning(
                "Request body exceeds size limit",
                extra={
                    "content_length": int(content_length),
                    "max_size": self.max_size,
                    "endpoint": request.url.path,
                },
            )
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )

        return await call_next(request)
```

**Configuration** (from `.env.example`):

```bash
MAX_REQUEST_BODY_SIZE=1048576  # 1MB (supports 1-10MB range)
```

**Behavior**:
- Checks `Content-Length` header before reading body
- Logs WARNING if body exceeds limit
- Returns HTTP 413 Payload Too Large
- Prevents large requests from consuming memory

**Note**: This is a fast check at the boundary. Full body parsing happens in endpoint handler, which has its own size checks via FastAPI's request.body() limits.

## User Context Propagation

**Responsibility**: Extract user ID from JWT claims and store in contextvars.

**Location**: `src/workflow/api/dependencies.py:verify_bearer_token()`

**Pattern**:

```python
from workflow.utils.user_context import set_user_context

def verify_bearer_token(credentials: HTTPAuthorizationCredentials):
    # Verify JWT (with error handling)
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=["HS256"],
        )
    except ExpiredSignatureError:
        logger.warning("JWT token verification failed: token expired")
        raise HTTPException(status_code=401)
    except InvalidTokenError:
        logger.warning("JWT token verification failed: invalid token")
        raise HTTPException(status_code=403)

    # Extract sub claim and store in contextvars
    user_id = payload.get("sub")
    set_user_context(user_id)

    return payload
```

**Timing**: Runs during dependency injection (after RequestIDMiddleware but before endpoint handler). User context available to all downstream code via `get_user_context()`.

**Trace Correlation**: Both request_id (from RequestIDMiddleware) and user_id (from authentication) are automatically injected into all logs, enabling complete request tracing.

## Security Headers Management

**Responsibility**: Add security-related headers to all responses.

**Pattern**: Security headers can be managed at middleware level or via FastAPI app configuration:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Typical secure headers
app = FastAPI()

# CORS configuration (restrict to trusted origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://example.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Or implement custom middleware:
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
```

**Note**: In the current template, security headers are optional. For production deployments, ensure appropriate CORS, CSP (Content-Security-Policy), and HSTS (Strict-Transport-Security) headers are configured.

## Context Variable Architecture

The middleware layer initializes context variables that are auto-injected into logs and accessible throughout the request lifecycle.

**Request Context (request_context.py)**

```python
from contextvars import ContextVar

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)

def get_request_id() -> str | None:
    return _request_id_var.get()

def generate_request_id() -> str:
    """Generate timestamp-based request ID."""
    return f"req_{int(time.time() * 1000)}"
```

**User Context (user_context.py)**

```python
from contextvars import ContextVar

_user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)

def set_user_context(user_id: str) -> None:
    _user_id_var.set(user_id)

def get_user_context() -> str | None:
    return _user_id_var.get()
```

**Key Properties**:
- **Async-Safe**: Each concurrent request/task gets isolated context—no cross-request leakage
- **Automatic Cleanup**: Context automatically cleared when request/task completes
- **No Manual Management**: No need to pass context through function calls
- **JSONFormatter Integration**: Both fields automatically injected into all logs

**Flow**:
1. RequestIDMiddleware calls `set_request_id()` → stored in contextvars
2. Authentication verifies JWT and calls `set_user_context()` → stored in contextvars
3. JSONFormatter reads both via `get_request_id()` and `get_user_context()` → auto-added to logs
4. Workflow steps call Anthropic API with `extra_headers={"X-Request-ID": get_request_id()}` → propagated to Claude
5. Request completes → context automatically cleared for next request

## Error Handling in Middleware

Middleware catches exceptions and logs appropriately:

**Request Size Errors**

```python
try:
    content_length = int(request.headers.get("content-length", 0))
except ValueError:
    logger.warning(
        "Invalid Content-Length header",
        extra={"content_length_header": request.headers.get("content-length")},
    )
    return JSONResponse(status_code=400, content={"detail": "Invalid header"})
```

**Authentication Errors** (from dependencies, not middleware strictly):

```python
except ExpiredSignatureError:
    logger.warning("JWT token verification failed: token expired")
    raise HTTPException(status_code=401, detail="Token has expired")
except InvalidTokenError as exc:
    logger.warning("JWT token verification failed: invalid token", extra={"error": str(exc)})
    raise HTTPException(status_code=403, detail="Invalid authentication credentials")
```

**Rate Limit Errors** (from SlowAPI limiter):

```python
# SlowAPI automatically returns 429 with Retry-After header
# Logged by SlowAPI, caught by FastAPI error handler
```

All errors logged with request_id and user_id (when available) for complete tracing.

## Middleware Logging Patterns

**Request Arrival** (optional, at DEBUG level):

```python
logger.debug(
    "Request received",
    extra={
        "method": request.method,
        "path": request.url.path,
        "content_type": request.headers.get("content-type"),
    },
)
```

**Request ID Initialization** (INFO level):

```python
logger.info(
    "Request context initialized",
    extra={
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
    },
)
```

**Authentication** (handled at dependencies, logged at WARNING for failures):

```python
logger.warning("JWT token verification failed: token expired")  # ExpiredSignatureError
logger.warning("JWT token verification failed: invalid token")  # InvalidTokenError
```

**Size Validation** (WARNING on failure):

```python
logger.warning(
    "Request body exceeds size limit",
    extra={
        "content_length": content_length,
        "max_size": max_size,
        "endpoint": request.url.path,
    },
)
```

## Integration with Other Layers

**Request Flow Through Middleware and Layers**:

```
Request Arrives
    ↓
[RequestIDMiddleware] - Generate/extract request_id, set_request_id()
    ↓ (request_id now in contextvars)
[RequestSizeMiddleware] - Check Content-Length header
    ↓
[RateLimitMiddleware] - SlowAPI rate limiting (uses JWT sub from header)
    ↓
[Authentication] - Bearer token verification, set_user_context(user_id)
    ↓ (both request_id and user_id now in contextvars)
[Endpoint Handler] - Route to /v1/chat/completions, /v1/models, etc.
    ↓
[JSONFormatter] - Auto-injects request_id and user_id into all logs
    ↓
[Workflow Steps] - Call Anthropic API with extra_headers["X-Request-ID"]
    ↓
Response → Client
```

All contextvars automatically cleared after request completes.

---

**References and Further Reading**:
- For logging patterns that use request_id and user_id, see `../utils/CLAUDE.md` "Logging Standards" and "Trace Correlation"
- For JWT authentication details and error responses, see `../api/CLAUDE.md` "Authentication Integration"
- For rate limiting integration, see `../api/CLAUDE.md` "Rate Limiting Patterns"
- For complete middleware configuration, see `../../../config.py` and `../../../main.py`
- For middleware architecture decisions, see `../../../ARCHITECTURE.md`
