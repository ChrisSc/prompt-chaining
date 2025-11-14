# Utils Layer: Observability, Logging, Error Handling

**Location**: `src/workflow/utils/`

**Purpose**: Shared utilities, logging standards, observability patterns, and error handling across the workflow.

## Navigation

- **Parent**: See `../../CLAUDE.md` for project overview
- **Related Files**:
  - `../api/CLAUDE.md` - API error responses and status codes
  - `../middleware/CLAUDE.md` - Context propagation and request ID
  - `../chains/CLAUDE.md` - Logging in workflow steps

## Logging Standards

The utils layer provides structured JSON logging for comprehensive observability. All logging is handled through `src/workflow/utils/logging.py` with support for both JSON and standard formats.

### Log Level Usage Guide

Choose log levels based on impact and severity to keep logs actionable and appropriately noisy.

**CRITICAL (50): Unrecoverable System Failures**

Use CRITICAL for failures that prevent the service from operating. These require immediate operator intervention.

When to use:
- Service initialization failures that cannot be recovered
- Missing or invalid required configuration
- Permanent circuit breaker failures (service deemed unreachable)

Example: Missing ANTHROPIC_API_KEY prevents any requests.

**ERROR (40): Recoverable Request-Level Failures**

Use ERROR for failures that affect individual requests but don't prevent the service from running.

When to use:
- Request processing failures (validation errors, LLM failures)
- Exceptions during step execution (analyze, process, synthesize)
- JSON parsing failures on step outputs
- Chain graph unavailable (returns 503)

Example pattern (from `src/workflow/chains/steps.py`):
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

**WARNING (30): Degraded State or Potential Issues**

Use WARNING for conditions that don't prevent operation but indicate a problem that should be reviewed.

When to use:
- Validation gate failures (confidence too low)
- Request size exceeds recommended threshold
- Rate limits or throttling conditions
- Failed recovery attempts
- Token streaming write failures

Example pattern (from `src/workflow/chains/validation.py`):
```python
logger.warning(
    f"Processing validation failed: {error_message}",
    extra={
        "step": "process_validation",
        "error": error_message,
    },
)
```

**INFO (20): Important State Transitions and Metrics**

Use INFO for successful completions, important milestones, and business logic events that should be tracked in production.

When to use:
- Step completion (analyze, process, synthesize finished successfully)
- Request tracking and audit trails
- Circuit breaker state changes
- Validation gate passes

Example pattern (from `src/workflow/chains/steps.py`):
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

Use DEBUG for internal state inspection and flow tracing. These logs are typically disabled in production.

When to use:
- Internal state initialization and setup
- Detailed flow tracing through components
- Configuration validation details
- Schema validation details (non-failure cases)

Example pattern (from `src/workflow/chains/steps.py`):
```python
logger.debug(
    "Stream writer obtained",
    extra={
        "step": "synthesize",
        "writer_is_none": writer is None,
        "writer_callable": callable(writer),
    },
)
```

### Structured Logging Fields

Always use structured fields instead of string formatting. The JSONFormatter in `src/workflow/utils/logging.py` automatically includes standard fields plus custom fields passed via `extra` parameter.

| Field | Type | When to Use | Example |
| --- | --- | --- | --- |
| error | string | On any error or warning | "Configuration validation failed" |
| error_type | string | When logging exceptions | "ValidationError", "JSONDecodeError" |
| request_id | string | Auto-injected for all logs | "req_1699123456789" |
| user_id | string | Auto-injected after JWT auth | "user@example.com" |
| step | string | For workflow steps | "analyze", "process", "synthesize" |
| service | string | For external services | "anthropic", "circuit_breaker" |
| status_code | int | For HTTP responses and API failures | 503, 429, 400 |
| elapsed_seconds | float | For performance-critical operations | 1.234, 2.567 |
| input_tokens | int | Token tracking (with output/total) | 150, 512 |
| output_tokens | int | Token tracking (with input/total) | 200, 1024 |
| total_tokens | int | Sum of input and output tokens | 350, 1536 |
| input_cost_usd | float | Monetary cost breakdown | 0.000075 |
| output_cost_usd | float | Monetary cost breakdown | 0.00030 |
| total_cost_usd | float | Total cost for operation or request | 0.000375 |
| confidence | float | Process step quality metrics | 0.85, 0.92 |
| content_length | int | Response size metrics | 2048, 4096 |

### Trace Correlation: Request and User ID

The logging system automatically injects `request_id` and `user_id` into every log entry, enabling end-to-end tracing without manual logging effort.

**Automatic Injection Mechanism**

Both fields are retrieved from Python `contextvars` and injected by the `JSONFormatter`:
- **request_id**: Generated or extracted by middleware at the request boundary, stored via `set_request_id()` in `src/workflow/utils/request_context.py`
- **user_id**: Extracted from JWT `sub` claim during authentication, stored via `set_user_context()` in `src/workflow/utils/user_context.py`
- **Context Isolation**: Context variables are async-safe, automatically isolated per request/task

**No Manual Logging Required**

Developers don't need to manually pass request_id or user_id:

