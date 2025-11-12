# Architecture Overview

This document describes the technical architecture of the Prompt-Chaining Workflow Template.

## Core Design Pattern: Prompt-Chaining

The system implements a production-grade prompt-chaining pattern for sequential multi-step AI workflows using LangGraph's StateGraph.

### Overview

The prompt-chaining pattern orchestrates sequential processing through three distinct steps, each optimized for its specific role:

1. **Analysis Step**: Parse user intent, identify key entities, assess complexity
2. **Processing Step**: Generate content based on analysis results
3. **Synthesis Step**: Combine and polish results into final response

Each step operates independently with its own Claude model, configuration, and validation gates between steps. State flows through the workflow via `ChainState`, a LangGraph TypedDict that accumulates messages and step outputs.

### Components

#### 1. Analysis Agent
- **Model**: Configurable (default: Claude Haiku 4.5)
- **Purpose**: Intent parsing and understanding
- **Responsibilities**:
  - Parse and understand user intent
  - Extract key entities and concepts
  - Assess task complexity
  - Provide context for processing
  - Return `AnalysisOutput` with intent, entities, complexity

#### 2. Processing Agent
- **Model**: Configurable (default: Claude Haiku 4.5)
- **Purpose**: Content generation
- **Responsibilities**:
  - Generate content based on analysis results
  - Operate on extracted intent and context
  - Return structured `ProcessOutput` with content and confidence
  - Provide metadata for traceability

#### 3. Synthesis Agent
- **Model**: Configurable (default: Claude Haiku 4.5)
- **Purpose**: Response polishing and formatting
- **Responsibilities**:
  - Combine processed content into final response
  - Apply formatting and styling
  - Return `SynthesisOutput` with polished text
  - Stream final response to client

### Coordination Flow

```
User Request
    ↓
[Security Headers Middleware]
    ↓
[Request Size Validation]
    ↓
[JWT Authentication]
    ↓
LangGraph StateGraph Initialization
    ↓
Analysis Step: Parse Intent & Extract Context
    ↓
[Validation Gate]
    ↓
Processing Step: Generate Content
    ↓
[Validation Gate]
    ↓
Synthesis Step: Polish & Format
    ↓
[Validation Gate]
    ↓
Stream Response (SSE format)
    ↓
[Apply Security Headers]
    ↓
Client
```

### Key Characteristics

1. **Sequential Execution**: Steps execute in order with state flowing through `ChainState`
2. **Message Accumulation**: `add_messages` reducer maintains conversation continuity
3. **Validation Gates**: Optional validation between steps with configurable strictness
4. **Independent Configuration**: Each step has its own model, tokens, temperature, and prompt
5. **Structured Outputs**: Type-safe step results (AnalysisOutput, ProcessOutput, SynthesisOutput)
6. **State Management**: Central `ChainState` TypedDict tracks messages and step outputs
7. **Defense-in-Depth Security**: Multiple layers of validation and protection

## Prompt-Chaining Pattern Details

### State Management with ChainState

The `ChainState` TypedDict (from `src/workflow/models/chains.py`) maintains state across all processing steps:

```python
class ChainState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    # Accumulated messages through chain - uses add_messages reducer for proper merging

    analysis: dict[str, Any] | None
    # Output from analysis step containing intent, entities, complexity

    processed_content: str | None
    # Output from processing step containing generated content

    final_response: str | None
    # Final synthesized output from synthesis step

    step_metadata: dict[str, Any]
    # Tracking metadata for the entire chain execution (timing, costs, etc.)
```

**Key Features**:
- **Message Accumulation**: `add_messages` reducer merges new messages with existing ones, maintaining conversation continuity
- **Step Outputs**: Each step populates its own field (analysis, processed_content, final_response)
- **Metadata Tracking**: Captures timing, costs, and other observability metrics across all steps

### Step Output Models

Each step returns a type-safe structured model:

**AnalysisOutput**:
```python
class AnalysisOutput(BaseModel):
    intent: str  # User's primary intent
    key_entities: list[str]  # Key concepts mentioned
    complexity: str  # "simple", "moderate", or "complex"
    context: dict[str, Any]  # Additional contextual information
```

**ProcessOutput**:
```python
class ProcessOutput(BaseModel):
    content: str  # Generated content
    confidence: float  # 0.0 to 1.0 confidence score
    metadata: dict[str, Any]  # Generation metadata
```

**SynthesisOutput**:
```python
class SynthesisOutput(BaseModel):
    final_text: str  # Polished and formatted response
    formatting: str  # Applied formatting style
```

### Configuration with ChainConfig

Complete workflow configuration (from `src/workflow/models/chains.py`):

```python
class ChainStepConfig(BaseModel):
    model: str  # Claude model ID
    max_tokens: int  # Maximum tokens to generate
    temperature: float  # 0.0-2.0 sampling temperature
    system_prompt_file: str  # System prompt filename

class ChainConfig(BaseModel):
    analyze: ChainStepConfig  # Analysis step config
    process: ChainStepConfig  # Processing step config
    synthesize: ChainStepConfig  # Synthesis step config
    analyze_timeout: int = 15  # Analysis timeout (1-270 seconds)
    process_timeout: int = 30  # Processing timeout (1-270 seconds)
    synthesize_timeout: int = 20  # Synthesis timeout (1-270 seconds)
    enable_validation: bool = True  # Enable validation gates
    strict_validation: bool = False  # Fail vs. warn on validation errors
```

## System Prompts

The prompt-chaining workflow uses three specialized system prompts that control the behavior of each processing step:

### chain_analyze.md - Analysis Step Prompt

**Purpose**: Analyze user requests and extract structured information for subsequent steps

**Location**: `src/workflow/prompts/chain_analyze.md`

**Responsibilities**:
- Parse user intent from natural language requests
- Extract key entities, concepts, and topics mentioned
- Assess task complexity (simple, moderate, complex)
- Gather contextual information for processing step

**Output**: AnalysisOutput JSON with:
- `intent`: Clear statement of user's primary goal
- `key_entities`: List of important topics/concepts/entities
- `complexity`: Complexity level assessment
- `context`: Dictionary with additional contextual information

**Example Output**:
```json
{
  "intent": "Compare synchronous vs asynchronous Python code for high-concurrency APIs",
  "key_entities": ["synchronous code", "asynchronous code", "performance", "concurrency"],
  "complexity": "moderate",
  "context": {
    "domain": "backend development",
    "scale": "1000 requests per second"
  }
}
```

### chain_process.md - Processing Step Prompt

**Purpose**: Generate substantive content based on analysis output

**Location**: `src/workflow/prompts/chain_process.md`

**Responsibilities**:
- Receive AnalysisOutput from analysis step
- Generate domain-specific content addressing identified intent
- Assess confidence in generated content
- Capture metadata for traceability

**Input**: AnalysisOutput from analysis step

**Output**: ProcessOutput JSON with:
- `content`: Generated content addressing the intent
- `confidence`: Confidence score (0.0 to 1.0)
- `metadata`: Dictionary with generation metadata

**Example Output**:
```json
{
  "content": "Synchronous Python code blocks each request until complete, while asynchronous code uses await...",
  "confidence": 0.85,
  "metadata": {
    "generation_approach": "comparative analysis",
    "coverage": "both approaches with examples"
  }
}
```

### chain_synthesize.md - Synthesis Step Prompt

**Purpose**: Polish and format the final response for user consumption

**Location**: `src/workflow/prompts/chain_synthesize.md`

**Responsibilities**:
- Receive ProcessOutput from processing step
- Apply formatting and styling to content
- Optimize response for clarity and presentation
- Ensure output meets quality standards

**Input**: ProcessOutput from processing step

**Output**: SynthesisOutput JSON with:
- `final_text`: Polished and formatted response
- `formatting`: Applied formatting style or approach

