# CLAUDE.md

Guidance for Claude Code when working with this multi-agent orchestration template.

## Project Overview

Generic template for building OpenAI-compatible multi-agent services that coordinate parallel AI agents. Template includes simple echo example—customize for your domain.

## Essential Commands

### Quick Start
```bash
./scripts/dev.sh                # Start dev server
./scripts/test.sh               # Run tests with coverage
./scripts/format.sh             # Format, lint, type check
```

### Manual Testing & Token Generation
```bash
export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)
python console_client.py "Hello, world!"
python scripts/generate_jwt.py --expires-in 7d
```

### Initial Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY and JWT_SECRET_KEY
```

This installs all dependencies including LangChain 1.0.0+ and LangGraph 1.0.0+, which are required for the prompt-chaining pattern and multi-step agentic workflows.

## Configuration Reference

**Environment variables only** (`.env`). Never commit secrets.

### Required
- `ANTHROPIC_API_KEY` - Claude API key
- `JWT_SECRET_KEY` - Min 32 chars: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### Server Configuration
- `API_HOST` (default: 0.0.0.0), `API_PORT` (default: 8000)
- `LOG_LEVEL` (default: INFO), `LOG_FORMAT` (default: json)

### Model Configuration
- `ORCHESTRATOR_MODEL`, `WORKER_MODEL`, `SYNTHESIZER_MODEL` (all default: claude-haiku-4-5-20251001)

### Timeouts (seconds)
- `WORKER_COORDINATION_TIMEOUT` - Parallel execution (default: 45, range: 1-270)
- `SYNTHESIS_TIMEOUT` - Response streaming (default: 30, range: 1-270)

### Circuit Breaker & Retry
- `CIRCUIT_BREAKER_ENABLED` - Enable circuit breaker (default: true)
- `CIRCUIT_BREAKER_FAILURE_THRESHOLD` - Failures before open (default: 3)
- `CIRCUIT_BREAKER_TIMEOUT` - Seconds open (default: 30)
- `CIRCUIT_BREAKER_HALF_OPEN_ATTEMPTS` - Test attempts (default: 1)
- `RETRY_MAX_ATTEMPTS` - Max retries (default: 3)
- `RETRY_EXPONENTIAL_MULTIPLIER` - Backoff multiplier (default: 1.0)
- `RETRY_EXPONENTIAL_MAX` - Max backoff seconds (default: 30)

### Security
- `MAX_REQUEST_BODY_SIZE` - Default 1MB (1048576), range 1KB-10MB, protects POST/PUT/PATCH
- `ENABLE_SECURITY_HEADERS` - Default true (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, HSTS)
- `JWT_ALGORITHM` - Default HS256 (do not change)

### Optional
- `LOKI_URL` - Log aggregation endpoint

## Quick Setup
1. `cp .env.example .env`
2. Add `ANTHROPIC_API_KEY=sk-ant-...`
3. Add `JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")`
4. For development:
   - Create virtual environment: `python -m venv .venv && source .venv/bin/activate`
   - Install dependencies: `pip install -e ".[dev]"` (includes LangChain 1.0.0+ and LangGraph 1.0.0+)
   - Start server: `./scripts/dev.sh`
5. For Docker: `docker-compose up -d`

## Docker Deployment

### Quick Start
```bash
cp .env.example .env  # Configure ANTHROPIC_API_KEY and JWT_SECRET_KEY
docker-compose up -d
curl http://localhost:8000/health/
export API_BEARER_TOKEN=$(docker-compose exec orchestrator-worker python scripts/generate_jwt.py)
python console_client.py "Hello from container!"
docker-compose logs -f
docker-compose down
```

### Build & Runtime
Multi-stage Docker build (builder + production stages, ~500MB final image, 60% size reduction). BuildKit caches efficiently.

```bash
docker build -t orchestrator-worker:latest .
docker-compose build --no-cache orchestrator-worker  # Force rebuild
```

### Docker Commands
```bash
docker-compose up -d            # Start background
docker-compose up               # Start foreground (logs visible)
docker-compose ps               # Check status/health
docker-compose logs -f          # Follow logs
docker-compose down             # Stop
docker-compose down -v          # Stop and remove volumes
docker-compose up -d --build    # Full rebuild
```

### Health Checks
- `GET /health/` - Liveness
- `GET /health/ready` - Readiness

Both return 200 OK when healthy. Docker auto-restarts on failure.

### Development Mode
```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
# Mounts source code, enables hot reload, provides shell access
```

### Container Shell
```bash
docker-compose exec orchestrator-worker bash
docker-compose exec orchestrator-worker python scripts/generate_jwt.py
docker-compose exec orchestrator-worker python -m pytest tests/ -v
```

### Production Deployment
- Use versioned tags: `orchestrator-worker:v0.2.0` (never `latest`)
- Set resource limits in docker-compose.yml: CPU/memory reservations + limits
- Use Docker secrets for production (not .env)
- Place nginx/reverse proxy in front for rate limiting, SSL/TLS
- Use Kubernetes or Docker Swarm for multi-replica deployments
- Configure logging drivers (json-file, splunk, awslogs)
- Monitor: response time, token usage, error rates

### Troubleshooting Docker

**Container won't start:**
- Check logs: `docker-compose logs orchestrator-worker`
- Verify `.env`: ANTHROPIC_API_KEY, JWT_SECRET_KEY (32+ chars), PORT availability

**Health check failing:**
- Verify API key: `grep ANTHROPIC_API_KEY .env`
- Test connectivity: `docker-compose exec orchestrator-worker curl -I https://api.anthropic.com`

**Port 8000 in use:**
- Change in .env: `API_PORT=8001`
- Or kill: `lsof -ti:8000 | xargs kill -9`

**401 Unauthorized on API:**
- Verify JWT_SECRET_KEY is set and consistent
- Regenerate token: `export API_BEARER_TOKEN=$(docker-compose exec orchestrator-worker python scripts/generate_jwt.py)`
- Test: `curl -H "Authorization: Bearer $API_BEARER_TOKEN" http://localhost:8000/v1/models`

## Architecture Overview

### Prompt-Chaining Pattern

#### LangGraph StateGraph Orchestration

The prompt-chaining pattern is orchestrated by LangGraph StateGraph in `src/workflow/chains/graph.py`:

**Graph Builder** (`build_chain_graph(config: ChainConfig)`)
- Location: `src/workflow/chains/graph.py`
- Creates a compiled StateGraph with 4 nodes: analyze, process, synthesize, error
- Graph flow: START → analyze → (validation gate) → process → (validation gate) → synthesize → END
- Error handling: Invalid outputs route to error_step which returns graceful error messages
- Configuration: Takes `ChainConfig` with model selection, token limits, and per-step timeouts
- Returns: Compiled graph ready for async streaming/non-streaming execution

**Execution Modes**:
1. **invoke_chain(graph, initial_state, config)** - Non-streaming execution via `graph.ainvoke()`
   - Returns complete final ChainState after all steps execute
   - Useful for testing, batch processing, or scenarios without client streaming
2. **stream_chain(graph, initial_state, config)** - Streaming execution via `graph.astream()`
   - AsyncIterator interface yields state updates as they arrive
   - Synthesize step yields token-by-token updates during streaming
   - Enables real-time streaming to client via SSE

**Message Conversion** (`src/workflow/utils/message_conversion.py`)
- `convert_openai_to_langchain_messages()`: OpenAI ChatMessage → LangChain BaseMessage (for input)
- `convert_langchain_chunk_to_openai()`: LangChain output → OpenAI ChatCompletionChunk (for output)
- Enables seamless integration between OpenAI-compatible API and LangChain/LangGraph internals

#### Step Functions Implementation

The three step functions in `src/workflow/chains/steps.py` are orchestrated by the LangGraph StateGraph:

**Step 1: Analyze Step** (`analyze_step()`)
- Location: `src/workflow/chains/steps.py`
- Model: Configurable via `ChainConfig.analyze.model` (default: Claude Haiku 4.5)
- Execution: Non-streaming via `ainvoke()` single LLM call
- Input: Latest user message from `ChainState.messages`
- Output: `AnalysisOutput` (intent, key_entities, complexity, context)
- System prompt: `src/workflow/prompts/chain_analyze.md`
- Token tracking: Extracts usage metadata, calculates cost, logs at INFO level
- Validation: `should_proceed_to_process()` gate routes to error if intent empty

**Step 2: Process Step** (`process_step()`)
- Location: `src/workflow/chains/steps.py`
- Model: Configurable via `ChainConfig.process.model` (default: Claude Haiku 4.5)
- Execution: Non-streaming via `ainvoke()` single LLM call
- Input: Analysis from `ChainState.analysis` (wrapped in context prompt)
- Output: `ProcessOutput` (content, confidence, metadata)
- System prompt: `src/workflow/prompts/chain_process.md`
- Token tracking: Extracts usage metadata, logs confidence score and content length
- Validation: `should_proceed_to_synthesize()` gate routes to error if confidence < 0.5

**Step 3: Synthesize Step** (`synthesize_step()`)
- Location: `src/workflow/chains/steps.py`
- Model: Configurable via `ChainConfig.synthesize.model` (default: Claude Haiku 4.5)
- Execution: **Streaming via `astream()`** - token-by-token delivery to client
- Input: Processed content from `ChainState.processed_content` (wrapped in context prompt)
- Output: `SynthesisOutput` (final_text, formatting)
- System prompt: `src/workflow/prompts/chain_synthesize.md`
- Token tracking: Extracts usage from final chunk, logs formatting style
- Streaming: Only this step yields incremental updates; earlier steps run to completion

#### Configuration

Each step is independently configured via `ChainConfig`:

```python
class ChainStepConfig(BaseModel):
    model: str                      # Claude model ID
    max_tokens: int                 # Maximum tokens to generate
    temperature: float              # Sampling temperature (0.0-2.0)
    system_prompt_file: str         # Prompt filename in src/workflow/prompts/

# Per-step timeouts (in seconds, range 1-270):
analyze_timeout: int = 15
process_timeout: int = 30
synthesize_timeout: int = 20
```

**Customization via environment variables** (optional, uses ChainConfig defaults if not set):
- Create custom `ChainConfig` instance in `config.py` for different model/timeout combinations
- Extend model classes in `src/workflow/models/chains.py` for domain-specific outputs

#### System Prompts

Three markdown system prompts control step behavior:

1. **chain_analyze.md** - Analysis step instructions
   - Must output valid JSON matching AnalysisOutput schema
   - Controls intent parsing, entity extraction, complexity assessment
   - Customizable for domain-specific analysis logic

2. **chain_process.md** - Processing step instructions
   - Must output valid JSON matching ProcessOutput schema
   - Controls content generation approach, confidence scoring, metadata capture
   - Customizable for domain-specific generation logic

3. **chain_synthesize.md** - Synthesis step instructions
   - Must output valid JSON matching SynthesisOutput schema
   - Controls formatting, polishing, styling, final validation
   - Customizable for domain-specific formatting logic

**Important**: Each prompt MUST output valid JSON-only (no markdown code blocks or extra text). The step functions parse these JSON responses and validate them against Pydantic models.

#### Step Execution Flow

When triggered by LangGraph StateGraph:

1. **analyze_step()**
   - Loads `chain_analyze.md` system prompt
   - Extracts latest user message from `ChainState.messages`
   - Calls Claude API with system prompt + user message (non-streaming)
   - Parses JSON response into AnalysisOutput
   - Returns state update with analysis, tokens, cost

2. **process_step()**
   - Loads `chain_process.md` system prompt
   - Builds context prompt from analysis (intent, entities, complexity, context)
   - Calls Claude API with system prompt + context (non-streaming)
   - Parses JSON response into ProcessOutput
   - Returns state update with processed content, confidence, tokens, cost

3. **synthesize_step()**
   - Loads `chain_synthesize.md` system prompt
   - Builds context prompt from processed content (content, confidence, metadata)
   - Calls Claude API with system prompt + context (STREAMING)
   - Yields incremental state updates for each chunk
   - Accumulates text, parses final JSON into SynthesisOutput
   - Returns final state update with polished response, formatting, tokens, cost

#### Error Handling

**JSON Parsing**:
- `analyze_step()`: Raises ValidationError on parse failure (logs at ERROR level)
- `process_step()`: Raises ValidationError on parse failure (logs at ERROR level)
- `synthesize_step()`: Falls back to accumulated text on parse failure (logs at WARNING level)

**Markdown Code Blocks**:
- Automatically detects and removes markdown wrappers (```json...```) before parsing
- Handles both quoted and unquoted JSON

**Validation Gates**:
- After analyze: `should_proceed_to_process()` validates intent is non-empty
- After process: `should_proceed_to_synthesize()` validates content and confidence >= 0.5

**Validation Gates** (`src/workflow/chains/validation.py`)
- File: `src/workflow/chains/validation.py`
- Purpose: Enforce schema compliance and business rules between chain steps
- Base class: `ValidationGate` - Pydantic schema validation with extensible design
- Subclasses:
  - `AnalysisValidationGate`: Validates `AnalysisOutput` (intent required and non-empty)
  - `ProcessValidationGate`: Validates `ProcessOutput` (content required, confidence >= 0.5)
- Conditional edge functions:
  - `should_proceed_to_process(state)` - Routes "process" or "error" after analysis
  - `should_proceed_to_synthesize(state)` - Routes "synthesize" or "error" after processing
- Business rules enforced:
  - Analysis: intent must be present and non-empty string
  - Process: content must be non-empty, confidence score >= 0.5 (minimum quality threshold)
- Error handling: Invalid outputs logged at WARNING level, route to error handler
- Transparent type handling: Works with dicts, Pydantic models, and strings
- Enables fast failure on quality issues without cascading bad data through workflow

### Orchestration via LangGraph

**Graph Structure** (`src/workflow/chains/graph.py`):
- `build_chain_graph(config: ChainConfig)` compiles StateGraph with config-driven timeouts
- Nodes: analyze, process, synthesize, error - each with own model and token limits
- Conditional edges: Validation gates route invalid outputs to error handler
- State management: ChainState TypedDict with add_messages reducer maintains message history
- Error step: Captures validation failures, logs warnings, returns user-friendly error messages

**Execution Flow**:
1. START triggers analyze_step (non-streaming, ~1-2s on Haiku)
2. Validation gate checks analysis intent is non-empty
3. process_step generates content (non-streaming, ~2-4s on Haiku)
4. Validation gate checks confidence >= 0.5
5. synthesize_step polishes response (STREAMING, ~1-2s on Haiku)
6. State flows through with add_messages reducer merging all step outputs
7. Both success and error paths terminate at END node

**Streaming Integration**:
- `stream_chain()` uses `graph.astream(stream_mode="messages")` for token-level updates
- Synthesis step's astream() enables incremental token delivery to client
- Earlier steps complete before yielding; synthesis step yields per-token
- FastAPI endpoint converts LangChain chunks to OpenAI SSE format via message_conversion.py

### Performance
- Time complexity: O(N) where N = number of sequential steps (typically 3)
- Cost: O(N) same as sequential processing
- Typical execution: ~4-8 seconds total (1-2s analyze + 2-4s process + 1-2s synthesize)
- Result: Enables complex multi-step reasoning with structured outputs and streaming responses

### Import System
Use relative imports only (required for FastAPI CLI discovery):
- Correct: `from workflow.config import Settings`
- Wrong: `from src.workflow.config import Settings`

### Configuration Architecture
- Settings class in `config.py` uses Pydantic v2 BaseSettings with .env loading
- Computed properties derive values from settings
- Validation enforces type checking and constraints

### Request Size Validation
Middleware validates body size on POST/PUT/PATCH (GET and `/health/*` exempt).
- Default: 1MB
- Response on exceed: HTTP 413 with detail
- Set: `MAX_REQUEST_BODY_SIZE=5242880` for 5MB

### API Structure
- `POST /v1/chat/completions` - Streaming chat (routes to Orchestrator) - Protected
- `GET /v1/models` - List models - Protected
- `GET /health/` - Liveness - Public
- `GET /health/ready` - Readiness - Public

### Authentication (JWT Bearer)
All protected endpoints require: `Authorization: Bearer <token>`

**Token generation:**
```bash
python scripts/generate_jwt.py
python scripts/generate_jwt.py --expires-in 7d
python scripts/generate_jwt.py --subject "my-service" --expires-in 24h
```

**Usage examples:**
```bash
# Bash/curl
TOKEN=$(python scripts/generate_jwt.py)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"orchestrator-worker","messages":[{"role":"user","content":"Hello"}]}' -N

# Python
import os, requests
headers = {"Authorization": f"Bearer {os.getenv('API_BEARER_TOKEN')}", "Content-Type": "application/json"}
response = requests.post("http://localhost:8000/v1/chat/completions", headers=headers, json={...}, stream=True)
```

**Error responses:**
- 401: `{"detail": "Token has expired"}`
- 403: `{"detail": "Invalid authentication credentials"}`

See `JWT_AUTHENTICATION.md` for complete auth documentation.

### Streaming Responses
All responses use Server-Sent Events (SSE):
1. POST to `/v1/chat/completions`
2. Yields `ChatCompletionChunk` objects
3. Formats as SSE: `data: {json}\n\n`
4. Ends with `data: [DONE]\n\n`

### Request Timeout Enforcement
Two-phase timeouts prevent runaway requests:

**Phase 1: Worker Coordination** (default 45s)
- Parallel worker execution via asyncio.gather()
- If exceeded: cancel workers, send error event

**Phase 2: Synthesis** (default 30s)
- Stream final response
- If exceeded: end stream with error event

**Configuration:**
```env
WORKER_COORDINATION_TIMEOUT=45    # 1-270 seconds
SYNTHESIS_TIMEOUT=30              # 1-270 seconds
```

**Adjustment guidelines:**
- Increase for complex tasks, slower models, many workers, high latency regions
- Decrease for strict latency SLAs, cost control, rate-sensitive apps

**Examples:**
```env
# Simple/fast tasks
WORKER_COORDINATION_TIMEOUT=20
SYNTHESIS_TIMEOUT=15

# Complex analysis
WORKER_COORDINATION_TIMEOUT=90
SYNTHESIS_TIMEOUT=45

# Strict latency
WORKER_COORDINATION_TIMEOUT=30
SYNTHESIS_TIMEOUT=20
```

**Timeout error format:**
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

**Troubleshooting timeouts:**
- Check logs: `grep "streaming_timeout_error" logs.json`
- Measure typical times: `python console_client.py "test" 100`
- Increase timeout in .env, restart: `./scripts/dev.sh`

Deprecated `STREAMING_TIMEOUT` still works but phase-specific timeouts override it.

### Circuit Breaker & Retry Logic

Automatic retry with exponential backoff protects against transient Anthropic API failures. Uses tenacity library for reliability.

**Configuration:**
```env
CIRCUIT_BREAKER_ENABLED=true              # Enable/disable circuit breaker
CIRCUIT_BREAKER_FAILURE_THRESHOLD=3       # Failures before circuit opens
CIRCUIT_BREAKER_TIMEOUT=30                # Seconds circuit stays open
CIRCUIT_BREAKER_HALF_OPEN_ATTEMPTS=1      # Attempts in half-open state
RETRY_MAX_ATTEMPTS=3                      # Max retry attempts per request
RETRY_EXPONENTIAL_MULTIPLIER=1.0          # Backoff multiplier
RETRY_EXPONENTIAL_MAX=30                  # Max backoff seconds
```

**Behavior:**
- **Retries on**: Rate limits (429), server errors (5xx), timeouts, connection errors
- **Exponential backoff**: ~1s, ~2s, ~4s... up to 30s max (with jitter)
- **Circuit opens**: After 3 consecutive failures
- **Circuit stays open**: 30 seconds, then transitions to half-open
- **Half-open state**: Allows 1 test request before fully reopening
- **Critical operations**: Fail fast when circuit open (503 response)
- **Non-critical operations**: Fallback gracefully (e.g., token capture skipped)

**Error Responses:**
- `CircuitBreakerOpenError`: HTTP 503 Service Temporarily Unavailable
  - Message: "Service temporarily unavailable - circuit breaker open"
- `RetryError`: HTTP 502 Bad Gateway
  - Message: "Failed after N retry attempts: [last_error]"

**Troubleshooting:**
- **"circuit_breaker_open" in logs**: Service recovering from API failures, wait 30s
- **Persistent failures**: Check API key validity: `grep ANTHROPIC_API_KEY .env`
- **Flaky networks**: Increase `RETRY_MAX_ATTEMPTS=5` for more tolerance
- **Prolonged outages**: Increase `CIRCUIT_BREAKER_TIMEOUT=60` for longer recovery window
- **High failure rates**: Check Anthropic API status: https://status.anthropic.com
- **Cost concerns**: Lower `RETRY_MAX_ATTEMPTS=2` to reduce retry overhead

