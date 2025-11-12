# Critical Bug Fix: LangGraph Stream Metadata Extraction

## Issue Summary

The LangGraph chain was executing all three steps (analyze, process, synthesize) successfully, but the **step_metadata was not being captured** when using `stream_mode="updates"`. This resulted in logs showing:

```json
{
  "steps_executed": 0,
  "total_tokens": 0,
  "total_cost_usd": 0.0
}
```

Even though the chain was completing with correct outputs.

## Root Cause

When LangGraph's `graph.astream()` is called with `stream_mode="updates"`, each event has a **nested structure**:

```python
# Event structure from astream(stream_mode="updates")
{
    "node_name": {           # <- Node name is key
        "analysis": {...},
        "messages": [...],
        "step_metadata": {...}  # <- Metadata is INSIDE node_update dict
    }
}
```

However, the `stream_chain()` function was checking for `step_metadata` at the **top level** of the event:

```python
# WRONG: This checks for "step_metadata" key in {"analyze": {...}}
if "step_metadata" in event:
    step_metadata = event.get("step_metadata", {})
```

Since `event` keys are `["analyze"]` not `["step_metadata"]`, the condition always failed and metadata was never accumulated.

## Solution

Update both `stream_chain()` in `graph.py` and the API endpoint in `chat.py` to properly extract metadata from the nested event structure:

```python
# CORRECT: Iterate through node updates and extract metadata from each
for node_name, node_update in event.items():
    if isinstance(node_update, dict):
        step_metadata = node_update.get("step_metadata", {})
        if isinstance(step_metadata, dict):
            accumulated_metadata.update(step_metadata)
```

## Changes Made

### File: `/src/workflow/chains/graph.py`

**Lines 288-312**: Fixed the `stream_chain()` function to properly extract metadata from nested event structure:

```python
# OLD (BROKEN)
if isinstance(event, dict):
    if "step_metadata" in event:
        step_metadata = event.get("step_metadata", {})
        if isinstance(step_metadata, dict):
            accumulated_metadata.update(step_metadata)
    yield event

# NEW (FIXED)
if isinstance(event, dict):
    for node_name, node_update in event.items():
        if isinstance(node_update, dict):
            step_metadata = node_update.get("step_metadata", {})
            if isinstance(step_metadata, dict):
                accumulated_metadata.update(step_metadata)
    yield event
```

### File: `/src/workflow/api/v1/chat.py`

**Lines 199-206**: Updated API endpoint to extract metadata from nested structure:

```python
# OLD (BROKEN)
if "step_metadata" in state_update:
    final_step_metadata.update(state_update.get("step_metadata", {}))

# NEW (FIXED)
for node_name, node_update in state_update.items():
    if isinstance(node_update, dict):
        step_metadata = node_update.get("step_metadata", {})
        if isinstance(step_metadata, dict):
            final_step_metadata.update(step_metadata)
```

### File: `/scripts/dev.sh`

Fixed incorrect path in dev script (was pointing to non-existent `src/orchestrator_worker/main.py`):

```bash
# OLD: fastapi dev src/orchestrator_worker/main.py
# NEW: fastapi dev src/workflow/main.py
```

## Verification Results

After the fix, the chain correctly reports:

```
Executing chain with stream_chain()...

Update 1: ['analyze']
  - Analysis intent: Understand the main features...
  - Step 'analyze': 1421 tokens, $0.0018

Update 2: ['process']
  - Process confidence: 0.94
  - Step 'process': 3069 tokens, $0.0050

Update 3: ['synthesize']
  - Final response length: 2158
  - Step 'synthesize': 3391 tokens, $0.0054

Steps executed: 3
Total tokens: 7881
Total cost: $0.012165

Detailed breakdown:
  analyze:
    - Total: 1421 tokens
    - Cost: $0.001837
    - Time: 1.94s
  process:
    - Total: 3069 tokens
    - Cost: $0.004953
    - Time: 6.17s
  synthesize:
    - Total: 3391 tokens
    - Cost: $0.005375
    - Time: 4.76s
```

## Impact

This bug fix ensures:

1. **Correct metrics tracking**: All token usage and costs are now properly aggregated
2. **Accurate logging**: Request completion logs now show actual step execution and costs
3. **Cost monitoring**: Operations teams can now properly track expenses per request
4. **Performance analysis**: Latency and token usage per step are correctly captured
5. **Validation gates**: Step metadata is essential for validation gate checking

## Testing

The fix has been verified with:

1. Direct call to `stream_chain()` - all 3 steps execute with metadata
2. Metrics aggregation - total tokens, costs correctly calculated
3. Log output - "steps_executed": 3, "total_tokens": 7000+, "total_cost_usd": 0.01+

## No Breaking Changes

- The async wrapper functions in the graph remain unchanged (they were working correctly)
- The node execution continues to work as before
- Only the metadata extraction logic was fixed
- This is a **pure bugfix** with no API or configuration changes

## Performance Impact

- **Negligible**: The fix adds one extra loop iteration per streaming event (3 per request)
- No additional API calls or latency introduced
- No change to computational complexity

## Commit

```
d2e3e31 Fix LangGraph metadata extraction: handle nested event structure in stream_mode='updates'
```
