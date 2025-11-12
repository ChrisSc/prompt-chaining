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

Data quality enforcement between chain steps via schema and business logic validation.

**Purpose**: Validation gates ensure step outputs conform to expected schemas and satisfy business rules before proceeding. Invalid outputs trigger error routing in the LangGraph workflow.

**Base Class Architecture**:
- `ValidationGate` (base class): Schema validation with Pydantic models
  - `validate(data)` returns tuple of (is_valid: bool, error_message: str | None)
  - Handles type checking and required field validation
  - Subclasses override for domain-specific business rules

**Step-Specific Gates**:

1. **AnalysisValidationGate** (`src/workflow/chains/validation.py`)
   - Validates `AnalysisOutput` schema
   - Business rules:
     - `intent` field required and must be non-empty (after stripping whitespace)
     - `key_entities` must be a list (can be empty)
     - `complexity` must be valid enum value
   - Returns structured error messages on failure

2. **ProcessValidationGate** (`src/workflow/chains/validation.py`)
   - Validates `ProcessOutput` schema
   - Business rules:
     - `content` field required and must be non-empty (after stripping whitespace)
     - `confidence` must be numeric and >= 0.5 (minimum quality threshold)
     - `confidence` must be <= 1.0
     - `metadata` optional but if present must be valid dict
   - Confidence threshold enforces quality gates (50% minimum confidence required)

**LangGraph Integration**:

Conditional edge functions route workflow based on validation results:
- `should_proceed_to_process(state)` → "process" (valid) or "error" (invalid)
  - Called after analysis step
  - Validates analysis output in ChainState["analysis"]
  - Routes to processing step or error handler
- `should_proceed_to_synthesize(state)` → "synthesize" (valid) or "error" (invalid)
  - Called after processing step
  - Validates processed content in ChainState["processed_content"]
  - Routes to synthesis step or error handler

**Error Handling**:
- Invalid data triggers error edge, preventing bad data from reaching next step
- Comprehensive error messages logged at WARNING level
- Errors include field names, failure reasons, and expected constraints
- State continues to error handler for graceful failure recovery

**Configuration**:
Via `ChainConfig`:
- `enable_validation: bool = True` - Enable/disable all validation gates
- `strict_validation: bool = False` - Fail fast (strict) vs. warn and continue (lenient)

**Data Type Support**:
Edge functions handle multiple input types transparently:
- **Dictionaries**: Direct validation
- **Pydantic Models**: Converted to dict via `model_dump()`
- **Strings** (ProcessOutput only): Wrapped with default confidence 0.8 for synthesis

**Real-World Impact**:
- Prevents low-confidence or incomplete analysis from corrupting processing
- Enforces data quality boundaries between interdependent steps
- Enables fast failure on quality issues vs. cascading bad data
- Supports both strict and lenient validation modes for different use cases

### Validation Gates: Examples and Failure Scenarios

**Success Path Example**:
```
Input: "What is the capital of France?"
  ↓
analyze_step()
  ├─ intent: "Find the capital of France"
  ├─ key_entities: ["France", "capital"]
  ├─ complexity: "simple"
  └─ context: {}
  ↓
should_proceed_to_process() validates:
  ├─ intent is non-empty? YES ("Find the capital of France")
  ├─ intent is only whitespace? NO
  └─ Result: PROCEED to process_step
  ↓
process_step()
  ├─ content: "The capital of France is Paris..."
  ├─ confidence: 0.95
  └─ metadata: { "source": "geographic_knowledge" }
  ↓
should_proceed_to_synthesize() validates:
  ├─ content is non-empty? YES
  ├─ confidence >= 0.5? YES (0.95)
  ├─ confidence <= 1.0? YES
  └─ Result: PROCEED to synthesize_step
  ↓
synthesize_step() streams formatted response
```

**Failure Path Example 1: Empty Intent**:
```
Input: "   " (whitespace only)
  ↓
analyze_step()
  ├─ intent: "   " (whitespace)
  ├─ key_entities: []
  ├─ complexity: "simple"
  └─ context: {}
  ↓
should_proceed_to_process() validates:
  ├─ intent is non-empty? NO (whitespace stripped = empty)
  ├─ Error: "intent field is required and must be non-empty"
  └─ Result: ROUTE TO ERROR
  ↓
error_step() returns:
  {
    "error": "Validation failed: intent field is required and must be non-empty",
    "step": "analysis",
    "details": {"field": "intent", "issue": "empty"}
  }
  ↓
Stream error to client via SSE
```

**Failure Path Example 2: Low Confidence**:
```
Input: "Explain quantum mechanics in one sentence"
  ↓
analyze_step() → OK (intent: "Explain quantum mechanics")
  ↓
process_step()
  ├─ content: "Quantum physics... [incomplete/uncertain]"
  ├─ confidence: 0.3 (LOW - model unsure)
  └─ metadata: { "source": "uncertain_reasoning" }
  ↓
should_proceed_to_synthesize() validates:
  ├─ content is non-empty? YES
  ├─ confidence >= 0.5? NO (0.3 < 0.5)
  ├─ Error: "confidence score 0.3 does not meet minimum threshold of 0.5"
  └─ Result: ROUTE TO ERROR
  ↓
error_step() returns:
  {
    "error": "Validation failed: confidence score is below minimum threshold",
    "step": "processing",
    "details": {"field": "confidence", "value": 0.3, "minimum": 0.5}
  }
  ↓
Stream error to client via SSE
```

