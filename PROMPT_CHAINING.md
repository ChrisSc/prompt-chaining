# Prompt-Chaining Customization Guide

## Overview

Prompt-chaining is a production-grade pattern for orchestrating sequential multi-step AI workflows. This implementation uses **LangGraph StateGraph** to coordinate three sequential processing steps: analyze (intent extraction), process (content generation), and synthesize (formatting and polish). Between each step, validation gates enforce quality requirements, preventing low-quality outputs from corrupting downstream processing.

Unlike parallel multi-agent patterns where agents work independently and results are merged, prompt-chaining creates a dependency chain where each step's output becomes the next step's context. This enables more coherent, context-aware responses at the cost of serial execution time.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for technical implementation details and the complete system architecture. See [CLAUDE.md](./CLAUDE.md) for configuration reference covering all environment variables and their ranges.

## Understanding the Chain

### The Three Steps

#### 1. Analyze Step (Intent Extraction)

**Purpose**: Parse user request and extract structured information for downstream processing.

**Input**: User message text

**Output**: `AnalysisOutput` with structured analysis
```json
{
  "intent": "what user is trying to accomplish",
  "key_entities": ["entity1", "entity2"],
  "complexity": "simple|moderate|complex",
  "context": {"additional": "contextual info"}
}
```

**Typical model**: Claude Haiku (fast, cost-efficient for intent parsing)

**When to upgrade to Claude Sonnet**:
- User requests are ambiguous or multi-intent
- Domain requires deep understanding to extract intent
- Intent assessment affects downstream quality significantly

**Configuration**:
- Default timeout: 15 seconds
- Default tokens: 2,048
- Default temperature: 0.5 (consistency preferred for intent parsing)

**Responsibilities**:
- Parse and understand user intent from natural language
- Extract key entities, concepts, or domains mentioned
- Assess task complexity (helps process step allocate effort)
- Provide context for the next step to use

#### 2. Process Step (Content Generation)

**Purpose**: Generate substantive response content based on analysis results.

**Input**:
- User message (original request)
- Analysis output (intent, entities, complexity from analyze step)

**Output**: `ProcessOutput` with generated content
```json
{
  "content": "substantive response content",
  "confidence": 0.85,
  "metadata": {"reasoning": "explanation of approach"}
}
```

**Typical model**: Claude Haiku (for cost-optimized services) or Claude Sonnet (for quality-critical applications)

**When to upgrade to Claude Sonnet**:
- Quality directly impacts user experience
- Content needs advanced reasoning or technical depth
- Domain expertise required (code review, research synthesis)

**Configuration**:
- Default timeout: 30 seconds
- Default tokens: 2,048
- Default temperature: 0.7 (balance between variety and focus)

**Responsibilities**:
- Generate content addressing the extracted intent
- Operate using analysis output as context
- Assess confidence in generated content (0.0-1.0)
- Capture metadata for traceability

**Confidence Scoring**: The confidence score (0.0-1.0) represents the model's self-assessment of response quality. The validation gate requires confidence >= 0.5 to proceed. Scores below 0.5 trigger the error handler:
- 0.9-1.0: High confidence, unambiguous response
- 0.7-0.9: Good confidence, solid response
- 0.5-0.7: Moderate confidence, acceptable but uncertain
- <0.5: Low confidence, validation gate fails

#### 3. Synthesize Step (Formatting & Polish)

**Purpose**: Format and polish final response for user delivery.

**Input**:
- User message (for context)
- Process output (content and confidence from process step)

**Output**: `SynthesisOutput` with formatted response
```json
{
  "final_text": "polished and formatted response",
  "formatting": "markdown|plain|html"
}
```

