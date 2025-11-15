# Chains Layer: LangGraph Workflow, State Management, Step Functions

**Location**: `src/workflow/chains/`

**Purpose**: LangGraph StateGraph architecture, step function patterns, state management, and workflow validation.

## Navigation

- **Parent**: See `../../CLAUDE.md` for project overview
- **Related Files**:
  - `../prompts/CLAUDE.md` - System prompt integration and prompt patterns
  - `../models/CLAUDE.md` - State structure and data models
  - `../utils/CLAUDE.md` - Logging patterns in steps

## LangGraph StateGraph Architecture

The chains layer implements a three-step sequential workflow using LangGraph's StateGraph pattern:

```
START → analyze → (validation gate) → process → (validation gate) → synthesize → END
                       ↓                                 ↓
                     error                             error
```

Each node wraps a step function and passes a ChainState through the graph. Validation gates route based on output quality.

**Key Components** (Reference: `src/workflow/chains/graph.py:88-175`):

- `build_chain_graph()`: Constructs the StateGraph with three nodes plus error handler
- Conditional edges use `should_proceed_to_process()` and `should_proceed_to_synthesize()` gate functions
- MemorySaver checkpointer maintains execution state and metrics
- Wrapper functions (`analyze_wrapper`, `process_wrapper`, `synthesize_wrapper`) provide proper async/config context
- `invoke_chain()`: Non-streaming graph invocation for testing and batch processing
- `stream_chain()`: Streaming execution with async generator yielding state updates and custom token chunks

The graph compiles with a checkpointer that enables execution resumption and state inspection. Each step runs independently in its own node, allowing timeout configuration per phase.

## ChainState Structure and Evolution

The ChainState TypedDict (Reference: `src/workflow/models/chains.py:29-64`) maintains state across all steps:

```python
class ChainState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # Accumulates all messages
    request_id: str                                        # Trace ID for correlation
    user_id: str                                           # From JWT sub claim
    analysis: dict[str, Any] | None                        # Output from analyze step
    processed_content: str | None                          # Output from process step
    final_response: str | None                             # Output from synthesize step
    step_metadata: dict[str, Any]                          # Timing, tokens, costs per step
```

**State Evolution Through Workflow**:

1. **Initial State**: Only `messages` populated with user request. `request_id` set by middleware, `user_id` extracted from JWT
2. **After Analyze**: `analysis` field filled with AnalysisOutput (intent, entities, complexity, context). `step_metadata` gains "analyze" key with timing/tokens/cost
3. **After Process**: `processed_content` filled with ProcessOutput (content, confidence, metadata). Step metadata accumulates "process" key
4. **After Synthesize**: `final_response` filled with SynthesisOutput (final_text, formatting). Step metadata accumulates "synthesize" key

The `messages` field uses `add_messages` reducer to accumulate LLM responses through the chain, creating a conversation-like continuity for context passing. Each step appends its LLM response to the messages list.

**step_metadata Structure**:
```python
{
    "analyze": {"elapsed_seconds": 1.2, "total_tokens": 235, "cost_usd": 0.000235},
    "process": {"elapsed_seconds": 2.1, "total_tokens": 450, "cost_usd": 0.000450, "confidence": 0.87},
    "synthesize": {"elapsed_seconds": 1.5, "total_tokens": 340, "cost_usd": 0.000340}
}
```

Metadata enables performance monitoring, cost tracking, and debugging across all steps in a single request context.

## Step Function Patterns

All step functions follow an async pattern with proper parameter passing and state returns. Reference: `src/workflow/chains/steps.py`

**Function Signature**:
```python
async def analyze_step(state: ChainState, config: ChainConfig) -> dict[str, Any]:
    """Step function returning dict with state field updates."""
async def process_step(state: ChainState, config: ChainConfig) -> dict[str, Any]:
    """Step function returning dict with state field updates."""
async def synthesize_step(
    state: ChainState,
    runnable_config: RunnableConfig,
    chain_config: ChainConfig,
) -> dict[str, Any]:
    """Synthesize step receives RunnableConfig for stream writer context."""
```

**Execution Pattern** (Lines 74-210):