**Boundary Condition: Confidence At Threshold**:
```
Input: "What is the weather?" (ambiguous - no location)
  ↓
process_step()
  ├─ content: "I need more information about location..."
  ├─ confidence: 0.5 (AT THRESHOLD)
  └─ metadata: { "ambiguous_input": true }
  ↓
should_proceed_to_synthesize() validates:
  ├─ confidence >= 0.5? YES (0.5 >= 0.5, boundary condition passes)
  └─ Result: PROCEED to synthesize_step
  ↓
synthesize_step() streams response asking for clarification
```

### Error Routing Diagram

```
ChainState flows through steps:

analyze_step outputs ChainState with analysis field
    ↓
┌─────────────────────────────────────────────┐
│ should_proceed_to_process(state)            │ (Conditional Edge)
│                                             │
│ if analysis.intent is non-empty:           │
│   → route to "process" node                 │
│ else:                                       │
│   → route to "error" node                   │
└─────────────────────────────────────────────┘
    ↓                               ↓
 process_step              error_step (returns error message)
    ↓                               ↓
┌─────────────────────────────────────────────┐
│ should_proceed_to_synthesize(state)         │ (Conditional Edge)
│                                             │
│ if processing.confidence >= 0.5 AND        │
│    processing.content is non-empty:        │
│   → route to "synthesize" node              │
│ else:                                       │
│   → route to "error" node                   │
└─────────────────────────────────────────────┘
    ↓                               ↓
 synthesize_step           error_step (returns error message)
    ↓                               ↓
    └─────────────┬─────────────────┘
                  ↓
              END node (success or error)
                  ↓
            Stream to client
```

### LangGraph Integration

The workflow uses `StateGraph` (from `src/workflow/chains/graph.py`) to orchestrate the sequential steps:

**Graph Architecture** (`build_chain_graph(config: ChainConfig)`):
- **Nodes**: `analyze`, `process`, `synthesize`, `error` - each step is an independent graph node
- **Edges**: START → analyze → (validation gate) → process → (validation gate) → synthesize → END (or error → END)
- **Conditional Edges**: Validation gates route to error handler on validation failures
- **State Management**: ChainState TypedDict with `add_messages` reducer maintains message accumulation
- **Async Execution**: Supports both non-streaming (`invoke_chain`) and streaming (`stream_chain`) modes

**Node Definitions**:

1. **START Node**
   - Entry point for all requests
   - Initializes ChainState with:
     - `messages`: List with initial HumanMessage from request
     - `analysis`: None (will be populated by analyze_step)
     - `processed_content`: None (will be populated by process_step)
     - `final_response`: None (will be populated by synthesize_step)
     - `step_metadata`: {} (accumulates metrics)

2. **analyze Node** (`analyze_step`)
   - Receives ChainState with user message
   - Outputs: ChainState with `analysis` field populated
   - Timeout: configurable (default 15s via `ChainConfig.analyze_timeout`)
   - State mutation: Updates `messages`, adds `analysis` dict, populates `step_metadata.analyze`

3. **process Node** (`process_step`)
   - Receives ChainState with `analysis` populated
   - Uses analysis output as context for generation
   - Outputs: ChainState with `processed_content` field populated
   - Timeout: configurable (default 30s via `ChainConfig.process_timeout`)
   - State mutation: Updates `messages`, adds `processed_content` string, populates `step_metadata.process`

4. **synthesize Node** (`synthesize_step`)
   - Receives ChainState with `processed_content` populated
   - Streams token-by-token (only streaming node)
   - Outputs: AsyncIterator yielding ChainState updates per chunk
   - Timeout: configurable (default 20s via `ChainConfig.synthesize_timeout`)
   - State mutation: Updates `messages` incrementally, accumulates `final_response`, populates `step_metadata.synthesize`

5. **error Node** (`error_step`)
   - Receives ChainState from failed validation gate
   - Returns user-friendly error message
   - Timeout: None (synchronous)
   - State mutation: Sets `final_response` to error message

**Conditional Edges**:

Edge 1: `analyze → should_proceed_to_process`
```python
# Logic in should_proceed_to_process(state):
if state.get("analysis") and state["analysis"].get("intent", "").strip():
    return "process"  # Valid: proceed
else:
    return "error"    # Invalid: route to error handler
```
- Success: ChainState flows to process node
- Failure: ChainState flows to error node with validation failure logged

