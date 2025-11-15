# Structured Outputs Migration Plan

**Status**: Planning
**Last Updated**: 2025-11-15
**Author**: Claude Code

## Executive Summary

This document outlines the migration from manual JSON parsing to LangChain's native `with_structured_output()` API. This upgrade reduces error-handling complexity, leverages Claude's native structured outputs feature, and aligns with LangChain 1.0+ best practices.

**Impact**: Refactoring of 3 step functions (analyze, process, synthesize) and simplification of validation logic.

**Timeline**: 1-2 sprints
**Risk**: Low (backward compatible data structures)

---

## Three-Step Architecture: Why Structured Outputs Only for Steps 1-2

The prompt-chaining workflow has three distinct steps with different requirements:

```
USER REQUEST
    ↓
[STEP 1: ANALYZE]
  Input:  Plain text (user request)
  Output: JSON (AnalysisOutput)
  ✅ Uses: with_structured_output(AnalysisOutput)
  Reason: Structured reasoning required
    ↓
[STEP 2: PROCESS]
  Input:  JSON (analysis results)
  Output: JSON (ProcessOutput)
  ✅ Uses: with_structured_output(ProcessOutput)
  Reason: Complex generation needs schema validation
    ↓
[STEP 3: SYNTHESIZE]
  Input:  JSON (process results)
  Output: Formatted text (markdown/plain/structured)
  ❌ Does NOT use: structured output
  Reason: Returns free-form text, optimal for streaming
    ↓
FORMATTED RESPONSE TO USER
(streamed token-by-token via SSE)
```

**Key Design Principle**: Each step uses the right tool for its job.
- Steps 1-2: Structured output API enforces schema for reasoning steps
- Step 3: Direct token streaming for optimal user experience

---

## Current Implementation Analysis

### Existing Approach

The prompt-chaining workflow currently uses **manual JSON parsing**:

```
LLM Response (text) → Strip Markdown → Parse JSON → Validate with Pydantic → Return object
```

**Current Code Locations**:
- `src/workflow/chains/steps.py:74-210` (analyze_step)
- `src/workflow/chains/steps.py:212-344` (process_step)
- `src/workflow/chains/steps.py:347-563` (synthesize_step)

**Key Patterns**:
1. Call `llm.ainvoke(messages)` → returns raw text response
2. Extract `response.content` (string)
3. Remove markdown code blocks (lines 142-145, 275-278)
4. Parse JSON string: `json.loads(response_text.strip())`
5. Validate with Pydantic: `AnalysisOutput(**analysis_dict)`
6. Handle exceptions: `json.JSONDecodeError`, `ValidationError`

**Problems with Current Approach**:
- ❌ LLM can return malformed JSON, causing parsing failures
- ❌ Markdown block stripping is fragile (format variations break parsing)
- ❌ Two-step validation (JSON parse → Pydantic) creates error handling complexity
- ❌ Not using Claude's native structured outputs capability
- ❌ Reduces reliability compared to API-enforced schema validation

### Pydantic Models (Already Defined)

Reference: `src/workflow/models/chains.py:69-123`

The workflow already has well-structured Pydantic models:
- `AnalysisOutput` (lines 69-88)
- `ProcessOutput` (lines 91-109)
- `SynthesisOutput` (lines 112-123)

These models are **perfect for direct use with `with_structured_output()`**.

---

## LangChain Structured Outputs Documentation

### Key References

| Reference | Location | Key Content |
|-----------|----------|-------------|
| **Structured Output Guide** | `documentation/langchain/oss/python/langchain/structured-output.md` | Complete feature overview, provider vs. tool strategy |
| **Models with Structured Output** | `documentation/langchain/oss/python/langchain/models.md` | `with_structured_output()` method patterns, include_raw usage |
| **LangGraph Workflows** | `documentation/langchain/oss/python/langgraph/workflows-agents.md` | Real-world examples using `with_structured_output()` |

### Core Concepts

**Provider Strategy** (Recommended for Claude):
- Uses Claude's native structured outputs API
- Most reliable method when available
- LangChain automatically selects this for Anthropic models
- Reference: `structured-output.md:33-162`

**Method Parameter**:
- `'json_schema'` - Dedicated structured output feature (recommended)
- `'function_calling'` - Tool-based fallback (automatic if json_schema unavailable)
- `'json_mode'` - Legacy JSON mode (less reliable)
- Reference: `models.md` (Key Considerations section)

