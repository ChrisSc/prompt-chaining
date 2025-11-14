# API Layer: OpenAI-Compatible Endpoints, Authentication, Rate Limiting

**Location**: `src/workflow/api/`

**Purpose**: API design patterns, endpoint implementations, authentication integration, and rate limiting configuration.

## Navigation

- **Parent**: See `../../CLAUDE.md` for project overview
- **Related Files**:
  - `../chains/CLAUDE.md` - Workflow invocation and state management
  - `../models/CLAUDE.md` - Request/response models (OpenAI layer)
  - `../utils/CLAUDE.md` - Error handling and circuit breaker
  - `../middleware/CLAUDE.md` - Request size validation and context propagation

## OpenAI-Compatible API Contract

The API implements OpenAI chat completions specification, enabling seamless integration with existing OpenAI clients and tools (Open WebUI, LangChain, etc.). Compatibility reduces client-side switching costs and enables reuse of community integrations.

**Core Endpoints**

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/v1/chat/completions` | POST | Required | Stream chat completions via prompt-chaining workflow |
| `/v1/models` | GET | Required | List available Claude models |
| `/health/` | GET | None | Liveness check (K8s readiness) |
| `/health/ready` | GET | None | Readiness check (K8s startup) |

**Request/Response Format**

Request bodies follow OpenAI's `ChatCompletionRequest` specification. Responses stream via Server-Sent Events (SSE) with `ChatCompletionChunk` format. This format is understood by OpenAI clients without modification.

**Why Compatibility Matters**

- **Client Ecosystem**: LangChain, LlamaIndex, and OpenAI API clients work without wrapper code
- **Production Integrations**: Drop-in replacement for OpenAI endpoints in existing deployments
- **Tool Integration**: Works with Open WebUI, prompt management systems, and third-party apps
- **Upgrade Path**: Migrate from OpenAI to self-hosted Claude transparently

**Model Metadata**

The `/v1/models` endpoint returns model information with three-layer structure:
- `id`: Display name from config (user-facing)
- `root`: Underlying Claude model from chain config (e.g., claude-haiku-4-5-20251001)
- Standard OpenAI fields (object, created, owned_by) for compatibility

## Endpoint Design Patterns

### POST /v1/chat/completions - Streaming Chat Completions

**Location**: `src/workflow/api/v1/chat.py:67-317`

Main endpoint for prompt-chaining execution. Orchestrates three sequential steps (analyze → process → synthesize) via LangGraph StateGraph and streams results to client via Server-Sent Events.

**Request Parameters**

- `model` (string, required): Model identifier (validates compatibility)
- `messages` (array, required): Conversation history with role/content
- `temperature` (float, optional): Sampling temperature 0.0-2.0 (default: 0.7)
- `max_tokens` (int, optional): Max response tokens 1-8000 (default: 4096)
- `top_p` (float, optional): Nucleus sampling 0.0-1.0 (default: 1.0)
- `stream` (bool, optional): Stream tokens as Server-Sent Events (default: false)

**Authentication**

Requires Bearer token in `Authorization` header:
```
Authorization: Bearer <jwt_token>
```

Token must be valid JWT signed with `JWT_SECRET_KEY`. Expired tokens return 401; invalid signatures return 403.

**Streaming Response Format**

Stream consists of newline-delimited JSON objects with `data:` prefix (SSE format):

Each chunk contains:
- `id`: Unique chunk identifier (timestamp-based)
- `model`: Model name from request
- `choices[0].delta.content`: Token text (empty first chunk has role)
- `finish_reason`: null for intermediate chunks, "stop" or "length" at end

Stream terminates with `data: [DONE]\n\n` marker. Clients using EventSource API (browser) receive chunks in order.

**Non-Streaming Response Format** (if stream=false)

Returns single response object instead of chunks with message content and usage statistics.

**Error Responses During Stream**

Errors are sent as SSE events with error structure. Common errors include external service errors (503), streaming timeouts (408), and server errors (500).

**Rate Limiting**

Rate limit: `10/minute` per authenticated user (JWT subject). Responses include rate limit headers:
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 9
X-RateLimit-Reset: 1699123470
```

When limit exceeded, returns HTTP 429 with Retry-After header.

### GET /v1/models - List Available Models

**Location**: `src/workflow/api/v1/models.py:14-66`

Returns list of available models compatible with the service configuration.

**Request**

```
GET /v1/models
Authorization: Bearer <jwt_token>
```

**Response Format**

