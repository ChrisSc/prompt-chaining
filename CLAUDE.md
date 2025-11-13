# CLAUDE.md

Guidance for Claude Code when working with the prompt-chaining orchestration template.

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

## API Quick Reference

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| POST | `/v1/chat/completions` | Required | Streaming chat (SSE) |
| GET | `/v1/models` | Required | List available models |
| GET | `/health/` | None | Liveness check |
| GET | `/health/ready` | None | Readiness check |

Streaming responses format: `data: {ChatCompletionChunk}\n\n`, ending with `data: [DONE]\n\n`.

## Authentication

Generate token: `python scripts/generate_jwt.py [--expires-in 7d] [--subject my-service]`

Usage: `Authorization: Bearer <token>` header on all protected endpoints.

For JWT details, error responses, and advanced configuration, see **JWT_AUTHENTICATION.md**.

## Data Models

**Two layers:**
1. OpenAI-compatible (`models/openai.py`): External API contract
2. Internal (`models/internal.py`): Domain logic—customize these:
   - `AnalysisOutput` - Intent, entities, complexity
   - `ProcessOutput` - Generated content, confidence
   - `SynthesisOutput` - Formatted response
   - `ChainConfig` - Domain-specific parameters

## Customization (Agent Focus)

### 1. System Prompts
Edit `src/workflow/prompts/chain_*.md` files. Each must output valid JSON matching its Pydantic model (no markdown wrappers).

### 2. Data Models
Extend in `src/workflow/models/chains.py`:
- Add domain-specific fields to AnalysisOutput, ProcessOutput, SynthesisOutput
- Add domain parameters to ChainConfig

### 3. Configuration
Update `.env.example` and `src/workflow/config.py`:
- Per-step models (upgrade to Sonnet for complex reasoning)
- Token limits, temperature, timeouts
- Domain-specific settings

For advanced customization, see **ARCHITECTURE.md "Customization"**.

## Development Essentials

### FastAPI CLI (IMPORTANT)
Always use `fastapi dev` (not `uvicorn`):
```bash
fastapi dev src/workflow/main.py                    # Correct: auto-reload, better errors
# Wrong: uvicorn src.workflow.main:app
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

## Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'src'` | Use `workflow.*` imports, run `pip install -e ".[dev]"` |
| `fastapi dev` can't find app | Use full path: `fastapi dev src/workflow/main.py`, verify `app = create_app()` at module level |
| 401/403 on protected endpoints | Generate token: `export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)`, verify `Authorization: Bearer <token>` header |
| Empty intent / Low confidence | Review `chain_analyze.md` / `chain_process.md` prompts, upgrade to Sonnet if needed |
| HTTP 413 (request too large) | Increase `MAX_REQUEST_BODY_SIZE` in .env (max 10MB), restart server |

For validation gate debugging, see **ARCHITECTURE.md "Validation Gates"**.

## Additional Resources

- **ARCHITECTURE.md** - Graph structure, timeout behavior, circuit breaker, logging architecture, request ID propagation
- **PROMPT-CHAINING.md** - Configuration tuning (temperature, token limits, cost optimization), validation gate configuration
- **JWT_AUTHENTICATION.md** - Token generation, error responses, advanced auth configuration
- **BENCHMARKS.md** - Performance data, model selection guidance
- **README.md** - Docker deployment, usage examples
