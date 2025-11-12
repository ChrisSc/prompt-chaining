# Design Document

## Overview

This design document describes the architecture for refactoring the existing orchestrator-worker pattern to a prompt-chaining pattern using FastAPI, LangChain, and LangGraph. The prompt-chaining pattern decomposes complex tasks into sequential LLM calls with explicit validation gates, providing a simpler, more debuggable foundation than parallel multi-agent coordination.

The refactored system will maintain OpenAI API compatibility, streaming responses, and all production features (authentication, logging, error handling, timeouts) while replacing the parallel orchestrator-worker architecture with a sequential chain pipeline.

## Architecture

### High-Level Pattern

**Current (Orchestrator-Worker):**
```
User Request → Orchestrator → [Worker1, Worker2, ..., WorkerN] (parallel) → Synthesizer → Response
```

**New (Prompt-Chaining):**
```
User Request → Chain Step 1 (Analyze) → Validation Gate → Chain Step 2 (Process) → Validation Gate → Chain Step 3 (Synthesize) → Response
```

### Core Principles

1. **Sequential Execution**: Each step processes the output of the previous step
2. **Explicit Validation**: Programmatic gates between steps enforce business rules
3. **Composability**: Steps are pure functions with clear input/output contracts
4. **Debuggability**: Each intermediate output is inspectable and logged
5. **Streaming-First**: Token-by-token streaming throughout the chain

### Technology Stack

- **FastAPI**: HTTP server framework (unchanged)
- **LangChain**: LLM integration and composable components
  - `ChatAnthropic`: Claude API client with streaming support
  - `RunnableSequence`: Chain composition primitives
- **LangGraph**: State machine for chain orchestration
  - `StateGraph`: Defines chain steps as nodes
  - `MessagesState`: Carries context between steps
  - Conditional edges for validation gates
- **Pydantic**: Data validation and settings (unchanged)

## Components and Interfaces

### 1. Chain State

The chain state carries context and outputs between steps.

```python
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class ChainState(TypedDict):
    """State object passed between chain steps."""
    # Messages accumulate through the chain
    messages: Annotated[list[BaseMessage], add_messages]
    
    # Analysis step output
    analysis: dict[str, Any] | None
    
    # Processing step output
    processed_content: str | None
    
    # Final synthesized output
    final_response: str | None
    
    # Metadata for tracking
    step_metadata: dict[str, Any]
```

### 2. Chain Steps (LangGraph Nodes)

Each chain step is a LangGraph node that processes state and returns updates.

#### Step 1: Analyze

**Purpose**: Extract intent and key information from user request

**Input**: User message from `ChainState.messages`

**Output**: Structured analysis in `ChainState.analysis`

**Model**: Claude Haiku (fast, cheap for analysis)

**System Prompt**: `prompts/chain_analyze.md`

```python
async def analyze_step(state: ChainState) -> dict[str, Any]:
    """
    Analyze user request and extract intent.
    
    Returns:
        State update with analysis results
    """
    # Extract user message
    user_message = get_latest_user_message(state["messages"])
    
    # Call LLM with analysis prompt
    llm = ChatAnthropic(model="claude-haiku-4-5")
    response = await llm.ainvoke([
        SystemMessage(content=ANALYZE_SYSTEM_PROMPT),
        HumanMessage(content=user_message)
    ])
    
    # Parse structured output
    analysis = parse_analysis_response(response.content)
    
    # Track tokens and cost
    log_step_metrics("analyze", response.usage_metadata)
    
    return {
        "analysis": analysis,
        "messages": [response],
        "step_metadata": {
            "analyze_tokens": response.usage_metadata
        }
    }
```

#### Step 2: Process

**Purpose**: Generate response based on analysis

**Input**: `ChainState.analysis`

**Output**: Processed content in `ChainState.processed_content`

**Model**: Claude Sonnet (intelligent processing)

**System Prompt**: `prompts/chain_process.md`

```python
async def process_step(state: ChainState) -> dict[str, Any]:
    """
    Process the analyzed request and generate content.
    
    Returns:
        State update with processed content
    """
    analysis = state["analysis"]
    
    # Build prompt from analysis
    prompt = build_processing_prompt(analysis)
    
    # Call LLM with processing prompt
    llm = ChatAnthropic(model="claude-sonnet-4-5")
    response = await llm.ainvoke([
        SystemMessage(content=PROCESS_SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ])
    
    # Track tokens and cost
    log_step_metrics("process", response.usage_metadata)
    
    return {
        "processed_content": response.content,
        "messages": [response],
        "step_metadata": {
            **state["step_metadata"],
            "process_tokens": response.usage_metadata
        }
    }
```

#### Step 3: Synthesize (Streaming)

**Purpose**: Format and polish final response with streaming

**Input**: `ChainState.processed_content`

**Output**: Streamed tokens to client

**Model**: Claude Haiku (fast, cheap for formatting)

**System Prompt**: `prompts/chain_synthesize.md`

```python
async def synthesize_step(state: ChainState) -> AsyncIterator[dict[str, Any]]:
    """
    Synthesize final response with streaming.
    
    Yields:
        State updates with streamed content chunks
    """
    processed_content = state["processed_content"]
    
    # Build synthesis prompt
    prompt = build_synthesis_prompt(processed_content)
    
    # Stream LLM response
    llm = ChatAnthropic(model="claude-haiku-4-5", streaming=True)
    
    accumulated_content = ""
    usage_metadata = None
    
    async for chunk in llm.astream([
        SystemMessage(content=SYNTHESIZE_SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ]):
        accumulated_content += chunk.content
        
        # Yield streaming chunk
        yield {
            "messages": [chunk],
            "final_response": accumulated_content
        }
        
        # Capture usage metadata from final chunk
        if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
            usage_metadata = chunk.usage_metadata
    
    # Track tokens and cost
    if usage_metadata:
        log_step_metrics("synthesize", usage_metadata)
```

### 3. Validation Gates (Conditional Edges)

Validation gates enforce business rules between steps.

```python
class ValidationGate:
    """Base class for validation gates."""
    
    def __init__(self, schema: Type[BaseModel]):
        self.schema = schema
    
    async def validate(self, state: ChainState, step_output: Any) -> tuple[bool, str | None]:
        """
        Validate step output.
        
        Returns:
            (is_valid, error_message)
        """
        try:
            # Validate against Pydantic schema
            self.schema.model_validate(step_output)
            return True, None
        except ValidationError as e:
            return False, str(e)

class AnalysisValidationGate(ValidationGate):
    """Validates analysis step output."""
    
    def __init__(self):
        super().__init__(AnalysisOutput)
    
    async def validate(self, state: ChainState, step_output: Any) -> tuple[bool, str | None]:
        """Validate analysis contains required fields."""
        is_valid, error = await super().validate(state, step_output)
        
        if not is_valid:
            return False, error
        
        # Additional business logic validation
        analysis = state["analysis"]
        if not analysis.get("intent"):
            return False, "Analysis must contain intent"
        
        return True, None

# Conditional edge function for LangGraph
def should_proceed_to_process(state: ChainState) -> str:
    """
    Determine if chain should proceed to process step.
    
    Returns:
        "process" if valid, "error" if invalid
    """
    gate = AnalysisValidationGate()
    is_valid, error = await gate.validate(state, state["analysis"])
    
    if is_valid:
        return "process"
    else:
        logger.error(f"Analysis validation failed: {error}")
        return "error"
```

### 4. LangGraph State Machine

The state machine orchestrates the chain with validation gates.

```python
from langgraph.graph import StateGraph, START, END

def build_chain_graph() -> StateGraph:
    """
    Build the prompt chain as a LangGraph state machine.
    
    Returns:
        Compiled state graph
    """
    # Create graph with ChainState
    graph = StateGraph(ChainState)
    
    # Add chain step nodes
    graph.add_node("analyze", analyze_step)
    graph.add_node("process", process_step)
    graph.add_node("synthesize", synthesize_step)
    graph.add_node("error", error_step)
    
    # Add edges with validation gates
    graph.add_edge(START, "analyze")
    
    # Conditional edge: analyze → process (if valid) or error (if invalid)
    graph.add_conditional_edges(
        "analyze",
        should_proceed_to_process,
        {
            "process": "process",
            "error": "error"
        }
    )
    
    # Conditional edge: process → synthesize (if valid) or error (if invalid)
    graph.add_conditional_edges(
        "process",
        should_proceed_to_synthesize,
        {
            "synthesize": "synthesize",
            "error": "error"
        }
    )
    
    # Final edges
    graph.add_edge("synthesize", END)
    graph.add_edge("error", END)
    
    # Compile graph
    return graph.compile()
```