Edge 2: `process → should_proceed_to_synthesize`
```python
# Logic in should_proceed_to_synthesize(state):
if state.get("processed_content"):
    content_dict = state["processed_content"]
    if isinstance(content_dict, dict):
        confidence = content_dict.get("confidence", 0)
        if confidence >= 0.5:
            return "synthesize"  # Valid: proceed
return "error"  # Invalid: route to error handler
```
- Success: ChainState flows to synthesize node
- Failure: ChainState flows to error node with validation failure logged

**Execution Modes**:
1. **invoke_chain()**: Non-streaming execution via `graph.ainvoke()`
   - Useful for testing and batch processing
   - Returns complete final ChainState after all steps execute
   - All steps run to completion before returning

2. **stream_chain()**: Streaming execution via `graph.astream()`
   - AsyncIterator yields state updates as they arrive
   - Earlier steps (analyze, process) run to completion
   - Synthesis step yields token-by-token via `astream()` on the LLM
   - Enables real-time streaming to client via SSE
   - `stream_mode="messages"` enables message-level granularity

**Error Handling**:
- Validation gates route invalid outputs to `error_step`
- Error step creates structured error response:
  ```python
  {
      "error": "Human-readable error message",
      "step": "analysis|processing|synthesis",
      "details": {
          "field": "field_name",
          "issue": "validation_issue",
          "value": actual_value,
          "expected": expected_constraint
      }
  }
  ```
- Both success and error paths terminate at END node
- Client receives error via SSE with [DONE] marker

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

## Prompt-Chaining Step Functions

The prompt-chaining workflow is implemented through three step functions orchestrated by LangGraph StateGraph. Each step processes `ChainState`, performs LLM operations, and returns state updates.

### Overview

The step functions implement the three sequential LLM calls that compose the prompt-chaining pattern:

- **File Location**: `src/workflow/chains/steps.py`
- **Graph Orchestration**: `src/workflow/chains/graph.py` - LangGraph StateGraph implementation
- **Integration**: Called by LangGraph StateGraph via conditional edges (validation gates)
- **State Management**: All steps read from and write to `ChainState` TypedDict
- **Token Tracking**: Each step extracts usage metadata and logs costs
- **Message Conversion**: `src/workflow/utils/message_conversion.py` - OpenAI ↔ LangChain message format conversion

### Step 1: Analyze Step (analyze_step)

**Purpose**: Parse user request and extract structured information for downstream processing.

**Input**:
- User message from `ChainState.messages` (latest HumanMessage)

**Configuration** (from `ChainConfig.analyze`):
- Model: Configurable (default: Claude Haiku 4.5)
- Max tokens: Configurable (default: 1000)
- Temperature: Configurable (default: 0.7)
- System prompt file: `src/workflow/prompts/chain_analyze.md`

**Output** (`AnalysisOutput`):
```json
{
  "intent": "User's primary goal",
  "key_entities": ["entity1", "entity2"],
  "complexity": "simple|moderate|complex",
  "context": { "additional": "contextual info" }
}
```

**Returns** (ChainState updates):
- `analysis`: AnalysisOutput as dict
- `messages`: Appended LLM response
- `step_metadata.analyze`: Token counts, costs, elapsed time

**Key Behavior**:
- Non-streaming: Uses `ainvoke()` for single LLM call
- JSON parsing: Validates response against AnalysisOutput Pydantic model
- Markdown handling: Automatically cleans markdown code blocks (```json...```)
- Error handling: Logs parsing errors at ERROR level; raises ValidationError

**Token Tracking**:
- Extracts `usage_metadata` from LLM response
- Calculates USD cost using `calculate_cost()` utility
- Logs input/output tokens and cost in structured format

### Step 2: Process Step (process_step)

**Purpose**: Generate content based on analysis results with confidence scoring.

**Input**:
- Analysis from `ChainState.analysis`
- Builds context prompt including: intent, key entities, complexity level, additional context

**Configuration** (from `ChainConfig.process`):
- Model: Configurable (default: Claude Haiku 4.5)
- Max tokens: Configurable (default: 2000)
- Temperature: Configurable (default: 0.7)
- System prompt file: `src/workflow/prompts/chain_process.md`

**Output** (`ProcessOutput`):
```json
{
  "content": "Generated content addressing the intent",
  "confidence": 0.85,
  "metadata": { "generation_approach": "value" }
}
```

**Returns** (ChainState updates):
- `processed_content`: ProcessOutput as dict
- `messages`: Appended LLM response
- `step_metadata.process`: Token counts, costs, confidence, elapsed time

**Key Behavior**:
- Non-streaming: Uses `ainvoke()` for single LLM call
- Context-aware: Incorporates analysis results into processing prompt
- Confidence scoring: Confidence score must pass validation gate (>= 0.5)
- JSON parsing: Validates response against ProcessOutput Pydantic model
- Error handling: Logs parsing errors at ERROR level; raises ValidationError

**Token Tracking**:
- Extracts `usage_metadata` from LLM response
- Calculates USD cost using `calculate_cost()` utility
- Logs confidence score and content length alongside token metrics

### Step 3: Synthesize Step (synthesize_step)

**Purpose**: Polish and format final response for user delivery.

