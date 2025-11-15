"""
Step functions for the prompt-chaining workflow.

This module implements the three core steps of the prompt-chaining pattern:
1. analyze_step: Parses user intent and extracts key information
2. process_step: Generates content based on analysis results
3. synthesize_step: Polishes and formats the final response

Each step is an async function that processes the current ChainState and returns
updates to the state. Steps are orchestrated by LangGraph and may have validation
gates between them to ensure quality outputs.

System prompts are loaded from the prompts/ directory and control the behavior
of each step. Token usage and costs are tracked throughout execution.
"""

import json
import time
from pathlib import Path
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from pydantic import ValidationError

from workflow.models.chains import (
    AnalysisOutput,
    ChainConfig,
    ChainState,
    ProcessOutput,
    SynthesisOutput,
)
from workflow.utils.logging import get_logger
from workflow.utils.token_tracking import calculate_cost

logger = get_logger(__name__)


def load_system_prompt(filename: str) -> str:
    """
    Load a system prompt from the prompts directory.

    Reads a markdown file from src/workflow/prompts/ and returns its contents
    as a string. Used by each step function to load its system prompt.

    Args:
        filename: Name of the prompt file (e.g., "chain_analyze.md")

    Returns:
        The prompt file contents as a string

    Raises:
        FileNotFoundError: If the prompt file is not found
        IOError: If there's an error reading the file
    """
    prompt_path = Path(__file__).parent.parent / "prompts" / filename

    if not prompt_path.exists():
        raise FileNotFoundError(f"System prompt not found: {prompt_path}")

    try:
        with open(prompt_path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        logger.error(
            f"Failed to load system prompt: {filename}",
            extra={"filename": filename, "error": str(e)},
        )
        raise


async def analyze_step(state: ChainState, config: ChainConfig) -> dict[str, Any]:
    """
    Analyze step: Extract intent and key information from user request.

    First step in prompt-chaining: parses user intent, entities, and complexity level.
    Uses Claude's native structured output API for reliable schema validation.

    Args:
        state: ChainState with messages
        config: ChainConfig with model and timeout settings

    Returns:
        Dict with analysis, messages, and step_metadata

    Raises:
        ValueError: If user message cannot be extracted
        Exception: If LLM fails or structured output validation fails
    """
    start_time = time.time()

    # Extract latest user message from state
    if not state.get("messages"):
        raise ValueError("No messages found in state for analysis step")

    # Get the latest user message (most recent message in the list)
    user_message = None
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage) or (
            isinstance(message, dict) and message.get("role") == "user"
        ):
            if isinstance(message, dict):
                user_message = message.get("content", "")
            else:
                user_message = message.content
            break

    if not user_message:
        raise ValueError("Could not extract user message from state for analysis step")

    # Load system prompt
    system_prompt = load_system_prompt(config.analyze.system_prompt_file)

    # Initialize ChatAnthropic client with request_id propagation to Anthropic API
    # The request_id flows: Middleware → ContextVar → ChainState → extra_headers
    # This enables distributed tracing by including the request ID in all Anthropic API calls,
    # allowing correlation of Claude API logs with our internal logs for end-to-end debugging.
    llm = ChatAnthropic(
        model=config.analyze.model,
        temperature=config.analyze.temperature,
        max_tokens=config.analyze.max_tokens,
        extra_headers={"X-Request-ID": state.get("request_id", "")},
    )

    # Enable structured output with Claude's native JSON schema API
    # This enforces schema validation at the API level, eliminating manual JSON parsing
    # include_raw=True returns (parsed_object, raw_message) to access token usage
    structured_llm = llm.with_structured_output(
        AnalysisOutput, method="json_schema", include_raw=True
    )

    # Prepare messages for LLM
    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    try:
        # Call LLM with structured output
        # include_raw=True returns dict with keys: 'parsed', 'raw', 'parsing_error'
        result = await structured_llm.ainvoke(messages)
        analysis_output = result.get("parsed")
        raw_message = result.get("raw")

        if not analysis_output:
            raise ValueError(
                f"Failed to parse analysis output. Parsing error: {result.get('parsing_error')}"
            )

        # Track token usage and cost
        usage = (
            raw_message.usage_metadata
            if hasattr(raw_message, "usage_metadata")
            else None
        )
        input_tokens = usage.get("input_tokens", 0) if usage else 0
        output_tokens = usage.get("output_tokens", 0) if usage else 0
        cost_metrics = calculate_cost(config.analyze.model, input_tokens, output_tokens)

        elapsed_time = time.time() - start_time

        logger.info(
            "Analysis step completed",
            extra={
                "step": "analyze",
                "elapsed_seconds": elapsed_time,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "input_cost_usd": cost_metrics.input_cost_usd,
                "output_cost_usd": cost_metrics.output_cost_usd,
                "total_cost_usd": cost_metrics.total_cost_usd,
                "intent": analysis_output.intent[:100],  # Log first 100 chars of intent
            },
        )

        # Return state updates
        return {
            "analysis": analysis_output.model_dump(),
            "messages": [raw_message],  # Append LLM response to messages
            "step_metadata": {
                "analyze": {
                    "elapsed_seconds": elapsed_time,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "cost_usd": cost_metrics.total_cost_usd,
                }
            },
        }

    except Exception as e:
        logger.error(
            "Analysis step failed",
            extra={
                "step": "analyze",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise


async def process_step(state: ChainState, config: ChainConfig) -> dict[str, Any]:
    """
    Process step: Generate content based on analysis results.

    Second step in prompt-chaining: creates substantive content addressing user intent.
    Uses Claude's native structured output API for reliable schema validation.

    Args:
        state: ChainState with analysis results
        config: ChainConfig with model and timeout settings

    Returns:
        Dict with processed_content, messages, and step_metadata

    Raises:
        ValueError: If analysis not available in state
        Exception: If LLM fails or structured output validation fails
    """
    start_time = time.time()

    # Extract analysis from state
    analysis = state.get("analysis")
    if not analysis:
        raise ValueError("Analysis not found in state for processing step")

    # Load system prompt
    system_prompt = load_system_prompt(config.process.system_prompt_file)

    # Build processing prompt that incorporates analysis context
    analysis_context = (
        f"Based on the analysis of the user's request, here is the context for content generation:\n\n"
        f"Intent: {analysis.get('intent', '')}\n"
        f"Key Entities: {', '.join(analysis.get('key_entities', []))}\n"
        f"Complexity Level: {analysis.get('complexity', 'moderate')}\n"
        f"Additional Context: {json.dumps(analysis.get('context', {}), indent=2)}\n\n"
        f"Please generate content that directly addresses this intent and complexity level."
    )

    # Initialize ChatAnthropic client with request_id propagation to Anthropic API
    # The request_id from ChainState is passed via extra_headers for distributed tracing.
    # This allows correlation of this processing step with Anthropic API logs.
    llm = ChatAnthropic(
        model=config.process.model,
        temperature=config.process.temperature,
        max_tokens=config.process.max_tokens,
        extra_headers={"X-Request-ID": state.get("request_id", "")},
    )

    # Enable structured output with Claude's native JSON schema API
    # This enforces schema validation at the API level, eliminating manual JSON parsing
    # include_raw=True returns (parsed_object, raw_message) to access token usage
    structured_llm = llm.with_structured_output(
        ProcessOutput, method="json_schema", include_raw=True
    )

    # Prepare messages for LLM
    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=analysis_context),
    ]

    try:
        # Call LLM with structured output
        # include_raw=True returns dict with keys: 'parsed', 'raw', 'parsing_error'
        result = await structured_llm.ainvoke(messages)
        process_output = result.get("parsed")
        raw_message = result.get("raw")

        if not process_output:
            raise ValueError(
                f"Failed to parse process output. Parsing error: {result.get('parsing_error')}"
            )

        # Track token usage and cost
        usage = (
            raw_message.usage_metadata
            if hasattr(raw_message, "usage_metadata")
            else None
        )
        input_tokens = usage.get("input_tokens", 0) if usage else 0
        output_tokens = usage.get("output_tokens", 0) if usage else 0
        cost_metrics = calculate_cost(config.process.model, input_tokens, output_tokens)

        elapsed_time = time.time() - start_time

        logger.info(
            "Processing step completed",
            extra={
                "step": "process",
                "elapsed_seconds": elapsed_time,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "input_cost_usd": cost_metrics.input_cost_usd,
                "output_cost_usd": cost_metrics.output_cost_usd,
                "total_cost_usd": cost_metrics.total_cost_usd,
                "confidence": process_output.confidence,
                "content_length": len(process_output.content),
            },
        )

        # Return state updates
        return {
            "processed_content": process_output.model_dump(),
            "messages": [raw_message],  # Append LLM response to messages
            "step_metadata": {
                "process": {
                    "elapsed_seconds": elapsed_time,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "cost_usd": cost_metrics.total_cost_usd,
                    "confidence": process_output.confidence,
                }
            },
        }

    except Exception as e:
        logger.error(
            "Processing step failed",
            extra={
                "step": "process",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise


async def synthesize_step(
    state: ChainState,
    runnable_config: RunnableConfig,
    chain_config: ChainConfig,
) -> dict[str, Any]:
    """
    Synthesize step: Polish and format final response with token streaming.

    Final step in prompt-chaining: streams tokens via get_stream_writer() for real-time
    delivery while maintaining state compatibility. Streaming enabled via custom mode.

    Args:
        state: ChainState with processed content
        runnable_config: RunnableConfig for streaming context propagation
        chain_config: ChainConfig with model and timeout settings

    Returns:
        Dict with final_response and step_metadata

    Raises:
        ValueError: If processed_content unavailable in state
    """
    start_time = time.time()

    # Extract processed content from state
    processed_content = state.get("processed_content")
    if not processed_content:
        raise ValueError("Processed content not found in state for synthesis step")

    # Load system prompt
    system_prompt = load_system_prompt(chain_config.synthesize.system_prompt_file)

    # Build synthesis prompt from processed content
    if isinstance(processed_content, dict):
        content_text = processed_content.get("content", "")
        confidence = processed_content.get("confidence", 0.8)
        metadata = processed_content.get("metadata", {})
    else:
        # Handle case where processed_content is already a ProcessOutput object
        content_text = str(processed_content)
        confidence = 0.8
        metadata = {}

    synthesis_context = (
        f"Please review and polish the following generated content. "
        f"Apply appropriate formatting, improve clarity and flow, and ensure "
        f"the response is professional and user-ready.\n\n"
        f"Generated Content:\n{content_text}\n\n"
        f"Confidence Level: {confidence}\n"
        f"Generation Metadata: {json.dumps(metadata, indent=2)}\n\n"
        f"Produce a polished, formatted final response."
    )

    # Initialize ChatAnthropic client for streaming with request_id propagation to Anthropic API
    # The request_id from ChainState is passed via extra_headers for distributed tracing.
    # This allows correlation of the streaming synthesis step with Anthropic API logs.
    llm = ChatAnthropic(
        model=chain_config.synthesize.model,
        temperature=chain_config.synthesize.temperature,
        max_tokens=chain_config.synthesize.max_tokens,
        extra_headers={"X-Request-ID": state.get("request_id", "")},
    )

    # Prepare messages for LLM
    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=synthesis_context),
    ]

    try:
        # Get the stream writer for custom token streaming
        # Per LangGraph documentation, this works inside graph nodes to emit custom data
        writer = get_stream_writer()

        logger.info(
            "Stream writer obtained",
            extra={
                "step": "synthesize",
                "writer_is_none": writer is None,
                "writer_callable": callable(writer),
                "runnable_config_is_none": runnable_config is None,
            },
        )

        # Stream from Claude and accumulate response while emitting tokens
        final_response = ""
        total_input_tokens = 0
        total_output_tokens = 0
        token_count = 0

        # Use Claude's stream API to get tokens progressively
        # Pattern from documentation: ./documentation/langchain/oss/python/langgraph/streaming.md lines 559-676
        # astream yields AIMessageChunk objects with token content
        # Pass runnable_config to ensure proper context propagation for get_stream_writer()
        async for chunk in llm.astream(messages, config=runnable_config):
            # Extract token from chunk
            token = chunk.content if chunk.content else ""
            if token:
                token_count += 1
                final_response += token
                # Emit token via stream writer for "custom" mode streaming
                if writer is not None:
                    try:
                        writer({"type": "token", "content": token})
                        # Sample-based logging: log every 100 tokens at DEBUG level
                        if token_count % 100 == 0:
                            logger.debug(
                                "Tokens streaming to client",
                                extra={
                                    "step": "synthesize",
                                    "token_count": token_count,
                                },
                            )
                    except Exception as write_error:
                        logger.warning(
                            "Failed to write token via stream writer",
                            extra={
                                "step": "synthesize",
                                "error": str(write_error),
                            },
                        )
                        # Continue processing despite write error

            # Capture token usage from response metadata
            # Usage is typically only populated on the final chunk
            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                total_input_tokens = chunk.usage_metadata.get("input_tokens", 0)
                total_output_tokens = chunk.usage_metadata.get("output_tokens", 0)

        # Create SynthesisOutput from clean markdown response
        # The final_response is already clean formatted markdown/text (no JSON wrapper)
        # Detect formatting based on content characteristics
        response_text = final_response.strip()

        # Simple heuristic to detect formatting style:
        # - If contains markdown headers (#, ##, ###), treat as markdown
        # - If contains numbered/bullet lists with specific patterns, detect accordingly
        # - Default to markdown for modern rich formatting
        if "#" in response_text and ("\n" in response_text or "##" in response_text):
            detected_formatting = "markdown"
        elif any(response_text.startswith(f"{i}.") for i in range(1, 10)):
            detected_formatting = "structured"
        elif "  -" in response_text or "\n-" in response_text:
            detected_formatting = "markdown"
        else:
            # Default to markdown for clean, modern formatting
            detected_formatting = "markdown"

        try:
            synthesis_output = SynthesisOutput(
                final_text=response_text,
                formatting=detected_formatting,
            )
        except ValidationError as e:
            logger.error(
                "Failed to create SynthesisOutput",
                extra={
                    "step": "synthesize",
                    "error": str(e),
                    "response_length": len(final_response),
                },
            )
            # Fallback: create output with response text as-is
            synthesis_output = SynthesisOutput(
                final_text=response_text,
                formatting="markdown",
            )

        # Track token usage and cost
        cost_metrics = calculate_cost(
            chain_config.synthesize.model, total_input_tokens, total_output_tokens
        )

        elapsed_time = time.time() - start_time

        logger.info(
            "Synthesis step completed",
            extra={
                "step": "synthesize",
                "elapsed_seconds": elapsed_time,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "input_cost_usd": cost_metrics.input_cost_usd,
                "output_cost_usd": cost_metrics.output_cost_usd,
                "total_cost_usd": cost_metrics.total_cost_usd,
                "final_text_length": len(synthesis_output.final_text),
                "formatting": synthesis_output.formatting,
            },
        )

        # Return single dict with complete synthesis result for LangGraph
        # Even though we streamed tokens, we still return complete dict for graph compatibility
        return {
            "final_response": synthesis_output.final_text,
            "step_metadata": {
                "synthesize": {
                    "elapsed_seconds": elapsed_time,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "total_tokens": total_input_tokens + total_output_tokens,
                    "cost_usd": cost_metrics.total_cost_usd,
                    "formatting": synthesis_output.formatting,
                }
            },
        }

    except Exception as e:
        logger.error(
            "Synthesis step failed",
            extra={
                "step": "synthesize",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise
