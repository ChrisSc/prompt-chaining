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
- `ORCHESTRATOR_MODEL`, `WORKER_MODEL`, `SYNTHESIZER_MODEL` (deprecated - use CHAIN_* variables instead)

### Prompt-Chaining Configuration

**Per-Step Model Selection**:
- `CHAIN_ANALYZE_MODEL` - Model for analysis step (default: claude-haiku-4-5-20251001)
- `CHAIN_PROCESS_MODEL` - Model for processing step (default: claude-haiku-4-5-20251001)
- `CHAIN_SYNTHESIZE_MODEL` - Model for synthesis step (default: claude-haiku-4-5-20251001)

**Per-Step Token Limits**:
- `CHAIN_ANALYZE_MAX_TOKENS` - Max tokens for analyze step (default: 2048, range: 1-8000)
- `CHAIN_PROCESS_MAX_TOKENS` - Max tokens for process step (default: 2048, range: 1-8000)
- `CHAIN_SYNTHESIZE_MAX_TOKENS` - Max tokens for synthesize step (default: 2048, range: 1-8000)

**Per-Step Temperature**:
- `CHAIN_ANALYZE_TEMPERATURE` - Temperature for analyze (default: 0.5, range: 0.0-2.0)
- `CHAIN_PROCESS_TEMPERATURE` - Temperature for process (default: 0.7, range: 0.0-2.0)
- `CHAIN_SYNTHESIZE_TEMPERATURE` - Temperature for synthesize (default: 0.5, range: 0.0-2.0)

**Per-Step Timeouts**:
- `CHAIN_ANALYZE_TIMEOUT` - Analysis step timeout in seconds (default: 15, range: 1-270)
- `CHAIN_PROCESS_TIMEOUT` - Processing step timeout in seconds (default: 30, range: 1-270)
- `CHAIN_SYNTHESIZE_TIMEOUT` - Synthesis step timeout in seconds (default: 20, range: 1-270)

**Validation Gates**:
- `CHAIN_ENABLE_VALIDATION` - Enable validation gates between steps (default: true)
- `CHAIN_STRICT_VALIDATION` - Fail fast on validation errors (default: false)

### Chain Configuration Reference

Each step in the prompt-chaining workflow can be independently tuned for your specific use case.

#### Step Models

**Analyze Step** (Intent Extraction)
- Purpose: Parse user intent, extract entities, assess complexity
- Typical model: Claude Haiku (fast, cost-efficient)
- Use Sonnet if: Analysis requires complex reasoning or domain expertise
- Upgrade rationale: Complex intent parsing with ambiguous user requests

**Process Step** (Content Generation)
- Purpose: Generate substantive content based on analysis
- Typical model: Claude Haiku (fast, cost-efficient) or Claude Sonnet (higher quality)
- Use Sonnet if: Quality/accuracy critical, content needs advanced reasoning
- Upgrade rationale: High stakes content generation where quality directly impacts user experience

**Synthesize Step** (Formatting & Polish)
- Purpose: Format and polish final response for presentation
- Typical model: Claude Haiku (fast, cost-efficient)
- Use Sonnet if: Complex formatting or styling requirements
- Upgrade rationale: Rare; formatting usually doesn't need advanced reasoning

#### Temperature Tuning Guide

**Analyze Step** (default: 0.5)
- 0.0-0.3: Deterministic, consistent intent extraction (best for consistency)
- 0.5: Balanced (default, good starting point)
- 0.7-1.0: More creative entity interpretation (use if results too rigid)

**Process Step** (default: 0.7)
- 0.5: More focused, deterministic content (use for factual accuracy needs)
- 0.7: Balanced, good for most use cases (default)
- 0.9-1.0: More diverse, creative responses (use when variety desired)
- 1.5-2.0: Highly creative/experimental (rarely used, can be incoherent)

**Synthesize Step** (default: 0.5)
- 0.3-0.5: Consistent, predictable formatting (best for structured output)
- 0.5-0.7: Balanced formatting with some variation
- Higher: Variable formatting (rarely needed for polish step)

#### Token Limits

**Analyze Step** (default: 2048)
- Typical need: 500-1000 tokens (intent extraction is concise)
- Increase to 2048 if: Complex intent parsing needs more tokens
- Decrease to 1000 if: Simple intent extraction with tight budgets

**Process Step** (default: 2048)
- Typical need: 1000-3000 tokens (content generation needs space)
- Increase to 4000+ if: Generating long-form content
- Decrease to 1000 if: Brief responses only

**Synthesize Step** (default: 2048)
- Typical need: 500-1500 tokens (formatting is relatively concise)
- Increase to 2048+ if: Complex formatting or styling
- Decrease to 1000 if: Simple formatting only

#### Timeout Configuration

**Analyze Step** (default: 15 seconds)
- 10s: Very fast (tight latency SLAs, simple intent)
- 15s: Balanced (default, most use cases)
- 30s: Slow models or complex analysis
- When to adjust:
  - Decrease if: p99 latency critical, intent extraction quick
  - Increase if: Using Sonnet or complex analysis

**Process Step** (default: 30 seconds)
- 15s: Fast models, simple generation
- 30s: Balanced (default, most use cases)
- 60s: Sonnet or long-form content
- When to adjust:
  - Decrease if: Latency-critical, using Haiku
  - Increase if: Using Sonnet or generating 2000+ token responses

**Synthesize Step** (default: 20 seconds)
- 10s: Very fast (tight latency SLAs)
- 20s: Balanced (default)
- 30s: Complex formatting or slower models
- When to adjust:
  - Decrease if: Streaming responsiveness critical
  - Increase if: Complex formatting or large outputs

**Typical Execution Times** (on Haiku models):
- Analyze: 1-2 seconds
- Process: 2-4 seconds
- Synthesize: 1-2 seconds
- Total: 4-8 seconds plus network latency

#### Cost Optimization Tips

**Cost Breakdown by Model**:
- Haiku: $1 per 1M input tokens, $5 per 1M output tokens
- Sonnet: $3 per 1M input tokens, $15 per 1M output tokens

**Example Cost Calculations** (per request):
```
All-Haiku Config (typical):
  Analyze:   250 input + 150 output  = $0.00125
  Process:   400 input + 400 output  = $0.00300
  Synthesize: 500 input + 400 output = $0.00350
  Total: ~$0.00775 per request

Haiku + Sonnet + Haiku (balanced):
  Analyze:    250 input + 150 output (Haiku) = $0.00125
  Process:    400 input + 400 output (Sonnet) = $0.00240
  Synthesize: 500 input + 400 output (Haiku) = $0.00350
  Total: ~$0.00715 per request (slightly cheaper due to Process optimization)

All-Sonnet Config (rarely needed):
  Analyze:    250 input + 150 output = $0.00120
  Process:    400 input + 400 output = $0.00240
  Synthesize: 500 input + 400 output = $0.00270
  Total: ~$0.00630 per request (cheaper due to Sonnet pricing on higher token counts)
```

**Cost Optimization Strategies**:
1. Start with all-Haiku config (cheapest, fastest)
2. If quality issues, upgrade Process step to Sonnet
3. Only upgrade Analyze/Synthesize if needed for specific domain
4. Reduce token limits if responses consistently under limits
5. Adjust temperature to find optimal quality/cost tradeoff

**Monitoring Costs**:
- Check logs for `total_cost_usd` entries: `grep "total_cost_usd" logs.json`
- Cost is calculated per request and logged at INFO level
- Adjust models/tokens based on actual cost metrics

#### Validation Gates Configuration

**Enable/Disable Validation**:
```env
CHAIN_ENABLE_VALIDATION=true   # Enable quality gates
CHAIN_STRICT_VALIDATION=false  # Warn on errors (vs. fail)
```

**What Gets Validated**:
- After Analyze: Intent must be present and non-empty
- After Process: Content non-empty AND confidence >= 0.5

**Strict Mode** (`CHAIN_STRICT_VALIDATION=true`):
- Fails immediately on validation error
- Returns error to client
- Use for: Strict quality requirements

**Lenient Mode** (`CHAIN_STRICT_VALIDATION=false`):
- Logs warning, continues processing
- Attempts to handle gracefully
- Use for: Fault-tolerant systems

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
cp .env.example .env
docker-compose up -d
curl http://localhost:8000/health/
export API_BEARER_TOKEN=$(docker-compose exec orchestrator-worker python scripts/generate_jwt.py)
python console_client.py "Hello from container!"
docker-compose down
```

For detailed Docker guidance, see README.md "Quick Start with Docker" section.

## Architecture Overview

### Prompt-Chaining Pattern with LangGraph

The prompt-chaining pattern uses **LangGraph StateGraph** to orchestrate three sequential steps:

**Graph Components** (`src/workflow/chains/graph.py`):
- Nodes: analyze, process, synthesize, error
- Flow: START → analyze → (validation gate) → process → (validation gate) → synthesize → END
- Execution modes: `invoke_chain()` (non-streaming) and `stream_chain()` (streaming via SSE)

**Three-Step Processing**:
1. **Analyze**: Extract intent, entities, complexity from user request
2. **Process**: Generate content based on analysis with confidence scoring
3. **Synthesize**: Polish and format response (streaming step)

**Validation Gates** enforce data quality:
- After analyze: Intent must be non-empty
- After process: Content must be non-empty AND confidence >= 0.5

**Key Features**:
- Each step independently configured (model, tokens, temperature, timeout)
- Structured outputs via Pydantic models (AnalysisOutput, ProcessOutput, SynthesisOutput)
- System prompts customizable in `src/workflow/prompts/chain_*.md`
- Token tracking per step with cost aggregation
- Message accumulation via `add_messages` reducer maintains state

See ARCHITECTURE.md for detailed graph structure, node definitions, conditional edges, and execution flow examples.

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

Per-step timeouts prevent runaway requests:
```env
CHAIN_ANALYZE_TIMEOUT=15      # Analysis step (1-270 seconds)
CHAIN_PROCESS_TIMEOUT=30      # Processing step (1-270 seconds)
CHAIN_SYNTHESIZE_TIMEOUT=20   # Synthesis step (1-270 seconds)
```

Typical execution: ~4-8s total. Increase for complex tasks or slower models, decrease for strict latency SLAs.

See ARCHITECTURE.md "Timeout Configuration" section for detailed timeout behavior and error handling.

### Circuit Breaker & Retry Logic

Automatic retry with exponential backoff protects against transient API failures:
```env
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=3
RETRY_MAX_ATTEMPTS=3
```

**Behavior**: Retries on 429, 5xx, timeouts, connection errors. Exponential backoff ~1s, ~2s, ~4s... up to 30s. Circuit opens after 3 failures for 30s.

See ARCHITECTURE.md "Circuit Breaker Pattern" section for state machine details and production recommendations.

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

**Configuration:**
```env
LOG_LEVEL=INFO        # Default: INFO (production)
LOG_FORMAT=json       # Structured JSON logging
LOKI_URL=http://...   # Optional: log aggregation
```

**Log Levels**: CRITICAL (startup failures) → ERROR (operation failed) → WARNING (potential issues) → INFO (normal ops, default) → DEBUG (detailed diagnostics, development only)

**Key Fields**: timestamp, level, logger, message, request_id, total_tokens, total_cost_usd, elapsed_seconds

See ARCHITECTURE.md "Logging Architecture" section for complete log level descriptions, JSON structure, monitoring queries, and filtering examples.

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

### 1. Chain Step Prompts

Primary customization points in `src/workflow/prompts/`:
- `chain_analyze.md` - Customize intent parsing and entity extraction
- `chain_process.md` - Customize content generation approach
- `chain_synthesize.md` - Customize formatting and polishing

**Important**: Each prompt MUST output valid JSON matching its Pydantic model (AnalysisOutput, ProcessOutput, SynthesisOutput). No markdown wrappers needed.

### 2. Chain Models

Edit `src/workflow/models/chains.py` to extend domain-specific fields:
- `AnalysisOutput` - Add domain analysis fields
- `ProcessOutput` - Add domain generation fields
- `SynthesisOutput` - Add domain formatting fields
- `ChainConfig` - Add domain parameters

### 3. Configuration

Update `.env.example` and `src/workflow/config.py`:
- Per-step model IDs (upgrade to Sonnet if complex reasoning needed)
- Token limits and temperature per phase
- Per-step timeouts (analyze_timeout, process_timeout, synthesize_timeout)
- Domain-specific settings

See ARCHITECTURE.md "Customization" section for detailed examples and step function logic customization patterns.

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
- Use full path: `fastapi dev src/workflow/main.py`
- Verify `app = create_app()` at module level

### Authentication
**401/403 on protected endpoints:**
- Generate token: `export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)`
- Verify header: `Authorization: Bearer <token>`
- Check JWT_SECRET_KEY matches and is 32+ chars

### Validation Gates
Common validation failures:
- **Empty Intent**: Review `chain_analyze.md` prompt
- **Low Confidence**: Adjust `chain_process.md` or upgrade to Sonnet
- **Empty Content**: Verify analysis extracted clear intent, check tokens allocated

See ARCHITECTURE.md "Validation Gates" section for detailed failure scenarios, debugging, and threshold adjustment.

### Request Too Large (413)
**Solution**: Increase `MAX_REQUEST_BODY_SIZE` in .env (default 1MB, max 10MB), restart server, or split request

See CLAUDE.md "Request Size Validation" (above) for configuration and optimization tips.