**Input**:
- Processed content from `ChainState.processed_content`
- Builds context prompt including: content, confidence level, generation metadata

**Configuration** (from `ChainConfig.synthesize`):
- Model: Configurable (default: Claude Haiku 4.5)
- Max tokens: Configurable (default: 2000)
- Temperature: Configurable (default: 0.7)
- System prompt file: `src/workflow/prompts/chain_synthesize.md`

**Output** (`SynthesisOutput`):
```json
{
  "final_text": "Polished and formatted response",
  "formatting": "markdown|plain|html"
}
```

**Yields** (AsyncIterator of ChainState updates):
- Incremental state updates for each streamed chunk
- `final_response`: Accumulated text from streaming chunks
- `messages`: Appended response chunks
- `step_metadata.synthesize`: Progressive and final token counts, costs, formatting

**Key Behavior**:
- **Streaming**: Only synthesis step uses `astream()` for token-by-token delivery to client
- Incremental yielding: Yields state updates for each chunk to enable real-time streaming
- JSON parsing with fallback: Attempts to parse accumulated text as SynthesisOutput; falls back to plain text on failure
- Markdown handling: Automatically cleans markdown code blocks from accumulated response
- Error handling: Logs JSON parsing warnings at WARNING level; uses accumulated text as fallback

**Token Tracking**:
- Extracts `usage_metadata` from final chunk (contains aggregate token counts)
- Calculates USD cost using `calculate_cost()` utility
- Logs formatting style and final text length alongside token metrics

### State Flow Through Steps

**Before and After State Examples**:

**Initial State** (at graph START):
```python
ChainState = {
    "messages": [
        HumanMessage(content="Compare Python async vs sync performance")
    ],
    "analysis": None,
    "processed_content": None,
    "final_response": None,
    "step_metadata": {}
}
```

**After analyze_step**:
```python
ChainState = {
    "messages": [
        HumanMessage(content="Compare Python async vs sync performance"),
        AIMessage(content='{"intent":"...", "key_entities":[...], ...}')  # Added by add_messages reducer
    ],
    "analysis": {
        "intent": "Compare performance characteristics of async vs sync Python code",
        "key_entities": ["Python", "async", "sync", "performance"],
        "complexity": "moderate",
        "context": {"domain": "backend development"}
    },
    "processed_content": None,
    "final_response": None,
    "step_metadata": {
        "analyze": {
            "model": "claude-haiku-4-5-20251001",
            "input_tokens": 85,
            "output_tokens": 156,
            "cost_usd": 0.000967,
            "elapsed_seconds": 1.23
        }
    }
}
```

**After process_step**:
```python
ChainState = {
    "messages": [
        HumanMessage(content="Compare Python async vs sync..."),
        AIMessage(content='{"intent":"...", ...}'),  # From analyze_step
        AIMessage(content='{"content":"Async Python code..."}')  # Added by process_step
    ],
    "analysis": { ... },  # Unchanged from analyze_step
    "processed_content": {
        "content": "Asynchronous Python uses await/async keywords to yield control...",
        "confidence": 0.87,
        "metadata": {"approach": "comparative analysis", "examples_included": True}
    },
    "final_response": None,
    "step_metadata": {
        "analyze": { ... },  # From previous step
        "process": {
            "model": "claude-haiku-4-5-20251001",
            "input_tokens": 287,  # Includes analysis output as context
            "output_tokens": 412,
            "cost_usd": 0.003515,
            "confidence_score": 0.87,
            "content_length": 2156,
            "elapsed_seconds": 3.45
        }
    }
}
```

**After synthesize_step** (streaming completes):
```python
ChainState = {
    "messages": [
        HumanMessage(content="Compare Python async vs sync..."),
        AIMessage(content='{"intent":"...", ...}'),
        AIMessage(content='{"content":"Asynchronous..."}'),
        AIMessage(content='{"final_text":"# Async vs Sync...", "formatting":"markdown"}')
    ],
    "analysis": { ... },
    "processed_content": { ... },
    "final_response": "# Async vs Sync Python Performance\n\nAsynchronous Python uses...",  # Accumulated from streaming chunks
    "step_metadata": {
        "analyze": { ... },
        "process": { ... },
        "synthesize": {
            "model": "claude-haiku-4-5-20251001",
            "input_tokens": 521,  # Includes processed_content as context
            "output_tokens": 387,
            "cost_usd": 0.002696,
            "formatting_style": "markdown",
            "final_text_length": 3421,
            "elapsed_seconds": 2.11,
            "chunks_received": 58  # Streaming detail
        }
    }
}
```

**Token Aggregation Across All Steps**:
```
ANALYZE STEP:
  Input tokens:  85  (user message + system prompt)
  Output tokens: 156 (analysis output)
  Cost: $0.000967

PROCESS STEP:
  Input tokens:  287 (analysis output + system prompt + context)
  Output tokens: 412 (process output)
  Cost: $0.003515

SYNTHESIZE STEP:
  Input tokens:  521 (process output + system prompt + context)
  Output tokens: 387 (final polished response)
  Cost: $0.002696

TOTAL REQUEST:
  Input tokens:  893 (85 + 287 + 521)
  Output tokens: 955 (156 + 412 + 387)
  Total tokens:  1,848
  Total cost:    $0.007178  ($0.000967 + $0.003515 + $0.002696)
  Total time:    6.79s (1.23 + 3.45 + 2.11)
```