### 5. FastAPI Integration

The FastAPI endpoint invokes the chain and streams responses.

```python
from fastapi import FastAPI, Depends
from fastapi.responses import StreamingResponse
from langgraph.graph import CompiledStateGraph

app = FastAPI()

# Initialize chain graph at startup
chain_graph: CompiledStateGraph | None = None

@app.on_event("startup")
async def startup():
    global chain_graph
    chain_graph = build_chain_graph()
    logger.info("Prompt chain initialized")

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    user: dict = Depends(verify_jwt_token)
) -> StreamingResponse:
    """
    OpenAI-compatible chat completions endpoint with prompt chaining.
    """
    # Build initial state from request
    initial_state = {
        "messages": convert_openai_messages(request.messages),
        "analysis": None,
        "processed_content": None,
        "final_response": None,
        "step_metadata": {}
    }
    
    # Stream chain execution
    async def generate_stream():
        try:
            # Stream with mode="messages" for token-by-token
            async for chunk in chain_graph.astream(
                initial_state,
                stream_mode="messages"
            ):
                # Convert LangChain message to OpenAI format
                openai_chunk = convert_to_openai_chunk(chunk)
                
                # Yield SSE formatted chunk
                yield f"data: {openai_chunk.model_dump_json()}\n\n"
            
            # Send final [DONE] marker
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"Chain execution failed: {e}")
            error_chunk = create_error_chunk(str(e))
            yield f"data: {error_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream"
    )
```

## Data Models

### Chain-Specific Models

```python
from pydantic import BaseModel, Field

class AnalysisOutput(BaseModel):
    """Output schema for analysis step."""
    intent: str = Field(description="User's primary intent")
    key_entities: list[str] = Field(description="Key entities mentioned")
    complexity: str = Field(description="Task complexity: simple, moderate, complex")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context")

class ProcessOutput(BaseModel):
    """Output schema for process step."""
    content: str = Field(description="Generated content")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")
    metadata: dict[str, Any] = Field(default_factory=dict)

class SynthesisOutput(BaseModel):
    """Output schema for synthesis step."""
    final_text: str = Field(description="Polished final response")
    formatting: str = Field(description="Applied formatting style")
```

### Configuration Models

```python
class ChainStepConfig(BaseModel):
    """Configuration for a single chain step."""
    model: str
    max_tokens: int
    temperature: float
    system_prompt_file: str

class ChainConfig(BaseModel):
    """Configuration for the entire chain."""
    analyze: ChainStepConfig
    process: ChainStepConfig
    synthesize: ChainStepConfig
    
    # Timeout settings
    analyze_timeout: int = 15
    process_timeout: int = 30
    synthesize_timeout: int = 20
    
    # Validation settings
    enable_validation: bool = True
    strict_validation: bool = False
```

## Error Handling

### Error Types

```python
class ChainExecutionError(Exception):
    """Base exception for chain execution errors."""
    pass

class ValidationGateError(ChainExecutionError):
    """Raised when validation gate fails."""
    def __init__(self, step: str, message: str):
        self.step = step
        self.message = message
        super().__init__(f"Validation failed at {step}: {message}")

class ChainTimeoutError(ChainExecutionError):
    """Raised when chain step exceeds timeout."""
    def __init__(self, step: str, timeout: int):
        self.step = step
        self.timeout = timeout
        super().__init__(f"Step {step} exceeded timeout of {timeout}s")
```

### Error Step Node