See `documentation/tenacity/` for detailed retry patterns and integration examples.

### Data Models
**Two layers:**
1. OpenAI-compatible (`models/openai.py`): External API contract
   - `ChatCompletionChunk`, `ChoiceDelta`, `ChatCompletionStreamChoice`
   - `ChatCompletionRequest`, `ChatMessage`
2. Internal (`models/internal.py`): Domain logic
   - `TaskRequest`, `TaskResult`, `AggregatedResult` - **Customize these**

### Agent Base Class
All agents inherit from `Agent` (`agents/base.py`):
- `process(request) -> AsyncIterator[ChatCompletionChunk]` - Main streaming method
- `initialize()` - Resource setup (e.g., AsyncAnthropic client)
- `shutdown()` - Graceful cleanup

### Logging & Observability

Structured JSON logging with five levels for comprehensive observability and debugging.

**Configuration:**
```env
LOG_LEVEL=INFO        # Default: INFO (production)
LOG_LEVEL=DEBUG       # Verbose (development/troubleshooting)
LOG_FORMAT=json       # Default: json (standard format also available)
LOKI_URL=http://...   # Optional: log aggregation
```

**Log Levels - When to Expect Each:**

**CRITICAL/FATAL** - Application cannot start or continue
- Orchestrator initialization failure (API key invalid, connection refused)
- Fatal configuration errors
- Example: `Failed to initialize orchestrator - application cannot start`

**ERROR** - Serious problems, operation failed
- Claude API timeouts or errors
- Worker task failures
- Agent processing errors
- Example: `External service error: Claude API timeout`

**WARNING** - Potentially harmful, operation continues
- Request size exceeded limits
- Rate limit exceeded
- Unknown model pricing requested
- JWT token verification failures
- Example: `Request body size 2MB exceeds limit of 1MB`

**INFO** - Normal operations (default production level)
- Application startup/shutdown
- Request tracking (method, path, status, response time)
- Chat completion requests
- Token usage and cost metrics
- Example: `Chat completion request completed - 3210 tokens, $0.0156 USD`

**DEBUG** - Detailed diagnostics (development only)
- Health check requests
- JWT token verification success
- Security headers applied
- Request size validation passed
- Rate limit checkpoints
- Token cost calculations
- Worker task execution details
- Example: `JWT token verified successfully - subject: user1`

**JSON Structure:**
```json
{
  "timestamp": "2025-11-09 03:00:00,000",
  "level": "INFO",
  "logger": "workflow.api.v1.chat",
  "message": "Chat completion request completed",
  "request_id": "req_1762674924016",
  "user": "test-user",
  "model": "orchestrator-worker",
  "total_tokens": 3210,
  "total_cost_usd": 0.0156,
  "elapsed_seconds": 2.45
}
```

**Standard fields:** timestamp, level, logger, message
**Context fields:** request_id, user/subject, method, path, status_code, response_time
**Cost tracking:** input_tokens, output_tokens, total_tokens, input_cost_usd, output_cost_usd, total_cost_usd
**Rate limiting:** limit, remaining, reset
**Errors:** error, error_type, error_code

**Docker Logs:**
```bash
docker-compose logs -f                     # Follow all logs
docker-compose logs -f orchestrator-worker # Specific service
docker-compose logs --tail 100             # Last 100 lines
docker-compose exec orchestrator-worker env | grep LOG_LEVEL  # Check level
```

**Log Filtering:**
- `LOG_LEVEL=DEBUG`: All logs (verbose, development)
- `LOG_LEVEL=INFO`: Normal ops + warnings + errors (default, production)
- `LOG_LEVEL=WARNING`: Only warnings, errors, critical
- `LOG_LEVEL=ERROR`: Only errors and critical
- `LOG_LEVEL=CRITICAL`: Only critical failures

**Common Patterns to Watch:**
- `streaming_timeout_error` - Increase WORKER_COORDINATION_TIMEOUT or SYNTHESIS_TIMEOUT
- `Request body too large` - Increase MAX_REQUEST_BODY_SIZE or split request
- `Rate limit exceeded` - Adjust RATE_LIMIT_* settings or implement backoff
- `Unknown model pricing` - Add model to token_tracking.py MODEL_PRICING dict
- `JWT token verification failed` - Check JWT_SECRET_KEY consistency

**Performance Metrics:**
All chat completion requests log:
- `elapsed_seconds` - Total request duration
- `total_tokens` - Tokens across all agents
- `total_cost_usd` - USD cost for entire request

Use these for cost monitoring and performance optimization.

### Token Usage & Cost Logging
Comprehensive token tracking for cost monitoring:

**Components:**
- `TokenUsage` model: Input/output/total tokens
- `CostMetrics`: USD cost calculation
- `AggregatedTokenMetrics`: Cross-agent aggregation
- `token_tracking.py` utilities: Cost helpers

**Flow:** Worker tasks → aggregated by Orchestrator → Synthesizer non-streaming call captures final tokens → API logs request completion.

**Model pricing (USD/1M tokens):**
- Haiku: $1 input, $5 output
- Sonnet: $3 input, $15 output