```json
{
  "object": "list",
  "data": [
    {
      "id": "turn-key-claude",
      "object": "model",
      "created": 1762232400,
      "owned_by": "Service Owner",
      "root": "claude-haiku-4-5-20251001",
      "parent": {}
    }
  ]
}
```

Response fields:
- `id`: Display name from config (what clients request in model parameter)
- `root`: Actual Claude model from chain config (underlying implementation)
- `created`: Unix timestamp of service deployment
- `owned_by`: Service owner name

**Rate Limiting**

Rate limit: `60/minute` per authenticated user (higher than chat/completions since this is a fast, read-only operation).

**Authentication**

Requires Bearer token (same as chat/completions). Returns 401/403 on token failure.

### GET /health/ - Liveness Check

**Location**: `src/workflow/api/health.py:12-21`

Simple liveness probe for Kubernetes or container orchestrators. Indicates whether the API process is running and responsive.

**Request**

```
GET /health/
```

No authentication required.

**Response (Success)**

HTTP 200 with `{"status": "healthy"}` indicates the service is alive.

**Response (Failure)**

HTTP 503 with error details. Returned when service encounters unrecoverable failures (missing configuration, failed initialization).

**Use Case**

Kubernetes `livenessProbe` for automatic restart on failure.

### GET /health/ready - Readiness Check

**Location**: `src/workflow/api/health.py:24-35`

Readiness probe indicating whether the service is ready to accept requests. Checks internal state (circuit breaker, rate limiter, chain graph).

**Request**

```
GET /health/ready
```

No authentication required.

**Response (Success)**

HTTP 200 with `{"status": "ready"}` indicates service is ready for traffic.

**Response (Failure)**

HTTP 503 when service is not ready:
- Circuit breaker in open state
- Chain graph not initialized
- Configuration validation failed

**Use Case**

Kubernetes `readinessProbe` for gradual traffic shift during deployments.

## Authentication Integration

All protected endpoints require Bearer token authentication. Authentication is implemented via JWT verification in the `dependencies` layer with automatic user context extraction.

**Bearer Token Format**

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyQGV4YW1wbGUuY29tIiwiaWF0IjoxNjk5MTIzNDU2LCJleHAiOjE2OTkxMjcwNTZ9.signature
```

**Verification Flow** (from `src/workflow/api/dependencies.py:36-120`)

1. Extract Bearer token from `Authorization` header via HTTPBearer security scheme
2. Verify JWT_SECRET_KEY is configured (32+ chars, checked on every request)
3. Decode JWT using configured algorithm (default: HS256)
4. Extract `sub` claim (user identifier) and store in context via `set_user_context()`
5. Return decoded payload for endpoint use

**Two Failure Modes**

| Error | HTTP Status | Scenario | Recovery |
|-------|------------|----------|----------|
| ExpiredSignatureError | 401 | Token passed `exp` claim | Client regenerates token via `generate_jwt.py` |
| InvalidTokenError | 403 | Signature invalid or token malformed | Verify JWT_SECRET_KEY matches issuer |

**Logging**

- Token expiration: Logged at WARNING level (expected client behavior)
- Invalid signature: Logged at WARNING level (verify secret key match)
- Missing secret key: Logged at CRITICAL level (service cannot start)

**User Context Extraction**

JWT `sub` claim is extracted and stored in ContextVar (thread-safe, async-safe). This enables:
- Automatic `user_id` injection into all structured logs
- Request filtering by user
- Multi-tenant data isolation
- Rate limiting per user instead of per IP

**Circuit Breaker Integration**

CircuitBreaker instance is initialized in `dependencies.py` and injected as dependency. Configuration:
- Service name: "anthropic"
- Failure threshold: 3 consecutive failures
- Timeout: 30 seconds before half-open state
- Half-open attempts: 1 request to test recovery

When circuit is open (service unavailable), endpoints return 503 with error detail.

## Rate Limiting Patterns

Rate limiting is implemented via SlowAPI (Starlette rate limiting) with JWT-based identification. This enables per-user limits and gradual degradation under load.

**Rate Limiter Configuration** (from `src/workflow/api/limiter.py:103-139`)

```python
limiter = Limiter(
    key_func=get_jwt_subject_or_ip,
    default_limits=["100/hour"],
    headers_enabled=True,
    enabled=os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true",
)
```

**Per-Endpoint Limits**

| Endpoint | Rate Limit | Reason |
|----------|-----------|--------|
| `/v1/chat/completions` | 10/minute | High resource cost (3-step workflow) |
| `/v1/models` | 60/minute | Lightweight query, read-only |
| Default | 100/hour | Conservative default |

**JWT-Based Key Function**

Extracts rate limit key from JWT `sub` claim or falls back to IP:

```
1. Check Authorization header for Bearer token
2. Decode JWT (no verification, performance optimization)
3. Extract 'sub' claim → format as "user_{subject}"
4. On failure (missing/invalid token) → format as "ip_{client_ip}"
```

Examples:
- Valid JWT with sub="alice@example.com" → Rate limit key: `user_alice@example.com`
- No token or invalid JWT → Rate limit key: `ip_192.168.1.100`

**Response Headers**

All rate-limited responses include headers:
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 9
X-RateLimit-Reset: 1699123470
```