```python
async def error_step(state: ChainState) -> dict[str, Any]:
    """
    Handle errors in the chain.
    
    Returns:
        State update with error message
    """
    # Extract error information from state
    error_msg = state.get("error_message", "Unknown error occurred")
    failed_step = state.get("failed_step", "unknown")
    
    logger.error(
        f"Chain failed at step: {failed_step}",
        extra={
            "step": failed_step,
            "error": error_msg,
            "state": state
        }
    )
    
    # Return error response
    return {
        "final_response": f"Error: {error_msg}",
        "messages": [
            AIMessage(content=f"I encountered an error: {error_msg}")
        ]
    }
```

## Testing Strategy

### Unit Tests

1. **Chain Step Tests**: Test each step in isolation with mocked LLM responses
2. **Validation Gate Tests**: Test validation logic with valid and invalid inputs
3. **State Transition Tests**: Test state updates between steps
4. **Error Handling Tests**: Test error scenarios and recovery

### Integration Tests

1. **End-to-End Chain Tests**: Test complete chain execution with real LLM calls
2. **Streaming Tests**: Verify token-by-token streaming works correctly
3. **Timeout Tests**: Verify timeout enforcement at each step
4. **Authentication Tests**: Verify JWT authentication still works

### Test Fixtures

```python
@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing."""
    return AIMessage(
        content="Test response",
        usage_metadata={
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30
        }
    )

@pytest.fixture
def sample_chain_state():
    """Sample chain state for testing."""
    return ChainState(
        messages=[HumanMessage(content="Test message")],
        analysis={"intent": "test", "key_entities": []},
        processed_content=None,
        final_response=None,
        step_metadata={}
    )

@pytest.fixture
def chain_graph():
    """Compiled chain graph for testing."""
    return build_chain_graph()
```

## Configuration

### Environment Variables

```bash
# Chain step models
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_PROCESS_MODEL=claude-sonnet-4-5-20250929
CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001

# Chain step parameters
CHAIN_ANALYZE_MAX_TOKENS=1000
CHAIN_ANALYZE_TEMPERATURE=0.3
CHAIN_PROCESS_MAX_TOKENS=2000
CHAIN_PROCESS_TEMPERATURE=0.7
CHAIN_SYNTHESIZE_MAX_TOKENS=1000
CHAIN_SYNTHESIZE_TEMPERATURE=0.5

# Timeout settings (seconds)
CHAIN_ANALYZE_TIMEOUT=15
CHAIN_PROCESS_TIMEOUT=30
CHAIN_SYNTHESIZE_TIMEOUT=20

# Validation settings
CHAIN_ENABLE_VALIDATION=true
CHAIN_STRICT_VALIDATION=false

# Existing settings (unchanged)
ANTHROPIC_API_KEY=<key>
JWT_SECRET_KEY=<secret>
LOG_LEVEL=INFO
```

### Settings Class

```python
class Settings(BaseSettings):
    """Application settings with chain configuration."""
    
    # Existing settings
    anthropic_api_key: str
    jwt_secret_key: str
    log_level: str = "INFO"
    
    # Chain step models
    chain_analyze_model: str = "claude-haiku-4-5-20251001"
    chain_process_model: str = "claude-sonnet-4-5-20250929"
    chain_synthesize_model: str = "claude-haiku-4-5-20251001"
    
    # Chain step parameters
    chain_analyze_max_tokens: int = 1000
    chain_analyze_temperature: float = 0.3
    chain_process_max_tokens: int = 2000
    chain_process_temperature: float = 0.7
    chain_synthesize_max_tokens: int = 1000
    chain_synthesize_temperature: float = 0.5
    
    # Timeout settings
    chain_analyze_timeout: int = 15
    chain_process_timeout: int = 30
    chain_synthesize_timeout: int = 20
    
    # Validation settings
    chain_enable_validation: bool = True
    chain_strict_validation: bool = False
    
    @property
    def chain_config(self) -> ChainConfig:
        """Build chain configuration from settings."""
        return ChainConfig(
            analyze=ChainStepConfig(
                model=self.chain_analyze_model,
                max_tokens=self.chain_analyze_max_tokens,
                temperature=self.chain_analyze_temperature,
                system_prompt_file="chain_analyze.md"
            ),
            process=ChainStepConfig(
                model=self.chain_process_model,
                max_tokens=self.chain_process_max_tokens,
                temperature=self.chain_process_temperature,
                system_prompt_file="chain_process.md"
            ),
            synthesize=ChainStepConfig(
                model=self.chain_synthesize_model,
                max_tokens=self.chain_synthesize_max_tokens,
                temperature=self.chain_synthesize_temperature,
                system_prompt_file="chain_synthesize.md"
            ),
            analyze_timeout=self.chain_analyze_timeout,
            process_timeout=self.chain_process_timeout,
            synthesize_timeout=self.chain_synthesize_timeout,
            enable_validation=self.chain_enable_validation,
            strict_validation=self.chain_strict_validation
        )
```

