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
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
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
    Analysis step: Parse user intent and extract key information.

    This is the first step in the prompt-chaining workflow. It analyzes the user's
    request to extract:
    - The primary intent or goal
    - Key entities, topics, or concepts
    - Assessment of task complexity (simple, moderate, complex)
    - Additional contextual information

    The step reads the latest user message from the state, sends it to the LLM
    with the analysis system prompt, and parses the JSON response into an
    AnalysisOutput model.

    Args:
        state: Current ChainState containing messages and prior step outputs
        config: ChainConfig with model selection, token limits, and timeouts

    Returns:
        Dictionary with state updates:
        - analysis: AnalysisOutput as dict (intent, key_entities, complexity, context)
        - messages: Appended response from the LLM
        - step_metadata: Tracking info (tokens, cost, duration)

    Raises:
        ValidationError: If the LLM response doesn't conform to AnalysisOutput schema
        FileNotFoundError: If the system prompt file is not found
        ValueError: If unable to extract user message from state
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

    # Initialize ChatAnthropic client
    llm = ChatAnthropic(
        model=config.analyze.model,
        temperature=config.analyze.temperature,
        max_tokens=config.analyze.max_tokens,
    )

    # Prepare messages for LLM
    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    try:
        # Call LLM synchronously (non-streaming)
        response = await llm.ainvoke(messages)

        # Extract response text
        response_text = response.content

        # Parse JSON response into AnalysisOutput
        try:
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]

            analysis_dict = json.loads(response_text.strip())
            analysis_output = AnalysisOutput(**analysis_dict)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(
                "Failed to parse analysis step response",
                extra={
                    "step": "analyze",
                    "error": str(e),
                    "response_text": response_text[:500],  # Log first 500 chars
                },
            )
            raise

        # Track token usage and cost
        usage = response.usage_metadata if hasattr(response, "usage_metadata") else None
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
            "messages": [response],  # Append LLM response to messages
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
    Processing step: Generate content based on analysis results.

    This is the second step in the prompt-chaining workflow. It takes the analysis
    output from the previous step and uses it to generate substantive content that
    addresses the user's intent.

    The step builds a processing prompt that incorporates the analysis context,
    sends it to the LLM with the processing system prompt, and parses the JSON
    response into a ProcessOutput model.

    Args:
        state: Current ChainState containing analysis results and messages
        config: ChainConfig with model selection, token limits, and timeouts

    Returns:
        Dictionary with state updates:
        - processed_content: ProcessOutput as dict (content, confidence, metadata)
        - messages: Appended response from the LLM
        - step_metadata: Tracking info (tokens, cost, duration)

    Raises:
        ValidationError: If the LLM response doesn't conform to ProcessOutput schema
        FileNotFoundError: If the system prompt file is not found
        ValueError: If analysis is not available in state
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

    # Initialize ChatAnthropic client
    llm = ChatAnthropic(
        model=config.process.model,
        temperature=config.process.temperature,
        max_tokens=config.process.max_tokens,
    )

    # Prepare messages for LLM
    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=analysis_context),
    ]

    try:
        # Call LLM synchronously (non-streaming)
        response = await llm.ainvoke(messages)

        # Extract response text
        response_text = response.content

        # Parse JSON response into ProcessOutput
        try:
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]

            process_dict = json.loads(response_text.strip())
            process_output = ProcessOutput(**process_dict)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(
                "Failed to parse processing step response",
                extra={
                    "step": "process",
                    "error": str(e),
                    "response_text": response_text[:500],  # Log first 500 chars
                },
            )
            raise

        # Track token usage and cost
        usage = response.usage_metadata if hasattr(response, "usage_metadata") else None
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
            "messages": [response],  # Append LLM response to messages
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


async def synthesize_step(state: ChainState, config: ChainConfig) -> AsyncIterator[dict[str, Any]]:
    """
    Synthesis step: Polish and format the final response (streaming).

    This is the final step in the prompt-chaining workflow. It takes the processed
    content from the previous step and transforms it into a polished, professionally
    formatted response optimized for readability and delivery.

    Unlike the other steps, this step uses streaming (astream) to incrementally
    yield response chunks, enabling real-time delivery to the user.

    Args:
        state: Current ChainState containing processed content and messages
        config: ChainConfig with model selection, token limits, and timeouts

    Yields:
        Dictionary with state updates for each chunk:
        - final_response: Accumulated text from streaming chunks
        - messages: Appended response chunks
        - step_metadata: Tracking info (tokens, cost, duration)

    Raises:
        ValidationError: If the final accumulated response doesn't conform to SynthesisOutput
        FileNotFoundError: If the system prompt file is not found
        ValueError: If processed_content is not available in state
    """
    start_time = time.time()

    # Extract processed content from state
    processed_content = state.get("processed_content")
    if not processed_content:
        raise ValueError("Processed content not found in state for synthesis step")

    # Load system prompt
    system_prompt = load_system_prompt(config.synthesize.system_prompt_file)

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

    # Initialize ChatAnthropic client with streaming enabled
    llm = ChatAnthropic(
        model=config.synthesize.model,
        temperature=config.synthesize.temperature,
        max_tokens=config.synthesize.max_tokens,
        streaming=True,
    )

    # Prepare messages for LLM
    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=synthesis_context),
    ]

    try:
        accumulated_text = ""
        total_input_tokens = 0
        total_output_tokens = 0

        # Stream response from LLM
        async for chunk in await llm.astream(messages):
            # Extract text content from chunk
            chunk_text = chunk.content if hasattr(chunk, "content") else str(chunk)

            # Accumulate text for final response
            accumulated_text += chunk_text

            # Extract token usage from chunk if available (typically only on final chunk)
            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                total_input_tokens = chunk.usage_metadata.get("input_tokens", 0)
                total_output_tokens = chunk.usage_metadata.get("output_tokens", 0)

            # Yield incremental state update
            yield {
                "final_response": accumulated_text,
                "messages": [chunk],  # Append chunk to messages
                "step_metadata": {
                    "synthesize": {
                        "elapsed_seconds": time.time() - start_time,
                        "accumulated_output": len(accumulated_text),
                    }
                },
            }

        # Parse final accumulated text into SynthesisOutput
        try:
            # Remove markdown code blocks if present
            response_text = accumulated_text
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]

            synthesis_dict = json.loads(response_text.strip())
            synthesis_output = SynthesisOutput(**synthesis_dict)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(
                "Failed to parse synthesis step response as JSON, using accumulated text",
                extra={
                    "step": "synthesize",
                    "error": str(e),
                    "accumulated_length": len(accumulated_text),
                },
            )
            # If parsing fails, create a SynthesisOutput from accumulated text
            synthesis_output = SynthesisOutput(
                final_text=accumulated_text,
                formatting="plain",
            )

        # Track token usage and cost
        cost_metrics = calculate_cost(
            config.synthesize.model, total_input_tokens, total_output_tokens
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

        # Yield final state update with complete metadata
        yield {
            "final_response": synthesis_output.final_text,
            "messages": [],  # No additional messages to append
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