```python
# AFTER (automatic injection - preferred):
logger.info("Step completed")  # request_id and user_id auto-added
```

Both fields are automatically present in all logs once the request passes authentication.

**Example: Single Request Traced Across Steps**

A request with `request_id: "req_1731424800123"` produces correlated logs across all steps:

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

### Best Practices

1. **Use structured fields, not string formatting**
   - Good: `logger.info("Step completed", extra={"step": "analyze", "elapsed_seconds": 2.5})`
   - Avoid: `logger.info(f"Step completed in {elapsed_time} seconds")`

2. **Log errors with full exception context**
   ```python
   logger.error("Operation failed", extra={"error": str(e), "error_type": type(e).__name__})
   ```

3. **Use appropriate log levels—don't over-log**
   - DEBUG for troubleshooting details only
   - INFO for business logic milestones and successes
   - WARNING for recoverable problems
   - ERROR for request failures

4. **For external services, include service name and status code**
   ```python
   logger.warning(
       "API call failed",
       extra={"service": "anthropic", "status_code": 429},
   )
   ```

5. **For token tracking, always include all three metrics**
   - Include input_tokens, output_tokens, and total_tokens together
   - Enables accurate cost tracking and performance monitoring
   - Never log partial token counts

6. **Sample verbose operations**
   - Don't log every token written to stream (can create thousands of logs)
   - Log at milestones: "Stream writer obtained", "Synthesis step completed"
   - Example: Sample-based logging at DEBUG level (every 100 tokens in synthesis step)

7. **Never log sensitive data**
   - Never include API keys, secrets, tokens, or PII in logs
   - Truncate responses if they contain sensitive data: `response_text[:500]`

**Reference**: `src/workflow/utils/logging.py`

## Circuit Breaker Patterns

The circuit breaker provides resilient API call handling with state management and exponential backoff retry logic.

**State Management**

Circuit breaker transitions between three states:
- **CLOSED**: Normal operation, calls allowed (calls proceed normally)
- **OPEN**: Too many failures, calls blocked (calls fail immediately with CircuitBreakerOpenError)
- **HALF_OPEN**: Testing if service recovered (limited attempts to verify recovery)

**State Transitions**

1. **CLOSED → OPEN**: When consecutive failures reach `failure_threshold` (default: 3)
2. **OPEN → HALF_OPEN**: After `timeout` seconds (default: 30s) elapse
3. **HALF_OPEN → CLOSED**: After `half_open_attempts` successful calls (default: 1)
4. **HALF_OPEN → OPEN**: If any call fails during recovery testing

**Startup Logging**

When the application starts, the circuit breaker logs its full state configuration. This helps verify initialization and shows failure thresholds and recovery parameters.

Logged fields (from `src/workflow/main.py:65-73`):
- `state`: Current state (closed/open/half_open)
- `failure_count`: Current consecutive failures
- `success_count`: Successful tests in half_open state
- `failure_threshold`: Failures needed to open circuit
- `timeout`: Seconds to wait before attempting recovery
- `half_open_attempts`: Tests needed to close circuit from half_open

Example startup log:
```json
{
  "timestamp": "2024-11-13T10:30:42.123Z",
  "level": "INFO",
  "logger": "workflow.main",
  "message": "Circuit breaker initialized with state dump",
  "service": "anthropic",
  "state": "closed",
  "failure_count": 0,
  "failure_threshold": 3,
  "timeout": 30,
  "half_open_attempts": 1
}
```

**Error Handling**

The circuit breaker maps Anthropic SDK exceptions to custom error classes:
- `RateLimitError` (429) → `AnthropicRateLimitError`
- `InternalServerError` (5xx) → `AnthropicServerError`
- `APITimeoutError` → `AnthropicTimeoutError`
- `APIConnectionError` → `AnthropicConnectionError`

Retry logic uses exponential backoff (via tenacity library) with jitter for rate-limited and transient errors.

**Reference**: `src/workflow/utils/circuit_breaker.py`, `src/workflow/utils/anthropic_errors.py`

## Token Tracking Patterns

Token tracking utilities in `src/workflow/utils/token_tracking.py` calculate costs and aggregate metrics across API calls.

**Model Pricing**

Current pricing (USD per 1M tokens):
- **Claude 3.5 Haiku** (claude-haiku-4-5-20251001): $1 input / $5 output
- **Claude 3.5 Sonnet** (claude-sonnet-4-5-20250929): $3 input / $15 output

Pricing is defined in `get_model_pricing()` and should be updated as rates change.

**Cost Calculation**

The `calculate_cost()` function computes USD cost for API usage:

```python
from workflow.utils.token_tracking import calculate_cost

cost = calculate_cost("claude-haiku-4-5-20251001", 100, 50)
# Returns CostMetrics(input_cost_usd=0.0001, output_cost_usd=0.00025, total_cost_usd=0.00035)
```

**Aggregation**

The `aggregate_token_metrics()` function combines usage across multiple API calls:

```python
usages = [
    {"input_tokens": 100, "output_tokens": 50},
    {"input_tokens": 150, "output_tokens": 75},
]
models = ["claude-haiku-4-5-20251001", "claude-haiku-4-5-20251001"]
total_tokens, total_cost = aggregate_token_metrics(usages, models)
```

