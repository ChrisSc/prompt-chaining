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
from collections.abc import AsyncIterator
from typing import Any

from langgraph.graph import END, START, StateGraph

from workflow.chains.steps import analyze_step, process_step, synthesize_step
from workflow.chains.validation import should_proceed_to_process, should_proceed_to_synthesize
from workflow.models.chains import ChainConfig, ChainState
from workflow.utils.logging import get_logger

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
    # Use lambda to capture config in closure
    graph.add_node("analyze", lambda state: analyze_step(state, config))
    graph.add_node("process", lambda state: process_step(state, config))

    # Note: synthesize_step is an async generator for streaming
    # LangGraph will handle this properly when used with astream()
    graph.add_node("synthesize", lambda state: synthesize_step(state, config))
    graph.add_node("error", lambda state: error_step(state, config))

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

    # Compile and return
    compiled_graph = graph.compile()
    logger.info("LangGraph StateGraph compiled successfully")

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
    for each step. This enables token-by-token delivery to the client during
    the synthesis step while maintaining proper state management through all steps.

    The synthesize step is the primary streaming phase - it uses astream internally
    and yields incremental text updates. Earlier steps (analyze, process) are
    non-streaming but their state updates are also yielded.

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
        # Stream graph execution with message-level streaming
        # This uses stream_mode="messages" to get token-level updates during synthesis
        async for event in await graph.astream(
            initial_state,
            stream_mode="messages",
        ):
            # Each event is a state update
            # The synthesize step yields incremental updates during streaming
            if isinstance(event, dict):
                # Accumulate metadata across steps
                if "step_metadata" in event:
                    step_metadata = event.get("step_metadata", {})
                    if isinstance(step_metadata, dict):
                        accumulated_metadata.update(step_metadata)

                # Yield the state update
                yield event

        elapsed_time = time.time() - start_time

        logger.info(
            "Chain streaming completed",
            extra={
                "elapsed_seconds": elapsed_time,
                "steps_executed": len(accumulated_metadata),
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
