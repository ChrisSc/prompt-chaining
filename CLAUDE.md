# CLAUDE.md: Guidance for Claude Code

Guidance for Claude Code when working with the prompt-chaining orchestration template. This is the project navigation hub. For detailed guidance on specific subsystems, see the nested CLAUDE.md files below.

## Project Overview

Generic template for building OpenAI-compatible prompt-chaining services that orchestrate sequential AI processing steps. Template includes system prompts, structured output models, and validation gates—customize for your domain.

## Essential Commands

```bash
./scripts/dev.sh                                    # Start dev server
./scripts/test.sh                                   # Run tests with coverage
./scripts/format.sh                                 # Format, lint, type check

# Manual testing & token generation
export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)
python console_client.py "Hello, world!"
```

## Quick Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                             # Includes LangChain 1.0.0+ and LangGraph 1.0.0+
cp .env.example .env && edit .env                   # Add ANTHROPIC_API_KEY and JWT_SECRET_KEY
./scripts/dev.sh                                    # Start server
```

## Configuration Quick Reference

| Variable | Purpose | Default |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Claude API key | Required |
| `JWT_SECRET_KEY` | Auth secret (32+ chars) | Required |
| `API_HOST`, `API_PORT` | Server binding | 0.0.0.0:8000 |
| `LOG_LEVEL`, `LOG_FORMAT` | Logging config | INFO, json |
| `CHAIN_*_MODEL` | Per-step model (analyze, process, synthesize) | claude-haiku-4-5-20251001 |
| `CHAIN_*_MAX_TOKENS` | Per-step token limits | 2048 |
| `CHAIN_*_TEMPERATURE` | Per-step temperature (0.0-2.0) | 0.5-0.7 |
| `CHAIN_*_TIMEOUT` | Per-step timeout (1-270s) | 15-30s |
| `CHAIN_ENABLE_VALIDATION`, `CHAIN_STRICT_VALIDATION` | Validation gates | true, false |
| `MAX_REQUEST_BODY_SIZE` | Request size limit | 1MB (1-10MB) |

For detailed configuration tuning, see **PROMPT-CHAINING.md**.

## Architecture Overview

Three-step sequential processing using LangGraph StateGraph:
1. **Analyze**: Extract intent, entities, complexity from user request
2. **Process**: Generate content based on analysis with confidence scoring
3. **Synthesize**: Polish and format response (streaming step)

Validation gates enforce data quality between steps. Each step independently configured for model, tokens, temperature, and timeout. Structured outputs via Pydantic models. System prompts customizable in `src/workflow/prompts/chain_*.md`.

For technical deep dives, see **ARCHITECTURE.md**.

## Import System

Use relative imports only (required for FastAPI CLI discovery):
- Correct: `from workflow.config import Settings`
- Wrong: `from src.workflow.config import Settings`

## Where to Find Guidance

This project uses nested CLAUDE.md files for context-aware, token-efficient guidance in each subsystem. Choose based on your task:

### Quick Reference by Task

| Task | Start Here |
|------|------------|
| **Adding/fixing API endpoints** | `src/workflow/api/CLAUDE.md` |
| **Customizing prompts or adding steps** | `src/workflow/chains/CLAUDE.md`, then `src/workflow/prompts/CLAUDE.md` |
| **Extending data models** | `src/workflow/models/CLAUDE.md` |
| **Debugging logging issues** | `src/workflow/utils/CLAUDE.md` |
| **Implementing middleware** | `src/workflow/middleware/CLAUDE.md` |
| **Cost analysis or token tracking** | `src/workflow/utils/CLAUDE.md` |
| **Authentication issues** | `JWT_AUTHENTICATION.md` |
| **Performance tuning** | `PROMPT-CHAINING.md` |

### Nested Files Directory

```
src/workflow/
├── api/
│   └── CLAUDE.md          ← API patterns, endpoints, authentication
├── chains/
│   └── CLAUDE.md          ← LangGraph, state management, step functions
├── middleware/
│   └── CLAUDE.md          ← Request handling, context propagation
├── models/
│   └── CLAUDE.md          ← Data models, Pydantic patterns
├── prompts/
│   └── CLAUDE.md          ← Prompt engineering, JSON output
└── utils/
    └── CLAUDE.md          ← Logging, observability, error handling
