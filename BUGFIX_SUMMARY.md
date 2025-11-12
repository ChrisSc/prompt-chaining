# LangGraph Critical Bugfix Summary

## Problem Statement

The LangGraph chain was executing all three processing steps correctly, but **step metadata (tokens, costs, timings) was not being captured or logged**.

Initial problem report showed:
```json
{
  "steps_executed": 0,
  "total_tokens": 0,
  "total_cost_usd": 0.0
}
```

This prevented proper cost tracking, performance monitoring, and verification of pipeline execution.

## Root Cause Analysis

### Event Structure Issue

When LangGraph's `graph.astream()` is used with `stream_mode="updates"`, each event has a **nested structure**:

```python
# Actual event structure from LangGraph
{
    "analyze": {                    # <- Node name is the top-level key
        "analysis": {...},          # <- Step output
        "messages": [...],          # <- Updated messages
        "step_metadata": {...}      # <- Metrics (INSIDE the node dict!)
    }
}
```

### Buggy Code

The `stream_chain()` function was checking the wrong level:

```python
# WRONG: Looking for "step_metadata" in event
# But event = {"analyze": {...}}, so this check always fails
if "step_metadata" in event:
    step_metadata = event.get("step_metadata", {})
    accumulated_metadata.update(step_metadata)
```

**Result**: Metadata was never extracted, never accumulated, and never logged.

## Solution Implemented

### Updated event extraction logic

```python
# CORRECT: Iterate through node updates to access nested step_metadata
for node_name, node_update in event.items():
    if isinstance(node_update, dict):
        step_metadata = node_update.get("step_metadata", {})
        if isinstance(step_metadata, dict):
            accumulated_metadata.update(step_metadata)
```

### Files Modified

1. **`src/workflow/chains/graph.py`** (lines 288-312)
   - Fixed `stream_chain()` function to extract metadata from nested event structure
   - Properly accumulates metadata from all three steps

2. **`src/workflow/api/v1/chat.py`** (lines 199-206)
   - Updated API endpoint to extract metadata from nested structure
   - Ensures cost logging works end-to-end

3. **`scripts/dev.sh`** (line 43)
   - Fixed incorrect path to main.py (was `src/orchestrator_worker/main.py`, now `src/workflow/main.py`)

## Validation Results

### Test 1: Simple Request
```
Chain execution:
  - Analyze: 1415 tokens, $0.0018, 2.21s
  - Process: 2849 tokens, $0.0039, 3.84s
  - Synthesize: 2788 tokens, $0.0033, 2.15s

Aggregated metrics:
  ✓ Steps executed: 3
  ✓ Total tokens: 7052
  ✓ Total cost: $0.008944
  ✓ Total time: 8.21s
```

### Test 2: Complex Request
```
Chain execution:
  - Analyze: 1466 tokens, $0.0021, 2.31s
  - Process: 3632 tokens, $0.0076, 10.52s
  - Synthesize: 4372 tokens, $0.0083, 7.19s

Aggregated metrics:
  ✓ Steps executed: 3
  ✓ Total tokens: 9470
  ✓ Total cost: $0.017938
  ✓ Total time: 20.03s
```

## Impact

### What's Fixed

1. ✓ Cost tracking now works (previously reported $0.00)
2. ✓ Step execution logging is accurate (previously reported 0 steps)
3. ✓ Token usage is tracked per step (previously all zeros)
4. ✓ Performance metrics are captured (latency per step)
5. ✓ Request completion logs are meaningful (had aggregated metrics)

### What's NOT Changed

- The async wrapper functions (they were working correctly)
- The node execution logic (unchanged)
- The LLM integration (unchanged)
- The validation gates (unchanged)
- API contracts (no breaking changes)

### Performance Impact

- **Negligible**: One extra loop iteration per streaming event (3 iterations per request)
- No additional API calls
- No increase in computational complexity
- No latency impact

## Verification Steps

To verify the fix in your environment:

```python
import asyncio
from workflow.chains.graph import build_chain_graph, stream_chain
from workflow.config import Settings
from workflow.models.chains import ChainState
from langchain_core.messages import HumanMessage

async def verify():
    settings = Settings()
    graph = build_chain_graph(settings.chain_config)

    initial_state = ChainState(
        messages=[HumanMessage(content='Test')],
        analysis=None, processed_content=None,
        final_response=None, step_metadata={}
    )

    metadata = {}
    async for update in stream_chain(graph, initial_state, settings.chain_config):
        for node, node_data in update.items():
            if "step_metadata" in node_data:
                metadata.update(node_data["step_metadata"])

    print(f"Steps: {len(metadata)}")  # Should be 3
    print(f"Tokens: {sum(m['total_tokens'] for m in metadata.values())}")  # Should be > 0
    print(f"Cost: ${sum(m['cost_usd'] for m in metadata.values()):.6f}")  # Should be > 0

asyncio.run(verify())
```

## Commit Information

```
Commit: d2e3e31
Message: Fix LangGraph metadata extraction: handle nested event structure in stream_mode='updates'
Files changed: 3
  - src/workflow/chains/graph.py
  - src/workflow/api/v1/chat.py
  - scripts/dev.sh
```

## References

- LangGraph streaming modes documentation
- Event structure with `stream_mode="updates"`
- Token tracking and cost aggregation utilities

## Status

✓ **FIXED AND VERIFIED**
- All three steps execute correctly
- Metadata properly extracted and aggregated
- Cost tracking functional
- Performance metrics captured
- End-to-end validation successful