**Example Output**:
```json
{
  "final_text": "# Synchronous vs Asynchronous Python\n\nSynchronous code blocks...",
  "formatting": "markdown with clear sections and examples"
}
```

### Data Flow Through Prompts

The three prompts work together in sequence:

```
User Request
    ↓
chain_analyze.md (Parse & Extract)
    ↓
AnalysisOutput (JSON)
    ↓
chain_process.md (Generate)
    ↓
ProcessOutput (JSON)
    ↓
chain_synthesize.md (Polish & Format)
    ↓
SynthesisOutput (JSON)
    ↓
User Response
```

Each step's system prompt defines:
- The agent's specific role and responsibilities
- What information to extract or generate
- How to structure output as valid JSON
- Quality expectations and guidelines

### JSON-Only Output Format

All three prompts enforce JSON-only output:
- No markdown code blocks or extra text
- Valid JSON matching the corresponding Pydantic model
- Enables strict parsing and validation in step functions
- Ensures reliable data flow between steps

This strict format is critical for prompt-chaining workflows where structured outputs feed directly into subsequent steps.

### Validation Gates

Optional validation gates run between steps:
- **After Analysis**: Verify intent extraction and entity identification
- **After Processing**: Verify content quality and confidence threshold
- **After Synthesis**: Verify final output meets quality standards

Configurable via `enable_validation` and `strict_validation` parameters.

### LangGraph Integration

The workflow uses `StateGraph` to orchestrate the sequential steps:
- Each step is a graph node
- Transitions between steps are deterministic (no conditional branching by default)
- State flows through ChainState with proper reducer merging
- Async execution via `astream()` for token-by-token output

## Performance Model

### Time Complexity
- **Prompt-Chaining**: O(N) where N = number of sequential steps
- **Total Time**: Sum of all step execution times + network latency
- **Typical**: 3-8 seconds for analysis + processing + synthesis

### Cost Complexity
- **Same as sequential processing**: O(N) - tokens used equals sum of all steps
- **Optimization**: Each step can use appropriate model size (Haiku for most, Sonnet if needed)

### Real-World Measurements
```
Analysis step:    ~1-2s (intent parsing, entity extraction)
Processing step:  ~2-4s (content generation)
Synthesis step:   ~1-2s (formatting and polishing)
Total request:    ~4-8s (plus network overhead)
```

## Technology Stack

### Framework
- **FastAPI**: Modern async web framework
- **Uvicorn**: ASGI server
- **Pydantic v2**: Data validation and settings

### AI Integration
- **Anthropic SDK**: Claude API client
- **AsyncAnthropic**: Async client for efficient operations
- **LangChain 1.0.0+**: LLM interactions and message handling
- **LangGraph 1.0.0+**: StateGraph for multi-step workflow orchestration
- **Streaming**: Native support for SSE streaming

### Development
- **pytest**: Testing framework
- **black**: Code formatting
- **ruff**: Fast linting
- **mypy**: Static type checking

## API Design

### OpenAI Compatibility
The API is designed to be compatible with OpenAI's chat completions API:
- Same request/response structure
- SSE streaming format
- Model listing endpoint

This enables:
- Drop-in replacement for OpenAI clients
- Integration with tools like Open WebUI
- Familiar developer experience

### Streaming Architecture
```
Client Request
    ↓
FastAPI Endpoint (chat.py)
    ↓
Orchestrator.process() → AsyncIterator[ChatCompletionChunk]
    ↓
Synthesizer.process() → AsyncIterator[ChatCompletionChunk]
    ↓
SSE Formatter (data: {json}\n\n)
    ↓
StreamingResponse
    ↓
Client (chunk by chunk)
```

## Data Flow

### Request Path

1. Client sends POST to `/v1/chat/completions` with `Authorization: Bearer <token>` header
2. **Security Headers Middleware**: Prepares response with security headers
3. **Request Size Validation**: Validates request body size
   - Maximum: 1 MB by default (configurable via `MAX_REQUEST_BODY_SIZE`)
   - Protects against memory exhaustion attacks
   - GET requests and health endpoints exempt
4. **JWT Bearer Token Verification**: Via dependency injection
   - Signature validated with `JWT_SECRET_KEY`
   - Token expiration checked (if exp claim present)
   - Returns 401 (unauthorized) for missing tokens
   - Returns 403 (forbidden) for invalid tokens
5. FastAPI validates request via Pydantic models
6. Dependency injection provides Orchestrator agent
7. **Timeout Enforcement**: Request execution with two-phase timeouts
   - Worker Coordination Phase: Maximum time for parallel execution (default: 45s)
   - Synthesis Phase: Maximum time for final response synthesis (default: 30s)
8. Orchestrator analyzes request
9. Workers spawned and executed in parallel
10. Results aggregated by Synthesizer
11. Response streamed as SSE
12. **Security Headers Applied**: All response headers added to streamed response

### Response Format
- **First chunk**: Contains `role: "assistant"` in delta
- **Subsequent chunks**: Contains incremental `content` in delta
- **Final chunk**: Contains `finish_reason` and token `usage`
- **Terminator**: `data: [DONE]` marker
- **All chunks**: Contain security headers

## Configuration Management

### Settings Hierarchy
1. Environment variables (.env file)
2. Pydantic Settings with validation
3. Computed properties (e.g., base_url, model_pricing)

### Key Settings
- **Anthropic API**: Key, model IDs
- **Agent Config**: Max tokens, temperature per agent type
- **Streaming**: Timeout configuration (worker coordination, synthesis)
- **Request Validation**: Maximum body size
- **Security**: JWT secret, security headers enablement
- **CORS**: Origins, methods, headers
- **Logging**: Level, format, Loki integration

### Timeout Configuration (Phase-Specific)

The service enforces separate timeouts for different execution phases:

**Worker Coordination Phase** (`WORKER_COORDINATION_TIMEOUT`)
- Default: 45 seconds
- Controls: Maximum duration for parallel worker execution
- Range: 1-270 seconds
- When exceeded: Workers cancelled, error event sent

**Synthesis Phase** (`SYNTHESIS_TIMEOUT`)
- Default: 30 seconds
- Controls: Maximum duration for final synthesis and streaming
- Range: 1-270 seconds
- When exceeded: Stream ends with error event

**Total Request Budget**: 45s (workers) + 30s (synthesis) = 75 seconds maximum

### Request Size Validation

Protects against memory exhaustion attacks by validating request body sizes.

**Default Behavior**:
- Default limit: 1 MB (1,048,576 bytes)
- Applies to: POST, PUT, PATCH requests
- Exemptions: GET requests, health check endpoints (`/health/*`)

**Configuration**:
- Environment variable: `MAX_REQUEST_BODY_SIZE`
- Valid range: 1 KB (1024) to 10 MB (10,485,760)
- Error response: HTTP 413 Payload Too Large

**Error Response Format**:
```json
{
  "detail": "Request body too large. Maximum size: 1048576 bytes, received: 2097152 bytes"
}
```

## Middleware Stack

### Security Headers Middleware (v0.3.0)

Adds HTTP security headers to all responses to protect against common web vulnerabilities.