```

Each nested file includes navigation aids to related files.

## API Quick Reference

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| POST | `/v1/chat/completions` | Required | Streaming chat (SSE) |
| GET | `/v1/models` | Required | List available models |
| GET | `/health/` | None | Liveness check |
| GET | `/health/ready` | None | Readiness check |

For detailed patterns and streaming implementation, see `src/workflow/api/CLAUDE.md`.

## Authentication

Generate token: `python scripts/generate_jwt.py [--expires-in 7d] [--subject my-service]`

Usage: `Authorization: Bearer <token>` header on all protected endpoints.

For JWT details, error responses, and advanced configuration, see **JWT_AUTHENTICATION.md**.

## Data Models

**Two layers:**
1. OpenAI-compatible (`models/openai.py`): External API contract
2. Internal (`models/internal.py`): Domain logic—customize:
   - `AnalysisOutput` - Intent, entities, complexity
   - `ProcessOutput` - Generated content, confidence
   - `SynthesisOutput` - Formatted response
   - `ChainConfig` - Domain-specific parameters

For customization patterns and Pydantic usage, see `src/workflow/models/CLAUDE.md`.

## Customization

The template supports domain-specific customization at three levels:

1. **System Prompts** - Edit `src/workflow/prompts/chain_*.md` files
   - Detailed patterns: see `src/workflow/prompts/CLAUDE.md`
2. **Data Models** - Extend in `src/workflow/models/chains.py`
   - Model architecture: see `src/workflow/models/CLAUDE.md`
3. **Configuration** - Update `.env.example` and `src/workflow/config.py`
   - Tuning guidance: see **PROMPT-CHAINING.md**

For advanced customization, see **ARCHITECTURE.md**.

## Development Essentials

### FastAPI CLI (IMPORTANT)
Always use `fastapi dev` (not `uvicorn`):
```bash
fastapi dev src/workflow/main.py                    # Correct: auto-reload, better errors
```

### Testing Strategy
- **Unit tests**: Components (models, config, utilities)
- **Integration tests**: API endpoints with mocked dependencies
- **Live endpoint tests**: Full app with running server
- **Target**: >80% coverage, use pytest-asyncio

### Development Workflow
1. Update `src/workflow/` files
2. Add/update tests in `tests/`
3. Run: `./scripts/test.sh && ./scripts/format.sh`
4. Verify: `./scripts/dev.sh` and test endpoints
5. Commit with descriptive message

## Observability

### Logging
Configure via `LOG_LEVEL` (default: INFO) and `LOG_FORMAT` (default: json). Structured JSON logs include: timestamp, level, message, request_id, total_tokens, total_cost_usd, elapsed_seconds.

For logging architecture and monitoring queries, see **ARCHITECTURE.md**.

### Startup Component Logging

The application logs detailed state dumps for critical components on startup, enabling visibility into initial configuration and readiness.

**Circuit Breaker State Dump**

When the application starts, the circuit breaker logs its full state configuration. This helps verify circuit breaker is initialized correctly and shows its failure thresholds and recovery parameters.

Logged fields (from `src/workflow/main.py:65-73`):
- `state`: Current state (closed/open/half_open)
- `failure_count`: Current consecutive failures
- `success_count`: Successful tests in half-open state
- `failure_threshold`: Failures needed to open circuit
- `timeout`: Seconds to wait before attempting recovery
- `half_open_attempts`: Tests needed to close circuit from half-open
- `recovery_attempt_count`: Total recovery attempts made
- `consecutive_recovery_failures`: Recent recovery failures
- `max_recovery_attempts`: Threshold for deeming service unrecoverable

Example startup log:

```json
{
  "timestamp": "2024-11-13T10:30:42.123Z",
  "level": "INFO",
  "logger": "workflow.main",
  "message": "Circuit breaker initialized with state dump",
  "step": "initialization",
  "service": "anthropic",
  "state": "closed",
  "failure_count": 0,
  "success_count": 0,
  "failure_threshold": 3,
  "timeout": 30,
  "half_open_attempts": 1,
  "recovery_attempt_count": 0,
  "consecutive_recovery_failures": 0,
  "max_recovery_attempts": 3
}
```

**Rate Limiter Health Status**

The rate limiter logs its configuration and enabled status at startup. This verifies rate limiting is properly initialized and shows the active rate limit rules for each endpoint.

Logged fields (from `src/workflow/api/limiter.py:113-138`):
- `enabled`: Whether rate limiting is active (bool)
- `default_limit`: Default rate limit string (e.g., "100/hour")
- `chat_completions_limit`: Rate limit for chat completions endpoint
- `models_limit`: Rate limit for models endpoint
- `key_function_type`: Type of key function used (jwt-based)

Example startup log:

```json
{
  "timestamp": "2024-11-13T10:30:42.456Z",
  "level": "INFO",
  "logger": "workflow.main",
  "message": "Rate limiter initialized with status",
  "step": "initialization",
  "component": "rate_limiter",
  "enabled": true,
  "default_limit": "100/hour",
  "chat_completions_limit": "50/hour",
  "models_limit": "100/hour",
  "key_function_type": "jwt-based"
}
```

### Token Streaming Logging

The synthesize step uses sample-based logging instead of per-token logging to avoid excessive log volume. Tokens are logged at DEBUG level every 100 tokens, capturing periodic checkpoints of streaming progress.

**Why Sample-Based Logging**

- **Volume Control**: Per-token logging at 4,000 tokens would generate 4,000 individual logs per request (overwhelming)
- **Debug-Level**: Sample logs only appear when LOG_LEVEL=DEBUG, suitable for development/troubleshooting
- **Frequency**: Approximately 1 log per 100 tokens keeps noise minimal while providing progress visibility

Example sample log (from `src/workflow/chains/steps.py:442-449`):

```json
{
  "timestamp": "2024-11-13T10:30:50.789Z",
  "level": "DEBUG",
  "logger": "workflow.chains.steps",
  "message": "Tokens streaming to client",
  "step": "synthesize",
  "token_count": 100
}
```

After 4,000 tokens, you'd see approximately 40 such sample logs (one every 100 tokens) instead of 4,000 per-token logs.

### Cost Tracking
```bash
grep "total_cost_usd" logs.json | jq '.total_cost_usd' | sort -n
```
Model pricing: Haiku $1/$5 per 1M input/output tokens, Sonnet $3/$15.

### Performance Monitoring
```bash
grep "step_breakdown\|total_elapsed_seconds" logs.json | jq '.'
python scripts/benchmark_chain.py                   # Compare configurations
```
Typical all-Haiku: $0.006/request, 4-8 seconds total.

For deep performance analysis, see **BENCHMARKS.md**.

## Logging Standards

The prompt-chaining template uses structured JSON logging for comprehensive observability and debugging. All logging is handled through `src/workflow/utils/logging.py` with support for both JSON and standard formats.

### Log Level Usage Guide

Proper log level selection ensures logs remain actionable and not overly noisy. Choose levels based on the impact and severity of the condition.

**CRITICAL (50): Unrecoverable System Failures**

Use CRITICAL for failures that prevent the service from operating. These require immediate operator intervention.

When to use:
- Service initialization failures that cannot be recovered
- Missing or invalid required configuration
- Permanent circuit breaker failures (service deemed unreachable)

Example scenario: Missing ANTHROPIC_API_KEY prevents any chat completion requests.

Code pattern:
```python
import logging
logger = logging.getLogger(__name__)