**Typical model**: Claude Haiku (formatting doesn't require advanced reasoning)

**When to upgrade to Claude Sonnet**:
- Complex formatting or styling requirements
- Rare - formatting is usually simpler than generation

**Configuration**:
- Default timeout: 20 seconds
- Default tokens: 2,048
- Default temperature: 0.5 (consistency preferred for formatting)

**Responsibilities**:
- Apply formatting and styling to content
- Optimize for clarity and presentation
- Ensure output meets quality standards
- Optionally apply domain-specific formatting

### ChainState and Message Accumulation

The workflow maintains state via `ChainState`, a TypedDict that evolves as each step completes:

```python
ChainState = {
    "messages": [HumanMessage, AIMessage, AIMessage, ...],  # Accumulated messages
    "analysis": {"intent": "...", "entities": [...]},       # From analyze step
    "processed_content": {"content": "...", "confidence": 0.87},  # From process step
    "final_response": "polished response text",               # From synthesize step
    "step_metadata": {                                        # Token/cost tracking
        "analyze": {"tokens": 450, "cost": 0.001, "elapsed": 1.2},
        "process": {"tokens": 800, "cost": 0.0024, "elapsed": 2.1},
        "synthesize": {"tokens": 900, "cost": 0.0015, "elapsed": 1.5}
    }
}
```

**Message Accumulation via `add_messages` Reducer**:
- Each step appends its LLM response as an AIMessage
- Conversation history preserved for potential multi-turn conversations
- Earlier messages available for later steps to reference context
- Enables future support for conversation continuity

**Metadata Tracking**:
- Each step populates `step_metadata[step_name]` with timing and cost info
- Enables cost monitoring, performance analysis, and SLA validation
- Complete workflow visibility: total tokens, cost, and execution time

### Validation Gates

Data quality enforcement between steps prevents cascading failures.

**After Analyze Step**:
- Validation gate: `should_proceed_to_process()`
- Checks: Intent field must be present and non-empty (after whitespace stripping)
- Purpose: Prevents vague or empty intents from corrupting processing
- On failure: Routes to error handler

**After Process Step**:
- Validation gate: `should_proceed_to_synthesize()`
- Checks:
  - Content field must be non-empty
  - Confidence score must be >= 0.5 (minimum quality threshold)
- Purpose: Ensures only high-quality content reaches final formatting
- On failure: Routes to error handler

**Configuration**:
- `CHAIN_ENABLE_VALIDATION`: Enable/disable all gates (default: true)
- `CHAIN_STRICT_VALIDATION`: Fail fast (strict) vs. warn and continue (lenient) on errors (default: false)

## Customizing Your Chain

### Customizing System Prompts

Each step loads its system prompt from a markdown file in `src/workflow/prompts/`:

**Files**:
- `chain_analyze.md` - System prompt for analyze step
- `chain_process.md` - System prompt for process step
- `chain_synthesize.md` - System prompt for synthesize step

**Critical Requirement**: Each prompt **MUST output valid JSON** matching its Pydantic model. No markdown code blocks or extra text - just JSON.

**Analyze Prompt Output Format**:
```json
{
  "intent": "clear statement of user's goal",
  "key_entities": ["entity1", "entity2"],
  "complexity": "simple|moderate|complex",
  "context": {}
}
```

**Process Prompt Output Format**:
```json
{
  "content": "substantive response content here",
  "confidence": 0.85,
  "metadata": {"reasoning": "why this approach"}
}
```

**Synthesize Prompt Output Format**:
```json
{
  "final_text": "formatted and polished response",
  "formatting": "applied formatting style"
}
```

### Example: Customizing for Research Synthesis

**Scenario**: Building a system that analyzes research questions and synthesizes findings from multiple papers.

**Step 1: Customize Analyze Prompt**

Original analyze prompt: Generic intent extraction
```markdown
# Your task: Parse the user request
Extract the user's intent, key entities, and complexity level.
Output JSON...
```

Customize for research domain:
```markdown
# Your task: Extract research intent
Analyze the user's research question or interest.

Extract:
- intent: What research question is the user asking?
- key_entities: Research domains, methodologies, specific topics mentioned
- complexity: "simple" (single-topic), "moderate" (multi-topic), "complex" (cross-disciplinary)
- context:
  - research_type: theoretical|empirical|literature_review|meta-analysis
  - domains: list of academic domains
  - required_sources: types of sources needed (papers|books|datasets)

Output JSON matching AnalysisOutput schema...
```

**Step 2: Customize Process Prompt**

Original process prompt: Generic content generation
```markdown
# Your task: Generate content
Use the analysis output and generate substantive content.
Output JSON...
```

Customize for research synthesis:
```markdown
# Your task: Synthesize research findings
Using the extracted research intent and domains, synthesize findings.

Instructions:
1. Identify key research questions from the intent
2. Summarize findings relevant to each question
3. Identify commonalities across papers
4. Highlight conflicting findings or methodological differences
5. Assess confidence in synthesis

Output JSON with:
- content: Comprehensive synthesis addressing all research questions
- confidence: 0.9 if synthesis thorough, 0.7 if data gaps, 0.5 if inconclusive
- metadata:
  - sources_cited: number of papers used
  - research_gaps: unresolved questions
  - conflicting_findings: areas of disagreement in literature

Output valid JSON...
```

**Step 3: Customize Synthesize Prompt**

Original synthesize prompt: Generic formatting
```markdown
# Your task: Format the response
Polish and format the content for delivery.
Output JSON...
```

Customize for academic formatting:
```markdown
# Your task: Format as academic synthesis
Format the research synthesis with academic structure.

Structure:
1. Research Questions (from intent)
2. Synthesis of Findings (by domain/topic)
3. Methodological Notes
4. Research Gaps
5. Conflicting Interpretations
6. Conclusion

Apply:
- Academic tone and terminology
- Proper citations format: (Author, Year)
- Clear section headers with markdown
- Emphasis on evidence-based statements

Output JSON with:
- final_text: Complete formatted synthesis
- formatting: "academic_markdown"

Output valid JSON...
```

**Step 4: Configure Models and Tokens**

```bash
# Research synthesis requires deeper reasoning in all steps
CHAIN_ANALYZE_MODEL=claude-sonnet-4-5-20250929
CHAIN_PROCESS_MODEL=claude-sonnet-4-5-20250929
CHAIN_SYNTHESIZE_MODEL=claude-sonnet-4-5-20250929

# Allow detailed analysis and synthesis
CHAIN_ANALYZE_MAX_TOKENS=3000
CHAIN_PROCESS_MAX_TOKENS=4000
CHAIN_SYNTHESIZE_MAX_TOKENS=3000

# Higher temperature for more comprehensive analysis
CHAIN_ANALYZE_TEMPERATURE=0.7
CHAIN_PROCESS_TEMPERATURE=0.8
CHAIN_SYNTHESIZE_TEMPERATURE=0.6

# Longer timeouts for complex synthesis
CHAIN_ANALYZE_TIMEOUT=30
CHAIN_PROCESS_TIMEOUT=60
CHAIN_SYNTHESIZE_TIMEOUT=30
```

### Customizing Step Logic

You can modify step functions to add domain-specific behavior.

**Location**: `src/workflow/chains/steps.py`

**Example: Custom Confidence Scoring in Process Step**

```python
async def process_step(state: ChainState) -> dict[str, Any]:
    # ... existing code to call LLM and parse response ...

    process_output = ProcessOutput(**parsed_response)

    # Add domain-specific confidence adjustment
    # Example: boost confidence for technical queries with concrete answers
    if any(entity in state.analysis.get("key_entities", [])
           for entity in ["code", "technical", "architecture"]):
        if len(process_output.content) > 500:  # detailed response
            process_output.confidence = min(1.0, process_output.confidence * 1.1)

    # ... rest of function ...
    return {...}
```

**Example: Custom Analysis Validation**

Location: `src/workflow/chains/validation.py`

```python
class DomainValidationGate(ValidationGate):
    def validate(self, output: AnalysisOutput) -> tuple[bool, str | None]:
        # Original validation
        if not output.intent or not output.intent.strip():
            return False, "Intent is empty"

        # Custom: Ensure analysis includes domain indicator
        # (for systems that require domain classification)
        context = output.context or {}
        if "domain" not in context:
            return False, "Analysis missing required domain classification"

        # Custom: Validate entity count for domain
        if len(output.key_entities) < 2:
            return False, "Analysis must extract at least 2 key entities"

        return True, None
```

Then use in `graph.py`:
```python
def should_proceed_to_process(state: ChainState) -> str:
    gate = DomainValidationGate()  # Use custom gate
    is_valid, error_msg = gate.validate(state["analysis"])
    return "process" if is_valid else "error"
```

### Customizing Configuration

Complete configuration reference available in [CLAUDE.md](./CLAUDE.md).

**Key variables for tuning**:

**Per-step models**:
```bash
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001      # or claude-sonnet-4-5-20250929
CHAIN_PROCESS_MODEL=claude-haiku-4-5-20251001      # or claude-sonnet-4-5-20250929
CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001   # or claude-sonnet-4-5-20250929
```

**Temperature tuning** (controls creativity/determinism):
```bash
CHAIN_ANALYZE_TEMPERATURE=0.5      # 0.3-0.7 preferred (consistency)
CHAIN_PROCESS_TEMPERATURE=0.7      # 0.5-1.0 (balance)
CHAIN_SYNTHESIZE_TEMPERATURE=0.5   # 0.3-0.7 (consistency)
```

**Token limits** (maximum output length per step):
```bash
CHAIN_ANALYZE_MAX_TOKENS=2048      # Typically 1000-2048
CHAIN_PROCESS_MAX_TOKENS=2048      # Typically 1500-4000
CHAIN_SYNTHESIZE_MAX_TOKENS=2048   # Typically 1000-2048
```

**Timeouts** (maximum execution time per step):
```bash
CHAIN_ANALYZE_TIMEOUT=15           # Typically 10-30 seconds
CHAIN_PROCESS_TIMEOUT=30           # Typically 20-60 seconds
CHAIN_SYNTHESIZE_TIMEOUT=20        # Typically 10-30 seconds
```

**Validation gates**:
```bash
CHAIN_ENABLE_VALIDATION=true       # Enable quality gates
CHAIN_STRICT_VALIDATION=false      # Warn vs fail on errors
```

#### Configuration Example: High-Quality Content Generation

For scenarios where quality is critical (legal documents, technical specifications, medical content):

```bash
# Upgrade to Sonnet for best quality
CHAIN_ANALYZE_MODEL=claude-sonnet-4-5-20250929
CHAIN_PROCESS_MODEL=claude-sonnet-4-5-20250929
CHAIN_SYNTHESIZE_MODEL=claude-sonnet-4-5-20250929

# Increase tokens for detailed output
CHAIN_ANALYZE_MAX_TOKENS=2500
CHAIN_PROCESS_MAX_TOKENS=4000
CHAIN_SYNTHESIZE_MAX_TOKENS=2500

# Longer timeouts for complex processing
CHAIN_ANALYZE_TIMEOUT=30
CHAIN_PROCESS_TIMEOUT=60
CHAIN_SYNTHESIZE_TIMEOUT=30

# Enable strict validation to catch quality issues early
CHAIN_STRICT_VALIDATION=true

# Moderate-high temperature for comprehensive responses
CHAIN_ANALYZE_TEMPERATURE=0.6
CHAIN_PROCESS_TEMPERATURE=0.8
CHAIN_SYNTHESIZE_TEMPERATURE=0.6
```

## Real-World Use Cases

### Use Case 1: Content Moderation Chain

**Problem**: Classify content severity, evaluate against policies, generate decisions.

**Customization**:

1. **Analyze Step**: Classify severity and identify policy violations
   - Extract: Severity level (1-10), policy categories affected, flagged content snippets
   - Output includes: `policy_categories: ["harassment", "misinformation"]`

2. **Process Step**: Evaluate against specific policies and recommend action
   - Input: Analysis output with severity and categories
   - Generate: Detailed evaluation, action recommendation (approve/warn/remove), supporting rationale
   - Output includes: `action_recommendation: "remove"`, `appeal_instructions: "..."`

3. **Synthesize Step**: Generate moderation explanation for user
   - Format: Clear, user-friendly explanation of decision
   - Include: Appeal process instructions
   - Output includes: `decision_explanation: "..."`, `appeal_process: "..."`

**Configuration**:
```bash
# Use Haiku for speed (moderation needs quick response)
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_PROCESS_MODEL=claude-haiku-4-5-20251001
CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001

# Tight timeouts for real-time moderation
CHAIN_ANALYZE_TIMEOUT=10
CHAIN_PROCESS_TIMEOUT=15
CHAIN_SYNTHESIZE_TIMEOUT=10

# Enable strict validation (errors shouldn't happen in production)
CHAIN_STRICT_VALIDATION=true

# Lower temperature for deterministic decisions
CHAIN_ANALYZE_TEMPERATURE=0.3
CHAIN_PROCESS_TEMPERATURE=0.3
CHAIN_SYNTHESIZE_TEMPERATURE=0.3
```

### Use Case 2: Code Review Chain

**Problem**: Analyze code, identify issues, generate review with recommendations.

**Customization**:

1. **Analyze Step**: Detect language, patterns, and complexity
   - Extract: Programming language, architectural patterns, complexity level, code metrics
   - Output includes: `language: "python"`, `patterns: ["dependency_injection"]`

2. **Process Step**: Identify bugs, smells, and improvements
   - Input: Code language, patterns, and context
   - Generate: List of issues with severity, suggested improvements
   - Output includes: `issues: [{severity: "critical", description: "..."}, ...]`

3. **Synthesize Step**: Generate readable review comment
   - Format: GitHub-compatible markdown
   - Prioritize: Most critical issues first
   - Output includes: `final_text: "## Code Review\n\n### Critical Issues\n..."`

**Configuration**:
```bash
# Haiku for analyze (language detection is straightforward)
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001

# Sonnet for process (code analysis needs expertise)
CHAIN_PROCESS_MODEL=claude-sonnet-4-5-20250929

# Haiku for synthesize (formatting doesn't need deep reasoning)
CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001

# Higher token limits for detailed analysis
CHAIN_ANALYZE_MAX_TOKENS=1500
CHAIN_PROCESS_MAX_TOKENS=3500
CHAIN_SYNTHESIZE_MAX_TOKENS=2000

# Moderate timeouts (code analysis can be complex)
CHAIN_ANALYZE_TIMEOUT=15
CHAIN_PROCESS_TIMEOUT=45
CHAIN_SYNTHESIZE_TIMEOUT=20

# Higher temperature for creative improvements
CHAIN_ANALYZE_TEMPERATURE=0.5
CHAIN_PROCESS_TEMPERATURE=0.8
CHAIN_SYNTHESIZE_TEMPERATURE=0.6
```

### Use Case 3: Customer Support Triage Chain

**Problem**: Analyze support tickets, determine category and priority, draft response template.

**Customization**:

1. **Analyze Step**: Extract issue type and urgency indicators
   - Extract: Issue category (billing/technical/account), priority (1-5), sentiment, required expertise
   - Output includes: `category: "technical"`, `priority: 3`, `sentiment: "frustrated"`

2. **Process Step**: Generate appropriate response approach
   - Input: Category, priority, sentiment context
   - Generate: Recommended response approach, escalation needs, required information
   - Output includes: `escalation_needed: true`, `escalation_team: "engineering"`

3. **Synthesize Step**: Draft response template
   - Format: Empathetic, professional response template
   - Include: Next steps and timeline
   - Output includes: `final_text: "Thank you for contacting us..."`

**Configuration**:
```bash
# All-Haiku for cost optimization (high volume support)
CHAIN_ANALYZE_MODEL=claude-haiku-4-5-20251001
CHAIN_PROCESS_MODEL=claude-haiku-4-5-20251001
CHAIN_SYNTHESIZE_MODEL=claude-haiku-4-5-20251001

# Lower token limits (support messages are usually concise)
CHAIN_ANALYZE_MAX_TOKENS=1200
CHAIN_PROCESS_MAX_TOKENS=1500
CHAIN_SYNTHESIZE_MAX_TOKENS=1000

# Quick timeouts (high-volume triage)
CHAIN_ANALYZE_TIMEOUT=10
CHAIN_PROCESS_TIMEOUT=15
CHAIN_SYNTHESIZE_TIMEOUT=10

# Consistent temperature (deterministic triage)
CHAIN_ANALYZE_TEMPERATURE=0.3
CHAIN_PROCESS_TEMPERATURE=0.4
CHAIN_SYNTHESIZE_TEMPERATURE=0.3
```

## Troubleshooting

### Common Issues and Solutions

**Issue: Empty Intent Validation Failures**

Symptom:
```
"Intent is empty" error from validation gate
Requests consistently hitting error handler after analyze step
```

Root causes:
- Analyze prompt unclear or not extracting intent properly
- User queries too vague for intent extraction
- Temperature too low (0.1-0.3) causing failure to extract

Solutions:
1. Review `chain_analyze.md` prompt - add examples for your domain
2. Increase temperature: `CHAIN_ANALYZE_TEMPERATURE=0.7` (more flexible extraction)
3. Upgrade to Sonnet: `CHAIN_ANALYZE_MODEL=claude-sonnet-4-5-20250929` (better ambiguity handling)
4. Increase token limit: `CHAIN_ANALYZE_MAX_TOKENS=3000` (more space for detailed extraction)
5. Disable strict validation temporarily: `CHAIN_STRICT_VALIDATION=false` (to see detailed errors)

**Issue: Low Confidence Scores**

Symptom:
```
Process step confidence < 0.5, routed to error handler
Logs show: "confidence score 0.3 does not meet minimum threshold"
```

Root causes:
- Process step uncertain about response
- Prompt doesn't guide confidence scoring clearly
- Task genuinely difficult or ambiguous

Solutions:
1. Review `chain_process.md` - add clarity about when to output high confidence
2. Increase temperature: `CHAIN_PROCESS_TEMPERATURE=0.8` (more exploratory)
3. Increase tokens: `CHAIN_PROCESS_MAX_TOKENS=3000` (more space for thorough response)
4. Upgrade to Sonnet: `CHAIN_PROCESS_MODEL=claude-sonnet-4-5-20250929` (more confident responses)
5. Add custom confidence adjustment in `process_step()` function
6. Increase confidence threshold: modify validation gate from 0.5 to 0.4

**Issue: Timeout Errors**

Symptom:
```
"Step timeout exceeded" error during execution
Logs show: "timeout during process_step after 30s"
```

Root causes:
- Step taking longer than configured timeout
- Complex generation or inference taking too long
- Network latency issues

Solutions:
1. Increase timeout: `CHAIN_PROCESS_TIMEOUT=60` (double the time)
2. Reduce token limit: `CHAIN_PROCESS_MAX_TOKENS=1500` (shorter responses)
3. Switch to Haiku: `CHAIN_PROCESS_MODEL=claude-haiku-4-5-20251001` (faster)
4. Lower temperature: `CHAIN_PROCESS_TEMPERATURE=0.4` (more deterministic = faster)
5. Check network latency: add 0.5s per step for high-latency environments
6. Monitor logs: check actual step execution times to set appropriate timeouts

**Issue: High Costs**

Symptom:
```
Logs show: "total_cost_usd": 0.025 (exceeds budget)
Cost per request higher than expected
```

Root causes:
- Token limits too high
- Using expensive models (Sonnet) unnecessarily
- Verbose prompts or long context

Solutions:
1. Check which step uses most tokens: `grep "step_breakdown\|input_tokens" logs.json`
2. Reduce token limits: `CHAIN_PROCESS_MAX_TOKENS=1500` (was 2048)
3. Switch to Haiku: `CHAIN_PROCESS_MODEL=claude-haiku-4-5-20251001` (from Sonnet)
4. Lower temperature: `CHAIN_ANALYZE_TEMPERATURE=0.3` (more concise responses)
5. Optimize prompts: Remove examples or detailed instructions if possible
6. Monitor costs weekly: `grep "total_cost_usd" logs.json | tail -100 | jq -s 'add / length'`

### Debugging Techniques

**Technique 1: View Step Metadata Logs**

```bash
# See cost breakdown by step
grep "step_breakdown" logs.json | jq '.step_breakdown'

# Find which step consumes most tokens
grep "step_breakdown" logs.json | jq '.step_breakdown | to_entries | sort_by(.value.total_tokens) | reverse'

# Monitor cost trends over time (last 100 requests)
grep "total_cost_usd" logs.json | jq '.total_cost_usd' | tail -100 | jq -s 'add / length'
```

**Technique 2: Test Individual Steps**

```python
# In your test file or console_client.py
from workflow.chains.steps import analyze_step
from workflow.models.chains import ChainState
from langchain_core.messages import HumanMessage

# Create test state with single message
state = ChainState(messages=[HumanMessage(content="your test query")])

# Run just analyze step
result = await analyze_step(state)

# Inspect analysis output
print("Analysis output:", result["analysis"])
print("Token usage:", result["step_metadata"]["analyze"])
```

**Technique 3: Use Non-Streaming Mode for Debugging**

Non-streaming mode (`invoke_chain()`) is easier to debug than streaming mode:
```python
# In workflow.chains.graph.py
final_state = await graph.ainvoke(initial_state)

# Returns complete state at end
# Easier to inspect step_metadata
# No streaming chunk ordering issues
```

**Technique 4: Enable Debug Logging**

```bash
# Set debug logging to see detailed step execution
LOG_LEVEL=DEBUG python console_client.py "your query"

# Shows:
# - Detailed step inputs/outputs
# - LLM request/response payloads
# - Validation gate decisions
# - Step execution timing
```

## Advanced Topics

### Adding Custom Validation Gates

Location: `src/workflow/chains/validation.py`

```python
from workflow.models.chains import ProcessOutput
from workflow.chains.validation import ValidationGate

class CustomProcessValidationGate(ValidationGate):
    def validate(self, output: ProcessOutput) -> tuple[bool, str | None]:
        # Original validation from base class
        if not output.content or not output.content.strip():
            return False, "Content is empty"

        if output.confidence < 0.5:
            return False, f"Confidence {output.confidence} below minimum 0.5"

        # Custom domain-specific validation
        # Example: ensure output length for your domain
        if len(output.content) < 100:
            return False, "Content too brief for this domain (minimum 100 chars)"

        # Example: validate metadata structure
        if output.metadata and "sources_cited" in output.metadata:
            if not output.metadata["sources_cited"]:
                return False, "No sources cited in metadata"

        return True, None
```

Then use in `src/workflow/chains/graph.py`:

```python
def should_proceed_to_synthesize(state: ChainState) -> str:
    gate = CustomProcessValidationGate()  # Use custom gate
    processed = state.get("processed_content")

    if isinstance(processed, str):
        # Fallback for string content
        return "synthesize" if processed.strip() else "error"

    # Validate using custom gate
    is_valid, error_msg = gate.validate(processed)
    if not is_valid:
        logger.warning(f"Validation failed: {error_msg}")
        return "error"

    return "synthesize"
```

### Session Persistence with Checkpointers

The implementation includes LangGraph's MemorySaver checkpointer for basic session persistence. For production multi-turn support, implement a custom persistent checkpointer:

```python
from langgraph.checkpoint.base import BaseCheckpointSaver

class PostgresCheckpointer(BaseCheckpointSaver):
    """Store conversation state in PostgreSQL for multi-turn support"""

    def __init__(self, connection_string: str):
        self.conn_string = connection_string

    async def get_tuple(self, config):
        """Retrieve saved state by thread_id"""
        thread_id = config.get("configurable", {}).get("thread_id")
        # Query PostgreSQL for saved state
        # Return (values, metadata)

    async def put(self, config, values, metadata):
        """Save state to PostgreSQL"""
        thread_id = config.get("configurable", {}).get("thread_id")
        # Insert/update PostgreSQL with state
```

Then use in graph compilation:

```python
from workflow.chains.graph import build_chain_graph

config = ChainConfig(...)
graph = build_chain_graph(config)

# Compile with persistent checkpointer
checkpointer = PostgresCheckpointer(connection_string)
compiled_graph = graph.compile(checkpointer=checkpointer)

# Now supports multi-turn conversations
state = await compiled_graph.ainvoke(
    initial_state,
    {"configurable": {"thread_id": "user-session-123"}}
)
```

### Future: Multi-Turn Conversations

Current implementation: Single turn (one user message per request)

Future capability: Multi-turn using accumulated messages

```
Turn 1: User: "Analyze my code"
        Chain analyzes, outputs review
        ChainState saved with full context

Turn 2: User: "Focus on security"
        Load prior ChainState (via thread_id)
        Append new user message
        Chain re-analyzes with full context of prior request
        Process step reads both messages for context
        Can reference prior analysis in new response
```

The checkpoint system and message accumulation already support this architecture. Implementation requires:
1. Persistent checkpointer (PostgreSQL, Firestore, etc.)
2. Thread ID tracking for conversation sessions
3. Frontend UI maintaining thread_id across turns

## Getting Help

**For technical details**: See [ARCHITECTURE.md](./ARCHITECTURE.md)
- Graph structure and node definitions
- State flow through steps
- Token tracking and cost calculation
- Logging architecture
- Security features

**For configuration reference**: See [CLAUDE.md](./CLAUDE.md)
- Complete environment variable list
- Configuration ranges and defaults
- Quick start commands
- Docker deployment

**For performance**: See BENCHMARKS.md (if available)
- Typical token usage per step
- Execution time profiles
- Cost benchmarks

**For issues**: Check logs with:
```bash
# All errors
grep '"level": "ERROR"' logs.json | jq '.'

# Specific request
grep '"request_id": "your-request-id"' logs.json | jq '.'

# Cost analysis
grep '"total_cost_usd"' logs.json | jq '.total_cost_usd' | jq -s 'add/length'
```
