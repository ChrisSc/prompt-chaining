"""
LangGraph StateGraph orchestration for the prompt-chaining workflow.

This module implements the complete LangGraph StateGraph that orchestrates
the three-step prompt-chaining pipeline: analyze, process, and synthesize.

The graph handles:
- Sequential execution of steps with proper state management
- Validation gates between steps using conditional edges
- Error handling and fallback behavior
- Token usage and cost tracking
- Streaming synthesis output

Components:
- build_chain_graph: Compiles the complete graph from step functions
- error_step: Handles validation failures and errors
- invoke_chain: Non-streaming invocation for testing
- stream_chain: Streaming execution with async generator interface
"""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from workflow.chains.steps import analyze_step, process_step, synthesize_step
from workflow.chains.validation import should_proceed_to_process, should_proceed_to_synthesize
from workflow.models.chains import ChainConfig, ChainState
from workflow.utils.logging import get_logger
from workflow.utils.token_tracking import aggregate_step_metrics

logger = get_logger(__name__)


async def error_step(state: ChainState, config: ChainConfig) -> dict[str, Any]:
    """
    Handle errors in the prompt-chaining workflow.

    This step is executed when validation gates or processing steps fail.
    It extracts error information from the state and creates a user-friendly
    error response, then returns state updates with the error message.

    Args:
        state: Current ChainState containing any error context
        config: ChainConfig for error handling configuration

    Returns:
        Dictionary with state updates:
        - final_response: Error message for the user
        - step_metadata: Error tracking information
    """
    logger.warning("Error step executed - workflow validation or processing failed")

    # Extract error information if available
    error_message = (
        "An error occurred during processing. Please try again with a different request."
    )

    # Check if there's specific error context in messages or state
    if state.get("messages"):
        # Try to find error information in messages
        for message in state.get("messages", []):
            if hasattr(message, "content") and "error" in str(message.content).lower():
                error_message = f"Processing error: {message.content[:200]}"
                break

    logger.error(
        "Workflow error step completed",
        extra={
            "step": "error",
            "error_message": error_message[:100],  # Log first 100 chars
        },
    )

    # Return state update with error message
    return {
        "final_response": error_message,
        "step_metadata": {
            "error": {
                "occurred": True,
                "message": error_message,
            }
        },
    }


def build_chain_graph(config: ChainConfig) -> Any:
    """
    Build and compile the LangGraph StateGraph for prompt-chaining.

    Creates a complete graph with:
    - START node connecting to "analyze" step
    - "analyze" step with conditional edge to "process" or "error"
    - "process" step with conditional edge to "synthesize" or "error"
    - "synthesize" step terminal edge to END
    - "error" step terminal edge to END

    Validation gates between steps ensure quality outputs:
    - After analyze: should_proceed_to_process validates AnalysisOutput
    - After process: should_proceed_to_synthesize validates ProcessOutput

    Args:
        config: ChainConfig with model selection, token limits, and timeouts

    Returns:
        Compiled StateGraph ready for execution
    """
    logger.info(
        "Building LangGraph StateGraph",
        extra={
            "analyze_model": config.analyze.model,
            "process_model": config.process.model,
            "synthesize_model": config.synthesize.model,
            "validation_enabled": config.enable_validation,
        },
    )

    # Create StateGraph with ChainState
    graph = StateGraph(ChainState)

    # Add nodes for each step
    # Create wrapper functions that LangGraph can properly invoke
    # LangGraph will detect these are async and handle them correctly
    async def analyze_wrapper(state: ChainState) -> dict[str, Any]:
        return await analyze_step(state, config)

    async def process_wrapper(state: ChainState) -> dict[str, Any]:
        return await process_step(state, config)

    async def synthesize_wrapper(state: ChainState) -> dict[str, Any]:
        return await synthesize_step(state, config)

    async def error_wrapper(state: ChainState) -> dict[str, Any]:
        return await error_step(state, config)

    graph.add_node("analyze", analyze_wrapper)
    graph.add_node("process", process_wrapper)

    # synthesize_step: Returns a single dict (not a generator) for LangGraph compatibility.
    # Streaming for HTTP SSE responses is handled at the FastAPI endpoint level.
    # See stream_chain() in this module for how synthesis output is streamed to clients.
    graph.add_node("synthesize", synthesize_wrapper)
    graph.add_node("error", error_wrapper)

    # Add START edge to analyze
    graph.add_edge(START, "analyze")

    # Add conditional edges with validation gates
    graph.add_conditional_edges(
        "analyze",
        should_proceed_to_process,
        {
            "process": "process",
            "error": "error",
        },
    )

    graph.add_conditional_edges(
        "process",
        should_proceed_to_synthesize,
        {
            "synthesize": "synthesize",
            "error": "error",
        },
    )

    # Add terminal edges
    graph.add_edge("synthesize", END)
    graph.add_edge("error", END)

    # Compile with MemorySaver checkpointer for state persistence and metrics tracking
    checkpointer = MemorySaver()
    compiled_graph = graph.compile(checkpointer=checkpointer)
    logger.info("LangGraph StateGraph compiled successfully with MemorySaver checkpointer")

    return compiled_graph


