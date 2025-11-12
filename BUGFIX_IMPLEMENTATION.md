# Bugfix Implementation Details

## Issue

LangGraph's `stream_mode="updates"` yields events with nested structure:
```python
{"node_name": {"field": value, "step_metadata": {...}}}
```

But the code was checking for `step_metadata` at the top level, causing it to never be found.

## File 1: src/workflow/chains/graph.py

### Location: Lines 288-312 in `stream_chain()` function

### Before (BROKEN)
```python
try:
    # Stream graph execution with state update streaming
    # Uses stream_mode="updates" to yield state dict updates from each node
    # (See ./documentation/langchain/ADVANCED_INDEX.md - LangGraph streaming modes)
    thread_id = str(uuid.uuid4())
    async for event in graph.astream(
        initial_state,
        config={"configurable": {"thread_id": thread_id}},
        stream_mode="updates",
    ):
        # Each event is a state update
        if isinstance(event, dict):
            # Accumulate metadata across steps
            if "step_metadata" in event:  # <- WRONG: step_metadata is nested inside node_update!
                step_metadata = event.get("step_metadata", {})
                if isinstance(step_metadata, dict):
                    accumulated_metadata.update(step_metadata)

            # Yield the state update
            yield event
```

**Problem**: `event` has structure `{"analyze": {...}}`, not `{"step_metadata": {...}}`. The condition `if "step_metadata" in event:` always fails.

### After (FIXED)
```python
try:
    # Stream graph execution with state update streaming
    # Uses stream_mode="updates" to yield state dict updates from each node
    # (See ./documentation/langchain/ADVANCED_INDEX.md - LangGraph streaming modes)
    thread_id = str(uuid.uuid4())
    async for event in graph.astream(
        initial_state,
        config={"configurable": {"thread_id": thread_id}},
        stream_mode="updates",
    ):
        # Each event is a state update in the format:
        # {"node_name": {"field1": value1, "field2": value2, ...}}
        if isinstance(event, dict):
            # Extract step_metadata from the node update
            # With stream_mode="updates", event structure is:
            # {"node_name": {"analysis": {...}, "step_metadata": {...}, ...}}
            for node_name, node_update in event.items():  # <- NEW: Iterate through nodes
                if isinstance(node_update, dict):
                    # Accumulate metadata across steps
                    step_metadata = node_update.get("step_metadata", {})  # <- NEW: Extract from nested dict
                    if isinstance(step_metadata, dict):
                        accumulated_metadata.update(step_metadata)

            # Yield the state update
            yield event
```

**Solution**: Iterate through the event dict to access node_update, then extract step_metadata from there.

---

## File 2: src/workflow/api/v1/chat.py

### Location: Lines 199-206 in `create_chat_completion()` event generator

### Before (BROKEN)
```python
# Stream the chain execution
settings = request.app.state.settings
async for state_update in stream_chain(
    chain_graph, initial_state, settings.chain_config
):
    # Capture step metadata for aggregation
    if "step_metadata" in state_update:  # <- WRONG: step_metadata is nested!
        final_step_metadata.update(state_update.get("step_metadata", {}))

    # Extract content from the state update and convert to OpenAI format
    try:
        chunk = convert_langchain_chunk_to_openai(state_update)
        chunk_json = chunk.model_dump_json()
        yield f"data: {chunk_json}\n\n"
        chunk_count += 1
    except Exception as chunk_error:
        logger.warning(
            "Failed to convert chain state to OpenAI format",
            extra={"error": str(chunk_error)},
        )
        continue
```

**Problem**: Same as above - top-level check fails, metadata never extracted.

### After (FIXED)
```python
# Stream the chain execution
settings = request.app.state.settings
async for state_update in stream_chain(
    chain_graph, initial_state, settings.chain_config
):
    # Capture step metadata for aggregation
    # state_update structure: {"node_name": {"analysis": {...}, "step_metadata": {...}, ...}}
    for node_name, node_update in state_update.items():  # <- NEW: Iterate through nodes
        if isinstance(node_update, dict):
            step_metadata = node_update.get("step_metadata", {})  # <- NEW: Extract from nested dict
            if isinstance(step_metadata, dict):
                final_step_metadata.update(step_metadata)

    # Extract content from the state update and convert to OpenAI format
    try:
        chunk = convert_langchain_chunk_to_openai(state_update)
        chunk_json = chunk.model_dump_json()
        yield f"data: {chunk_json}\n\n"
        chunk_count += 1
    except Exception as chunk_error:
        logger.warning(
            "Failed to convert chain state to OpenAI format",
            extra={"error": str(chunk_error)},
        )
        continue
```

**Solution**: Same pattern as graph.py - iterate through the dict to access nested step_metadata.

---

## File 3: scripts/dev.sh

### Location: Line 43

### Before (BROKEN)
```bash
fastapi dev src/orchestrator_worker/main.py --host ${API_HOST} --port ${API_PORT}
```

**Problem**: Path doesn't exist, dev server fails to start.

### After (FIXED)
```bash
fastapi dev src/workflow/main.py --host ${API_HOST} --port ${API_PORT}
```

**Solution**: Fixed path to actual main.py location.

---

## Event Structure Explanation

When LangGraph executes with `stream_mode="updates"`, it yields events like this:

```python
# Event from analyze node
{
    "analyze": {
        "analysis": {
            "intent": "...",
            "key_entities": ["..."],
            "complexity": "simple",
            "context": {...}
        },
        "messages": [HumanMessage(...), AIMessage(...)],
        "step_metadata": {
            "analyze": {
                "elapsed_seconds": 2.1,
                "input_tokens": 1315,
                "output_tokens": 79,
                "total_tokens": 1394,
                "cost_usd": 0.00171
            }
        }
    }
}

# Event from process node
{
    "process": {
        "processed_content": {
            "content": "...",
            "confidence": 0.95,
            "metadata": {...}
        },
        "messages": [...],
        "step_metadata": {
            "process": {
                "elapsed_seconds": 3.3,
                "input_tokens": 2576,
                "output_tokens": 221,
                "total_tokens": 2797,
                "cost_usd": 0.00368
            }
        }
    }
}

# Event from synthesize node
{
    "synthesize": {
        "final_response": "...",
        "step_metadata": {
            "synthesize": {
                "elapsed_seconds": 2.1,
                "input_tokens": 2637,
                "output_tokens": 131,
                "total_tokens": 2768,
                "cost_usd": 0.00329
            }
        }
    }
}
```

The fix correctly extracts `step_metadata` from each node update by:

1. Iterating `for node_name, node_update in event.items()`
2. Accessing `node_update.get("step_metadata", {})`
3. Aggregating across all steps

---

## Testing

```python
# Before fix
for state_update in stream_chain(...):
    if "step_metadata" in state_update:  # Always False!
        pass  # Never executed

# After fix
for state_update in stream_chain(...):
    for node_name, node_update in state_update.items():
        if "step_metadata" in node_update:  # Now True for each node!
            metadata = node_update["step_metadata"]  # Successfully extracted!
```

---

## Deployment

No configuration changes needed. Simply deploy the updated code:

```bash
git pull
# or
git checkout main  # Once merged
```

The fix is backward compatible and doesn't break any existing functionality.