**Include Raw**:
- Get both parsed object AND raw AIMessage
- Enables access to token counts: `response.usage_metadata`
- Optional but recommended for observability
- Reference: `models.md` (Example: Message output alongside parsed structure)

---

## Why This Matters for Prompts

**Current Pain Point**: Prompts show JSON examples wrapped in markdown code blocks:
```markdown
```json
{
  "intent": "...",
  "key_entities": [...],
  ...
}
```
```

**Problem**: This creates cognitive load when writing prompts:
- Writers see markdown syntax (```` ```json ````, closing ` ``` `)
- But Claude must output **raw JSON without markdown**
- Creates a mismatch: "Show me markdown-wrapped JSON but output raw JSON"
- Confusing for prompt engineers to test and refine

**With Structured Output**: Prompts can just ask for clean data structures:
```
You must respond with the following structure:
{
  "intent": "user's primary goal",
  "key_entities": ["topic1", "topic2"],
  "complexity": "simple",
  "context": {...}
}
```

**Benefits for Prompt Writing**:
- ✅ No markdown syntax confusion
- ✅ Direct request for the data structure (matches what API enforces)
- ✅ Easier to write and iterate on prompts
- ✅ Easier for new team members to understand

---

## Implementation Strategy

### Phase 1: Update Step Functions (Core Refactoring)

**Scope**: Steps 1-2 only (analyze & process)
- ✅ Analyze step: Add structured output
- ✅ Process step: Add structured output
- ⏭️ Synthesize step: Keep as-is (returns formatted text, not JSON)

#### 1.1 Analyze Step Migration

**File**: `src/workflow/chains/steps.py:74-210`

**Before**:
```python
async def analyze_step(state: ChainState, config: ChainConfig) -> dict[str, Any]:
    # ... setup ...
    llm = ChatAnthropic(...)
    response = await llm.ainvoke(messages)
    response_text = response.content

    # Manual parsing
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
    analysis_dict = json.loads(response_text.strip())
    analysis_output = AnalysisOutput(**analysis_dict)  # Double validation
```

**After**:
```python
async def analyze_step(state: ChainState, config: ChainConfig) -> dict[str, Any]:
    # ... setup ...
    llm = ChatAnthropic(...)

    # Enable structured output
    structured_llm = llm.with_structured_output(
        AnalysisOutput,
        method="json_schema"
    )

    # Direct object response, no parsing needed
    analysis_output = await structured_llm.ainvoke(messages)
```

**Removed Code**:
- Lines 140-159: Markdown stripping and JSON parsing
- Lines 150-159: JSONDecodeError and ValidationError handling
- Simplifies to 3 lines of setup + 1 line of invocation

**Benefits**:
- ✅ No manual JSON parsing
- ✅ Guaranteed valid AnalysisOutput object
- ✅ Claude API enforces schema at generation time
- ✅ Error handling reduced from try/except to single API call

**Migration Steps**:
1. Import `AnalysisOutput` (already imported from `workflow.models.chains`)
2. Add `.with_structured_output(AnalysisOutput, method="json_schema")` chain
3. Remove markdown stripping (lines 142-145)
4. Remove json.loads() call (line 147)
5. Remove AnalysisOutput() constructor call (line 148)
6. Simplify error handling: remove JSONDecodeError/ValidationError branches
7. Keep existing token tracking logic (response.usage_metadata unchanged)
8. Keep existing logging at INFO level

**Testing Checklist**:
- [ ] Verify AnalysisOutput returned directly (no dict conversion needed)
- [ ] Confirm response.usage_metadata still available for token tracking
- [ ] Test with complex user input (ensure schema validation works)
- [ ] Verify error logging when schema validation fails
- [ ] Check step_metadata structure unchanged

#### 1.2 Process Step Migration

**File**: `src/workflow/chains/steps.py:212-344`

**Identical pattern to analyze step**:
1. Add `.with_structured_output(ProcessOutput, method="json_schema")`
2. Remove markdown stripping (lines 275-278)
3. Remove json.loads() call (line 280)
4. Remove ProcessOutput() constructor (line 281)
5. Simplify error handling (lines 283-292)

**Testing Checklist**:
- [ ] ProcessOutput returned with confidence field accessible
- [ ] Token tracking via usage_metadata functional
- [ ] Confidence scoring in step_metadata still captured