async def invoke_chain(graph: Any, initial_state: ChainState, config: ChainConfig) -> ChainState:
    """
    Non-streaming invocation of the prompt-chaining graph.

    Executes the complete graph in non-streaming mode and returns the final state.
    Useful for testing, batch processing, or scenarios where streaming is not needed.

    Args:
        graph: Compiled LangGraph StateGraph
        initial_state: Initial ChainState to start execution with
        config: ChainConfig for the chain execution

    Returns:
        Final ChainState after all steps complete

    Raises:
        ValueError: If graph execution fails
        asyncio.TimeoutError: If execution exceeds phase timeouts
    """
    logger.debug(
        "Starting non-streaming chain invocation",
        extra={
            "message_count": len(initial_state.get("messages", [])),
        },
    )

    start_time = time.time()

    try:
        # Invoke graph - use ainvoke for async support
        final_state = await graph.ainvoke(initial_state)

        elapsed_time = time.time() - start_time

        logger.info(
            "Chain invocation completed",
            extra={
                "elapsed_seconds": elapsed_time,
                "final_response_length": len(final_state.get("final_response", "")),
            },
        )

        return final_state

    except asyncio.TimeoutError as exc:
        logger.error(
            "Chain invocation timeout",
            extra={
                "error": str(exc),
                "elapsed_seconds": time.time() - start_time,
            },
        )
        raise

    except Exception as exc:
        logger.error(
            "Chain invocation failed",
            extra={
                "error": str(exc),
                "error_type": type(exc).__name__,
                "elapsed_seconds": time.time() - start_time,
            },
        )
        raise


async def stream_chain(
    graph: Any, initial_state: ChainState, config: ChainConfig
) -> AsyncIterator[dict[str, Any]]:
    """
    Stream the prompt-chaining graph execution with async generator interface.

    Executes the graph with streaming enabled (astream), yielding state updates
    from each step. All steps (analyze, process, synthesize) are non-streaming
    at the LangGraph node level and return single dictionaries. State updates are
    yielded for each step completion.

    Streaming for HTTP SSE delivery to clients happens at the FastAPI endpoint
    level, where final_response is streamed back to users. This architecture
    ensures LangGraph nodes follow the single-dict-return pattern while still
    supporting streaming responses to end users.

    Args:
        graph: Compiled LangGraph StateGraph
        initial_state: Initial ChainState to start execution with
        config: ChainConfig for the chain execution

    Yields:
        Dictionary state updates from each step, containing accumulated results
        and metadata. Later updates merge with earlier ones via ChainState reducers.

    Raises:
        ValueError: If graph execution fails
        asyncio.TimeoutError: If execution exceeds phase timeouts
    """
    logger.debug(
        "Starting streaming chain execution",
        extra={
            "message_count": len(initial_state.get("messages", [])),
        },
    )

    start_time = time.time()
    accumulated_metadata = {}

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
                for node_name, node_update in event.items():
                    if isinstance(node_update, dict):
                        # Accumulate metadata across steps
                        step_metadata = node_update.get("step_metadata", {})
                        if isinstance(step_metadata, dict):
                            accumulated_metadata.update(step_metadata)

                # Yield the state update
                yield event

        elapsed_time = time.time() - start_time

        # Calculate aggregated metrics from step_metadata
        if accumulated_metadata:
            total_tokens, total_cost, total_elapsed = aggregate_step_metrics(accumulated_metadata)
        else:
            total_tokens, total_cost, total_elapsed = 0, 0.0, 0.0

        logger.info(
            "Chain streaming completed",
            extra={
                "elapsed_seconds": elapsed_time,
                "steps_executed": len(accumulated_metadata),
                "total_tokens": total_tokens,
                "total_cost_usd": total_cost,
                "aggregated_elapsed_seconds": total_elapsed,
            },
        )

    except asyncio.TimeoutError as exc:
        logger.error(
            "Chain streaming timeout",
            extra={
                "error": str(exc),
                "elapsed_seconds": time.time() - start_time,
            },
        )
        raise

    except asyncio.CancelledError:
        logger.info("Chain streaming cancelled by client")
        raise

    except Exception as exc:
        logger.error(
            "Chain streaming failed",
            extra={
                "error": str(exc),
                "error_type": type(exc).__name__,
                "elapsed_seconds": time.time() - start_time,
            },
        )
        raise