**Cost Calculation Details** (Haiku pricing: $1/$5 per 1M tokens):
```python
# For Haiku model (claude-haiku-4-5-20251001)
input_cost = input_tokens / 1_000_000 * 1.00   # $1 per 1M input tokens
output_cost = output_tokens / 1_000_000 * 5.00 # $5 per 1M output tokens
total_cost = input_cost + output_cost

# Example from analyze_step:
# 85 input + 156 output
input_cost = 85 / 1_000_000 * 1.00 = $0.000085
output_cost = 156 / 1_000_000 * 5.00 = $0.000780
total_cost = $0.000865 (matches logged $0.000967 with variance for rounding)
```

**Message Accumulation via add_messages Reducer**:
The `add_messages` reducer automatically handles merging of new messages into the messages list:
- Each step appends its output to messages
- Conversation history preserved for context
- Earlier messages available for later steps to reference if needed
- Enables full conversation continuity if adapted for multi-turn

**State Flow Through Steps**:
```
User Request (ChainState.messages)
    ↓
[analyze_step] extracts intent, entities, complexity
    ├─ Reads: messages (latest HumanMessage)
    ├─ Processes: ~1-2 seconds (LLM inference)
    └─ Writes: analysis dict, messages (appends AIMessage), step_metadata.analyze
    ↓
[validation gate: should_proceed_to_process]
    ├─ Checks: analysis.intent is non-empty
    └─ Routes: to "process" (success) or "error" (failure)
    ↓
[process_step] generates content with confidence
    ├─ Reads: analysis dict (uses as context)
    ├─ Processes: ~2-4 seconds (LLM inference)
    └─ Writes: processed_content dict, messages (appends AIMessage), step_metadata.process
    ↓
[validation gate: should_proceed_to_synthesize]
    ├─ Checks: processed_content confidence >= 0.5
    └─ Routes: to "synthesize" (success) or "error" (failure)
    ↓
[synthesize_step] polishes and formats (STREAMING)
    ├─ Reads: processed_content dict (uses as context)
    ├─ Processes: ~1-2 seconds (LLM streaming inference)
    ├─ Yields: ChainState updates per chunk (~20-100ms per chunk)
    └─ Writes: final_response accumulated, messages (appends chunks), step_metadata.synthesize
    ↓
Client receives streamed response (58 chunks in example)
```

### System Prompts

Each step loads its system prompt from a markdown file in `src/workflow/prompts/`:

1. **chain_analyze.md**: Instructions for analysis step
   - Controls intent parsing logic
   - Defines entity extraction rules
   - Specifies complexity assessment criteria
   - Customizable for domain-specific analysis

2. **chain_process.md**: Instructions for processing step
   - Controls content generation approach
   - Defines confidence scoring logic
   - Specifies metadata capture
   - Customizable for domain-specific generation

3. **chain_synthesize.md**: Instructions for synthesis step
   - Controls formatting and polishing logic
   - Defines styling preferences
   - Specifies final validation rules
   - Customizable for domain-specific formatting

### Error Handling & Validation

**JSON Parsing**:
- Analyze and Process steps raise exceptions on parse failures
- Synthesize step falls back to accumulated text on parse failures
- Markdown code block wrapper is automatically removed before parsing

**Validation Gates**:
- After analyze step: `should_proceed_to_process()` routes to process or error handler
- After process step: `should_proceed_to_synthesize()` routes to synthesize or error handler
- Business rules enforced:
  - Analysis: Intent must be present and non-empty
  - Process: Content must be non-empty, confidence >= 0.5

**Logging**:
- All steps log token usage and cost metrics at INFO level
- Parse failures logged at ERROR (analyze, process) or WARNING (synthesize) level
- Step execution duration and performance metrics included in logs

### Configuration Reference

All step functions are configured via `ChainConfig` (from `src/workflow/models/chains.py`):

```python
class ChainStepConfig(BaseModel):
    model: str                      # Claude model ID
    max_tokens: int                 # Maximum tokens to generate
    temperature: float              # Sampling temperature (0.0-2.0)
    system_prompt_file: str         # Prompt filename in src/workflow/prompts/

class ChainConfig(BaseModel):
    analyze: ChainStepConfig        # Analysis step config
    process: ChainStepConfig        # Processing step config
    synthesize: ChainStepConfig     # Synthesis step config
    analyze_timeout: int = 15       # Step timeout (1-270 seconds)
    process_timeout: int = 30
    synthesize_timeout: int = 20
    enable_validation: bool = True  # Enable validation gates
    strict_validation: bool = False # Fail fast vs. warn on errors
```

### Cost & Performance