#### 1.3 Synthesize Step - NO STRUCTURED OUTPUT

**File**: `src/workflow/chains/steps.py:347-563`

**Key Design Decision**: The synthesize step **does NOT use structured output** and should NOT be modified.

**Why Not Structured Output for Synthesis?**

1. **Output Format is Plain Markdown/Text, Not JSON**
   - Analyze: returns JSON (AnalysisOutput)
   - Process: returns JSON (ProcessOutput)
   - Synthesize: returns **formatted text** (markdown/plain/structured) - NOT JSON
   - Structured output API enforces JSON schema, which doesn't match synthesis output

2. **Streaming is Optimized for Token-Level Delivery**
   - Synthesis streams individual tokens to client via SSE (Server-Sent Events)
   - This enables real-time token delivery: user sees response appear as it's generated
   - Structured output would interfere with token-level streaming
   - Current approach (manual accumulation + streaming) is optimal

3. **No Schema Validation Needed**
   - Unlike analyze/process, synthesis doesn't have strict schema requirements
   - Output is user-facing formatted text, not machine-consumed structured data
   - Validation gates only check final_response is non-empty (no schema validation)
   - Free-form text formatting (markdown/plain/structured) is intentionally flexible

4. **Architecture is Clean**
   - Steps 1-2: Structured reasoning (JSON → JSON → JSON)
   - Step 3: Formatting & delivery (text → streaming to user)
   - Each step has the right tool for its job

**Current Implementation is Correct**:
```python
# Lines 441-474: Stream tokens one at a time
async for chunk in llm.astream(messages, config=runnable_config):
    token = chunk.content if chunk.content else ""
    if token:
        token_count += 1
        final_response += token
        if writer is not None:
            writer({"type": "token", "content": token})

# Lines 495-513: Create SynthesisOutput from accumulated text
synthesis_output = SynthesisOutput(
    final_text=response_text,
    formatting=detected_formatting,
)
```

**No changes needed** - keep synthesis step as-is. It's working as designed.

**Testing Checklist** (for reference, not action items):
- ✅ Tokens still stream to client via stream_writer
- ✅ Final_response accumulates correctly
- ✅ Token counting works
- ✅ SSE protocol works correctly
- ✅ No modifications required

#### 1.4 Remove Manual JSON Parsing Utilities

**Files to Update**:
- `src/workflow/chains/steps.py`: Remove markdown stripping logic used in all steps
- Consider extracting markdown stripping to utility if other code depends on it

**Code to Remove**:
```python
# Lines 142-145 (analyze_step)
if response_text.startswith("```"):
    response_text = response_text.split("```")[1]
    if response_text.startswith("json"):
        response_text = response_text[4:]

# Lines 275-278 (process_step) - identical pattern
```

---

### Phase 2: Update Validation Gates

**File**: `src/workflow/chains/validation.py`

**Current Behavior**: Validation gates validate dict-based outputs from ChainState.

**Impact Analysis**:
- AnalysisOutput, ProcessOutput become objects, not dicts
- Existing validation still works (Pydantic models are dict-like via `.model_dump()`)
- No changes required to validation logic itself

**Verification**:
- [ ] `state.get("analysis")` still returns dict (via state storage mechanism)
- [ ] Validation gate tests pass without modification
- [ ] Consider updating gate tests to use `model_dump()` for clarity

---

### Phase 3: Update Error Handling Strategy

**Current Pattern**:
```python
try:
    response = await llm.ainvoke(messages)
    response_text = response.content
    analysis_dict = json.loads(response_text.strip())
    analysis_output = AnalysisOutput(**analysis_dict)
except (json.JSONDecodeError, ValidationError) as e:
    logger.error(
        "Failed to parse analysis step response",
        extra={"step": "analyze", "error": str(e)}
    )
    raise
```

**New Pattern**:
```python
try:
    structured_llm = llm.with_structured_output(AnalysisOutput, method="json_schema")
    analysis_output = await structured_llm.ainvoke(messages)
except Exception as e:  # Broader error handling
    logger.error(
        "Analysis step failed",
        extra={
            "step": "analyze",
            "error": str(e),
            "error_type": type(e).__name__
        }
    )
    raise