**Headers Applied**:
- `X-Content-Type-Options: nosniff` - Prevents MIME-type sniffing attacks
- `X-Frame-Options: DENY` - Protects against clickjacking
- `X-XSS-Protection: 1; mode=block` - Enables browser XSS filtering
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` - HTTPS only

**HSTS Header Behavior**:
- Only added for HTTPS requests
- Detects both direct HTTPS and reverse proxy scenarios (via `X-Forwarded-Proto` header)
- Never sent over HTTP to avoid compatibility issues

**Configuration**:
- Environment variable: `ENABLE_SECURITY_HEADERS` (default: `true`)
- Enabled by default for production-ready security posture
- Can be disabled if needed: `ENABLE_SECURITY_HEADERS=false`

**Applied To**:
- All HTTP responses, including streaming responses
- Both protected and public endpoints
- Health check endpoints

### Request Size Validation Middleware

Validates request body sizes before processing to prevent memory exhaustion attacks.

**Scope**:
- Applied to: POST, PUT, PATCH requests with body content
- Exemptions: GET requests, HEAD requests, health check endpoints

**Behavior**:
- Reads `Content-Length` header
- Rejects requests exceeding configured limit
- Returns HTTP 413 Payload Too Large

### Authentication Middleware

JWT bearer token verification applied to protected endpoints.

**Scope**:
- Applied to: `/v1/chat/completions`, `/v1/models`
- Public endpoints: `/health/`, `/health/ready`

**Error Handling**:
- Missing token: HTTP 401 Unauthorized
- Expired token: HTTP 401 Unauthorized
- Invalid signature: HTTP 403 Forbidden

## Error Handling

### Exception Hierarchy
```
TemplateServiceError (base)
├── ConfigurationError
├── ValidationError
├── ExternalServiceError
├── AgentError
└── SessionError
```

### Error Propagation
- Exceptions caught at multiple layers
- Logged with structured context
- Converted to appropriate HTTP responses
- Streamed errors in SSE format for streaming endpoints

### Timeout Error Handling

When a timeout occurs during streaming, an error event is sent via Server-Sent Events:

```json
{
  "error": {
    "message": "Streaming operation timed out during worker coordination phase after 45s",
    "type": "streaming_timeout_error",
    "phase": "worker coordination",
    "timeout_seconds": 45
  }
}
```

Stream terminates with `data: [DONE]\n\n` after error event.

## Request ID Propagation

### Overview
Request IDs flow through the entire system for end-to-end observability in distributed tracing.

### Flow
```
Client Request
    ↓
Middleware (generates/extracts X-Request-ID)
    ↓
contextvars.ContextVar (request_id stored)
    ↓
FastAPI endpoint
    ↓
Orchestrator (retrieves from context, passes to API)
    ↓
Workers (retrieve from context, pass to API)
    ↓
Synthesizer (retrieves from context, passes to API)
    ↓