## Migration Strategy

### Phase 1: Add LangChain/LangGraph Dependencies

- Add `langchain`, `langchain-anthropic`, `langgraph` to dependencies
- Update `pyproject.toml`
- Test dependency installation

### Phase 2: Implement Chain Components

- Create chain state models
- Implement chain step functions
- Implement validation gates
- Build LangGraph state machine

### Phase 3: Update FastAPI Integration

- Modify `/v1/chat/completions` endpoint to use chain
- Update startup/shutdown hooks
- Preserve middleware stack

### Phase 4: Update Configuration

- Add chain-specific settings
- Update `.env.example`
- Update configuration documentation

### Phase 5: Update Documentation

- Update ARCHITECTURE.md with prompt-chaining pattern
- Update README.md with new examples
- Create migration guide from orchestrator-worker

### Phase 6: Testing and Validation

- Run unit tests
- Run integration tests
- Validate streaming behavior
- Verify authentication and middleware

## Performance Considerations

### Latency

- **Sequential vs Parallel**: Chain will be slower than parallel workers for independent tasks
- **Optimization**: Use faster models (Haiku) for analysis and synthesis steps
- **Streaming**: Maintain token-by-token streaming to preserve perceived responsiveness

### Cost

- **Model Selection**: Use Haiku for simple steps, Sonnet only for complex processing
- **Token Efficiency**: Focused prompts per step reduce total token usage
- **Validation**: Early validation gates prevent wasted API calls on invalid inputs

### Scalability

- **Stateless**: Each request is independent, enabling horizontal scaling
- **Async**: FastAPI + async LangChain enables high concurrency
- **Caching**: Consider caching analysis results for similar requests

## Security Considerations

### Preserved Security Features

- JWT authentication on protected endpoints
- Request size validation middleware
- Security headers middleware
- Rate limiting per user
- Circuit breaker for API resilience

### New Security Considerations

- **Validation Gates**: Prevent injection attacks by validating step outputs
- **Timeout Enforcement**: Per-step timeouts prevent resource exhaustion
- **Error Sanitization**: Validation errors don't expose sensitive data

## Observability

### Logging

- Log each chain step execution with timing and token usage
- Log validation gate results (pass/fail with reasons)
- Aggregate metrics across all steps
- Maintain request ID propagation through chain

### Metrics

- Step execution time per step
- Token usage per step and total
- Cost per step and total
- Validation failure rate per gate
- Error rate per step

### Example Log Output

```json
{
  "timestamp": "2025-11-11T10:00:00Z",
  "level": "INFO",
  "request_id": "req_123",
  "step": "analyze",
  "duration_ms": 1200,
  "input_tokens": 50,
  "output_tokens": 100,
  "cost_usd": 0.0001,
  "validation": "passed"
}
```

## Future Enhancements

### Dynamic Chain Composition

- Allow runtime chain configuration based on request complexity
- Support conditional step execution (skip steps based on analysis)
- Enable parallel sub-chains for independent tasks

### Advanced Validation

- Schema evolution and versioning
- Custom validation plugins
- Validation result caching

### Observability

- LangSmith integration for chain visualization
- Distributed tracing across chain steps
- Performance profiling per step

### Optimization

- Response caching for common patterns
- Batch processing for multiple requests
- Adaptive timeout adjustment based on historical data

### Documentation
**THE Code SHALL follow curated documentation:**
- **FastAPI:** ./documentation/fastapi/INDEX_AGENT.md
- **LangChain:** ./documentation/langchain/INDEX.md
- **Pydantic:** ./documentation/pydantic/LLM_INDEX.md
