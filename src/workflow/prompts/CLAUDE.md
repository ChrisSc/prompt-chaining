# Prompts Layer: Prompt Engineering, System Prompts, JSON Output Patterns

**Location**: `src/workflow/prompts/`

**Purpose**: Prompt design patterns, JSON output requirements, and step-specific prompt engineering guidance for multi-step AI workflows.

## Navigation

- **Parent**: See `../../CLAUDE.md` for project overview
- **Related Files**:
  - `../chains/CLAUDE.md` - Step execution, prompt loading, and workflow orchestration
  - `../models/CLAUDE.md` - Output models that prompts must match (AnalysisOutput, ProcessOutput, SynthesisOutput)
  - `../utils/CLAUDE.md` - Logging patterns for prompt failures and error handling

---

## System Prompt Structure and Conventions

All system prompts in this layer are stored as Markdown files in `src/workflow/prompts/` and loaded dynamically by the workflow at runtime.

**File Naming Convention**

System prompts follow the naming pattern `chain_<step>.md`:
- `chain_analyze.md` - First step: intent extraction and analysis
- `chain_process.md` - Second step: content generation
- `chain_synthesize.md` - Third step: formatting and polish

**Loading Mechanism**

The `load_prompt()` function in `src/workflow/utils/prompts.py` loads prompts from disk:

```python
from workflow.utils.prompts import load_prompt

# Loads src/workflow/prompts/chain_analyze.md
system_prompt = load_prompt("chain_analyze")
```

**Prompt File Structure**

Each system prompt file should contain:
1. **Role Definition**: Clear statement of the agent's purpose and position in the workflow
2. **Responsibilities**: Numbered list of specific tasks the agent must perform
3. **Guidelines**: Best practices and constraints for execution
4. **Output Format Specification**: Exact JSON schema expected (with examples)
5. **Examples**: Concrete input/output pairs demonstrating expected behavior
6. **Important Notes**: Critical warnings about output formatting

**Output Format Requirement**

Every system prompt (analyze and process steps) must specify that output is **ONLY JSON** with no markdown wrappers:
- Output raw JSON (not inside ` ```json ... ``` ` code blocks)
- No additional explanatory text before or after JSON
- All required fields must be present
- Field names must match Pydantic model exactly
- Enum values must be from the defined set

**Note on Structured Outputs**: With LangChain's `with_structured_output()` API, the Claude API itself validates schema compliance. You no longer need to worry about JSON parsing errors—the API enforces the schema. This simplifies prompts: just focus on the content, and the schema is guaranteed to be valid.

---

## JSON Output Requirements

The prompt-chaining pattern relies on strict JSON output validation. Each step's LLM output must be valid JSON that matches the corresponding Pydantic model schema exactly.

**Critical Requirements**

1. **Output ONLY Valid JSON**
   - No markdown code blocks (` ```json ... ``` `)
   - No explanatory text before or after JSON
   - No trailing comments or additional text
   - Single valid JSON object per response

2. **Field Name Matching**
   - Field names must exactly match model definition (case-sensitive)
   - No extra fields are allowed
   - All required fields must be present
   - Typos in field names cause ValidationError

3. **Type Compliance**
   - String fields must be quoted strings (e.g., `"intent": "user wants..."`)
   - Numeric fields must be unquoted numbers (e.g., `"confidence": 0.85`)
   - Array fields must use `[]` syntax (e.g., `"key_entities": ["topic1", "topic2"]`)
   - Object fields must use `{}` syntax (e.g., `"context": {"domain": "value"}`)
   - Enum fields must use exact string value (e.g., `"complexity": "moderate"`)

4. **Validation and Error Handling**
   - JSON parsing happens in `src/workflow/chains/steps.py` for each step
   - ValidationError is caught and logged at ERROR level with truncated response
   - Invalid JSON causes request to fail with HTTP 503
   - Example log: `"Failed to parse analysis step response"` with error_type and response snippet

**Good vs. Bad Examples**