if not settings.anthropic_api_key:
    logger.critical(
        "Missing required API key",
        extra={
            "error": "ANTHROPIC_API_KEY not configured",
            "error_type": "ConfigurationError",
        },
    )
    sys.exit(1)
```

**ERROR (40): Recoverable Request-Level Failures**

Use ERROR for failures that affect individual requests but don't prevent the service from running. The service can continue to accept and process other requests.

When to use:
- Request processing failures (validation errors, LLM failures)
- Exceptions during step execution (analyze, process, synthesize)
- JSON parsing failures on step outputs
- Chain graph unavailable (returns 503)

Example scenario: LLM returns invalid JSON that cannot be parsed into AnalysisOutput.

Code pattern (from `src/workflow/chains/steps.py`):
```python
except (json.JSONDecodeError, ValidationError) as e:
    logger.error(
        "Failed to parse analysis step response",
        extra={
            "step": "analyze",
            "error": str(e),
            "error_type": type(e).__name__,
            "response_text": response_text[:500],
        },
    )
    raise
```

**Authentication Failures**

Authentication failures are logged at WARNING level (not ERROR) because they don't indicate service malfunction—they are expected when clients provide invalid or expired credentials. The log level allows monitoring of auth issues without triggering alert thresholds designed for service errors.

Auth failures occur in `src/workflow/api/dependencies.py:84-109`:

- **ExpiredSignatureError (401 response)**: Token has passed its expiration time
  ```python
  logger.warning("JWT token verification failed: token expired")
  raise HTTPException(status_code=401, detail="Token has expired")
  ```

- **InvalidTokenError (403 response)**: Token signature is invalid or malformed
  ```python
  logger.warning(
      "JWT token verification failed: invalid token",
      extra={"error": str(exc)},
  )
  raise HTTPException(status_code=403, detail="Invalid authentication credentials")
  ```

These distinguish between two common failure modes: expired tokens (client should refresh) versus tampered/invalid tokens (security concern).

**WARNING (30): Degraded State or Potential Issues**

Use WARNING for conditions that don't prevent operation but indicate a problem that should be reviewed. These often require operator action to optimize or prevent future failures.

When to use:
- Validation gate failures (non-empty intent not found, confidence too low)
- Request size exceeds recommended threshold
- Rate limits or throttling conditions
- Failed recovery attempts
- Token streaming write failures

Example scenario: Processing validation fails because confidence score is 0.4 (below 0.5 threshold).

Code pattern (from `src/workflow/chains/validation.py`):
```python
if not is_valid:
    logger.warning(
        f"Processing validation failed: {error_message}",
        extra={
            "step": "process_validation",
            "error": error_message,
        },
    )
    return "error"
```

**INFO (20): Important State Transitions and Metrics**

Use INFO for successful completions, important milestones, and business logic events that should be tracked in production.

When to use:
- Step completion (analyze, process, synthesize finished successfully)
- Request tracking and audit trails
- Circuit breaker state changes
- Validation gate passes
- Stream writer state changes

Example scenario: Analysis step completes with extracted intent and confidence metrics.

Code pattern (from `src/workflow/chains/steps.py`):
```python
logger.info(
    "Analysis step completed",
    extra={
        "step": "analyze",
        "elapsed_seconds": elapsed_time,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_cost_usd": cost_metrics.input_cost_usd,
        "output_cost_usd": cost_metrics.output_cost_usd,
        "total_cost_usd": cost_metrics.total_cost_usd,
        "intent": analysis_output.intent[:100],
    },
)
```

**DEBUG (10): Detailed Diagnostic Information**

Use DEBUG for internal state inspection and flow tracing. These logs are typically disabled in production and enabled during development or troubleshooting.

When to use:
- Internal state initialization and setup
- Detailed flow tracing through components
- Configuration validation details
- Optional field value inspection
- Schema validation details (non-failure cases)

Example scenario: Inspecting stream writer state and runnable_config propagation in synthesize step.

Code pattern (from `src/workflow/chains/steps.py`):
```python
logger.debug(
    "Stream writer obtained",
    extra={
        "step": "synthesize",
        "writer_is_none": writer is None,
        "writer_callable": callable(writer),
        "runnable_config_is_none": runnable_config is None,
    },
)
```

### Structured Logging Fields

The JSONFormatter in `src/workflow/utils/logging.py` automatically includes standard fields (timestamp, level, logger, message) plus any custom fields passed via the `extra` parameter. Always use structured fields instead of string formatting.

Standard custom fields to include:

| Field | Type | When to Use | Example |
| --- | --- | --- | --- |
| error | string | On any error or warning | "Configuration validation failed" |
| error_type | string | When logging exceptions | "ValidationError", "ValueError", "JSONDecodeError" |
| request_id | string | Auto-injected for all logs | "req_1699123456789" |
| user_id | string | Auto-injected after JWT auth | "user@example.com" |
| step | string | For workflow steps | "analyze", "process", "synthesize", "error" |
| service | string | For external services | "anthropic", "openai", "circuit_breaker" |
| status_code | int | For HTTP responses and external API failures | 503, 429, 400, 401 |
| elapsed_seconds | float | For all performance-critical operations | 1.234, 2.567 |
| input_tokens | int | Token tracking (required with output/total) | 150, 512 |
| output_tokens | int | Token tracking (required with input/total) | 200, 1024 |
| total_tokens | int | Sum of input and output tokens | 350, 1536 |
| input_cost_usd | float | Monetary cost breakdown | 0.000075 |
| output_cost_usd | float | Monetary cost breakdown | 0.00030 |
| total_cost_usd | float | Total cost for operation or request | 0.000375 |
| confidence | float | Process step quality metrics | 0.85, 0.92 |
| content_length | int | Response size metrics | 2048, 4096 |

### Trace Correlation (Request and User ID)

The logging system automatically injects `request_id` and `user_id` into every log entry, enabling end-to-end tracing across the entire workflow without manual logging effort.

**Automatic Injection Mechanism**

Both fields are retrieved from Python `contextvars` and injected by the `JSONFormatter` in `src/workflow/utils/logging.py`:
- **request_id**: Generated or extracted by middleware at the request boundary, stored in context via `set_request_id()`
- **user_id**: Extracted from JWT `sub` claim during authentication, stored in context via `set_user_context()`
- **Context Isolation**: Context variables are async-safe, automatically isolated per request/task

**End-to-End Request Tracing**

A single request ID flows through the entire system, enabling complete request tracing:

1. **Middleware Layer**: Request enters, middleware generates/extracts request_id from `X-Request-ID` header
2. **Authentication Layer**: JWT verified, `sub` claim extracted and stored as user_id
3. **Workflow Steps**: All logs from analyze → process → synthesize automatically include both IDs
4. **External API Calls**: request_id propagated to Anthropic API via `extra_headers` parameter
5. **Error Handling**: Both IDs present in all error logs for debugging

**No Manual Logging Required**

Developers don't need to manually pass request_id or user_id to log calls:

```python
# BEFORE (manual approach - not needed):
logger.info("Step completed", extra={"request_id": req_id, "user_id": user})