**Logging Pattern**

Always log input_tokens, output_tokens, and total_tokens together:

```python
logger.info(
    "Step completed",
    extra={
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_cost_usd": cost_metrics.input_cost_usd,
        "output_cost_usd": cost_metrics.output_cost_usd,
        "total_cost_usd": cost_metrics.total_cost_usd,
    },
)
```

**Reference**: `src/workflow/utils/token_tracking.py`

## Request Context Management

Request context utilities provide async-safe request tracking throughout the request lifecycle.

**ContextVar Usage**

The `src/workflow/utils/request_context.py` module uses Python's `contextvars` for async-safe context isolation:

```python
from workflow.utils.request_context import set_request_id, get_request_id

# Middleware sets request ID at request boundary
set_request_id("req_1731424800123")

# Any code in the request can retrieve it
request_id = get_request_id()  # "req_1731424800123"
```

**Propagation Pattern**

1. **Middleware Layer**: Request enters, middleware generates or extracts request_id from `X-Request-ID` header
2. **Context Storage**: `set_request_id()` stores in contextvars
3. **Automatic Injection**: JSONFormatter retrieves and adds to all logs
4. **External APIs**: request_id propagated to Anthropic API via `extra_headers` parameter

**Async Safety**

Context variables are automatically isolated per request/task:
- Each concurrent request gets its own context
- No manual context cleanup required
- Safe for FastAPI async handlers and background tasks

**Reference**: `src/workflow/utils/request_context.py`

## User Context Management

User context utilities propagate user identity (from JWT authentication) throughout the request.

**Usage Pattern**

1. JWT authentication extracts user_id from token's `sub` claim
2. `set_user_context(user_id)` stores in contextvars
3. `get_user_context()` retrieves from anywhere in call stack
4. JSONFormatter auto-injects into all logs
5. ChainState includes user_id for workflow tracking

**Example**

```python
from workflow.utils.user_context import set_user_context, get_user_context

# At JWT authentication boundary
set_user_context("alice@example.com")

# In workflow or logging code (automatic in JSONFormatter)
user_id = get_user_context()  # "alice@example.com"
```

**Benefits**

- Async-safe: Automatic isolation per request
- Zero boilerplate: No manual parameter passing needed
- Multi-tenant support: Filter logs and metrics by user
- Security auditing: Track all user actions for compliance

**Reference**: `src/workflow/utils/user_context.py`

## Error Handling Utilities

Custom exception hierarchy and error mapping for consistent error handling.

**Exception Hierarchy**

Base exception: `TemplateServiceError` (all application errors inherit from this)

Common exceptions:
- `ConfigurationError`: Invalid application configuration (critical)
- `ValidationError`: Input validation failures (request-level)
- `RequestSizeError`: Request body exceeds limit
- `AnthropicRateLimitError`: Rate limit hit (429)
- `AnthropicServerError`: Anthropic service error (5xx)
- `AnthropicTimeoutError`: Request timeout
- `AnthropicConnectionError`: Network connection failure
- `CircuitBreakerOpenError`: Circuit breaker is open

**Anthropic Error Mapping**

The `map_anthropic_exception()` function in `src/workflow/utils/anthropic_errors.py` converts Anthropic SDK exceptions to custom errors:

```python
from anthropic import RateLimitError as AnthropicRateLimitError
from workflow.utils.anthropic_errors import map_anthropic_exception

try:
    response = client.messages.create(...)
except Exception as exc:
    mapped_exc = map_anthropic_exception(exc)
    # Now using custom exception with consistent error handling
```

This enables consistent retry logic, rate limit handling, and logging across all external API calls.

**Reference**: `src/workflow/utils/errors.py`, `src/workflow/utils/anthropic_errors.py`

---

## Quick Reference: Utils Files

| File | Purpose |
| --- | --- |
| `logging.py` | Structured JSON logging with JSONFormatter and context auto-injection |
| `circuit_breaker.py` | Circuit breaker pattern for API resilience |
| `token_tracking.py` | Token cost calculation and metric aggregation |
| `request_context.py` | Async-safe request ID management via contextvars |
| `user_context.py` | Async-safe user ID management via contextvars |
| `errors.py` | Custom exception hierarchy |
| `anthropic_errors.py` | Anthropic SDK exception mapping |

## Related Documentation

- **API Endpoints**: `../api/CLAUDE.md` for HTTP error responses and rate limiting that log via this layer
- **Workflow Steps**: `../chains/CLAUDE.md` for step-specific logging patterns and error handling
- **Request Interception**: `../middleware/CLAUDE.md` for request_id and user_id propagation via contextvars
- **Error Handling**: `../api/CLAUDE.md` for HTTP status codes and error response formats
- **Data Models**: `../models/CLAUDE.md` for Pydantic validation errors that get logged here
- **Configuration**: `../../../CLAUDE.md` for LOG_LEVEL and LOG_FORMAT environment variables
- **Architecture**: `../../../ARCHITECTURE.md` for detailed circuit breaker design and observability patterns