```json
// GOOD: Valid JSON, all fields present, correct types
{
  "intent": "Understand Python and its popularity",
  "key_entities": ["Python", "programming language"],
  "complexity": "simple",
  "context": {"domain": "programming"}
}

// BAD: Missing required context field
{
  "intent": "Understand Python and its popularity",
  "key_entities": ["Python", "programming language"],
  "complexity": "simple"
}

// BAD: Field name typo (should be "intent", not "user_intent")
{
  "user_intent": "Understand Python and its popularity",
  "key_entities": ["Python"],
  "complexity": "simple",
  "context": {}
}

// BAD: Markdown code block wrapper (prompts must output raw JSON only)
```json
{
  "intent": "Understand Python",
  "key_entities": ["Python"],
  "complexity": "simple",
  "context": {}
}
```

// BAD: Trailing explanation text
{
  "intent": "Understand Python",
  "key_entities": ["Python"],
  "complexity": "simple",
  "context": {}
}

This analysis correctly identifies the three key aspects...
```

---

## Pydantic Model Alignment

Each step's system prompt must align exactly with its output model. This ensures JSON validation succeeds and enables strict contract enforcement between steps.

**AnalysisOutput Model Schema** (from `src/workflow/models/chains.py`)

```python
class AnalysisOutput(BaseModel):
    intent: str
    key_entities: list[str]
    complexity: str  # Must be: "simple", "moderate", or "complex"
    context: dict[str, Any] = {}  # Optional, defaults to empty dict
```

Required fields: `intent`, `key_entities`, `complexity`
Optional field: `context` (defaults to empty `{}`)

**ProcessOutput Model Schema**

```python
class ProcessOutput(BaseModel):
    content: str
    confidence: float  # Must be 0.0 to 1.0
    metadata: dict[str, Any] = {}  # Optional, defaults to empty dict
```

Required fields: `content`, `confidence`
Optional field: `metadata` (defaults to empty `{}`)

Type constraint on confidence: `0.0 <= confidence <= 1.0` (enforced by Pydantic)

**SynthesisOutput Model Schema**

```python
class SynthesisOutput(BaseModel):
    final_text: str
    formatting: str  # Values: "markdown", "plain", "structured"
```

Required fields: `final_text`, `formatting`
All fields are required for this step.

**Type Constraints and Validation**

- **Enum-like fields**: `complexity` (simple/moderate/complex), `formatting` (markdown/plain/structured)
- **Numeric ranges**: `confidence` must be float between 0.0 and 1.0
- **String lengths**: No explicit length constraints in models, but process content should be substantive (>100 chars)
- **Default values**: `context` and `metadata` default to empty dict `{}` when omitted
- **Validation errors**: When JSON doesn't match schema, logging captures error_type, error message, and truncated response

---

## Analysis Prompt Patterns

The analysis step is the entry point for the workflow. It extracts structure from unstructured user input, enabling subsequent steps to generate focused, relevant content.

**Role and Responsibilities**

The analysis agent receives a user request and extracts:
1. **Intent**: What the user wants to accomplish (single clear goal)
2. **Key Entities**: Topics, concepts, or specific items to address (1-5 items)
3. **Complexity Assessment**: Simple, moderate, or complex (determines depth for process step)
4. **Context**: Additional information about constraints, domain, or requirements

**Complexity Levels and Guidance**

Use these descriptions to guide complexity assessment:

- **Simple** (~1-2 paragraphs): Straightforward, single-domain requests requiring basic explanation
  - Example: "What is Python?" → simple (basic definition only)
  - Example: "Explain loops in Python" → simple (one concept, clear answer)

- **Moderate** (~3-4 paragraphs): Multi-faceted requests with balanced depth and reasoning
  - Example: "Compare synchronous vs asynchronous programming for web APIs handling 1000 QPS" → moderate (requires comparison, performance analysis, trade-offs)
  - Example: "Design a caching strategy for a web application" → moderate (multiple considerations, but focused scope)

- **Complex** (>4 paragraphs): Deep analysis, multiple domains, edge cases, or extensive reasoning
  - Example: "Design a distributed caching strategy for microservices at 50k QPS with failure recovery and cost optimization" → complex (multiple layers, constraints, domains)
  - Example: "Compare three architectures for real-time data processing and justify trade-offs" → complex (deep analysis, multiple options, nuanced comparison)

