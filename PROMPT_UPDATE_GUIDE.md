# System Prompt Updates for Structured Outputs Migration

**Purpose**: Guide for updating system prompts to work with LangChain's `with_structured_output()` API.

**Files Affected**: 2 of 3
- ✅ `src/workflow/prompts/chain_analyze.md` - REQUIRES UPDATE
- ✅ `src/workflow/prompts/chain_process.md` - REQUIRES UPDATE
- ⏭️ `src/workflow/prompts/chain_synthesize.md` - NO CHANGES

---

## Why Prompts Need Updating (And Why It's Easier!)

When using Claude's structured outputs API (via `with_structured_output()`), the API **enforces the JSON schema at generation time**. This makes prompts **easier to write**, not harder.

### Current Situation: Confusing for Prompt Writers

**Current Prompts Show This**:
```markdown
You must respond with ONLY valid JSON (no markdown code blocks, no extra text):

```json
{
  "intent": "user's primary goal",
  "key_entities": ["topic1", "topic2"],
  "complexity": "simple",
  "context": {...}
}
```
```

**Problem**: Prompt writers see **markdown code block syntax** in examples, but Claude outputs **raw JSON without markdown**. This creates a mismatch that's confusing to test and refine.

### After Migration: Clearer for Prompt Writers

**New Prompts Will Show This**:
```markdown
You must respond with the following structure:

{
  "intent": "user's primary goal",
  "key_entities": ["topic1", "topic2"],
  "complexity": "simple",
  "context": {...}
}
```

**Benefits**:
- ✅ No confusing markdown syntax in examples
- ✅ Examples match exactly what Claude will output (raw JSON)
- ✅ Easier for new team members to understand
- ✅ Easier to test prompts manually (copy-paste examples directly)
- ✅ Clearer intent: "output this structure" not "output markdown-wrapped JSON"

### Why This Works

**With Structured Outputs API**:
1. The API enforces the schema directly
2. Claude cannot output markdown code blocks (API prevents it)
3. Examples should show raw JSON to avoid confusion
4. Prompts focus on the data structure, not on formatting workarounds

---

## Change 1: Update `chain_analyze.md`

**File**: `src/workflow/prompts/chain_analyze.md`
**Lines Affected**: 46-61
**Change Type**: Example formatting only (minimal)

### BEFORE (Current)

```markdown
## Output Format

You must respond with ONLY valid JSON (no markdown code blocks, no extra text):

```json
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

**Note**: The `complexity` field must be one of: `simple`, `moderate`, or `complex`
```

### AFTER (Updated)

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

**Note**: The `complexity` field must be one of: `simple`, `moderate`, or `complex`
```

### What Changed

1. **Removed**: Triple backticks and `json` language identifier (`` ```json `` and ` ``` `)
2. **Result**: Shows raw JSON instead of markdown-wrapped JSON
3. **Why**: Matches what structured output API actually returns (raw JSON, no wrappers)

### What Stayed the Same

- ✅ All instructions and guidelines (unchanged)
- ✅ Role and responsibilities (unchanged)
- ✅ Examples in "Examples" section (unchanged)
- ✅ Complexity levels guidance (unchanged)
- ✅ Field requirements and notes (unchanged)

### Validation

After updating, verify:
- [ ] File is valid markdown (no syntax errors)
- [ ] JSON structure is clear and readable
- [ ] All three examples in "Examples" section are still present and unchanged
- [ ] No other sections affected

---

## Change 2: Update `chain_process.md`

**File**: `src/workflow/prompts/chain_process.md`
**Lines Affected**: 63-86
**Change Type**: Example formatting only (identical to Change 1)

### BEFORE (Current)

```markdown
## Output Format

You must respond with ONLY valid JSON (no markdown code blocks, no extra text):

```json
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

**Field Requirements:**
- `content`: Substantive generated text (string, at least 100 characters)
- `confidence`: Decimal between 0.0 and 1.0 (number)
- `metadata.approach`: One of: `descriptive`, `analytical`, `comparative`, or `creative` (string)
- `metadata.sources`: List of relevant knowledge domains (array of strings)
- `metadata.assumptions`: Description of key assumptions made (string)
- `metadata.key_points`: Optional list of main points covered (array of strings)
```

### AFTER (Updated)

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

**Field Requirements:**
- `content`: Substantive generated text (string, at least 100 characters)
- `confidence`: Decimal between 0.0 and 1.0 (number)
- `metadata.approach`: One of: `descriptive`, `analytical`, `comparative`, or `creative` (string)
- `metadata.sources`: List of relevant knowledge domains (array of strings)
- `metadata.assumptions`: Description of key assumptions made (string)
- `metadata.key_points`: Optional list of main points covered (array of strings)
```

### What Changed

1. **Removed**: Triple backticks and `json` language identifier
2. **Result**: Shows raw JSON instead of markdown-wrapped JSON
3. **Why**: Matches what structured output API actually returns

### What Stayed the Same

- ✅ All instructions (unchanged)
- ✅ Confidence scoring guidance (unchanged)
- ✅ Metadata structure guidance (unchanged)
- ✅ How to use analysis fields (unchanged)
- ✅ All three examples in "Examples" section (unchanged)

### Validation

After updating, verify:
- [ ] File is valid markdown
- [ ] JSON structure is clear and readable
- [ ] Field requirements section is still present and unchanged
- [ ] All three examples (simple, moderate, complex) are still present

---

## No Changes: `chain_synthesize.md`

**File**: `src/workflow/prompts/chain_synthesize.md`
**Status**: ✅ NO CHANGES REQUIRED

