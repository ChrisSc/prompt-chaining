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

Logging and observability patterns are fully documented in `src/workflow/utils/CLAUDE.md`. Configure via environment variables:

```bash
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT=json             # json or standard
```

**Key patterns** (see `src/workflow/utils/CLAUDE.md` for complete reference):
- Structured JSON logging with automatic request_id and user_id injection via contextvars
- Log levels: CRITICAL (system failures), ERROR (request failures), WARNING (degradation), INFO (milestones), DEBUG (diagnostics)
- Token tracking across all steps with cost calculation (Haiku $1/$5, Sonnet $3/$15 per 1M tokens)
- Circuit breaker startup logs with state dump
- Rate limiter health status at startup

For cost tracking: `grep "total_cost_usd" logs.json | jq '.total_cost_usd' | sort -n`

For performance analysis and benchmarking, see **BENCHMARKS.md**.

## Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'src'` | Use `workflow.*` imports, run `pip install -e ".[dev]"` |
| `fastapi dev` can't find app | Use full path: `fastapi dev src/workflow/main.py`, verify `app = create_app()` at module level |
| 401/403 on protected endpoints | Generate token: `export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)`, verify `Authorization: Bearer <token>` header |
| Empty intent / Low confidence | Review `chain_analyze.md` / `chain_process.md` prompts, upgrade to Sonnet if needed |
| HTTP 413 (request too large) | Increase `MAX_REQUEST_BODY_SIZE` in .env (max 10MB), restart server |
| `request_id` or `user_id` missing from logs | Middleware sets `request_id` automatically; `user_id` only after JWT auth |


## Additional Resources

- **ARCHITECTURE.md** - Graph structure, timeout behavior, circuit breaker, logging architecture
- **PROMPT-CHAINING.md** - Configuration tuning, validation gate configuration, performance guidance
- **JWT_AUTHENTICATION.md** - Token generation, error responses, advanced auth configuration
- **BENCHMARKS.md** - Performance data, model selection guidance
- **README.md** - Docker deployment, usage examples