```

**Error Scenarios Handled by LangChain**:
- Schema validation failures → LangChain retries or raises
- LLM timeouts → Anthropic API errors
- Network failures → Standard exception propagation

**Changes**:
1. Remove specific JSONDecodeError/ValidationError handling
2. Keep broader Exception handler for LLM/API errors
3. Update error logging to reflect new source of failures
4. Test error scenarios: invalid schema, timeout, API errors

---

### Phase 4: Update System Prompts (MINIMAL CHANGES)

**Impact Analysis**: The current prompts are already well-designed and require **minimal updates**.

**What Stays the Same**:
- All role definitions, guidelines, and responsibilities (unchanged)
- Output format structure (JSON field names, types, required fields)
- Examples (they already show correct JSON output)
- Complexity levels and metadata guidance

**What Changes**:

#### 4.1 Analyze Prompt (`chain_analyze.md`)

**Current Section** (lines 46-61):
```markdown
## Output Format

You must respond with ONLY valid JSON (no markdown code blocks, no extra text):

```json
{
  "intent": "...",
  "key_entities": [...],
  "complexity": "simple",
  "context": {...}
}
```
```

**Updated Section** (replace code block with plain text note):
```markdown
## Output Format

You must respond with ONLY valid JSON (no markdown code blocks, no extra text):

{
  "intent": "user's primary goal extracted from the request",
  "key_entities": ["entity1", "entity2", "entity3"],
  "complexity": "simple",
  "context": {
    "key_context_field": "value",
    "domain": "relevant domain if applicable",
    "additional_info": "any other relevant context"
  }
}
```

**Rationale**: With structured outputs enabled, Claude's API enforces the JSON schema directly. The prompt's emphasis on "ONLY valid JSON (no markdown code blocks, no extra text)" is now unnecessary—the API prevents markdown wrappers. However, keeping the instruction doesn't hurt; it just becomes redundant. The key change is removing the triple-backtick markdown code block from the example (showing raw JSON instead) to avoid confusing the structured output parser.

#### 4.2 Process Prompt (`chain_process.md`)

**Current Section** (lines 63-86):
```markdown
## Output Format

You must respond with ONLY valid JSON (no markdown code blocks, no extra text):

```json
{
  "content": "generated content...",
  "confidence": 0.85,
  "metadata": {...}
}
```
```

**Updated Section** (same change—remove markdown code block wrapper):
```markdown
## Output Format

You must respond with ONLY valid JSON (no markdown code blocks, no extra text):

{
  "content": "generated content addressing the intent with appropriate depth for the complexity level",
  "confidence": 0.85,
  "metadata": {
    "approach": "descriptive",
    "sources": ["domain1", "domain2"],
    "assumptions": "key assumptions made during generation",
    "key_points": ["point1", "point2"]
  }
}
```

#### 4.3 Synthesize Prompt (`chain_synthesize.md`)

**Current Section** (lines 80-93):
```markdown
## Output Format

You must respond with ONLY clean, formatted text (no JSON wrapping, no code blocks, no extra text).