**Reason**: The synthesis step outputs **formatted text, not JSON**. The current guidance is already correct:

```markdown
## Output Format

You must respond with ONLY clean, formatted text (no JSON wrapping, no code blocks, no extra text).
```

This remains accurate because:
1. Synthesis doesn't use structured output schema
2. It returns formatted text (markdown/plain/structured)
3. No JSON validation or wrapping needed
4. Current guidance prevents confusion

**Future Consideration**: In a future iteration, synthesis could wrap output in `SynthesisOutput` Pydantic model using structured outputs, but current approach (streaming formatted text directly) is optimal for token-level streaming to clients.

---

## How to Make the Changes

### Option 1: Manual Edit (Recommended for understanding)

1. Open `src/workflow/prompts/chain_analyze.md` in your editor
2. Find line 50 (the line with ` ```json `)
3. Delete that line
4. Find the closing ` ``` ` (line 61, after the JSON object)
5. Delete that line
6. Save file

Repeat for `chain_process.md` (lines 68 and 86).

### Option 2: Automated via Script

```bash
# For analyze prompt
sed -i '' '/^```json$/d' src/workflow/prompts/chain_analyze.md
sed -i '' '0,/^```$/{ /^```$/{d;}; }' src/workflow/prompts/chain_analyze.md

# For process prompt
sed -i '' '/^```json$/d' src/workflow/prompts/chain_process.md
sed -i '' '0,/^```$/{ /^```$/{d;}; }' src/workflow/prompts/chain_process.md
```

### Option 3: Search & Replace in IDE

1. Open both files in your IDE
2. Find: ` ```json\n` (newline after json)
3. Replace with: (nothing—delete it)
4. Find: ` ``` ` (closing backticks)
5. Replace with: (nothing—delete it)
6. **Careful**: Only in the "Output Format" section, not in examples

---

## Verification Checklist

After making changes:

### For `chain_analyze.md`
- [ ] File opens without errors
- [ ] Line 46-61 shows raw JSON (no markdown code block syntax)
- [ ] JSON structure is visible and readable
- [ ] "Examples" section unchanged (examples 1-3 still show correct JSON)
- [ ] All 120 lines still present

### For `chain_process.md`
- [ ] File opens without errors
- [ ] Lines 63-86 show raw JSON (no markdown code block syntax)
- [ ] JSON structure is visible and readable
- [ ] "Examples" section unchanged (examples 1-3 still show correct JSON)
- [ ] All 160 lines still present

### For Both Files
- [ ] Syntax highlighted correctly in editor
- [ ] Valid markdown structure
- [ ] No broken links or references
- [ ] Field requirements still clear and complete

---

## Testing the Updated Prompts

After updating prompts, the system will automatically test them:

1. **Unit Tests**: `./scripts/test.sh` runs tests on prompt loading
2. **Integration Tests**: Tests verify LLM responses match schema
3. **End-to-End Tests**: Console client tests verify full workflow

The prompts work with structured outputs if:
- ✅ Claude returns valid JSON (no markdown wrappers)
- ✅ JSON matches AnalysisOutput or ProcessOutput schema
- ✅ Pydantic validation succeeds
- ✅ Step metadata and token tracking work correctly

---

## Troubleshooting

### Issue: "Schema validation failed"

**Cause**: Claude is still outputting markdown code blocks (` ```json ... ``` `)

**Solution**:
1. Verify both prompt updates are applied
2. Check that triple backticks were removed from "Output Format" section
3. Run prompt through test to confirm

### Issue: "Missing field" errors

**Cause**: Prompt is not requesting all required fields

**Solution**: Verify "Field Requirements" section lists all required fields (shouldn't have changed with update)

### Issue: Prompts work in test but fail in production

**Cause**: Cached prompts may be used

**Solution**:
1. Restart the application: `./scripts/dev.sh` (forces prompt reload)
2. Verify `.venv` environment is fresh
3. Check that file permissions allow reading updated prompts

---

## Documentation Updates

After updating prompts, update documentation:

### Update: `src/workflow/prompts/CLAUDE.md`

Add new section after "JSON Output Requirements" (around line 100):

```markdown
## Structured Output Compatibility (Post-Migration)

When using LangChain's `with_structured_output()` API (available in version 1.0+), the API enforces JSON schema at generation time. This means:

**What Changed in Prompts**:
- JSON examples in "Output Format" sections no longer use markdown code block syntax (` ```json ... ``` `)
- Examples show raw JSON instead (easier for API to parse correctly)
- Instructions to output "only valid JSON" remain for clarity but become redundant

**Why This Matters**:
- Structured output API prevents markdown wrappers automatically
- Showing raw JSON in examples avoids confusing the API parser
- No behavioral change to prompts—they still request the same JSON structure

**Reference**: See `STRUCTURED_OUTPUTS_MIGRATION_PLAN.md` for complete migration details.
```

---

## Summary

| File | Change | Scope |
|------|--------|-------|
| `chain_analyze.md` | Remove markdown code block wrappers from "Output Format" example | Lines 50, 61 |
| `chain_process.md` | Remove markdown code block wrappers from "Output Format" example | Lines 68, 86 |
| `chain_synthesize.md` | No changes | No impact |

**Total Lines Changed**: 4 deletions, 0 additions
**Complexity**: Minimal (formatting only, no content changes)
**Risk**: Very low (examples formatting, not behavior)

---

**Last Updated**: November 15, 2025
**Status**: Ready for Implementation
**Dependencies**: Requires corresponding code changes in `src/workflow/chains/steps.py` to enable `with_structured_output()`