1. Extract context from state (e.g., user message for analyze, analysis for process)
2. Load system prompt via `load_system_prompt(config.STEP.system_prompt_file)`
3. Initialize ChatAnthropic with model, temperature, token limits, and request_id propagation:
   ```python
   llm = ChatAnthropic(
       model=config.analyze.model,
       temperature=config.analyze.temperature,
       max_tokens=config.analyze.max_tokens,
       extra_headers={"X-Request-ID": state.get("request_id", "")},  # Propagate request_id
   )
   ```
4. **For analyze and process steps**: Enable structured output via LangChain's `with_structured_output()` API
5. Build message list with SystemMessage (prompt) and HumanMessage (input)
6. Call LLM and extract parsed output and raw message for token tracking
7. Extract token usage from `raw_message.usage_metadata`
8. Calculate cost via `calculate_cost(model, input_tokens, output_tokens)`
9. Log completion with full metrics at INFO level
10. Return dict with field updates: `{"field_name": value, "messages": [response], "step_metadata": {...}}`

**Structured Output Pattern** (Analyze & Process Steps):

The analyze and process steps use LangChain's `with_structured_output()` API to enforce schema validation at the API level:

```python
# Enable structured output with schema validation
structured_llm = llm.with_structured_output(
    AnalysisOutput,
    method="json_schema",
    include_raw=True  # Returns (parsed, raw) to access token usage
)

# Invoke and extract results
result = await structured_llm.ainvoke(messages)
analysis_output = result.get("parsed")      # Validated Pydantic model instance
raw_message = result.get("raw")             # Raw API response with usage_metadata

# Extract token usage from raw message
tokens = raw_message.usage_metadata.get("output_tokens", 0)
```

**Why Structured Outputs**:
- Schema validation happens at API level (no manual JSON parsing)
- `ValidationError` still possible if LLM response doesn't match schema
- LangChain automatically selects strategy:
  - **ProviderStrategy**: For Sonnet 4.5 and Opus 4.1 (native Anthropic API)
  - **ToolStrategy**: For Haiku 4.5 (via tool calling with ~1% token overhead)
- All transparent to application code

**Synthesis Step Note**:
The synthesis step does not use structured outputs. It streams formatted text directly to the user, making direct streaming via `llm.astream()` optimal for real-time responsiveness.

**Error Handling** (Lines 200-209):
```python
except ValidationError as e:
    logger.error(
        "Failed to parse analysis step response",
        extra={
            "step": "analyze",
            "error": str(e),
            "error_type": type(e).__name__,
        },
    )
    raise  # Let LangGraph route to error step
```

Note: `json.JSONDecodeError` no longer occurs with structured outputs—API-level validation eliminates manual JSON parsing. `ValidationError` still possible if LLM response doesn't match schema. Exceptions are logged with full context then re-raised so LangGraph conditional edges route to error handling.

## Validation Gate Design

Validation gates enforce quality between steps using conditional edge functions. Reference: `src/workflow/chains/validation.py:185-250`

**Gate Functions Return** (conditional edge routing):
- `"process"` or `"synthesize"` to proceed to next step
- `"error"` to route to error_step if validation fails

**Example: should_proceed_to_process** (Lines 185-231):

```python
def should_proceed_to_process(state: ChainState) -> str:
    """Conditional edge: validate analysis before processing."""
    analysis_data = state.get("analysis")
    if analysis_data is None:
        logger.warning(
            "Analysis validation gate triggered: analysis output is None",
            extra={"step": "analysis_validation"},
        )
        return "error"

    gate = AnalysisValidationGate()
    is_valid, error_message = gate.validate(analysis_dict)

    if not is_valid:
        logger.warning(
            f"Analysis validation failed: {error_message}",
            extra={"step": "analysis_validation", "error": error_message},
        )
        return "error"

    logger.info("Analysis validation passed, proceeding to processing")
    return "process"
```

**Validation Rules** (Lines 69-182):
- AnalysisValidationGate: intent field must be non-empty string
- ProcessValidationGate: content must be non-empty, confidence >= 0.5
- Schema conformance checked via Pydantic validation

**Error State Handling** (Lines 40-85 in graph.py):
The error_step receives state when any validation gate fails. It logs the error context and returns user-friendly error message in final_response. Recovery mechanisms depend on client retry logic (no automatic retry in graph).

Validation at WARNING level prevents alerting on expected client input issues while allowing monitoring of gate failures for process improvement.