**Cost calculation:**
```python
from workflow.utils.token_tracking import calculate_cost, aggregate_token_metrics

cost = calculate_cost("claude-haiku-4-5-20251001", 500, 200)  # Returns cost object
total_tokens, total_cost = aggregate_token_metrics(usage_list=[...], model_list=[...])
```

**Monitoring:** Check logs for `total_cost_usd` entries. Adjust models/decomposition based on metrics.

### Request ID Propagation

Request IDs are automatically propagated to Anthropic API calls for end-to-end distributed tracing and debugging.

**How it works:**
1. Middleware generates or extracts `X-Request-ID` from request headers
2. Request ID is stored in Python `contextvars` for async context propagation
3. All agents (Orchestrator, Worker, Synthesizer) retrieve request ID and pass it to Anthropic API
4. Anthropic includes X-Request-ID in their API responses for correlation

**Usage:**
Clients can optionally provide custom request ID in headers:
```bash
curl -H "X-Request-ID: my-request-123" http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"orchestrator-worker","messages":[...]}'
```

If not provided, middleware auto-generates: `req_{timestamp_ms}`

**Debugging:**
Search logs for request_id to trace full request lifecycle:
```bash
grep "request_id: my-request-123" logs.json
```

**Response Headers:**
All responses include X-Request-ID:
```
X-Request-ID: my-request-123
```

**Technical Details:**
- Uses Python `contextvars.ContextVar` for thread-safe async context
- Context automatically isolated per request (async-safe)
- Gracefully handles missing request IDs (no errors)
- Works with concurrent requests without interference

### Error Handling
Custom hierarchy in `utils/errors.py`:
- `TemplateServiceError` (base)
- `ConfigurationError`, `ValidationError`, `ExternalServiceError`, `AgentError`, `SessionError`
- FastAPI handlers convert to HTTP responses

### Type Safety
Comprehensive type hints, strict mypy checking in `pyproject.toml`.

## Customization Guide

Template provides infrastructure. Customize for your domain:

### 1. Chain Step Prompts

The three system prompts are the primary customization points. They control how each step processes information and must be tailored for your domain:

**Files to customize:**
- `src/workflow/prompts/chain_analyze.md` - Customize intent parsing and entity extraction for your domain
- `src/workflow/prompts/chain_process.md` - Customize content generation logic based on analysis output
- `src/workflow/prompts/chain_synthesize.md` - Customize formatting and polishing of final response

**How Step Functions Load and Use Prompts:**

The step functions use `load_system_prompt(filename)` helper to read markdown files:

1. `analyze_step()` loads `chain_analyze.md` as system prompt
2. `process_step()` loads `chain_process.md` as system prompt
3. `synthesize_step()` loads `chain_synthesize.md` as system prompt

Each system prompt is sent to Claude with contextual information specific to that step.

**Important Notes on JSON Output:**

Each prompt MUST output valid JSON matching its Pydantic model. The step functions parse these JSON responses and validate them:

1. **chain_analyze.md** must output valid JSON matching `AnalysisOutput`:
   ```json
   {
     "intent": "user's goal",
     "key_entities": ["entity1", "entity2"],
     "complexity": "simple|moderate|complex",
     "context": { "key": "value" }
   }
   ```

2. **chain_process.md** must output valid JSON matching `ProcessOutput`:
   ```json
   {
     "content": "generated content",
     "confidence": 0.85,
     "metadata": { "key": "value" }
   }
   ```

3. **chain_synthesize.md** must output valid JSON matching `SynthesisOutput`:
   ```json
   {
     "final_text": "polished response",
     "formatting": "markdown|plain|html"
   }
   ```

**No markdown code blocks**: Prompts should output JSON directly (no ```json...``` wrappers). The step functions automatically handle markdown wrappers if the LLM adds them.

**When to customize each:**
- `chain_analyze.md`: When you need domain-specific intent parsing, different entity types, or custom complexity assessment
- `chain_process.md`: When you need domain-specific content generation, different output structure, or custom confidence scoring
- `chain_synthesize.md`: When you need domain-specific formatting, styling, or final validation

**Example customization - Marketing domain:**

For a marketing copywriting tool, customize `chain_analyze.md` to extract marketing-specific context:
```markdown
### Extract Marketing Context
- Identify target audience
- Note tone and voice preferences
- Capture brand personality traits
- Extract call-to-action requirements

Output must be valid JSON matching this schema:
{
  "intent": "The marketing goal or target audience request",
  "key_entities": ["audience segment", "brand element", "marketing channel"],
  "complexity": "simple|moderate|complex",
  "context": {
    "tone": "professional|casual|persuasive",
    "brand_fit": "primary|secondary"
  }
}
```

Then customize `chain_process.md` to generate marketing copy:
```markdown
### Generate Marketing Copy
Using the analyzed marketing context:
- Write persuasive copy addressing the identified audience
- Incorporate brand voice and personality
- Include relevant call-to-action
- Score persuasiveness and brand alignment (0.0-1.0)

Output must be valid JSON matching this schema:
{
  "content": "The generated marketing copy",
  "confidence": 0.85,
  "metadata": {
    "generation_approach": "comparative|emotional|benefit-focused",
    "cta_strength": "weak|moderate|strong"
  }
}
```

