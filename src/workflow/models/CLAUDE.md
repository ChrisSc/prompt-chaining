# Models Layer: Data Structures, Pydantic Patterns, Two-Layer Architecture

**Location**: `src/workflow/models/`

**Purpose**: Data model architecture, Pydantic validation patterns, and model customization guidance.

## Navigation

- **Parent**: See `../../CLAUDE.md` for project overview
- **Related Files**:
  - `../chains/CLAUDE.md` - ChainState usage in workflow
  - `../prompts/CLAUDE.md` - Prompt output must match these models
  - `../api/CLAUDE.md` - OpenAI models for API contract

## Two-Layer Model Architecture

The models layer implements a critical separation between external API compatibility and internal domain logic:

**External Layer** (`models/openai.py`): OpenAI-compatible data structures that define the public API contract. These models ensure that the service works seamlessly with OpenAI API clients, tools like Open WebUI, and any standard chat completion consumers. This layer prioritizes compatibility over domain-specific detail.

**Internal Layer** (`models/chains.py`): Domain-specific data models that drive workflow logic. These models capture the analysis outputs, processing results, synthesis state, and configuration needed for multi-step orchestration. The internal layer has no constraints from external API requirements—it evolves freely based on workflow needs.

This separation enables several key benefits:

1. **API Evolution Independence**: The OpenAI compatibility layer stays stable while internal models evolve for domain needs
2. **No Leakage of Internal Concerns**: Workflow-specific metadata (confidence scores, validation metadata) stays internal
3. **Cleaner Customization**: When extending for your domain, you customize internal models without affecting clients
4. **Model Mapping**: Adapters between layers handle translation (synthesis output → chat completion chunk)

**When to Extend vs. Create**:
- Extending `AnalysisOutput`, `ProcessOutput`, or `SynthesisOutput`: Add domain-specific fields you'll use in subsequent steps
- Creating new internal models: For supporting data structures (lookup results, external API responses) that aren't step outputs
- Modifying OpenAI models: Only when updating to align with newer OpenAI API versions (rare)

**Model Evolution Through Workflow**:
The workflow receives a `ChatCompletionRequest` (OpenAI layer), internally processes through `ChainState` (internal layer), and returns data via `ChatCompletionChunk` streaming messages. Each step updates internal state models, and only the final response maps to OpenAI format.

## OpenAI Compatibility Layer

File: `src/workflow/models/openai.py`

The OpenAI layer defines the public contract—request structures and streaming response formats that match OpenAI's official specification.

**ChatMessage and MessageRole** (Lines 12-28):
```python
class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"

class ChatMessage(BaseModel):
    role: MessageRole = Field(description="Role of the message sender")
    content: str = Field(description="Message content")
```

Standard OpenAI message structure with role enumeration. Role field validates against allowed values, preventing invalid roles from entering the system.

**ChatCompletionRequest** (Lines 31-61):
```python
class ChatCompletionRequest(BaseModel):
    model: str = Field(description="Model identifier")
    messages: list[ChatMessage] = Field(description="Conversation messages")
    temperature: float | None = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=4096, ge=1, le=8000)
    top_p: float | None = Field(default=1.0, ge=0.0, le=1.0)
    stream: bool | None = Field(default=False)
```

Captures client configuration for model selection, temperature (0.0 = deterministic, 2.0 = highly creative), output size limits, and streaming preference. All numeric fields have bounds constraints—Pydantic validation rejects requests outside these ranges before reaching the workflow.

**Streaming Response Models** (Lines 64-105):

`ChoiceDelta`: Represents incremental text updates:
```python
class ChoiceDelta(BaseModel):
    role: MessageRole | None = Field(default=None)  # Only in first chunk
    content: str | None = Field(default=None)        # Text delta
```

`ChatCompletionStreamChoice`: Wraps delta in choice structure:
```python
class ChatCompletionStreamChoice(BaseModel):
    index: int = Field(description="Choice index")
    delta: ChoiceDelta = Field(description="Incremental content")
    finish_reason: str | None = Field(default=None)  # "stop" in final chunk
```

`ChatCompletionChunk`: Complete streaming message sent as Server-Sent Event:
```python
class ChatCompletionChunk(BaseModel):
    id: str = Field(description="Stream ID")
    object: str = Field(default="chat.completion.chunk")
    created: int = Field(description="Unix timestamp")
    model: str = Field(description="Model used")
    choices: list[ChatCompletionStreamChoice]
    usage: dict[str, int] | None = Field(default=None)  # Only in final chunk
```