# AFTER (automatic injection - preferred):
logger.info("Step completed")  # request_id and user_id auto-added
```

Both fields are automatically present in all logs once the request passes authentication.

**Example: Single Request Traced Across Steps**

A request with `request_id: "req_1731424800123"` and `user_id: "alice@example.com"` produces correlated logs across all steps:

```json
{
  "timestamp": "2024-11-13T10:30:45.123Z",
  "level": "INFO",
  "logger": "workflow.chains.steps",
  "message": "Analysis step completed",
  "request_id": "req_1731424800123",
  "user_id": "alice@example.com",
  "step": "analyze",
  "elapsed_seconds": 1.2,
  "total_tokens": 235
}
```

```json
{
  "timestamp": "2024-11-13T10:30:47.456Z",
  "level": "INFO",
  "logger": "workflow.chains.steps",
  "message": "Processing step completed",
  "request_id": "req_1731424800123",
  "user_id": "alice@example.com",
  "step": "process",
  "elapsed_seconds": 2.1,
  "confidence": 0.87
}
```

```json
{
  "timestamp": "2024-11-13T10:30:49.789Z",
  "level": "INFO",
  "logger": "workflow.chains.steps",
  "message": "Synthesis step completed",
  "request_id": "req_1731424800123",
  "user_id": "alice@example.com",
  "step": "synthesize",
  "elapsed_seconds": 1.5
}
```

**Filtering and Analysis**

Query all logs for a specific request:
```bash
jq 'select(.request_id=="req_1731424800123")' logs.json
```

Query all activity for a specific user:
```bash
jq 'select(.user_id=="alice@example.com")' logs.json
```

Trace request performance across all steps:
```bash
jq 'select(.request_id=="req_1731424800123") | {step, elapsed_seconds}' logs.json
```

**External API Propagation**

The `request_id` is also sent to the Anthropic API via `extra_headers` in all step functions, enabling correlation of Claude API logs with application logs for complete observability.

### JSON Log Format

All logs with `log_format: "json"` (the default) are output as single-line JSON for easy parsing and aggregation. Here's an example of a parsed log entry:

```json
{
  "timestamp": "2024-11-13T10:30:45.123Z",
  "level": "INFO",
  "logger": "workflow.chains.steps",
  "message": "Analysis step completed",
  "request_id": "req_1699123456789",
  "step": "analyze",
  "elapsed_seconds": 2.345,
  "input_tokens": 150,
  "output_tokens": 85,
  "total_tokens": 235,
  "input_cost_usd": 0.00015,
  "output_cost_usd": 0.000085,
  "total_cost_usd": 0.000235
}
```

Error log example with exception information:

```json
{
  "timestamp": "2024-11-13T10:30:47.456Z",
  "level": "ERROR",
  "logger": "workflow.chains.steps",
  "message": "Failed to parse analysis step response",
  "step": "analyze",
  "error_type": "JSONDecodeError",
  "error": "Expecting value: line 1 column 2 (char 1)",
  "response_text": "{invalid json truncated..."
}
```

Startup component dump example - Circuit breaker state:

```json
{
  "timestamp": "2024-11-13T10:30:42.123Z",
  "level": "INFO",
  "logger": "workflow.main",
  "message": "Circuit breaker initialized with state dump",
  "step": "initialization",
  "service": "anthropic",
  "state": "closed",
  "failure_count": 0,
  "success_count": 0,
  "failure_threshold": 3,
  "timeout": 30,
  "half_open_attempts": 1,
  "recovery_attempt_count": 0,
  "consecutive_recovery_failures": 0,
  "max_recovery_attempts": 3
}
```

Startup component dump example - Rate limiter health:

```json
{
  "timestamp": "2024-11-13T10:30:42.456Z",
  "level": "INFO",
  "logger": "workflow.main",
  "message": "Rate limiter initialized with status",
  "step": "initialization",
  "component": "rate_limiter",
  "enabled": true,
  "default_limit": "100/hour",
  "chat_completions_limit": "50/hour",
  "models_limit": "100/hour",
  "key_function_type": "jwt-based"
}
```

### Configuration

Log level and format are controlled via environment variables in `.env`:

```bash
# Set minimum log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# Set output format: json or standard
LOG_FORMAT=json
```

Default behavior (from `src/workflow/config.py`):
- LOG_LEVEL defaults to INFO (suppresses DEBUG messages)
- LOG_FORMAT defaults to json (structured logging)

Change these to debug:
```bash
LOG_LEVEL=DEBUG
LOG_FORMAT=standard  # For human-readable output
```

### Best Practices

1. **Use structured fields, not string formatting**
   - Good: `logger.info("Step completed", extra={"step": "analyze", "elapsed_seconds": 2.5})`
   - Avoid: `logger.info(f"Analyze step completed in {elapsed_time} seconds")`

2. **request_id and user_id are auto-injected - no manual logging needed**
   - Both fields automatically added to all logs by JSONFormatter
   - Retrieved from contextvars (request_id from middleware, user_id from JWT auth)
   - No need to include in `extra={}` parameter
   - Enable complete request tracing and user activity monitoring

3. **Log errors with full exception context**
   ```python
   logger.error("Operation failed", extra={"error": str(e), "error_type": type(e).__name__})
   ```

4. **Use appropriate log levels—don't over-log**
   - DEBUG should only contain details needed during troubleshooting
   - INFO should cover business logic milestones and successes
   - WARNING for recoverable problems that warrant attention
   - ERROR for request failures that need investigation

5. **For external services, include service name and status code**
   ```python
   logger.warning(
       "API call failed",
       extra={"service": "anthropic", "status_code": 429},
   )
   ```

6. **For token tracking, always include all three metrics**
   - Include input_tokens, output_tokens, and total_tokens together
   - Enables accurate cost tracking and performance monitoring
   - Never log partial token counts

7. **Sample verbose operations**
   - Don't log every token written to stream (can create thousands of logs)
   - Log at milestones: "Stream writer obtained", "Synthesis step completed"
   - Example from `src/workflow/chains/steps.py`: log stream state once, not per token

8. **Never log sensitive data**
   - Never include API keys, secrets, tokens, or PII in logs
   - Truncate responses if they contain sensitive data: `response_text[:500]`
   - Use placeholder values for masked fields

### Examples from the Codebase

**Example 1: Logging step completion with full metrics (INFO level)**

From `src/workflow/chains/steps.py` (lines 296-310):
```python
logger.info(
    "Processing step completed",
    extra={
        "step": "process",
        "elapsed_seconds": elapsed_time,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_cost_usd": cost_metrics.input_cost_usd,
        "output_cost_usd": cost_metrics.output_cost_usd,
        "total_cost_usd": cost_metrics.total_cost_usd,
        "confidence": process_output.confidence,
        "content_length": len(process_output.content),
    },
)
```

**Example 2: Logging validation failure (WARNING level)**

From `src/workflow/chains/validation.py` (lines 217-224):
```python
logger.warning(
    f"Analysis validation failed: {error_message}",
    extra={
        "step": "analysis_validation",
        "error": error_message,
    },
)
```

**Example 3: Logging error with exception type (ERROR level)**

From `src/workflow/chains/steps.py` (lines 197-204):
```python
logger.error(
    "Analysis step failed",
    extra={
        "step": "analyze",
        "error": str(e),
        "error_type": type(e).__name__,
    },
)
```

### References

- See "Configuration Quick Reference" (line 30) for LOG_LEVEL and LOG_FORMAT environment variable defaults
- See "Observability" section (line 133) for monitoring, cost tracking, and performance analysis patterns:
  - "Startup Component Logging" (line 140): Circuit breaker state dump and rate limiter health status logged on startup
  - "Token Streaming Logging" (line 210): Sample-based token logging at DEBUG level (every 100 tokens)
- See "Common Issues" section (line 485) for debugging tips using log output
- For logging architecture details, circuit breaker behavior, and request ID propagation, see **ARCHITECTURE.md**
- For detailed performance monitoring and token tracking, see **BENCHMARKS.md**

## Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'src'` | Use `workflow.*` imports, run `pip install -e ".[dev]"` |
| `fastapi dev` can't find app | Use full path: `fastapi dev src/workflow/main.py`, verify `app = create_app()` at module level |
| 401/403 on protected endpoints | Generate token: `export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)`, verify `Authorization: Bearer <token>` header |
| Empty intent / Low confidence | Review `chain_analyze.md` / `chain_process.md` prompts, upgrade to Sonnet if needed |
| HTTP 413 (request too large) | Increase `MAX_REQUEST_BODY_SIZE` in .env (max 10MB), restart server |
| `request_id` or `user_id` missing from logs | Middleware sets `request_id` automatically; `user_id` only after JWT auth |

For validation gate debugging, see **ARCHITECTURE.md "Validation Gates"**.
For logging and observability, see `src/workflow/utils/CLAUDE.md`.

## Additional Resources

- **ARCHITECTURE.md** - Graph structure, timeout behavior, circuit breaker, logging architecture
- **PROMPT-CHAINING.md** - Configuration tuning, validation gate configuration, performance guidance
- **JWT_AUTHENTICATION.md** - Token generation, error responses, advanced auth configuration
- **BENCHMARKS.md** - Performance data, model selection guidance
- **README.md** - Docker deployment, usage examples