### 2. Step Function Logic Customization

If you need domain-specific processing beyond prompt customization, modify the step functions in `src/workflow/chains/steps.py`:

**Customize analyze_step():**
- Extract additional fields from analysis output
- Implement custom intent extraction logic
- Add domain-specific complexity assessment
- Enhance entity extraction with domain knowledge

**Customize process_step():**
- Add custom confidence scoring logic
- Implement quality validation before moving to synthesis
- Enhance metadata capture with domain metrics
- Filter or validate generated content

**Customize synthesize_step():**
- Add custom post-processing or formatting rules
- Implement domain-specific styling or templates
- Add content validation or fact-checking
- Enhance or override system prompt behavior

**Example**: Adding domain-specific entity extraction to analyze_step():

```python
async def analyze_step(state: ChainState, config: ChainConfig) -> dict[str, Any]:
    # ... existing code ...

    # Add custom domain logic
    if domain == "legal":
        # Extract legal entities, jurisdictions, case types
        analysis_dict['legal_entities'] = extract_legal_entities(user_message)
        analysis_dict['jurisdiction'] = extract_jurisdiction(user_message)

    # ... rest of function ...
```

### 3. Chain Models

Edit `src/workflow/models/chains.py` to extend output models with domain-specific fields:

**Extend AnalysisOutput:**
```python
class AnalysisOutput(BaseModel):
    intent: str
    key_entities: list[str]
    complexity: str  # "simple", "moderate", or "complex"
    context: dict[str, Any]
    # Add domain-specific fields:
    custom_field: str  # Your custom analysis field
```

**Extend ProcessOutput:**
```python
class ProcessOutput(BaseModel):
    content: str
    confidence: float
    metadata: dict[str, Any]
    # Add domain-specific fields:
    processing_metric: float  # Your custom metric
```

**Extend SynthesisOutput:**
```python
class SynthesisOutput(BaseModel):
    final_text: str
    formatting: str
    # Add domain-specific fields:
    formatting_quality: float  # Your custom quality score
```

**Extend ChainConfig:**
```python
class ChainConfig(BaseModel):
    analyze: ChainStepConfig
    process: ChainStepConfig
    synthesize: ChainStepConfig
    # Add domain-specific configuration:
    domain_parameter: str = "default"
```

### 4. Internal Models

Edit `src/workflow/models/internal.py`:
- Add domain-specific models and validation
- Define custom data structures for your workflow

### 5. Step Function Logic (Advanced)

For complex domain logic beyond prompts, modify step functions in `src/workflow/chains/steps.py`:

**analyze_step()**: Customize intent parsing and complexity assessment
- Extract additional entities specific to your domain
- Implement custom complexity scoring
- Add domain-specific context enrichment

**process_step()**: Customize content generation and confidence scoring
- Add domain-specific quality checks
- Implement custom confidence calculation
- Filter or enhance generated content

**synthesize_step()**: Customize formatting and post-processing
- Apply domain-specific formatting rules
- Add content validation or enrichment
- Implement custom styling logic

### 6. Configuration

Update `.env.example` and `src/workflow/config.py`:
- Configure model IDs for each step (upgrade to Sonnet if needed)
- Adjust token limits and temperature per phase
- Set per-step timeouts (analyze_timeout, process_timeout, synthesize_timeout)
- Add domain-specific settings and parameters

## Development Workflow

### FastAPI CLI - IMPORTANT
Always use `fastapi dev` (not `uvicorn`). Provides auto-reload, better errors, proper module discovery.
- Correct: `fastapi dev src/workflow/main.py`
- Wrong: `uvicorn src.workflow.main:app`

### Testing Strategy
- Unit tests: Components (models, config, utilities)
- Integration tests: API endpoints with mocked dependencies
- Live endpoint tests: Full app with running server
- Target: >80% coverage, use pytest-asyncio

### Interactive API Testing
FastAPI auto-generates docs at `/docs`:
1. Start: `./scripts/dev.sh`
2. Navigate: http://localhost:8000/docs
3. Test endpoints directly

Use for: sanity checks, edge cases, API demos, regression testing.

### Development Workflow
1. Update `src/workflow/` files
2. Add/update tests in `tests/`
3. `./scripts/test.sh` and `./scripts/format.sh`
4. Verify: `./scripts/dev.sh` and test endpoints
5. Commit with descriptive message

## Common Issues

### Import Errors
`ModuleNotFoundError: No module named 'src'`
- Check imports use `workflow.*` not `src.workflow.*`
- Install: `pip install -e ".[dev]"`

### FastAPI Discovery
`fastapi dev` can't find app:
- Ensure full path: `fastapi dev src/workflow/main.py`
- Verify `app = create_app()` at module level
- Activate virtual environment

### Authentication
**Missing JWT_SECRET_KEY:**
Add to `.env`: `JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")`

**401/403 on protected endpoints:**
- Set token: `export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)`
- Verify header: `Authorization: Bearer <token>`
- Check JWT_SECRET_KEY matches between server and client
- For console_client: verify `API_BEARER_TOKEN` env var exported

**API_BEARER_TOKEN not set:**
```bash
export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)
```

See `JWT_AUTHENTICATION.md` for complete troubleshooting.

### Rate Limiting