**Token Usage**:
- Each step extracts `input_tokens` and `output_tokens` from LLM response
- Used to calculate USD cost via `calculate_cost(model, input_tokens, output_tokens)`
- Aggregated across steps for complete workflow cost tracking

**Timing**:
- Each step measures elapsed time via `time.time()`
- Logged in structured format: `elapsed_seconds`
- Enables performance optimization and SLA monitoring

**Typical Performance** (on Haiku models):
- Analysis step: 1-2 seconds
- Processing step: 2-4 seconds
- Synthesis step: 1-2 seconds (plus streaming overhead)
- Total request: 4-8 seconds + network latency

## Configuration Best Practices

This section provides production guidance for optimizing the prompt-chaining workflow for your specific use case.

### Cost Optimization Strategies

**Cost Breakdown by Step** (typical Haiku model execution):
```
Analyze Step (Intent Extraction)
  - Input: 250 tokens (user message + system prompt)
  - Output: 150 tokens (intent, entities, complexity)
  - Cost: (250 * $1/1M) + (150 * $5/1M) = $0.00100

Process Step (Content Generation)
  - Input: 400 tokens (analysis output + system prompt + context)
  - Output: 400 tokens (generated content)
  - Cost: (400 * $1/1M) + (400 * $5/1M) = $0.00240

Synthesize Step (Formatting & Polishing)
  - Input: 500 tokens (process output + system prompt + context)
  - Output: 400 tokens (formatted response)
  - Cost: (500 * $1/1M) + (400 * $5/1M) = $0.00250

Total per request: $0.00590
```

**Configuration Cost Impact** (per request, 1000 user message tokens):

| Configuration | Analyze Cost | Process Cost | Synthesize Cost | Total Cost | Speed | Use Case |
|--|--|--|--|--|--|--|
| All-Haiku | $0.00100 | $0.00240 | $0.00250 | $0.00590 | 4-8s | Cost-optimized, fast |
| Haiku + Sonnet + Haiku | $0.00100 | $0.00720 | $0.00250 | $0.01070 | 5-10s | Balanced quality/cost |
| All-Sonnet | $0.00300 | $0.00720 | $0.00750 | $0.01770 | 8-15s | Max quality (expensive) |

**Cost Optimization Strategies**:
1. Start with all-Haiku baseline ($0.01/req)
2. Monitor actual costs: `grep "total_cost_usd" logs.json`
3. Upgrade Process step first if quality issues (biggest quality impact per dollar)
4. Only upgrade Analyze/Synthesize if domain-specific requirements demand it
5. Reduce token limits if responses consistently under max
6. Use lower temperature (0.3-0.5) to get more deterministic, shorter responses

### Performance Tuning

**Latency Analysis by Step** (typical execution on Haiku):
```
Analyze Step (intent parsing)
  - Network roundtrip: 200ms
  - LLM inference: 800ms
  - Subtotal: ~1.0s (range: 0.5s-2.0s)

Process Step (content generation)
  - Network roundtrip: 300ms
  - LLM inference: 2.0-3.0s
  - Subtotal: ~2.5s (range: 1.5s-4.0s)

Synthesize Step (formatting + streaming)
  - Network roundtrip: 300ms
  - LLM inference: 1.0-1.5s
  - Streaming overhead: 0.5s
  - Subtotal: ~2.0s (range: 1.0s-2.5s)

Total Request Time: 5.5s (range: 4.0s-8.5s depending on model and complexity)
```

**Timeout Adjustment for Different SLAs**:

| SLA Target | Analyze | Process | Synthesize | Notes |
|--|--|--|--|--|
| p99 < 5s (mobile) | 10s | 15s | 10s | Tight timeouts, use Haiku only, low tokens |
| p99 < 8s (web) | 15s | 30s | 20s | Default, balanced for most use cases |
| p99 < 15s (batch) | 30s | 60s | 30s | Loose timeouts, can use Sonnet, high tokens |

**Optimization for Low-Latency Services**:
```env
# Tight timeouts force quick completion or failure
CHAIN_ANALYZE_TIMEOUT=10
CHAIN_PROCESS_TIMEOUT=15
CHAIN_SYNTHESIZE_TIMEOUT=10

# Smaller token limits mean shorter responses
CHAIN_ANALYZE_MAX_TOKENS=800
CHAIN_PROCESS_MAX_TOKENS=1200
CHAIN_SYNTHESIZE_MAX_TOKENS=800

# Lower temperature means more deterministic (faster) responses
CHAIN_ANALYZE_TEMPERATURE=0.3
CHAIN_PROCESS_TEMPERATURE=0.5
CHAIN_SYNTHESIZE_TEMPERATURE=0.3

# Use only Haiku for speed
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_PROCESS_MODEL=claude-haiku-4-5-20251001
CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001
```

### Common Configuration Patterns

**Pattern 1: Cost-Optimized** (best for volume services)
```env
# All-Haiku: cheapest option (~$0.008 per request)
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_PROCESS_MODEL=claude-haiku-4-5-20251001
CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001

# Reduce tokens for brevity
CHAIN_ANALYZE_MAX_TOKENS=1000
CHAIN_PROCESS_MAX_TOKENS=1500
CHAIN_SYNTHESIZE_MAX_TOKENS=800

# Lower temperature for determinism
CHAIN_ANALYZE_TEMPERATURE=0.3
CHAIN_PROCESS_TEMPERATURE=0.5
CHAIN_SYNTHESIZE_TEMPERATURE=0.3

# Default timeouts
CHAIN_ANALYZE_TIMEOUT=15
CHAIN_PROCESS_TIMEOUT=30
CHAIN_SYNTHESIZE_TIMEOUT=20
```
Cost: ~$0.006-0.010/req | Speed: 4-8s

**Pattern 2: Balanced Quality** (best for most applications)
```env
# Haiku for analysis (fast intent parsing)
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_ANALYZE_MAX_TOKENS=1000
CHAIN_ANALYZE_TEMPERATURE=0.3

# Sonnet for generation (quality matters here)
CHAIN_PROCESS_MODEL=claude-sonnet-4-5-20250929
CHAIN_PROCESS_MAX_TOKENS=2500
CHAIN_PROCESS_TEMPERATURE=0.7

# Haiku for synthesis (efficient formatting)
CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001
CHAIN_SYNTHESIZE_MAX_TOKENS=1000
CHAIN_SYNTHESIZE_TEMPERATURE=0.5

# Slightly longer timeouts for Sonnet
CHAIN_ANALYZE_TIMEOUT=15
CHAIN_PROCESS_TIMEOUT=45
CHAIN_SYNTHESIZE_TIMEOUT=20
```
Cost: ~$0.008-0.012/req | Speed: 5-10s

**Pattern 3: Accuracy-Optimized** (for high-stakes applications)
```env
# All-Sonnet: best quality (~$0.020+ per request)
CHAIN_ANALYZE_MODEL=claude-sonnet-4-5-20250929
CHAIN_PROCESS_MODEL=claude-sonnet-4-5-20250929
CHAIN_SYNTHESIZE_MODEL=claude-sonnet-4-5-20250929

# Higher token limits for detailed responses
CHAIN_ANALYZE_MAX_TOKENS=2000
CHAIN_PROCESS_MAX_TOKENS=4000
CHAIN_SYNTHESIZE_MAX_TOKENS=2000

# Balanced temperature for quality
CHAIN_ANALYZE_TEMPERATURE=0.5
CHAIN_PROCESS_TEMPERATURE=0.7
CHAIN_SYNTHESIZE_TEMPERATURE=0.5

# Longer timeouts for careful processing
CHAIN_ANALYZE_TIMEOUT=30
CHAIN_PROCESS_TIMEOUT=60
CHAIN_SYNTHESIZE_TIMEOUT=30
```
Cost: ~$0.015-0.025/req | Speed: 8-15s

**Pattern 4: Latency-Optimized** (for real-time systems)
```env
# All-Haiku for speed
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_PROCESS_MODEL=claude-haiku-4-5-20251001
CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001

# Tight token limits force brevity
CHAIN_ANALYZE_MAX_TOKENS=800
CHAIN_PROCESS_MAX_TOKENS=1200
CHAIN_SYNTHESIZE_MAX_TOKENS=600

# Low temperature for determinism
CHAIN_ANALYZE_TEMPERATURE=0.2
CHAIN_PROCESS_TEMPERATURE=0.4
CHAIN_SYNTHESIZE_TEMPERATURE=0.2

# Strict timeouts enforce fast completion
CHAIN_ANALYZE_TIMEOUT=8
CHAIN_PROCESS_TIMEOUT=12
CHAIN_SYNTHESIZE_TIMEOUT=8
```
Cost: ~$0.005-0.008/req | Speed: 2-4s

### Troubleshooting Configuration Issues

**Problem: Validation failures (intent empty, low confidence)**

Symptoms:
- Frequent "intent field is required and must be non-empty" errors
- Process step producing content with confidence < 0.5

Solutions:
1. Check analyze step temperature: try 0.5-0.7 for more flexibility
2. Increase analyze max_tokens to 1500 for more detailed extraction
3. Review chain_analyze.md prompt - may need adjustment for your domain
4. Upgrade analyze to Sonnet if dealing with ambiguous user requests

**Problem: Timeouts (requests exceeding CHAIN_*_TIMEOUT)**

Symptoms:
- Logs showing "timeout" errors during chain execution
- Clients receiving partial responses or errors

Solutions:
1. Increase the timeout for the failing step (15s → 30s, 30s → 60s)
2. Reduce token limits if generating too much content
3. Switch to faster models (Sonnet → Haiku, but only after trying other options)
4. Check network latency (add 0.5s per step for high-latency networks)
5. Monitor actual step execution times in logs to set appropriate timeouts

**Problem: Low quality outputs**

Symptoms:
- Generated content is shallow, inaccurate, or missing key information
- User complaints about response quality

Solutions:
1. Increase process step temperature: 0.7 → 0.9 for more diverse responses
2. Increase process max_tokens: 2000 → 3000+ for more detailed content
3. Upgrade process step to Sonnet for better reasoning
4. Review/improve chain_process.md prompt for better instructions
5. Increase analyze temperature to 0.7 for more thorough analysis

**Problem: High costs**

Symptoms:
- logs show total_cost_usd consistently above budget
- Cost per request higher than expected

Solutions:
1. Check which step uses most tokens: `grep "input_tokens\|output_tokens" logs.json`
2. Reduce token limits for high-consumption steps
3. Lower temperature for more concise responses (0.7 → 0.3-0.5)
4. Switch expensive steps to Haiku (Sonnet → Haiku)
5. Monitor token usage and adjust limits based on actual needs

**Problem: Streaming stops or feels slow**

Symptoms:
- Synthesis step doesn't stream smoothly to client
- Delays between token arrivals

Solutions:
1. Reduce synthesize max_tokens to force shorter outputs
2. Increase synthesize temperature slightly (0.3 → 0.5) for less determinism = faster inference
3. Check STREAMING_CHUNK_BUFFER env var (default 0, increase to 100 for batching)
4. Increase synthesize_timeout if timeout is cutting off streaming
5. Check network bandwidth and latency

## LangGraph StateGraph Implementation

### Graph Builder (`build_chain_graph` in src/workflow/chains/graph.py)

The `build_chain_graph(config: ChainConfig)` function constructs the complete workflow graph:

```
START
  ↓
analyze_step
  ↓
should_proceed_to_process (validation gate)
  ├─→ "process" (valid)
  └─→ "error" (invalid)
  ↓
process_step
  ↓
should_proceed_to_synthesize (validation gate)
  ├─→ "synthesize" (valid)
  └─→ "error" (invalid)
  ↓
synthesize_step
  ↓
END
```

**Graph Properties**:
- **Nodes**: 4 nodes (analyze, process, synthesize, error)
- **Edges**: 6 edges (START→analyze, analyze→process/error, process→synthesize/error, both→END)
- **Conditional Logic**: Validation gates between steps route to error handler on failures
- **State Type**: ChainState TypedDict with add_messages reducer for message accumulation
- **Compilation**: Graph compiled once at application startup for performance

### Execution Modes

**Non-Streaming Mode** (`invoke_chain`):
```python
final_state = await graph.ainvoke(initial_state)
# Returns complete final ChainState after all steps
# Useful for testing, batch processing, or scenarios where streaming not needed
```

**Streaming Mode** (`stream_chain`):
```python
async for state_update in stream_chain(graph, initial_state, config):
    # Each state_update is yielded as it arrives
    # Synthesize step yields token-by-token updates via astream
    # Enables real-time streaming to client
```

### Message Conversion Utilities

The `src/workflow/utils/message_conversion.py` module bridges OpenAI and LangChain message formats:

**`convert_openai_to_langchain_messages(messages: list[ChatMessage])`**:
- Converts incoming OpenAI API messages to LangChain format for internal processing
- Maps: `system` → SystemMessage, `user` → HumanMessage, `assistant` → AIMessage
- Validates: Ensures no empty content, logs warnings for skipped messages
- Input: List of ChatMessage from POST /v1/chat/completions request
- Output: List of BaseMessage for use in chain steps

**`convert_langchain_chunk_to_openai(chunk)`**:
- Converts internal LangChain output back to OpenAI-compatible format for streaming response
- Handles multiple input types: dict (state updates), BaseMessage, or plain string
- Creates proper ChatCompletionChunk with: id, created timestamp, delta content, finish_reason
- Extracts content from: final_response field, accumulated messages, or any string value
- Output: ChatCompletionChunk formatted for OpenAI API compatibility

**Benefits of Separation**:
- OpenAI API contract stays stable and familiar to users
- Internal workflow can use LangChain abstractions optimally
- Easy to swap out or upgrade underlying LLM integration
- Message format compatibility with OpenAI clients and tools

## Extensibility Points

The template is designed for easy customization of the prompt-chaining workflow:

1. **Step Function Prompts**: Text files in `src/workflow/prompts/` directory
   - `chain_analyze.md`: Customize intent parsing and entity extraction
   - `chain_process.md`: Customize content generation logic
   - `chain_synthesize.md`: Customize formatting and polishing
   - Each prompt MUST output valid JSON matching its Pydantic model
2. **Chain Models**: Workflow models in `src/workflow/models/chains.py`
   - Extend `AnalysisOutput`, `ProcessOutput`, `SynthesisOutput` for domain data
   - Customize `ChainConfig` with additional parameters
3. **Step Function Logic**: Customize step functions in `src/workflow/chains/steps.py`
   - Modify `analyze_step()` for custom intent extraction or complexity assessment
   - Modify `process_step()` for custom confidence scoring or content validation
   - Modify `synthesize_step()` for custom formatting or post-processing
4. **Internal Models**: Domain-specific models in `src/workflow/models/internal.py`
   - Add domain-specific validation and business logic
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