Each chunk is sent as `data: {ChatCompletionChunk}\n\n` followed by `data: [DONE]\n\n` at stream end.

## Internal Domain Models

File: `src/workflow/models/chains.py`

Internal models drive the workflow logic and capture domain-specific information at each step.

**ChainState TypedDict** (Lines 29-64):

The central state container maintained by LangGraph across all steps:

```python
class ChainState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    request_id: str                              # Trace ID for all logs
    user_id: str                                 # From JWT sub claim
    analysis: dict[str, Any] | None              # AnalysisOutput.model_dump()
    processed_content: str | None                # ProcessOutput.model_dump()
    final_response: str | None                   # SynthesisOutput.final_text
    step_metadata: dict[str, Any]                # Timing, tokens, costs per step
```

The `messages` field uses `add_messages` reducer to accumulate LLM responses, enabling conversation-like context passing. All other fields get populated step-by-step. Reference: `../chains/CLAUDE.md` for state evolution details.

**AnalysisOutput** (Lines 69-88):

Output from the analyze step—extracts intent, entities, and task complexity:

```python
class AnalysisOutput(BaseModel):
    intent: str = Field(description="User's primary goal")
    key_entities: list[str] = Field(description="Topics/concepts mentioned")
    complexity: str = Field(description="Level: simple, moderate, or complex")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context discovered"
    )
```

Fields enable routing to appropriate processing strategies (simple tasks can use Haiku, complex tasks might upgrade to Sonnet). `context` field stores optional discovery data for later steps. Validation gates check that `intent` is non-empty before proceeding.

**ProcessOutput** (Lines 91-109):

Output from the processing step—generated content with confidence:

```python
class ProcessOutput(BaseModel):
    content: str = Field(description="Generated content")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Quality confidence 0.0-1.0"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Generation metadata (sources, tokens, etc.)"
    )
```

Confidence field enables quality gates (validation rejects if confidence < 0.5). Metadata field captures internal processing details (source documents, reasoning steps) without exposing them to external API.

**SynthesisOutput** (Lines 112-123):

Output from the synthesis step—polished final response:

```python
class SynthesisOutput(BaseModel):
    final_text: str = Field(description="Formatted response")
    formatting: str = Field(description="Applied style/template")
```

Maps directly to SSE chunks—`final_text` becomes the chat message content streamed to client. `formatting` field documents the template applied (useful for consistency tracking).

**ChainStepConfig** (Lines 128-148):

Configuration for a single step:

```python
class ChainStepConfig(BaseModel):
    model: str = Field(description="Claude model ID")
    max_tokens: int = Field(ge=1, description="Output token limit")
    temperature: float = Field(
        ge=0.0,
        le=2.0,
        description="Sampling: 0.0-2.0"
    )
    system_prompt_file: str = Field(description="Prompt filename in prompts/")
```

Each step gets independent configuration—allows using Haiku for fast analysis, Sonnet for complex processing, then Haiku again for synthesis. Temperature per-step enables precise vs. creative tuning. System prompt file names are loaded at runtime via `load_system_prompt()`.

**ChainConfig** (Lines 151-191):

Complete workflow configuration orchestrating all three steps:

```python
class ChainConfig(BaseModel):
    analyze: ChainStepConfig = Field(description="Analyze step config")
    process: ChainStepConfig = Field(description="Process step config")
    synthesize: ChainStepConfig = Field(description="Synthesize step config")
    analyze_timeout: int = Field(default=15, ge=1, le=270)
    process_timeout: int = Field(default=30, ge=1, le=270)
    synthesize_timeout: int = Field(default=20, ge=1, le=270)
    enable_validation: bool = Field(default=True)
    strict_validation: bool = Field(default=False)
    min_confidence_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score for process validation gate (0.0-1.0)"
    )
```

Timeouts set per-step—allows slow reasoning steps longer timeout than fast synthesis. Validation gates can be disabled for testing or strict mode enforced for production safety. Confidence threshold controls quality gates in the process validation gate. Loaded from environment variables in `src/workflow/config.py`.

## Structured Outputs and Pydantic Models

The analyze and process steps use LangChain's `with_structured_output()` API with Pydantic models to enforce schema validation at the API level. This integration is seamless and transparent.