Slowapi-based rate limiting protects API endpoints from abuse. Per-user limits via JWT subject; IP fallback for unauthenticated requests.

**Configuration:**
```env
RATE_LIMIT_ENABLED=true                           # Enable/disable rate limiting
RATE_LIMIT_DEFAULT=100/hour                       # Default for unlisted endpoints
RATE_LIMIT_CHAT_COMPLETIONS=10/minute             # Chat completions endpoint
RATE_LIMIT_MODELS=60/minute                       # Models listing endpoint
```

**Rate Limit Behavior:**
- **Authenticated**: Limited by JWT `sub` claim (per-user quota)
- **Unauthenticated**: Limited by IP address
- Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` included in all responses
- Exceeded limit: HTTP 429 with `{"detail": "X per Y minute/hour"}` and `Retry-After` header

**Testing Rate Limits:**
```bash
TOKEN=$(python scripts/generate_jwt.py --subject "user-1")
# Make requests - 61st to /v1/models returns 429
for i in {1..61}; do
  curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/models
done
```

**Troubleshooting:**
- **429 on first request**: Check RATE_LIMIT_ENABLED=true in .env
- **Different users hit same limit**: Verify JWT_SECRET_KEY is set and consistent
- **Unauthenticated requests not limited**: Confirm RATE_LIMIT_ENABLED=true and check logs

### Streaming Issues
- Verify AsyncAnthropic initialized (check logs)
- Validate ANTHROPIC_API_KEY in .env
- Ensure bearer token set
- Test with curl: `curl -N -H "Authorization: Bearer $TOKEN" http://localhost:8000/...`
- Review server logs

### Validation Gates

Validation gates enforce data quality between prompt-chaining steps. They validate step outputs and route to error handler if validation fails.

**Configuration:**
```env
# Validation gates are enabled by default
# In ChainConfig (src/workflow/models/chains.py):
# enable_validation=True        # Enable/disable all validation gates
# strict_validation=False       # True: fail fast, False: warn and continue
```

**When Validation Occurs:**
- **After Analysis Step**: `AnalysisValidationGate` validates `AnalysisOutput`
- **After Processing Step**: `ProcessValidationGate` validates `ProcessOutput`

**Business Rules:**
- **Analysis**: `intent` field must be present and non-empty (whitespace is stripped)
- **Processing**: `content` must be non-empty, `confidence` must be >= 0.5 (minimum quality threshold)

**Common Validation Failures & Solutions:**

**Empty Intent Error**
- Symptom: Log shows "Analysis validation failed: 'intent' field is required and must be non-empty"
- Cause: Analysis step produced empty intent extraction
- Solution: Review `chain_analyze.md` prompt, ensure it extracts clear user intent from requests
- Check: Run analysis step in isolation to test prompt quality

**Low Confidence Error**
- Symptom: Log shows "Processing validation failed: 'confidence' must be >= 0.5"
- Cause: Processing step returned low confidence (< 0.5) in generated content
- Solution:
  - Adjust `chain_process.md` prompt to produce higher-quality content
  - Review analysis output to ensure sufficient context is provided
  - Check if task is too complex for Haiku model (upgrade to Sonnet)

**Empty Content Error**
- Symptom: Log shows "Processing validation failed: 'content' field is required and must be non-empty"
- Cause: Processing step failed to generate content
- Solution:
  - Verify analysis step extracted clear intent
  - Check `chain_process.md` prompt is well-formed
  - Ensure sufficient tokens allocated (check `process_max_tokens` in config)

**Validation Disabled Debugging**
- Temporarily disable validation for debugging: Set `enable_validation=False` in `ChainConfig`
- This allows bad data to flow through for investigating downstream issues
- Always re-enable in production

**Viewing Validation Logs**
```bash
# Check validation errors in logs
LOG_LEVEL=DEBUG ./scripts/dev.sh
grep -i "validation" logs.json

# Filter to validation failures only
grep "validation failed" logs.json
```

**Adjusting Thresholds:**
- Confidence threshold is hardcoded at 0.5 in `ProcessValidationGate.validate()`
- To change: Edit `confidence < 0.5` check in `src/workflow/chains/validation.py`
- Consider impact: Lower threshold accepts lower-quality outputs; higher threshold may reject valid results

### Request Too Large (413)
**Symptoms:** HTTP 413 on POST requests, "Request body too large" error

**Common causes:** Long conversation histories, large prompts, batch requests, embedded data, default 1MB limit too small

**Check size:**
```bash
TOKEN=$(python scripts/generate_jwt.py)
curl -w "Request size: %{size_request} bytes\n" -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"orchestrator-worker","messages":[{"role":"user","content":"test"}]}' --output /dev/null
```

**Solutions:**
1. Increase limit in .env: `MAX_REQUEST_BODY_SIZE=5242880` (5MB), restart: `./scripts/dev.sh`
2. Split large requests into multiple API calls
3. Optimize: trim whitespace, remove verbose examples, use conversation summary, compress data

**Configuration examples:**
```env
MAX_REQUEST_BODY_SIZE=1048576      # 1MB (default)
MAX_REQUEST_BODY_SIZE=5242880      # 5MB
MAX_REQUEST_BODY_SIZE=10485760     # 10MB (max)
```

Note: Max 10MB limit for security. Break larger requests at app level.