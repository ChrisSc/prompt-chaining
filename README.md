# Prompt-Chaining Workflow Template

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Anthropic](https://img.shields.io/badge/Anthropic-Claude-ED8002?logo=anthropic)
![LangChain](https://img.shields.io/badge/LangChain-1.0.0+-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-1.0.0+-blue)
![OpenAI API](https://img.shields.io/badge/OpenAI-API-412991?logo=openai)
![GitHub Template](https://img.shields.io/badge/GitHub-Template-blue?logo=github)

A *github repository template* for scaffolding **prompt-chaining workflows** with Anthropic's Claude and OpenAI-compatible APIs. Built on the proven prompt-chaining pattern with LangGraph StateGraph orchestration and streaming SSE responses.

In this pattern, sequential processing steps (Analysis, Processing, Synthesis) work together to handle complex multi-step reasoning tasks. Each step is independently configured with its own Claude model, token limits, and system prompt. State flows through the workflow via LangGraph's StateGraph, enabling structured outputs and validation gates between steps.

![Prompt Chaining Pattern](prompt-chaining.png "Prompt Chaining Pattern")

## Key components
- **Analysis Agent:** Parses user intent, extracts key entities, assesses task complexity, and provides contextual information for subsequent steps. Returns `AnalysisOutput` with structured analysis data.
- **Processing Agent:** Generates content based on analysis results with domain-specific logic. Returns `ProcessOutput` with generated content and confidence metrics.
- **Synthesis Agent:** Polishes and formats the processed content into a final, user-ready response. Returns `SynthesisOutput` with structured formatting and styling applied.
- **LangGraph StateGraph:** Orchestrates sequential step execution with message accumulation, validation gates, and step-specific timeouts via `ChainState` TypedDict.

## Overview

This template provides a complete foundation for creating prompt-chaining workflows that:
- Execute sequential multi-step AI reasoning tasks
- Stream responses via Server-Sent Events (SSE)
- Expose OpenAI-compatible APIs
- Provide structured outputs with type safety
- Integrate with LangGraph StateGraph for complex workflows

## Features

- **Prompt-Chaining Pattern**: Sequential execution of Analysis, Processing, and Synthesis steps
- **LangGraph Integration**: StateGraph orchestration with message accumulation and validation gates
- **Streaming Responses**: Real-time SSE streaming compatible with OpenAI format
- **Structured Outputs**: Type-safe step models (AnalysisOutput, ProcessOutput, SynthesisOutput)
- **Flexible Configuration**: Per-step model selection, token limits, temperature, and timeouts
- **Observability**: Comprehensive logging, error handling, and configuration
- **Validation Gates**: Data quality enforcement between steps with schema validation and business rules (intent required, confidence >= 0.5). Invalid outputs route to error handler, preventing bad data from cascading through the workflow.
- **Token Usage Tracking**: Automatic cost tracking with per-step token/cost logging for workflow validation and optimization. Every API call logs input/output tokens and USD costs, with aggregated metrics across all steps for complete cost visibility.
- **Request ID Propagation**: Automatic end-to-end request tracing through all steps to Anthropic API for debugging and distributed tracing
- **Request Size Validation**: Protects against memory exhaustion with configurable request body size limits (default 1MB)
- **Request Timeout Enforcement**: Prevents runaway requests from consuming resources indefinitely. Separate timeouts for analysis (15s default), processing (30s default), and synthesis (20s default) phases ensure predictable behavior. Configurable via environment variables for different deployment requirements.
- **Circuit Breaker**: Automatic retry with exponential backoff for Anthropic API resilience
- **Security Headers**: Standard HTTP security headers (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Strict-Transport-Security) enabled by default to protect against common web attacks
- **Rate Limiting**: Per-user JWT + IP-based, configurable limits, standard HTTP 429 responses
- **FastAPI**: Modern async Python framework with automatic OpenAPI docs
- **Type-Safe**: Full type hints and Pydantic v2 validation
- **LangChain 1.0.0+**: For building prompt chains and managing LLM interactions
- **LangGraph 1.0.0+**: For composing multi-step agentic workflows with StateGraph orchestration

## Quick Start

### Prerequisites

- Docker and Docker Compose (recommended), OR
- Python 3.10+ for manual installation
- Anthropic API key (required)

### Quick Start with Docker (Recommended)

The fastest way to get started:

```bash
# 1. Clone and navigate to project
git clone <repo-url>
cd agentic-orchestrator-worker-template

# 2. Configure environment (see Environment Variables section)
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY and JWT_SECRET_KEY

# 3. Build and start the service
docker-compose up -d

# 4. Test the service
curl http://localhost:8000/health/

# 5. Generate an authentication token
export API_BEARER_TOKEN=$(docker-compose exec orchestrator-worker python scripts/generate_jwt.py)

# 6. Test the API
python console_client.py "Hello, world!"

# 7. View logs
docker-compose logs -f

# 8. Stop the service
docker-compose down
```

**What you get:**
- Isolated environment with all dependencies
- Reproducible builds across machines
- Ready-to-deploy container for production
- Automatic health monitoring

For more Docker information, see **Deployment Options** below or [CLAUDE.md](./CLAUDE.md#container-deployment-docker).

### Manual Installation

If you prefer manual installation:

```bash
# Clone or copy this template
cd agentic-orchestrator-worker-template

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env and add:
#   - ANTHROPIC_API_KEY (required)
#   - JWT_SECRET_KEY (required, generate with: python -c "import secrets; print(secrets.token_urlsafe(32))")
```

### Run Development Server

```bash
./scripts/dev.sh
# Or manually:
# fastapi dev src/workflow/main.py --host 0.0.0.0 --port 8000
```

Navigate to:
- API: http://localhost:8000
- Documentation: http://localhost:8000/docs
- Health: http://localhost:8000/health

### Test with Console Client

```bash
# Generate a bearer token first
export API_BEARER_TOKEN=$(python scripts/generate_jwt.py)

# Test the service
python console_client.py "Hello, world!"
```

## Authentication

This service uses JWT (JSON Web Token) bearer token authentication on all protected endpoints, following OpenAI API authentication standards.

### Setup

1. Generate a secure secret (minimum 32 characters):
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. Add to `.env`:
   ```env
   JWT_SECRET_KEY=<generated_secret>
   JWT_ALGORITHM=HS256
   ```

3. Generate bearer tokens:
   ```bash
   # Token without expiration
   python scripts/generate_jwt.py

   # Token with 7-day expiration
   python scripts/generate_jwt.py --expires-in 7d
   ```

### Usage

Include the bearer token in the `Authorization` header:

```bash
TOKEN=$(python scripts/generate_jwt.py)

# With curl
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/models

# With console client
export API_BEARER_TOKEN=$TOKEN
python console_client.py "Your prompt here"
```

### Protected vs. Public Endpoints

**Protected (require bearer token):**
- `POST /v1/chat/completions`
- `GET /v1/models`

**Public (no authentication required):**
- `GET /health/`
- `GET /health/ready`

See [JWT_AUTHENTICATION.md](./JWT_AUTHENTICATION.md) for complete authentication documentation.

## Understanding the Prompt-Chaining Workflow

The system implements a three-step prompt-chaining pattern orchestrated by **LangGraph StateGraph** that processes requests sequentially through specialized agents. Each step is independently configured with its own Claude model, token limits, and system prompt. State flows through the workflow via LangGraph's `ChainState` TypedDict with message accumulation and validation gates between steps.

### The Three-Phase Flow

**Phase 1: Analysis** (`analyze_step()`)
Parses user requests to extract structured information for downstream processing.
- Extracts user intent (what they want to accomplish)
- Identifies key entities, topics, and concepts mentioned
- Assesses task complexity (simple, moderate, or complex)
- Gathers contextual information for the processing phase
- Output: `AnalysisOutput` as structured JSON (intent, key_entities, complexity, context)

**Phase 2: Processing** (`process_step()`)
Generates substantive content addressing the identified intent from the analysis phase.
- Receives analysis output as context
- Generates domain-specific content based on analysis
- Scores confidence in the generated content (0.0-1.0)
- Captures metadata for traceability and debugging
- Output: `ProcessOutput` as structured JSON (content, confidence, metadata)

**Phase 3: Synthesis** (`synthesize_step()`)
Polishes and formats the response with appropriate styling for user consumption (streaming).
- Receives processed content as context
- Applies formatting, styling, and polish
- Streams response token-by-token in real-time to client
- Ensures professional, user-ready output
- Output: `SynthesisOutput` as structured JSON (final_text, formatting)

### Data Flow Diagram with Validation Gates

```
User Request
    ↓
analyze_step() → Intent, Entities, Complexity
    ↓
[Validation Gate: Intent required & non-empty?]
    ├─→ PASS → process_step()
    └─→ FAIL → error_step() returns error
    ↓
process_step() → Generated Content with Confidence
    ↓
[Validation Gate: Content required & Confidence >= 0.5?]
    ├─→ PASS → synthesize_step()
    └─→ FAIL → error_step() returns error
    ↓
synthesize_step() → Polished Response (STREAMED)
    ↓
Client receives response incrementally
```

### Validation Gates for Quality Control

Validation gates enforce data quality between steps and prevent bad data from cascading:

**After Analysis Step**:
- Gate validates `AnalysisOutput` schema
- Business rule: `intent` field must be present and non-empty
- Fails fast: Routes invalid analysis to error handler

**After Processing Step**:
- Gate validates `ProcessOutput` schema
- Business rules:
  - `content` field must be present and non-empty
  - `confidence` must be >= 0.5 (minimum quality threshold)
- Fails fast: Routes low-confidence or empty content to error handler

**Benefits**:
- Prevents empty intent from corrupting processing step
- Prevents low-confidence responses from being synthesized
- Enables early failure with clear error messages
- Maintains workflow integrity and data quality

### Why This Pattern?

- **Structured Reasoning**: Breaking down complex tasks into focused steps enables better reasoning at each stage
- **Quality Control**: Validation gates between steps prevent bad data from cascading through the workflow
- **Flexibility**: Each step can use different models, token limits, and configurations for optimal cost/quality
- **LangGraph Orchestration**: StateGraph provides robust multi-step workflow management with message continuity
- **Observability**: Independent step execution provides visibility into reasoning process and per-step token usage
- **User Experience**: Streaming synthesis provides real-time responsiveness while maintaining quality
- **Cost Optimization**: Fast Haiku models for most steps, with ability to upgrade to Sonnet if needed

### Token Usage & Cost Tracking

Token usage is automatically tracked and logged throughout execution:

```bash
# Each step logs token usage and cost metrics
# View in logs: grep "elapsed_seconds" logs.json
# Cost is logged per step and aggregated for total request

# Example log output:
# "Analysis step completed - 250 input_tokens, 180 output_tokens, $0.0012 cost"
# "Processing step completed - 450 input_tokens, 520 output_tokens, $0.0042 cost"
# "Synthesis step completed - 620 input_tokens, 410 output_tokens, $0.0035 cost"
# Total: 1,320 input_tokens, 1,110 output_tokens, $0.0089 cost
```

All step metrics are aggregated and available in structured JSON logs for cost monitoring and optimization.

### System Prompts

Each step loads its behavior from a specialized system prompt:
- `src/workflow/prompts/chain_analyze.md` - Analysis instructions
- `src/workflow/prompts/chain_process.md` - Processing instructions
- `src/workflow/prompts/chain_synthesize.md` - Synthesis instructions

For detailed information about system prompts, configuration, and architecture, see [ARCHITECTURE.md](./ARCHITECTURE.md#prompt-chaining-step-functions).

## Architecture

### Prompt-Chaining Pattern with LangGraph

The workflow uses **LangGraph StateGraph** (`src/workflow/chains/graph.py`) to orchestrate three sequential processing steps with validation gates:

**Graph Structure**:
- **Nodes**: analyze, process, synthesize, error (4 nodes)
- **Flow**: START → analyze → (validation gate) → process → (validation gate) → synthesize → END
- **Conditional Edges**: Validation gates route invalid outputs to error handler
- **State Management**: ChainState TypedDict with `add_messages` reducer maintains message history
- **Execution Modes**: Non-streaming (`invoke_chain`) and streaming (`stream_chain`)

**Analysis Agent** (Intent Parser)
- Model: Configurable (default: Claude Haiku 4.5)
- Role: Parse user intent, extract key entities, assess complexity
- Output: `AnalysisOutput` with structured analysis data
- Execution: Non-streaming via `ainvoke()` (default timeout: 15s)
- System Prompt: `src/workflow/prompts/chain_analyze.md`
- Validation Gate: Intent must be non-empty and non-whitespace

**Processing Agent** (Content Generator)
- Model: Configurable (default: Claude Haiku 4.5)
- Role: Generate content based on analysis results
- Output: `ProcessOutput` with generated content and confidence score
- Execution: Non-streaming via `ainvoke()` (default timeout: 30s)
- System Prompt: `src/workflow/prompts/chain_process.md`
- Validation Gate: Content non-empty AND confidence >= 0.5 (minimum quality threshold)

**Synthesis Agent** (Polish & Format)
- Model: Configurable (default: Claude Haiku 4.5)
- Role: Polish and format content into final response
- Output: `SynthesisOutput` with formatted final text
- Execution: **Streaming via `astream()`** - token-by-token delivery (default timeout: 20s)
- System Prompt: `src/workflow/prompts/chain_synthesize.md`
- Streaming: Only node that yields per-token; earlier steps run to completion

### Conditional Edge Logic

**Edge 1: analyze → should_proceed_to_process**
- Validates: `AnalysisOutput` schema and intent non-empty
- Routes: "process" (valid) or "error" (invalid)

**Edge 2: process → should_proceed_to_synthesize**
- Validates: `ProcessOutput` schema, content non-empty, confidence >= 0.5
- Routes: "synthesize" (valid) or "error" (invalid)

See ARCHITECTURE.md "Validation Gates: Examples and Failure Scenarios" for detailed success/failure path examples with actual state transitions.

### Sequential Processing with State Management

This architecture delivers multi-step reasoning benefits:

**Structured Reasoning**
- Analysis step extracts intent and context
- Processing step builds on analysis results
- Synthesis step polishes and formats output

**State Continuity**
- LangGraph StateGraph manages state through `ChainState` TypedDict
- Message accumulation via `add_messages` reducer maintains conversation context
- Step outputs populate dedicated state fields (analysis, processed_content, final_response)
- Metadata tracking across entire workflow (per-step tokens, costs, timing)

**Quality Control**
- Validation gates enforce schema compliance and business rules
- Invalid outputs route to error handler for graceful failure
- Prevents low-quality intermediate results from cascading downstream

**Flexibility**
- Each step independently configurable (model, tokens, temperature, timeout)
- Per-step system prompts customizable in `src/workflow/prompts/`
- Message conversion bridge enables OpenAI API compatibility with LangChain/LangGraph internally

**Streaming Integration**
- Synthesis step uses `astream()` for token-by-token delivery to client
- Earlier steps run to completion before synthesis begins streaming
- SSE format for client-side streaming with [DONE] terminator

**Observability & Cost Tracking**
- Per-step token usage and cost logging
- Request ID propagation for end-to-end tracing
- Total cost aggregation across all steps

**Real-World Impact**
- Complex multi-step reasoning with quality control between steps
- Structured outputs enable downstream processing and validation
- Cost-optimized: Fast Haiku for most steps, upgrade to Sonnet if complex reasoning needed
- User experience: Streaming responses provide real-time feedback
- Error handling: Validation failures handled gracefully without bad data cascading

See ARCHITECTURE.md "Prompt-Chaining Step Functions" and "LangGraph StateGraph Implementation" for detailed state flow diagrams, token aggregation examples, and conditional edge logic.

## Use Cases

This architecture excels in domains that require sequential multi-step reasoning with structured outputs:

**Research & Analysis**
- Document analysis (analyze document, extract insights, synthesize summary)
- Research synthesis (gather information, organize findings, generate report)
- Competitive intelligence (analyze competitor, assess threat, recommend strategy)
- Market analysis (evaluate market, identify trends, forecast outcomes)

**Content Generation**
- Technical documentation (analyze code, generate docs, format output)
- Blog posts (analyze topic, generate draft, polish final version)
- Marketing copy (understand audience, write copy, optimize tone)
- Email campaigns (analyze recipient, generate message, personalize content)

**Data Processing**
- Document processing (analyze document, extract entities, validate results)
- Form analysis (understand requirements, generate response, validate accuracy)
- Data validation (check quality, identify issues, recommend corrections)
- Report generation (analyze data, create summary, format output)

**Code & Development**
- Code review (understand changes, identify issues, provide feedback)
- Documentation generation (analyze code, understand purpose, generate docs)
- Test generation (understand code, design tests, generate test code)
- Refactoring guidance (analyze code, identify improvements, recommend changes)

**Decision Support**
- Multi-criteria evaluation (understand criteria, score options, rank results)
- Risk assessment (identify risks, analyze impact, prioritize mitigation)
- Scenario planning (understand scenario, model outcomes, recommend actions)
- Option comparison (analyze options, evaluate tradeoffs, recommend choice)

**Ideal Characteristics**
- Tasks **require sequential steps** (step N depends on step N-1 results)
- Output needs **structure** (type-safe results for downstream processing)
- Steps have **different concerns** (analysis vs. generation vs. synthesis)
- **Quality matters** (each step can be optimized independently)
- **Observability needed** (intermediate outputs for transparency)

**Not Ideal For**
- Parallel independent tasks (better suited for orchestrator-worker pattern)
- Single-turn chat (better suited for single-agent chat)
- Simple tasks that don't require multiple reasoning steps
- Real-time bidirectional conversations (better suited for streaming chat)

## Deployment Options

### Docker (Recommended)

**Best for:** Production deployments, consistent environments, cloud deployments

**Requires:** Docker and Docker Compose

**Quick start:**
```bash
docker-compose up -d
curl http://localhost:8000/health/
```

**Documentation:** See "Quick Start with Docker" above and [CLAUDE.md Container Deployment](./CLAUDE.md#container-deployment-docker) section for comprehensive Docker guidance including:
- Building and running containers
- Environment configuration
- Health checks and monitoring
- Troubleshooting Docker issues
- Production deployment considerations

### Manual Installation

**Best for:** Development, learning, custom environments

**Requires:** Python 3.10+, virtual environment setup

**Instructions:** See "Manual Installation" above and [CLAUDE.md Development Setup](./CLAUDE.md#development-setup) section

### Kubernetes

**Best for:** Large-scale deployments, auto-scaling, enterprise environments

**Status:** The Docker container serves as the foundation for Kubernetes deployments. Additional Kubernetes manifests (Deployments, Services, ConfigMaps, etc.) can be created based on the Docker container.

## Configuration

### Request Timeout Settings

For information on configuring request timeouts, including separate phase-specific controls for each step, see the **Request Timeout Enforcement** section in [CLAUDE.md](./CLAUDE.md).

Key environment variables (from `ChainConfig`):
- `ANALYZE_TIMEOUT` - Maximum time for analysis step (default: 15s, range: 1-270s)
- `PROCESS_TIMEOUT` - Maximum time for processing step (default: 30s, range: 1-270s)
- `SYNTHESIZE_TIMEOUT` - Maximum time for synthesis step (default: 20s, range: 1-270s)

## Customization Guide

This is a **generic template** with a simple example workflow. To adapt for your use case:

### 1. Update Chain Step Prompts

Edit `src/workflow/prompts/`:
- `chain_analyze.md` - Customize analysis step behavior (intent parsing, entity extraction)
- `chain_process.md` - Customize processing step behavior (content generation)
- `chain_synthesize.md` - Customize synthesis step behavior (formatting, polishing)

See [CLAUDE.md Customization Guide](./CLAUDE.md#customization-guide) for detailed guidance on prompt customization and JSON output requirements.

### 2. Customize Chain Models

Edit `src/workflow/models/chains.py`:
- Extend `AnalysisOutput` with domain-specific analysis fields
- Extend `ProcessOutput` with domain-specific content fields
- Extend `SynthesisOutput` with domain-specific formatting fields
- Customize `ChainConfig` with additional workflow parameters

### 3. Customize Internal Models

Edit `src/workflow/models/internal.py`:
- Add domain-specific models and validation
- Define custom data structures for your workflow

### 4. Implement Agents

Edit `src/workflow/agents/`:
- `analysis.py` - Customize intent parsing and entity extraction for your domain
- `processing.py` - Implement domain-specific content generation
- `synthesis.py` - Customize formatting and polishing logic

### 5. Update Configuration

Edit `.env` and `src/workflow/config.py`:
- Per-step model IDs (upgrade to Sonnet if needed for complex reasoning)
- Per-step token limits and temperature
- Timeout configuration per phase
- Enable/disable validation gates between steps

## Project Structure

```
agentic-service-template/
├── src/workflow/
│   ├── agents/           # Orchestrator and Worker agents
│   ├── api/              # FastAPI endpoints
│   ├── chains/           # Prompt-chaining workflow
│   │   ├── graph.py      # LangGraph StateGraph orchestration
│   │   ├── steps.py      # Step functions (analyze, process, synthesize)
│   │   ├── validation.py # Validation gates for data quality
│   │   └── __init__.py
│   ├── models/           # Data models (OpenAI + internal + chains)
│   ├── prompts/          # System prompts (chain_analyze.md, etc.)
│   ├── utils/            # Errors, logging, utilities
│   │   ├── message_conversion.py  # OpenAI ↔ LangChain format bridge
│   │   ├── token_tracking.py      # Cost tracking utilities
│   │   └── logging.py             # Structured JSON logging
│   ├── config.py         # Configuration management
│   └── main.py           # FastAPI application
├── tests/                # Test suite
├── scripts/              # Development scripts
├── console_client.py     # Testing client
└── pyproject.toml        # Dependencies and config
```

**Key Workflow Components**:
- `chains/graph.py` - LangGraph StateGraph builder with invoke_chain and stream_chain functions
- `chains/steps.py` - Three step functions (analyze, process, synthesize) orchestrated by graph
- `chains/validation.py` - Validation gates that route invalid outputs to error handler
- `utils/message_conversion.py` - Bridges OpenAI and LangChain message formats

## Development

### Run Tests

```bash
./scripts/test.sh
```

### Format Code

```bash
./scripts/format.sh
```

### View Coverage

```bash
open htmlcov/index.html
```

## API Reference

### POST /v1/chat/completions

OpenAI-compatible streaming chat completion endpoint.

**Request:**
```json
{
  "model": "template-service-v1",
  "messages": [
    {"role": "user", "content": "Your prompt here"}
  ],
  "max_tokens": 1000
}
```

**Response:** Server-Sent Events (SSE) stream

### GET /v1/models

List available models.

### GET /health

Health check endpoint.

## Docker Quick Reference

Common Docker commands for this project:

```bash
# Build image (usually automatic with docker-compose)
docker build -t orchestrator-worker:latest .

# Start service (foreground - see logs in real-time)
docker-compose up

# Start service (background)
docker-compose up -d

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f orchestrator-worker

# Stop service
docker-compose down

# Stop and remove all data
docker-compose down -v

# Execute command in running container
docker-compose exec orchestrator-worker bash

# Rebuild image and restart
docker-compose up -d --build

# Check container status
docker-compose ps

# See resource usage
docker stats orchestrator-worker-api

# Clean rebuild (skip cache)
docker-compose build --no-cache orchestrator-worker
```

For more details, see [CLAUDE.md Container Deployment](./CLAUDE.md#container-deployment-docker) section.

## Environment Variables

See `.env.example` for all available configuration options.

Critical variables:

**API & Authentication:**
- `ANTHROPIC_API_KEY` - **Required** for Claude API access
- `JWT_SECRET_KEY` - **Required** for authentication (minimum 32 characters)
- `JWT_ALGORITHM` - JWT algorithm (default: HS256)

**Orchestrator Models** (legacy, for backward compatibility):
- `ORCHESTRATOR_MODEL` - Model for orchestrator (default: claude-sonnet-4-5-20250929)
- `WORKER_MODEL` - Model for workers (default: claude-haiku-4-5-20251001)
- `SYNTHESIZER_MODEL` - Model for synthesizer (default: claude-haiku-4-5-20251001)

**Prompt-Chain Step Models** (per-step configuration):
- `CHAIN_ANALYZE_MODEL` - Model for analysis step (default: claude-haiku-4-5-20251001)
- `CHAIN_ANALYZE_MAX_TOKENS` - Max tokens for analysis (default: 1000)
- `CHAIN_ANALYZE_TEMPERATURE` - Temperature for analysis (default: 0.7)
- `CHAIN_ANALYZE_TIMEOUT` - Analysis timeout in seconds (default: 15, range: 1-270)

- `CHAIN_PROCESS_MODEL` - Model for processing step (default: claude-haiku-4-5-20251001)
- `CHAIN_PROCESS_MAX_TOKENS` - Max tokens for processing (default: 2000)
- `CHAIN_PROCESS_TEMPERATURE` - Temperature for processing (default: 0.7)
- `CHAIN_PROCESS_TIMEOUT` - Processing timeout in seconds (default: 30, range: 1-270)

- `CHAIN_SYNTHESIZE_MODEL` - Model for synthesis step (default: claude-haiku-4-5-20251001)
- `CHAIN_SYNTHESIZE_MAX_TOKENS` - Max tokens for synthesis (default: 2000)
- `CHAIN_SYNTHESIZE_TEMPERATURE` - Temperature for synthesis (default: 0.7)
- `CHAIN_SYNTHESIZE_TIMEOUT` - Synthesis timeout in seconds (default: 20, range: 1-270)

**Prompt-Chain Validation:**
- `CHAIN_ENABLE_VALIDATION` - Enable validation gates between steps (default: true)
- `CHAIN_STRICT_VALIDATION` - Fail fast on validation errors vs. warn and continue (default: false)

**Server:**
- `LOG_LEVEL` - Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL) - default: INFO
- `LOG_FORMAT` - Log format (json, standard) - default: json
- `API_HOST` - Server host (default: 0.0.0.0)
- `API_PORT` - Server port (default: 8000)

### Logging

Structured JSON logging with five levels (CRITICAL, ERROR, WARNING, INFO, DEBUG). Default is INFO for production. Use DEBUG for development/troubleshooting.

See [CLAUDE.md Logging & Observability](./CLAUDE.md#logging--observability) for:
- Log level descriptions and when each is used
- JSON log structure and fields
- Docker log viewing commands
- Performance and cost tracking
- Common troubleshooting patterns