Output the polished response directly:
- If using markdown formatting: Include markdown syntax directly (# for headers, ** for bold, - for lists, etc.)
- If using plain text: Simple paragraphs with clear line breaks
- If using structured format: Organized with clear hierarchical formatting

**Requirements:**
- Output the complete, polished response text ready for user delivery
- Include all appropriate formatting (headers, lists, emphasis, code blocks, etc.)
- No JSON wrapping, no markdown code block wrappers, no explanatory preamble
- The entire response should be your formatted output
```

**No changes needed** - synthesize prompt is unaffected by structured outputs migration because:
1. Synthesis step returns **formatted text, not JSON**
2. Current guidance is already clear (no JSON wrapping)
3. No schema enforcement at API level for this step (yet)

**Note**: In future iterations, synthesis could also use structured output if wrapped in SynthesisOutput model, but current approach (streaming formatted text) is optimal for token-level streaming.

---

### Phase 5: Update Imports and Dependencies

**Changes to Make**:

1. **Keep existing imports** (no new dependencies):
   ```python
   from langchain_anthropic import ChatAnthropic  # Already used
   from pydantic import ValidationError  # Remove if no longer needed
   ```

2. **Remove unused imports** (after refactoring):
   ```python
   import json  # No longer needed
   ```

3. **Verify LangChain version** (from `pyproject.toml`):
   - `langchain>=1.0.0` supports `with_structured_output()`
   - `langchain-anthropic>=0.1.0` supports native structured outputs
   - Reference: Check current `pyproject.toml` for exact versions

**Verification**:
- [ ] Run `pip list | grep langchain` to confirm versions
- [ ] Check `pyproject.toml` for dependency specifications

---

## Data Flow Changes

### State Storage Format

**Current**: Step functions return dicts
```python
return {
    "analysis": analysis_output.model_dump(),  # Dict stored in state
    "messages": [response],
    "step_metadata": {...}
}
```

**After Migration**: Step functions return dicts (state mechanism unchanged)
```python
return {
    "analysis": analysis_output.model_dump(),  # Same dict for state storage
    "messages": [response],
    "step_metadata": {...}
}
```

**Impact**: Zero breaking changes. State format is identical.

### Response Object Structure

**Current**:
- `response` is AIMessage from `llm.ainvoke()`
- `response.content` is string (JSON text)
- `response.usage_metadata` contains token counts

**After Migration with structured output**:
- Response is still AIMessage (structured output wraps it)
- `response` is AnalysisOutput/ProcessOutput/SynthesisOutput Pydantic object
- `response.usage_metadata` may not be directly accessible

**Action Required**: Update token tracking to use `include_raw=True` option
```python
structured_llm = llm.with_structured_output(
    AnalysisOutput,
    method="json_schema",
    include_raw=True  # Returns (object, raw_message)
)

analysis_output, raw_message = await structured_llm.ainvoke(messages)
usage = raw_message.usage_metadata if hasattr(raw_message, 'usage_metadata') else None
```

---

## Token Tracking Preservation

**Critical Requirement**: Maintain exact token tracking and cost calculations.

**Current Implementation** (lines 162-166):
```python
usage = response.usage_metadata if hasattr(response, 'usage_metadata') else None
input_tokens = usage.get('input_tokens', 0) if usage else 0
output_tokens = usage.get('output_tokens', 0) if usage else 0
cost_metrics = calculate_cost(config.analyze.model, input_tokens, output_tokens)
```

**After Migration with include_raw=True**:
```python
structured_llm = llm.with_structured_output(
    AnalysisOutput,
    method="json_schema",
    include_raw=True
)
analysis_output, raw_message = await structured_llm.ainvoke(messages)

# Extract usage from raw message instead
usage = raw_message.usage_metadata if hasattr(raw_message, 'usage_metadata') else None
input_tokens = usage.get('input_tokens', 0) if usage else 0
output_tokens = usage.get('output_tokens', 0) if usage else 0
cost_metrics = calculate_cost(config.analyze.model, input_tokens, output_tokens)
```

**Verification Tests**:
- [ ] Token counts logged correctly for all 3 steps
- [ ] Cost metrics match pre-migration behavior
- [ ] step_metadata structure unchanged
- [ ] Total cost per request calculated correctly

---

## Implementation Tasks (Detailed Breakdown)

### Task 1: Code Changes

```
1.1 Analyze Step
  [ ] Update analyze_step() function signature (no changes needed)
  [ ] Add with_structured_output() to ChatAnthropic instance
  [ ] Remove markdown stripping code (lines 142-145)
  [ ] Remove json.loads() call (line 147)
  [ ] Remove AnalysisOutput() constructor (line 148)
  [ ] Remove try/except JSONDecodeError/ValidationError block
  [ ] Verify response object is now AnalysisOutput instance
  [ ] Update token tracking if needed
  [ ] Test: Run step in isolation with test data

1.2 Process Step
  [ ] Repeat 1.1 pattern for process_step()
  [ ] Update with_structured_output(ProcessOutput)
  [ ] Remove identical markdown stripping
  [ ] Test: Run step in isolation

1.3 Synthesize Step - NO CHANGES
  [ ] Verify synthesize_step() is unchanged (returns formatted text, not JSON)
  [ ] Confirm token streaming via get_stream_writer() still works
  [ ] No code changes required - design is optimal for streaming

1.4 Cleanup
  [ ] Remove json import if unused elsewhere
  [ ] Remove ValidationError import if unused elsewhere
  [ ] Verify no other code depends on removed patterns
```

### Task 1.5: Update System Prompts

```
1.5 Prompt Updates (MINIMAL - only 2 files affected)
  [ ] Update chain_analyze.md
      [ ] Line 50: Remove triple-backtick markdown code block wrapper from JSON example
      [ ] Show raw JSON instead (no ```json ... ``` syntax)
      [ ] Keep all text and examples unchanged
      [ ] Verify output format section still clear

  [ ] Update chain_process.md
      [ ] Line 68: Remove triple-backtick markdown code block wrapper from JSON example
      [ ] Show raw JSON instead (no ```json ... ``` syntax)
      [ ] Keep all text and examples unchanged
      [ ] Verify output format section still clear

  [ ] Verify chain_synthesize.md
      [ ] No changes needed (not affected by structured output migration)
      [ ] Current guidance is already correct

  [ ] Update src/workflow/prompts/CLAUDE.md documentation
      [ ] Add section: "Structured Output Compatibility (Post-Migration)"
      [ ] Document: Why markdown code block wrappers are no longer needed
      [ ] Document: API now enforces schema directly
      [ ] Provide link back to this migration plan for future reference
```

### Task 2: Testing

```
2.1 Unit Tests (tests/unit/)
  [ ] Test analyze_step with valid user input
  [ ] Test analyze_step with complex intent
  [ ] Test process_step with analysis output
  [ ] Test process_step confidence scoring
  [ ] Test synthesize_step streaming
  [ ] Test streaming token accumulation

2.2 Integration Tests (tests/integration/)
  [ ] Test full chain execution: analyze → process → synthesize
  [ ] Test validation gates still work
  [ ] Test error handling: invalid input, timeout
  [ ] Test state transitions

2.3 End-to-End Tests
  [ ] Run ./scripts/test.sh - full test suite passes
  [ ] Run ./scripts/dev.sh - dev server starts cleanly
  [ ] Test via console_client.py with real requests
  [ ] Monitor logs for structured output flow
```

### Task 3: Documentation

```
3.1 Code Documentation
  [ ] Update docstrings: explain structured output behavior
  [ ] Document token tracking changes (if any)
  [ ] Add comment explaining with_structured_output() method choice

3.2 Architecture Documentation
  [ ] Update src/workflow/chains/CLAUDE.md: Step Function Patterns section
  [ ] Update src/workflow/models/CLAUDE.md: Model Customization section
  [ ] Document: "Why we use structured outputs"

3.3 Upgrade Guide (for users of this template)
  [ ] Create UPGRADE_GUIDE.md with migration details
  [ ] Document changes to response formats
  [ ] Show before/after examples
```

### Task 4: Deployment & Validation

```
4.1 Pre-Deployment
  [ ] Code review of all three step functions
  [ ] Verify backward compatibility of state format
  [ ] Run full test suite: ./scripts/test.sh
  [ ] Check coverage hasn't decreased

4.2 Deployment
  [ ] Deploy to staging environment
  [ ] Monitor logs for structured output errors
  [ ] Run smoke tests against staging

4.3 Post-Deployment
  [ ] Monitor production logs for errors
  [ ] Verify token tracking matches previous behavior
  [ ] Confirm cost metrics are accurate
  [ ] Gather performance metrics (latency impact)
```

---

## Testing Strategy

### Unit Test Examples

**Test structured output returns correct type**:
```python
import pytest
from workflow.chains.steps import analyze_step
from workflow.models.chains import AnalysisOutput, ChainState, ChainConfig

@pytest.mark.asyncio
async def test_analyze_step_returns_analysis_output():
    # Setup
    state = ChainState(
        messages=[HumanMessage(content="Analyze this request")],
        request_id="test-123",
        user_id="user-456",
        analysis=None,
        processed_content=None,
        final_response=None,
        step_metadata={}
    )
    config = ChainConfig(...)  # From test fixtures

    # Execute
    result = await analyze_step(state, config)

    # Verify
    assert "analysis" in result
    analysis = result["analysis"]
    assert isinstance(analysis, dict)  # Stored as dict in state
    assert "intent" in analysis
    assert "key_entities" in analysis
    assert "complexity" in analysis
```

**Test structured output matches schema**:
```python
@pytest.mark.asyncio
async def test_analyze_step_validates_schema():
    # ... setup ...
    result = await analyze_step(state, config)

    # Reconstruct object to verify schema
    analysis = AnalysisOutput.model_validate(result["analysis"])
    assert len(analysis.intent) > 0
    assert len(analysis.key_entities) >= 0
    assert analysis.complexity in ["simple", "moderate", "complex"]
```

### Integration Test Examples

**Test full chain with structured outputs**:
```python
@pytest.mark.asyncio
async def test_full_chain_execution():
    # Setup
    initial_state = ChainState(
        messages=[HumanMessage(content="Write a poem about clouds")],
        request_id="test-chain",
        user_id="test-user",
        analysis=None,
        processed_content=None,
        final_response=None,
        step_metadata={}
    )

    # Execute (invoke_chain returns final state)
    final_state = await invoke_chain(initial_state, config)

    # Verify all steps produced structured output
    assert final_state["analysis"] is not None
    assert final_state["processed_content"] is not None
    assert final_state["final_response"] is not None

    # Verify schemas
    AnalysisOutput.model_validate(final_state["analysis"])
    ProcessOutput.model_validate(final_state["processed_content"])
    SynthesisOutput.model_validate_assignment(
        {"final_text": final_state["final_response"]}
    )
```

### Error Handling Tests

**Test structured output error handling**:
```python
@pytest.mark.asyncio
async def test_analyze_step_with_invalid_response():
    # Mock LLM to return response that doesn't match schema
    with patch('workflow.chains.steps.ChatAnthropic') as mock_llm:
        mock_llm.return_value.with_structured_output.return_value.ainvoke.side_effect = \
            Exception("Schema validation failed")

        state = ChainState(...)
        config = ChainConfig(...)

        # Should raise, allowing error_step to catch
        with pytest.raises(Exception):
            await analyze_step(state, config)
```

---

## Rollback Plan

**If migration encounters issues**:

### Option 1: Per-Step Rollback
If only one step has issues:
1. Revert that step function to manual JSON parsing
2. Keep other steps with structured outputs
3. Requires careful state handling (mixed dict/object format)

### Option 2: Complete Rollback
If structured outputs cause widespread issues:
1. Revert all three step functions to manual parsing
2. Restore markdown stripping and json.loads() calls
3. Restore JSONDecodeError/ValidationError handling
4. Command: `git revert <commit-hash>`

### Option 3: Feature Flag
For gradual rollout:
```python
if config.use_structured_outputs:
    structured_llm = llm.with_structured_output(AnalysisOutput)
    analysis_output = await structured_llm.ainvoke(messages)
else:
    response = await llm.ainvoke(messages)
    # ... manual parsing ...
    analysis_output = AnalysisOutput(**analysis_dict)
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Token tracking changes | Low | High | Use `include_raw=True`, test extensively |
| Streaming disruption | Low | High | Option B fallback available |
| API breaking changes | Very Low | Medium | Pin langchain versions, test early |
| Performance degradation | Very Low | Medium | Benchmark pre/post migration |
| State format incompatibility | Very Low | High | State storage unchanged (dicts) |

**Overall Risk Level**: 🟢 **LOW** (backward compatible data structures, well-documented patterns)

---

## Success Criteria

- ✅ All three step functions use `with_structured_output()`
- ✅ Zero breaking changes to state format
- ✅ Token tracking produces identical results
- ✅ Error handling improved (fewer try/except blocks)
- ✅ Full test suite passes with >80% coverage
- ✅ End-to-end testing via console_client.py succeeds
- ✅ Code complexity reduced (fewer lines, fewer branches)
- ✅ Documentation updated with new patterns

---

## Timeline & Effort Estimate

| Phase | Effort | Duration |
|-------|--------|----------|
| Code changes (2 steps only) | 2-3 hours | 0.5-1 day |
| Testing (unit + integration) | 3-4 hours | 0.5-1 day |
| Documentation | 1-2 hours | 0.25 days |
| Staging validation | 2-3 hours | 0.5 day |
| **Total** | **8-12 hours** | **1-2 days** |

**Reduced Scope Note**: Only 2 of 3 steps need code changes (analyze & process). Synthesize step is intentionally kept as-is for optimal token-level streaming.

---

## Documentation References

### LangChain Official Documentation

1. **Structured Output Guide**
   - Path: `documentation/langchain/oss/python/langchain/structured-output.md`
   - Covers: Provider strategy, tool strategy, error handling
   - Lines: 1-200+ (comprehensive guide)

2. **Models with Structured Output**
   - Path: `documentation/langchain/oss/python/langchain/models.md`
   - Covers: `with_structured_output()` method, include_raw usage, examples
   - Key section: "Structured output" (with code examples)

3. **LangGraph Workflows & Agents**
   - Path: `documentation/langchain/oss/python/langgraph/workflows-agents.md`
   - Covers: Real-world structured output usage in workflows
   - Example: Router pattern using `with_structured_output(Route)`

### Project Documentation

1. **Chains Layer Architecture**
   - Path: `src/workflow/chains/CLAUDE.md`
   - Section: "Step Function Patterns" (update required)

2. **Models Layer Architecture**
   - Path: `src/workflow/models/CLAUDE.md`
   - Section: "Model Customization Guidance" (context for structured output)

3. **Current Step Functions**
   - Path: `src/workflow/chains/steps.py`
   - Lines: 74-210 (analyze), 212-344 (process), 347-563 (synthesize)

### Configuration & Dependencies

1. **Project Dependencies**
   - Path: `pyproject.toml`
   - Check: langchain version (requires 1.0+), langchain-anthropic version

2. **Environment Configuration**
   - Path: `.env.example`
   - Check: No new environment variables needed

---

## Next Steps

1. **Review this plan** with team stakeholders
2. **Identify questions** about structured output behavior
3. **Schedule implementation** in sprint planning
4. **Create GitHub issues** from Task breakdown (Task 1-4 sections)
5. **Start with Phase 1, Task 1.1** (analyze_step migration)
6. **Iterate**: Test → Document → Deploy → Monitor

---

## Appendix: Quick Reference Code Examples

### Before (Current Manual Parsing)

```python
async def analyze_step(state: ChainState, config: ChainConfig) -> dict[str, Any]:
    # ... setup ...
    llm = ChatAnthropic(
        model=config.analyze.model,
        temperature=config.analyze.temperature,
        max_tokens=config.analyze.max_tokens,
        extra_headers={"X-Request-ID": state.get("request_id", "")},
    )

    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    try:
        response = await llm.ainvoke(messages)
        response_text = response.content

        # Manual parsing
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        analysis_dict = json.loads(response_text.strip())
        analysis_output = AnalysisOutput(**analysis_dict)

    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"Failed to parse response: {e}")
        raise

    # ... token tracking and logging ...
    return {"analysis": analysis_output.model_dump(), ...}
```

### After (Structured Outputs)

```python
async def analyze_step(state: ChainState, config: ChainConfig) -> dict[str, Any]:
    # ... setup ...
    llm = ChatAnthropic(
        model=config.analyze.model,
        temperature=config.analyze.temperature,
        max_tokens=config.analyze.max_tokens,
        extra_headers={"X-Request-ID": state.get("request_id", "")},
    )

    # Enable structured output with native Claude API
    structured_llm = llm.with_structured_output(
        AnalysisOutput,
        method="json_schema"
    )

    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    try:
        # Direct structured object response
        analysis_output = await structured_llm.ainvoke(messages)

    except Exception as e:
        logger.error(f"Analysis step failed: {e}")
        raise

    # ... token tracking and logging ...
    return {"analysis": analysis_output.model_dump(), ...}
```

**Key Differences**:
- ✅ No markdown stripping
- ✅ No json.loads()
- ✅ No AnalysisOutput constructor (Claude returns it directly)
- ✅ Simpler error handling
- ✅ Same state format (`.model_dump()` still returns dict)

---

## Quick Links to Related Documents

| Document | Purpose | Audience |
|----------|---------|----------|
| **STRUCTURED_OUTPUTS_MIGRATION_PLAN.md** (this file) | Complete implementation strategy with technical details | Engineering leads, developers |
| **PROMPT_UPDATE_GUIDE.md** | Detailed guide for updating 2 system prompts (4 line deletions) | Developers, content team |
| **src/workflow/prompts/CLAUDE.md** | Prompt architecture documentation (to be updated) | Developers maintaining prompts |
| **documentation/langchain/oss/python/langchain/structured-output.md** | LangChain official structured output guide | Reference for implementation details |
| **documentation/langchain/oss/python/langchain/models.md** | LangChain models and with_structured_output() | Reference for API usage |

---

**Document Last Updated**: November 15, 2025
**Status**: Ready for Implementation Planning
**Approval Required**: ✓ Technical review

**Related Documents**:
- ✅ PROMPT_UPDATE_GUIDE.md - Companion guide for prompt updates
- ✅ STRUCTURED_OUTPUTS_MIGRATION_PLAN.md - This document