**Anti-Patterns to Avoid**

- Don't extract overly generic intent ("the user wants something") - be specific
- Don't include more than 5-7 key entities - focus on the essential ones
- Don't inflate complexity - a straightforward request is simple, even if wordy
- Don't create context fields for things that don't matter - omit unnecessary fields
- Don't use placeholder names ("entity1", "topic1") - use actual extracted concepts

**Optimization Tips**

- Analysis runs first, so optimize for clarity over length (faster = cheaper)
- Intent and entities should be specific enough to guide process step
- Complexity assessment directly impacts process step token usage - be honest
- Context field is optional - use it only for genuinely useful information (domain, scale, constraints)

---

## Processing Prompt Patterns

The processing step receives analysis output as context input and generates substantive content. This is where the bulk of reasoning happens.

**Role and Responsibilities**

The processing agent receives analysis output (intent, entities, complexity, context) and:
1. **Interprets Analysis**: Understand the user's goal and constraints
2. **Generates Content**: Create detailed response matching the complexity level
3. **Assesses Confidence**: Score how confident (0.0-1.0) in the generated content
4. **Captures Metadata**: Document the approach, sources, assumptions, and key points

**Confidence Scoring Guidance**

Confidence reflects how complete, accurate, and useful the generated content is:

- **0.9-1.0** (High): Content is well-supported, complete, clear, and ready for minimal refinement
  - Use when: Content is thorough, addresses all entities, has good examples, no glaring gaps

- **0.7-0.9** (Good): Content is solid with room for polishing and minor detail addition
  - Use when: Content covers the topic well but could use more examples or slightly deeper coverage

- **0.5-0.7** (Moderate): Content is usable but needs significant refinement or additional detail
  - Use when: Content is correct but incomplete, lacks examples, or is slightly shallow for complexity

- **<0.5** (Low): Content is uncertain or incomplete - not recommended for delivery
  - Use when: Content is speculative, unclear, or missing key information

**Metadata Field Structure**

The `metadata` dict should document:

```json
{
  "approach": "descriptive|analytical|comparative|creative",
  "sources": ["domain1", "domain2", "knowledge_area"],
  "assumptions": "Key assumptions made during generation",
  "key_points": ["point1", "point2", "point3"]
}
```

- **approach**: How you solved the problem (describe facts, analyze trade-offs, compare options, generate creatively)
- **sources**: Knowledge domains used (e.g., "distributed systems", "Python asyncio", "web architecture")
- **assumptions**: What assumptions did you make? What's uncertain? (e.g., "Assumes team has infrastructure expertise")
- **key_points**: Main insights or conclusions (optional but recommended)

**Handling Complexity Levels**

Processing depth should match the analysis complexity level:

- **Simple complexity**: Generate focused response (1-2 paragraphs), confidence can be high (0.85-0.95)
- **Moderate complexity**: Generate balanced coverage (3-5 paragraphs), confidence typically 0.75-0.87
- **Complex complexity**: Generate thorough analysis with examples (6-10+ paragraphs), confidence often 0.65-0.85 due to nuance

**Validation Gate: Confidence Threshold**

Processing validation gate checks: `confidence >= 0.5`
- If confidence >= 0.5: Content passes to synthesis step
- If confidence < 0.5: Validation fails, request returns error
- This threshold is configurable in `CHAIN_STRICT_VALIDATION` setting

---

## Synthesis Prompt Patterns

The synthesis step is the final stage. It receives generated content from processing and polishes it for delivery to the user.

**Role and Responsibilities**

The synthesis agent receives processed content and:
1. **Polish and Refine**: Improve clarity, flow, and readability
2. **Apply Formatting**: Choose markdown, plain, or structured format
3. **Optimize for Streaming**: Structure for token-by-token delivery
4. **Ensure Quality**: Verify content addresses intent and maintains substance

**Output Format: No JSON Wrapping**

Unlike analyze and process steps, synthesis outputs **formatted text directly, not JSON**:

```
# What is Python?

Python is a high-level, interpreted programming language created in 1991...

## Why Python is Popular

- Gentle learning curve
- Rich ecosystem
- Versatility
```

This is raw formatted text (markdown, plain, or structured), not wrapped in JSON. No JSON parsing happens on synthesis output.

**Formatting Strategies**

- **Markdown**: Use for technical/complex content with headers, lists, code blocks, emphasis
  - Best for: Architecture guides, comparisons, how-to articles, technical explanations

- **Plain**: Use for simple, accessible content with clear paragraphs
  - Best for: Simple explanations, overviews, narrative content, non-technical audiences

- **Structured**: Use for organized, hierarchical content with numbered steps and bullets
  - Best for: Tutorials, processes, feature lists, hierarchical information

**Streaming-Friendly Structure**

Since synthesis output streams to the user token-by-token, structure content carefully:
- Start with important information first
- Use complete sentences that make sense if interrupted
- Avoid lists that are incomplete without later items
- Keep paragraphs concise but complete
- Don't use excessive nesting or parenthetical asides

---

## Structured Outputs and Prompts

The analyze and process steps use LangChain's `with_structured_output()` API with Pydantic models. This changes how you should structure your prompts.

**Benefits of Structured Outputs**:
- API enforces schema validation (no manual JSON parsing errors)
- Clearer prompts (no need for markdown code block examples)
- Type-safe outputs (IDE autocomplete in downstream code)
- Better error messages (schema mismatch caught by API)

**Prompt Writing for Structured Outputs**:

Instead of showing JSON in markdown code blocks, show raw JSON examples:

```
GOOD (with structured outputs):
Output a JSON object with:
- intent: User's primary goal
- key_entities: List of topics
- complexity: "simple", "moderate", or "complex"

Example:
{
  "intent": "Compare Python and JavaScript",
  "key_entities": ["Python", "JavaScript", "performance"],
  "complexity": "moderate",
  "context": {}
}

BAD (markdown-wrapped, unnecessary with structured outputs):
Output the following JSON in a markdown code block:
```json
{
  "intent": "...",
  "key_entities": [...],
  "complexity": "...",
  "context": {}
}
```
```

**Field Descriptions Impact**:

Pydantic Field descriptions become part of the schema sent to the API. Write clear, specific descriptions:

```python
class AnalysisOutput(BaseModel):
    intent: str = Field(description="User's primary goal")      # Good
    intent: str = Field(description="Analyze the request")      # Too vague
```

Clear descriptions help the API understand what you want for each field, improving schema compliance.

**Synthesis Step**:

The synthesis step does not use structured outputs. It outputs free-form formatted text (markdown, plain, or structured format). No JSON required—just polished, formatted content for the user.

---

## Quick Reference: System Prompt Files

| File | Purpose | Output Model | Uses Structured Output |
| --- | --- | --- | --- |
| `chain_analyze.md` | Extract intent, entities, complexity | AnalysisOutput (JSON) | Yes |
| `chain_process.md` | Generate content with confidence | ProcessOutput (JSON) | Yes |
| `chain_synthesize.md` | Polish and format for delivery | Formatted text | No |

## Quick Reference: Field Requirements

| Step | Required Fields | Optional Fields | Enum Values |
| --- | --- | --- | --- |
| analyze | intent, key_entities, complexity | context | complexity: simple, moderate, complex |
| process | content, confidence | metadata | approach: descriptive, analytical, comparative, creative |
| synthesize | final_text, formatting | none | formatting: markdown, plain, structured |

## Related Documentation

- **Workflow Execution**: `../chains/CLAUDE.md` for step execution, graph structure, and prompt loading patterns
- **Data Models**: `../models/CLAUDE.md` for Pydantic model definitions that prompts must match (AnalysisOutput, ProcessOutput, SynthesisOutput)
- **API Endpoints**: `../api/CLAUDE.md` for how `/v1/chat/completions` orchestrates the prompt-chaining workflow
- **Logging**: `../utils/CLAUDE.md` for logging patterns when prompts fail to generate valid JSON
- **Request Context**: `../middleware/CLAUDE.md` for request_id propagation that enables tracing of prompt failures
- **Configuration**: `../../../CLAUDE.md` for per-step model selection and temperature tuning
- **Architecture**: `../../../ARCHITECTURE.md` for validation gate design and step output requirements