**How It Works**:

1. **Model Definition**: Pydantic models (AnalysisOutput, ProcessOutput) define the schema
2. **Schema Conversion**: LangChain converts Pydantic model to JSON Schema for the API
3. **API Enforcement**: Claude API validates response against schema (ProviderStrategy for Sonnet/Opus, ToolStrategy for Haiku)
4. **Automatic Parsing**: LangChain deserializes JSON response into Pydantic model instance
5. **Type Safety**: Result is fully typed Pydantic instance with validation

**Token Tracking with Structured Outputs**:

The `include_raw=True` parameter is critical for token tracking:

```python
# Enable structured output with raw message access
structured_llm = llm.with_structured_output(
    AnalysisOutput,
    method="json_schema",
    include_raw=True  # Essential for token tracking
)

# Invoke returns dict with 'parsed' and 'raw'
result = await structured_llm.ainvoke(messages)

# Access validated model and raw message
analysis = result.get("parsed")      # AnalysisOutput instance
raw_msg = result.get("raw")          # AIMessage with usage_metadata

# Extract token usage from raw message
input_tokens = raw_msg.usage_metadata.get("input_tokens", 0)
output_tokens = raw_msg.usage_metadata.get("output_tokens", 0)
```

**Field Descriptions Matter**:

With structured outputs, Pydantic Field descriptions become schema documentation visible to the API. Always include clear descriptions:

```python
class AnalysisOutput(BaseModel):
    intent: str = Field(
        description="User's primary goal or intent"  # Used as schema doc
    )
    key_entities: list[str] = Field(
        description="Important topics, concepts, or entities mentioned"
    )
    complexity: str = Field(
        description="Task complexity level: simple, moderate, or complex"
    )
```

The API uses these descriptions to guide response generation, so clear, specific descriptions improve schema compliance.

---

## Pydantic Validation Patterns

All models use Pydantic 2.x validation with Field() constraints and type annotations.

**Field Constraints**:
```python
# Numeric bounds
max_tokens: int = Field(ge=1, le=8000, description="...")
confidence: float = Field(ge=0.0, le=1.0, description="...")
temperature: float = Field(ge=0.0, le=2.0, description="...")

# Required vs. Optional
intent: str                                    # Required (no default)
context: dict = Field(default_factory=dict)   # Optional (empty dict default)
metadata: dict | None = Field(default=None)   # Optional (None default)
```

**Type Annotations and Validation**:
- `str`: Validates non-empty string (Pydantic raises ValueError on empty)
- `int`: Validates integer type
- `list[str]`: Validates list of strings
- `dict[str, Any]`: Validates dictionary with string keys
- `float | None`: Union types allow None or float (optional fields)

**Enum Usage for Constrained Values**:
```python
class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"

role: MessageRole  # Validation enforces one of three values
```

Enums prevent invalid values from entering the system. Client passing `role: "invalid"` gets Pydantic validation error before reaching workflow.

**Nested Models and Composition**:
```python
class ChatCompletionRequest(BaseModel):
    messages: list[ChatMessage]   # Nests ChatMessage model

class ChainConfig(BaseModel):
    analyze: ChainStepConfig      # Nests configuration model
    process: ChainStepConfig
    synthesize: ChainStepConfig
```

Pydantic validates nested structures recursively—invalid nested data fails at the boundary.

**Model Serialization**:
```python
output = AnalysisOutput(intent="...", key_entities=[], complexity="simple")

# Convert to dict for ChainState storage
state["analysis"] = output.model_dump()

# Convert to JSON for logging
json_str = output.model_dump_json()

# Reconstruct from dict
restored = AnalysisOutput.model_validate(state["analysis"])
```

Use `model_dump()` for dict conversion (for state storage) and `model_dump_json()` for JSON serialization. `model_validate()` reconstructs from dict with full validation.

## Model Customization Guidance

Customize internal models for your domain without affecting API compatibility.

**Extending AnalysisOutput for Domain Entities**:

Base model extracts generic intent/entities/complexity. For a document analysis domain, extend to capture document-specific details:

```python
# In src/workflow/models/chains.py
class AnalysisOutput(BaseModel):
    intent: str
    key_entities: list[str]
    complexity: str
    context: dict[str, Any] = Field(default_factory=dict)

    # Add domain-specific fields
    document_type: str = Field(description="Type: report, email, code, etc.")
    language: str = Field(description="Detected language")
    sentiment: str = Field(description="Overall tone: positive, neutral, negative")
```