When limit exceeded (HTTP 429):
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1699123470
Retry-After: 30
```

Client should wait `Retry-After` seconds before retrying.

**Configuration via Environment**

```bash
RATE_LIMIT_ENABLED=true|false        # Enable/disable globally (default: true)
RATE_LIMIT_DEFAULT=100/hour          # Fallback limit (default from limiter config)
RATE_LIMIT_CHAT_COMPLETIONS=10/minute  # Chat endpoint limit
RATE_LIMIT_MODELS=60/minute          # Models endpoint limit
```

Disable for tests:
```bash
RATE_LIMIT_ENABLED=false pytest tests/
```

**Startup Logging**

Limiter configuration is logged at startup, showing enabled status and per-endpoint limits.

## Streaming Response Patterns

Server-Sent Events (SSE) format enables real-time token delivery with automatic client reconnection.

**SSE Format Specification**

Each chunk is formatted as:
```
data: {json_object}

```

Trailing newline is required. Multiple consecutive newlines separate chunks.

**Client-Side Reception** (Browser EventSource API)

```javascript
const source = new EventSource('/v1/chat/completions', {
  headers: {'Authorization': 'Bearer ' + token}
});

source.addEventListener('message', (event) => {
  const chunk = JSON.parse(event.data);
  if (chunk === '[DONE]') {
    source.close();
    return;
  }
  // Process chunk.choices[0].delta.content
});
```

**Chunk Structure**

First chunk includes role indicator. Intermediate chunks contain token content. Final chunk is `data: [DONE]`.

**Error Handling During Stream**

If error occurs mid-stream, sends error chunk then [DONE]. Client should check for error presence in chunks and handle gracefully.

**Circuit Breaker Integration**

If circuit opens during stream, endpoint returns 503 before stream starts. If circuit opens during active stream (rare), error chunk is sent.

**Browser Compatibility**

EventSource API is supported in all modern browsers. For older browsers, use WebSocket or polling fallback.

## Layer Integration

**Request Flow**

```
Client Request
    ↓
[Middleware] - Request ID generation, size validation
    ↓
[Authentication] - verify_bearer_token() - JWT verification, user context
    ↓
[Rate Limiting] - SlowAPI key_func() - JWT-based key extraction
    ↓
[Endpoint Handler] - Dependency injection (chain_graph, token)
    ↓
[Workflow Invocation] - stream_chain() from chains/graph.py
    ↓
[Streaming Response] - SSE format with ChatCompletionChunk
    ↓
Client
```

**State Propagation**

Request state flows through multiple layers:
- `request_id`: Generated/extracted in middleware, propagated via context
- `user_id`: Extracted from JWT `sub`, propagated via context
- `circuit_breaker`: Injected as dependency, shared across all endpoints
- `rate_limit_key`: Generated from JWT `sub` or IP, isolated per identifier

**Dependency Injection**

FastAPI Depends mechanism enables clean separation of concerns with lazy evaluation and per-request caching.

---

**References and Further Reading**:
- **Workflow Execution**: See `../chains/CLAUDE.md` for ChainState usage and step execution
- **Data Models**: See `../models/CLAUDE.md` for request/response schemas and model customization
- **Logging and Error Handling**: See `../utils/CLAUDE.md` for logging standards and circuit breaker patterns
- **Request Interception**: See `../middleware/CLAUDE.md` for request ID propagation and context management
- **Prompts and Output**: See `../prompts/CLAUDE.md` for system prompt patterns and JSON validation
- **Configuration**: See `../../../config.py` for API configuration settings
- **Architecture Details**: See `../../../ARCHITECTURE.md` for deep dives on circuit breaker and request lifecycle
- **Authentication**: See `../../../JWT_AUTHENTICATION.md` for detailed JWT configuration