Anthropic API (X-Request-ID header included)
```

### Implementation Details

**Middleware** (`main.py:add_request_tracking`)
- Checks `X-Request-ID` header in incoming request
- Generates `req_{timestamp_ms}` if missing or empty
- Calls `set_request_id(request_id)` to store in context

**Context Storage** (`utils/request_context.py`)
- Uses `ContextVar('request_id', default=None)`
- Automatically isolated per async task
- Accessible via `get_request_id()` from any async context

**Agent Usage** (all three agents)
- Call `get_request_id()` to retrieve from context
- Pass `extra_headers={"X-Request-ID": request_id}` to `messages.create()`
- Handles None gracefully (no header sent if not set)

### Benefits
1. **Debugging**: Correlate client requests with Anthropic API calls
2. **Tracing**: Follow request path through orchestrator → workers → synthesizer
3. **Support**: Share request IDs with Anthropic for investigating issues
4. **Logging**: Filter logs by request_id to see complete request lifecycle
5. **Monitoring**: Track request timing and token usage per request ID

### Example Correlation

Client sends: `X-Request-ID: req_client_123`

Logs will show:
```json
{
  "timestamp": "2025-11-09 17:00:00,000",
  "request_id": "req_client_123",
  "message": "Chat completion request completed",
  "total_tokens": 3210,
  "total_cost_usd": 0.0156
}
```

Anthropic API sees: `X-Request-ID: req_client_123` in request headers

This enables end-to-end correlation across all systems.

## Logging Architecture

### Structured Logging System

**JSON Formatter** - All logs emit structured JSON with:
- Standard fields: timestamp, level, logger, message
- Context fields: request_id, user/subject, method, path, status_code
- Performance: response_time, elapsed_seconds, duration_ms
- Cost tracking: input_tokens, output_tokens, total_tokens, input_cost_usd, output_cost_usd, total_cost_usd
- Rate limiting: limit, remaining, reset
- Errors: error, error_type, error_code

**Log Levels by Component:**

| Component | CRITICAL | ERROR | WARNING | INFO | DEBUG |
|-----------|----------|-------|---------|------|-------|
| main.py | Orchestrator init failure | Shutdown errors, service errors | Request size exceeded | Startup, requests, responses | - |
| api/v1/chat.py | - | Agent unavailable, API errors | - | Request tracking, completion | Request details, streaming |
| api/health.py | - | - | - | - | Health checks |
| api/dependencies.py | - | - | JWT verification failed | - | JWT verified |
| middleware/* | - | - | Request size exceeded | - | Security headers, size validation passed |
| utils/token_tracking.py | - | - | Unknown model pricing | - | Cost calculations |
| agents/* | - | Task failures | - | Task processing | Task execution details |

**Log Level Usage:**
- **CRITICAL**: Application cannot start (API key invalid, orchestrator init failed)
- **ERROR**: Operation failed (API timeout, worker task error, agent processing error)
- **WARNING**: Potentially harmful (request too large, rate limit exceeded, JWT invalid)
- **INFO**: Normal operations (requests, responses, token usage, costs) - **production default**
- **DEBUG**: Detailed diagnostics (health checks, JWT success, validation passed) - **development only**

### Cost & Performance Tracking

**Token Usage Flow:**
1. Worker agents track input/output tokens per task
2. Orchestrator aggregates worker metrics
3. Synthesizer adds final synthesis tokens
4. API logs total tokens and USD cost on request completion

**Cost Calculation:**
- Model pricing: Haiku ($1/$5 per 1M tokens), Sonnet ($3/$15 per 1M tokens)
- Computed per agent, aggregated per request
- Logged at INFO level on every request completion

**Example Cost Log:**
```json
{
  "level": "INFO",
  "logger": "workflow.api.v1.chat",
  "message": "Chat completion request completed",
  "request_id": "req_1762674924016",
  "model": "orchestrator-worker",
  "elapsed_seconds": 2.45,
  "total_tokens": 3210,
  "total_cost_usd": 0.0156
}
```

**Performance Metrics:**
- `response_time` (seconds) - Per-request latency
- `elapsed_seconds` (seconds) - Total request duration
- `duration_ms` (milliseconds) - Specific operation timing

### Production Considerations

**Log Aggregation:**
- JSON format compatible with: Loki, Elasticsearch, CloudWatch, Splunk
- Set `LOKI_URL` environment variable for automatic Loki integration
- All logs include timestamp, level, logger, message for filtering

**Log Retention:**
- Container logs: Docker handles rotation (json-file driver default)
- Production: Configure Docker logging driver (splunk, awslogs, etc.)
- Aggregation systems: Apply retention policies (30-90 days typical)

**Log Filtering:**
- Production: `LOG_LEVEL=INFO` (excludes DEBUG noise)
- Troubleshooting: `LOG_LEVEL=DEBUG` (temporary, verbose)
- Errors only: `LOG_LEVEL=ERROR` (minimal logging)
- Query by level: `level="ERROR"` (aggregation system query)

**Monitoring Queries:**
- Cost tracking: `SELECT total_cost_usd, model FROM logs WHERE level="INFO" AND message LIKE "%completed%"`
- Error rates: `SELECT COUNT(*) FROM logs WHERE level="ERROR" GROUP BY error_type`
- Performance: `SELECT AVG(elapsed_seconds) FROM logs WHERE level="INFO"`
- Rate limiting: `SELECT remaining FROM logs WHERE message LIKE "%rate limit%"`

## Security Considerations

### Default-On Security Posture

The template implements a **default-on** security posture where protection mechanisms are enabled by default and can be disabled only explicitly:

1. **Security Headers**: Enabled by default via `ENABLE_SECURITY_HEADERS=true`
2. **Request Size Validation**: Always active (configurable limits only)
3. **Authentication**: Required via JWT tokens on protected endpoints
4. **Error Sanitization**: Sensitive data never exposed in responses

### Implemented Security Features

#### HTTP Security Headers (v0.3.0)
- **X-Content-Type-Options**: Prevents MIME-type sniffing
- **X-Frame-Options**: Clickjacking protection
- **X-XSS-Protection**: Browser XSS filter enablement
- **HSTS**: Enforces HTTPS (HTTPS-only environments)

Configuration:
```env
# Enable/disable security headers (default: true)
ENABLE_SECURITY_HEADERS=true
```

#### JWT Bearer Token Authentication
- HS256 (HMAC-SHA256) symmetric signing algorithm
- Configurable token expiration
- OpenAI-compatible bearer token format (`Authorization: Bearer <token>`)
- Automatic signature and expiration verification
- Minimum 32-character secret key enforcement

Configuration:
```env
JWT_SECRET_KEY=<your-secure-secret-32-chars-minimum>
JWT_ALGORITHM=HS256
```

#### Request Size Validation
- Protects against memory exhaustion attacks
- Configurable limits (1 KB to 10 MB)
- GET requests and health endpoints exempt
- HTTP 413 Payload Too Large on violation

Configuration:
```env
# Default: 1 MB
MAX_REQUEST_BODY_SIZE=1048576
```

#### Request Timeout Enforcement
- Two-phase timeouts for granular control
- Worker coordination phase protection (default: 45s)
- Synthesis phase protection (default: 30s)
- Error events sent on timeout

Configuration:
```env
WORKER_COORDINATION_TIMEOUT=45
SYNTHESIS_TIMEOUT=30
```

#### Environment-Based Secrets
- API keys, JWT secret loaded from .env
- Never committed to version control
- Validated at startup (missing required values cause startup failure)

#### Error Message Sanitization
- Sensitive data never exposed in error responses
- Structured error responses with appropriate HTTP status codes
- Detailed logging for debugging

#### Public Health Endpoints
- `/health/` and `/health/ready` require no authentication
- Enable load balancer and container orchestration health checks
- No sensitive information exposed

See [JWT_AUTHENTICATION.md](./JWT_AUTHENTICATION.md) for complete authentication documentation.

### Rate Limiting Architecture

Implemented with Slowapi (slowapi.readthedocs.io). Rate limits enforce per endpoint:
- Chat completions: 10/minute (default, configurable via RATE_LIMIT_CHAT_COMPLETIONS)
- Models listing: 60/minute (default, configurable via RATE_LIMIT_MODELS)

**Key identification:**
- **Authenticated requests**: Extract JWT `sub` claim from Authorization Bearer token
- **Unauthenticated requests**: Use client IP address
- Each key maintains independent request counter per configured time window

**Response headers** (on all responses):
- `X-RateLimit-Limit`: Total requests allowed in window
- `X-RateLimit-Remaining`: Requests remaining before limit
- `X-RateLimit-Reset`: Unix timestamp when limit resets

**Rate limit exceeded** (HTTP 429):
- Response: `{"detail": "X per Y minute/hour"}`
- Header: `Retry-After: 60` (seconds to wait before retrying)

See CLAUDE.md "Rate Limiting" section for configuration and testing.

### Circuit Breaker Pattern

Protects against cascading failures from external API issues using tenacity library.

**State Machine:**
- **CLOSED**: Normal operation, requests pass through
  - On success: Remains closed
  - On failure: Increment failure count
  - After N failures (default 3): Transition to OPEN
- **OPEN**: Service unavailable, requests fail fast
  - Duration: 30 seconds (default)
  - After timeout: Transition to HALF_OPEN
- **HALF_OPEN**: Testing recovery
  - Allows 1 test request (default)
  - On success: Transition to CLOSED, reset counters
  - On failure: Return to OPEN, restart timeout
- Circuit states tracked per service instance (not shared across replicas)

**Retry Flow:**
1. Request invokes Anthropic API via circuit breaker decorator
2. On transient error (429, 5xx, timeout, connection): Retry with exponential backoff
3. Backoff sequence: ~1s, ~2s, ~4s, ~8s... up to 30s max (with jitter for thundering herd prevention)
4. After max attempts (default 3): Raise RetryError, increment circuit breaker failure count
5. After threshold failures (default 3): Circuit opens, subsequent requests fail fast (503)

**Implementation:**
- Uses tenacity library (`@retry` decorator with custom predicates)
- Exponential backoff: `wait_exponential(multiplier=1.0, max=30)`
- Stop condition: `stop_after_attempt(3)`
- Retry on: `APIError`, `APITimeoutError`, `APIConnectionError`, HTTP 429/5xx
- Circuit breaker state: In-memory (per instance), not distributed

**Benefits:**
- **Resilience**: Automatic recovery from transient failures
- **Fail-fast**: Rapid error responses when service degraded (no cascading timeouts)
- **Observability**: Logs retry attempts, circuit state transitions, failure patterns
- **Flexibility**: Configurable thresholds for different deployment environments

See CLAUDE.md "Circuit Breaker & Retry Logic" section for configuration details.

### Production Recommendations

**API & Authentication**:
- Use strong, randomly-generated JWT secret (minimum 32 characters)
- Store secrets in secure secret management system (e.g., AWS Secrets Manager, HashiCorp Vault)
- Implement token expiration (1-24 hours recommended)
- Enable HTTPS/TLS (tokens only secure with encrypted transport)
- Implement token refresh mechanism for long-running clients

**Infrastructure**:
- HTTPS/TLS termination at reverse proxy
- Reverse proxy (nginx, Traefik) for request filtering and rate limiting
- Input sanitization for prompts and user-supplied data
- Monitoring and alerting (especially for auth failures)
- Plan for secret key rotation

**Deployment**:
- Containerized deployment (Docker)
- Horizontal scaling with multiple instances
- Load balancing
- Health checks and readiness probes

**Operations**:
- Regular security audits
- Dependency vulnerability scanning
- Log aggregation and analysis
- Rate limiting per API key/client
- Request timeout tuning based on actual usage patterns

## Extensibility Points

The template is designed for easy customization of the prompt-chaining workflow:

1. **System Prompts**: Text files in `src/workflow/prompts/` directory
   - `analysis_system.md`: Analysis step instructions
   - `processing_system.md`: Processing step instructions
   - `synthesis_system.md`: Synthesis step instructions
2. **Chain Models**: Workflow models in `src/workflow/models/chains.py`
   - Extend `AnalysisOutput`, `ProcessOutput`, `SynthesisOutput` for domain data
   - Customize `ChainConfig` with additional parameters
3. **Internal Models**: Domain-specific models in `src/workflow/models/internal.py`
   - Add domain-specific validation and business logic
4. **Workflow Agents**: Step execution logic in `src/workflow/agents/`
   - Customize analysis, processing, and synthesis agent behavior
5. **Configuration**: Environment-based settings in `src/workflow/config.py`
   - Add domain-specific configuration parameters
6. **API Endpoints**: Additional routes in `src/workflow/api/` directory
7. **Middleware**: Custom request/response processing in `src/workflow/middleware/` directory

## Deployment

### Development
- Local FastAPI dev server
- Hot reload on code changes
- Interactive API docs at /docs

### Production (Recommended)
- Containerized deployment (Docker)
- Reverse proxy (nginx, Traefik)
- Process manager (systemd, supervisor)
- Health checks and readiness probes
- Horizontal scaling (multiple instances)
- Load balancing

## Future Enhancements

Potential additions to the template:
- Persistent storage for session history
- Advanced user management and RBAC
- WebSocket support for bidirectional communication
- Tool use and function calling
- Multi-modal support (images, files)
- Advanced error recovery and retry logic
- Comprehensive metrics and observability (Prometheus, Grafana)
- A/B testing framework
- Request deduplication and caching
- Custom rate limiting strategies
- API key management and tracking