## Timeout Handling Per Step

Each step has independent timeout configuration via ChainConfig (Reference: `src/workflow/models/chains.py:165-182`):

```python
analyze_timeout: int = Field(default=15, ge=1, le=270)      # 1-270 seconds
process_timeout: int = Field(default=30, ge=1, le=270)      # 1-270 seconds
synthesize_timeout: int = Field(default=20, ge=1, le=270)   # 1-270 seconds
```

Timeout values are configured via environment variables (`CHAIN_ANALYZE_TIMEOUT`, etc.) from `.env.example`.

**Timeout Behavior in LangGraph**:
- LangGraph doesn't enforce timeouts at node level automatically
- Timeouts are enforced at FastAPI endpoint level using `asyncio.wait_for()`
- If a step exceeds its timeout, the entire request fails with asyncio.TimeoutError
- Error is caught in `stream_chain()` and logged with elapsed_seconds for diagnosis

Timeout values should be set based on model complexity: Haiku typically needs 10-20s, Sonnet needs 20-30s.

## Streaming in Synthesis Step

The synthesis step implements token-level streaming using LangGraph's custom mode. Reference: `src/workflow/chains/steps.py:347-530`

**Stream Writer Pattern** (Lines 417-429):

```python
writer = get_stream_writer()  # Obtained from LangGraph context
logger.info(
    "Stream writer obtained",
    extra={
        "step": "synthesize",
        "writer_is_none": writer is None,
        "writer_callable": callable(writer),
    },
)
```

The `get_stream_writer()` function (from `langgraph.config`) retrieves the custom stream writer only when the request uses streaming mode. It's None for non-streaming invocations.

**Token Streaming Loop** (Lines 441-474):

```python
async for chunk in llm.astream(messages, config=runnable_config):
    token = chunk.content if chunk.content else ""
    if token:
        token_count += 1
        final_response += token

        if writer is not None:
            try:
                writer({"type": "token", "content": token})
                # Sample-based logging: log every 100 tokens at DEBUG level
                if token_count % 100 == 0:
                    logger.debug(
                        "Tokens streaming to client",
                        extra={"step": "synthesize", "token_count": token_count},
                    )
            except Exception as write_error:
                logger.warning(
                    "Failed to write token via stream writer",
                    extra={"step": "synthesize", "error": str(write_error)},
                )
                # Continue processing despite write error
```

**Sample-Based Logging**: Tokens logged at DEBUG level every 100 tokens (not per-token) to avoid excessive log volume. For 4,000 tokens, approximately 40 logs instead of 4,000. Disabled unless LOG_LEVEL=DEBUG.

**Stream Writer State Inspection**: Log whether writer is None (non-streaming request) and whether it's callable. Helps diagnose streaming infrastructure issues.

**Runnable Config Propagation**: The `runnable_config` parameter from LangGraph node context is passed to `llm.astream()` to enable get_stream_writer() to function. Without this, writer will be None even in streaming requests.

**Stream Writer Error Handling**: Attempts to write each token but catches and logs errors at WARNING level, then continues. Ensures one write failure doesn't stop synthesis.

## Structured Outputs Integration

The analyze and process steps use LangChain's native `with_structured_output()` API to enforce type-safe schema validation at the API level, eliminating manual JSON parsing and improving reliability.

**Architecture Decision**:
- **Analyze Step**: Structured output enforces AnalysisOutput schema (intent, entities, complexity)
- **Process Step**: Structured output enforces ProcessOutput schema (content, confidence, metadata)
- **Synthesize Step**: No structured output—streams formatted text directly for real-time responsiveness

**LangChain Strategy Selection** (Automatic):

LangChain intelligently selects the best strategy based on model capabilities:

1. **ProviderStrategy** (Sonnet 4.5, Opus 4.1):
   - Uses Claude's native Anthropic API structured output (json_schema mode)
   - Direct API support, no extra tokens required
   - Maximum performance and accuracy

2. **ToolStrategy** (Haiku 4.5):
   - Uses tool calling to enforce schema
   - Generates ~1% additional tokens (minor overhead)
   - Transparent to application code
   - Example: 1000-token response becomes ~1010 tokens due to tool schema

**Implementation Pattern**:

```python
# Initialize LLM with configuration
llm = ChatAnthropic(
    model=config.analyze.model,  # Haiku, Sonnet, or Opus
    temperature=config.analyze.temperature,
    max_tokens=config.analyze.max_tokens,
    extra_headers={"X-Request-ID": state.get("request_id", "")},
)

# Enable structured output (LangChain selects strategy automatically)
structured_llm = llm.with_structured_output(
    AnalysisOutput,           # Pydantic model
    method="json_schema",     # Anthropic's json_schema method
    include_raw=True          # Returns (parsed, raw) tuple
)

# Invoke and extract results
result = await structured_llm.ainvoke(messages)

# Access validated output and raw message for token tracking
parsed_output = result.get("parsed")      # AnalysisOutput instance
raw_message = result.get("raw")           # AIMessage with usage_metadata

# Token tracking with raw message
input_tokens = raw_message.usage_metadata.get("input_tokens", 0)
output_tokens = raw_message.usage_metadata.get("output_tokens", 0)
cost = calculate_cost(model, input_tokens, output_tokens)
```

**Benefits**:
- **Schema Validation**: API enforces schema compliance, invalid responses caught immediately
- **Type Safety**: Parsed output is a Pydantic model instance, full IDE autocomplete
- **Token Tracking**: Raw message provides usage_metadata for cost attribution
- **Error Clarity**: ValidationError indicates schema mismatch with clear error messages
- **Consistency**: Same pattern across all steps using structured outputs
- **No Breaking Changes**: Transparent to API consumers—only internal implementation detail

**Configuration**:
- Method `json_schema` works with all Claude models (Haiku, Sonnet, Opus)
- LangChain automatically falls back to ToolStrategy if needed
- No configuration required; works out of the box
- Token overhead minimal and acceptable for reliability gains

---

## Error Handling and Recovery

Error handling spans three levels: step functions, validation gates, and graph-level recovery.

**Try/Except in Step Functions** (Reference: Lines 200-209, 335-344):

```python
try:
    response = await llm.ainvoke(messages)
    # ... processing ...
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
    raise  # Re-raise to let LangGraph route to error step
```

**Error Log Levels**:
- ERROR (40): Request-level failures (parsing errors, LLM failures, validation exceptions)
- WARNING (30): Recoverable degradation (validation gate failures, write errors)
- CRITICAL (50): Service-level failures (missing config, initialization errors)

**Step Failure Routing**:
When a step function raises an exception, LangGraph catches it and routes to the error_step node (defined in conditional edges). No automatic retry occurs—clients must retry at HTTP level.

**Error Step Recovery** (Lines 40-85 in graph.py):
```python
async def error_step(state: ChainState, config: ChainConfig) -> dict[str, Any]:
    """Handle validation or step failures with user-friendly response."""
    error_message = "An error occurred during processing. Please try again with a different request."
    logger.error(
        "Workflow error step completed",
        extra={"step": "error", "error_message": error_message[:100]},
    )
    return {
        "final_response": error_message,
        "step_metadata": {"error": {"occurred": True, "message": error_message}},
    }
```

The error_step always produces a valid final_response, preventing client-facing exceptions. State includes error metadata for monitoring.

**Circuit Breaker Pattern**: External resilience (Anthropic API failures) handled by circuit breaker middleware (see `src/workflow/api/middleware.py`). Circuit breaker catches consecutive API failures and returns 503 Service Unavailable before attempting more API calls.

---

**References and Further Reading**:
- **System Prompts**: See `../prompts/CLAUDE.md` for prompt engineering patterns and JSON output requirements
- **Data Models**: See `../models/CLAUDE.md` for ChainState structure and Pydantic model customization
- **API Integration**: See `../api/CLAUDE.md` for endpoint patterns that invoke `stream_chain()` and `invoke_chain()`
- **Logging**: See `../utils/CLAUDE.md` for logging standards and error handling patterns used in steps
- **Request Context**: See `../middleware/CLAUDE.md` for request ID and user ID propagation through workflow
- **Configuration**: See `../../../CLAUDE.md` and `../../../PROMPT-CHAINING.md` for tuning timeout, temperature, and token limits
- **Architecture**: See `../../../ARCHITECTURE.md` for validation gate design, timeout behavior, and circuit breaker integration
