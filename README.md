# Prompt-Chaining Workflow Template

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Built with Haiku 4.5](https://img.shields.io/badge/Built%20with-Haiku%204.5-ED8002)
![Anthropic](https://img.shields.io/badge/Anthropic-Claude-ED8002?logo=anthropic)
![LangChain](https://img.shields.io/badge/LangChain-1.0.0+-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-1.0.0+-blue)
![OpenAI API](https://img.shields.io/badge/OpenAI-API-412991?logo=openai)
![GitHub Template](https://img.shields.io/badge/GitHub-Template-blue?logo=github)

A *github repository template* for scaffolding **turnkey prompt-chaining workflows** with Anthropic's Claude and OpenAI-compatible APIs. Built on the proven prompt-chaining pattern: sequential steps (Analysis, Processing, Synthesis) orchestrated by LangGraph StateGraph with validation gates between steps.

**Observability-first architecture**: Unlike traditional agentic frameworks where observability is retrofitted, this template treats observability as a foundational design principle. Every request gets automatic distributed tracing via context propagation, every LLM call logs token usage and cost attribution, and every agent step tracks quality metrics—with zero manual instrumentation. Context variables (`request_id`, `user_id`) flow automatically from middleware → workflow state → external API calls → structured logs, enabling complete request reconstruction and multi-tenant debugging without boilerplate. Validation gates enforce quality boundaries between agents with full visibility into why workflows succeed or fail.

![Prompt Chaining Pattern](prompt-chaining.png "Prompt Chaining Pattern")

## Key Components
- **Analysis Agent:** Parses user intent, extracts entities, assesses complexity. Returns `AnalysisOutput`.
- **Processing Agent:** Generates content based on analysis with confidence scoring. Returns `ProcessOutput`.
- **Synthesis Agent:** Polishes and formats response (streaming). Returns `SynthesisOutput`.
- **LangGraph StateGraph:** Orchestrates sequential steps with message accumulation and validation gates.

## Overview & Features

This template provides a complete foundation for prompt-chaining workflows:

**Core**:
- Sequential Analysis → Processing → Synthesis steps
- LangGraph StateGraph orchestration with validation gates
- Streaming responses via Server-Sent Events (SSE)
- OpenAI-compatible API interface
- Type-safe structured outputs

**Configuration**:
- Per-step model selection (Haiku vs. Sonnet)
- Independent token limits, temperature, timeouts per step
- Validation gates for data quality enforcement
- Flexible configuration via environment variables

**Observability & Production Features**:
- **Zero-boilerplate distributed tracing**: Auto-propagating `request_id` and `user_id` via context variables
- **Automatic cost attribution**: Every LLM call logs tokens and USD cost per user/request
- **State evolution visibility**: Each workflow step logs metrics (elapsed time, confidence, token usage)
- **Startup component dumps**: Circuit breaker and rate limiter state logged on initialization
- **Quality enforcement**: Validation gates with full logging of why workflows pass/fail
- **Multi-tenant debugging**: Filter all logs by user_id without manual instrumentation
- **Circuit breaker with retry logic**: Automatic resilience with observable state transitions
- **Structured JSON logging**: turnkey logs compatible with Loki, Elasticsearch, CloudWatch
- **Security**: JWT auth, security headers, request size validation, timeout enforcement
- **Rate limiting**: JWT + IP-based keys with observable limits via response headers

**Development**:
- Full type hints and Pydantic v2 validation
- >80% test coverage
- Benchmark script for performance comparison
- Hot reload development server
- Interactive API documentation

## Quick Start

### Setup (3 minutes)

```bash
# 1. Clone and configure
git clone <repo-url>
cd prompt-chaining
cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY and JWT_SECRET_KEY (generate: python -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. Choose your path:
# DOCKER (recommended):
docker build --no-cache -t prompt-chaining:latest .
docker-compose up -d
curl http://localhost:8000/health/

# OR MANUAL:
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pip install "fastapi[standard]" # Installs FastAPI cli
./scripts/dev.sh

# 3. Test the API
export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)
python console_client.py "Hello, world!"
```

**Docker**: Isolated environment, reproducible builds, turnkey
**Manual**: Development-focused, hot reload, interactive /docs

See [CLAUDE.md](./CLAUDE.md#quick-setup) for detailed setup and Docker guidance.

## Authentication

JWT bearer token authentication on protected endpoints (`/v1/chat/completions`, `/v1/models`).

```bash
# Generate token (configured in .env via JWT_SECRET_KEY)
python scripts/generate_jwt.py
python scripts/generate_jwt.py --expires-in 7d

# Use token
export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)
curl -H "Authorization: Bearer $API_BEARER_TOKEN" http://localhost:8000/v1/models
python console_client.py "Your prompt"
```

Public endpoints: `/health/`, `/health/ready` (no authentication required)

## Understanding Prompt-Chaining

Three-step pattern orchestrated by LangGraph StateGraph:

1. **Analyze**: Extract intent, entities, complexity → `AnalysisOutput`
2. **Process**: Generate content with confidence score → `ProcessOutput`
3. **Synthesize**: Polish, format, stream response → `SynthesisOutput` (streamed)

**Validation Gates**: After each step, quality gates enforce:
- After Analyze: Intent must be non-empty
- After Process: Content non-empty AND confidence >= 0.5
- Invalid outputs route to error handler

**Why This Pattern**:
- Structured reasoning for complex multi-step tasks
- Quality control between steps prevents bad data cascading
- Each step independently configurable (model, tokens, temperature, timeout)
- Cost-optimized: Haiku for most steps, upgrade to Sonnet if needed
- Real-time responsiveness: Synthesis step streams token-by-token

**Configuration**: See [PROMPT-CHAINING.md](./PROMPT-CHAINING.md) for detailed configuration guide and recipes.

**System Prompts**: Customize in `src/workflow/prompts/chain_*.md`

For technical deep dive: see [ARCHITECTURE.md](./ARCHITECTURE.md)

## Architecture

LangGraph StateGraph orchestrates three sequential steps with validation gates and message accumulation:

**Node Structure**:
- START → analyze (intent extraction) → process (content gen) → synthesize (streaming) → END
- Validation gates route invalid outputs to error handler
- Each step is independently configurable (model, tokens, temperature, timeout)

**Key Features**:
- **Structured Outputs**: Type-safe Pydantic models (AnalysisOutput, ProcessOutput, SynthesisOutput)
- **State Management**: ChainState TypedDict with `add_messages` reducer maintains conversation context
- **Streaming**: Only synthesis step streams; earlier steps run to completion
- **Token Tracking**: Per-step usage logged with USD cost calculation
- **Error Handling**: Validation failures route gracefully to error handler

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed state flow, conditional edge logic, and token aggregation examples.

## Use Cases

**Ideal For**:
- Document analysis and summarization
- Content generation (blogs, documentation, marketing)
- Data extraction and validation
- Decision support and comparative analysis
- Code review and refactoring guidance
- Any task requiring sequential analysis → generation → formatting

**Pattern Characteristics**:
- Sequential steps (step N depends on step N-1)
- Structured outputs needed
- Steps have different concerns
- Quality and observability matter
- Per-step optimization valuable

**Not Ideal For**:
- Parallel independent tasks (consider alternative orchestration patterns)
- Simple single-turn requests
- Real-time bidirectional conversations

## Deployment Options

| Method | Best For | Setup Time |
|--------|----------|-----------|
| **Docker** | Production, consistent environments | 2 min |
| **Manual** | Development, learning | 5 min |
| **Kubernetes** | Large-scale, auto-scaling | Container foundation + manifests |

See [CLAUDE.md](./CLAUDE.md#deployment-options) for comprehensive deployment guidance.

## Configuration

**Quick Start**: Copy `.env.example` to `.env` and add:
```env
ANTHROPIC_API_KEY=sk-ant-...
JWT_SECRET_KEY=<32-char-random-string>
```

**Per-Step Tuning**: Each step can independently configure:
- `CHAIN_ANALYZE_MODEL`, `CHAIN_PROCESS_MODEL`, `CHAIN_SYNTHESIZE_MODEL` (default: Haiku)
- `CHAIN_*_MAX_TOKENS` (default: 1000-2000)
- `CHAIN_*_TEMPERATURE` (default: 0.3-0.7)
- `CHAIN_*_TIMEOUT` (default: 15-30 seconds)

**Configuration Patterns**:
- **Cost-Optimized**: All-Haiku (~$0.006/req, 4-8s)
- **Balanced**: Haiku + Sonnet process + Haiku (~$0.011/req, 5-10s)
- **Accuracy-Optimized**: All-Sonnet (~$0.018/req, 8-15s)

See [PROMPT-CHAINING.md](./PROMPT-CHAINING.md) for detailed configuration guide, temperature tuning, token limits, timeout adjustment, and decision tree.

See [CLAUDE.md](./CLAUDE.md#chain-configuration-reference) for complete environment variable reference.

## Customization

Generic template for your domain. To customize:

1. **System Prompts** (`src/workflow/prompts/chain_*.md`): Edit to customize analysis, generation, and formatting logic
2. **Data Models** (`src/workflow/models/chains.py`): Extend AnalysisOutput, ProcessOutput, SynthesisOutput with domain fields
3. **Configuration** (`.env`): Adjust per-step models, tokens, temperature, timeouts
4. **Validation** (`src/workflow/chains/validation.py`): Add domain-specific validation rules

See [CLAUDE.md](./CLAUDE.md#customization-guide) for detailed customization guidance.

## Project Structure

```
src/workflow/
├── chains/
│   ├── graph.py      # LangGraph StateGraph orchestration
│   ├── steps.py      # Step functions (analyze, process, synthesize)
│   └── validation.py # Validation gates
├── prompts/
│   ├── chain_analyze.md
│   ├── chain_process.md
│   └── chain_synthesize.md
├── models/
│   ├── chains.py     # AnalysisOutput, ProcessOutput, SynthesisOutput
│   └── openai.py     # OpenAI-compatible API models
├── api/              # FastAPI endpoints
├── config.py         # Configuration management
└── main.py           # FastAPI application
tests/                # Test suite
scripts/              # Development & utility scripts
```

Key files: `chains/graph.py` (orchestration), `chains/steps.py` (step implementations), `prompts/chain_*.md` (system prompts)

## Development

```bash
./scripts/test.sh          # Run tests with coverage
./scripts/format.sh        # Format, lint, type check
./scripts/dev.sh           # Start dev server with hot reload
```

See [CLAUDE.md](./CLAUDE.md#development-workflow) for development workflow details.

## API Reference

**Endpoints**:
- `POST /v1/chat/completions` - Streaming chat completion (OpenAI-compatible)
- `GET /v1/models` - List available models
- `GET /health/` - Liveness check
- `GET /health/ready` - Readiness check
- `GET /docs` - Interactive API documentation

**Request** (OpenAI-compatible):
```json
{
  "model": "prompt-chaining",
  "messages": [{"role": "user", "content": "Your prompt"}],
  "max_tokens": 2000
}
```

**Response**: Server-Sent Events (SSE) stream with `ChatCompletionChunk` objects

Full API docs at http://localhost:8000/docs after starting the server.

## Key Environment Variables

See `.env.example` for complete reference.

**Required**:
- `ANTHROPIC_API_KEY` - Claude API key
- `JWT_SECRET_KEY` - Min 32 chars, JWT secret

**Chain Configuration** (optional, all have defaults):
- `CHAIN_ANALYZE_MODEL` - Model for analyze step (default: Haiku)
- `CHAIN_PROCESS_MODEL` - Model for process step (default: Haiku)
- `CHAIN_SYNTHESIZE_MODEL` - Model for synthesize step (default: Haiku)
- `CHAIN_*_MAX_TOKENS` - Token limits per step
- `CHAIN_*_TEMPERATURE` - Temperature per step
- `CHAIN_*_TIMEOUT` - Timeout per step in seconds

**Server** (optional):
- `API_HOST` - Server host (default: 0.0.0.0)
- `API_PORT` - Server port (default: 8000)
- `LOG_LEVEL` - DEBUG/INFO/WARNING/ERROR/CRITICAL (default: INFO)
- `LOG_FORMAT` - json or standard (default: json)

See [CLAUDE.md](./CLAUDE.md#configuration-reference) for complete configuration reference.