Update `chain_analyze.md` prompt to output the new fields as JSON, matching the updated schema.

**Adding Fields to ProcessOutput**:

Base model produces content + confidence. For a research assistant, add source tracking:

```python
class ProcessOutput(BaseModel):
    content: str
    confidence: float
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Add custom metadata fields
    sources_used: list[str] = Field(
        default_factory=list,
        description="List of reference sources"
    )
    citations_count: int = Field(default=0, description="Number of citations")
    requires_review: bool = Field(
        default=False,
        description="Flag if content needs human review"
    )
```

The process step's LLM outputs these new fields in JSON, and validation gates can check `requires_review` before proceeding to synthesis.

**Updating ChainConfig for Domain Parameters**:

Base model configures models and timeouts. Add domain-specific settings:

```python
class ChainConfig(BaseModel):
    analyze: ChainStepConfig
    process: ChainStepConfig
    synthesize: ChainStepConfig
    analyze_timeout: int = Field(default=15, ge=1, le=270)
    process_timeout: int = Field(default=30, ge=1, le=270)
    synthesize_timeout: int = Field(default=20, ge=1, le=270)
    enable_validation: bool = Field(default=True)
    strict_validation: bool = Field(default=False)

    # Add domain settings
    min_confidence_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for proceeding"
    )
    max_sources_allowed: int = Field(
        default=10,
        ge=1,
        description="Maximum sources for fact-checking"
    )
    enable_citations: bool = Field(
        default=True,
        description="Require citations in output"
    )
```

Load these from environment variables in `src/workflow/config.py` (e.g., `MIN_CONFIDENCE_THRESHOLD`).

**Maintaining Pydantic Validation**:

Always use Field() with descriptions and constraints:
```python
# Good
sources_used: list[str] = Field(
    default_factory=list,
    description="Source documents used in processing"
)

# Avoid
sources_used: list = []  # No type hint, no description, mutable default
```

Type hints enable IDE autocomplete and mypy type checking. Descriptions appear in auto-generated API docs.

**Testing Customized Models**:

Create tests to verify extended models work end-to-end:

```python
# tests/test_models_custom.py
from workflow.models.chains import AnalysisOutput

def test_analysis_output_with_custom_fields():
    output = AnalysisOutput(
        intent="analyze document",
        key_entities=["PDF", "contract"],
        complexity="moderate",
        document_type="legal",
        language="en",
        sentiment="neutral"
    )

    # Verify all fields present
    assert output.document_type == "legal"
    assert output.sentiment == "neutral"

    # Verify serialization works
    dumped = output.model_dump()
    assert dumped["document_type"] == "legal"

    # Verify reconstruction
    restored = AnalysisOutput.model_validate(dumped)
    assert restored.sentiment == "neutral"
```

Run tests in CI/CD to catch schema mismatches early.

**Updating Prompts for New Schema**:

When extending models, update system prompts to output the new fields. Example:

```json
{
  "intent": "analyze this legal document",
  "key_entities": ["contract", "party names", "dates"],
  "complexity": "moderate",
  "context": {"page_count": 15},
  "document_type": "legal",
  "language": "en",
  "sentiment": "formal"
}
```

Prompt must output valid JSON matching your updated Pydantic schema, or validation will fail with helpful error messages.

---

**References and Further Reading**:
- **Workflow State Usage**: See `../chains/CLAUDE.md` "ChainState Structure and Evolution" for state evolution through steps
- **Prompt Output Requirements**: See `../prompts/CLAUDE.md` for JSON validation and Pydantic model alignment
- **API Contract**: See `../api/CLAUDE.md` for OpenAI ChatCompletionRequest/ChatCompletionChunk models
- **Step Execution**: See `../chains/CLAUDE.md` for how step functions parse and validate model outputs
- **Request Context**: See `../middleware/CLAUDE.md` for how request_id and user_id flow into ChainState
- **Logging and Errors**: See `../utils/CLAUDE.md` for error handling and token tracking utilities
- **Configuration**: See `../../../config.py` for ChainConfig loading from environment variables
- **Architecture**: See `../../../ARCHITECTURE.md` for model design decisions and customization patterns
