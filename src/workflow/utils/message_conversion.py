"""
Message format conversion utilities for OpenAI ↔ LangChain compatibility.

This module provides conversion functions between OpenAI API message format
(used by FastAPI endpoints) and LangChain message format (used internally
by the prompt-chaining workflow and LangGraph).

Conversions:
- OpenAI ChatMessage list → LangChain BaseMessage list
- LangChain chunks/messages → OpenAI ChatCompletionChunk format

This enables seamless integration between the OpenAI-compatible API
and the LangChain/LangGraph-based internal implementation.
"""

import time
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from workflow.models.openai import (
    ChatCompletionChunk,
    ChatCompletionStreamChoice,
    ChatMessage,
    ChoiceDelta,
    MessageRole,
)
from workflow.utils.logging import get_logger

logger = get_logger(__name__)


def split_response_into_chunks(text: str, chunk_size: int = 50) -> list[str]:
    """
    Split long text into progressively yielded chunks for streaming.

    Splits text by word boundaries to avoid breaking words mid-stream.
    This enables progressive streaming to clients, making responses appear
    word-by-word rather than all at once.

    Args:
        text: Text to split into streaming chunks
        chunk_size: Target size per chunk in characters (default: 50)
                   Actual chunks may be slightly larger to preserve word boundaries

    Returns:
        List of text chunks, each approximating chunk_size characters
        Empty list if input text is empty or None

    Example:
        >>> chunks = split_response_into_chunks("Hello world from streaming", chunk_size=10)
        >>> len(chunks) > 1
        True
        >>> "".join(chunks) == "Hello world from streaming"
        True

    Reference:
        ./documentation/langchain/FASTAPI_LANGCHAIN_STREAMING_CHEATSHEET.md - progressive chunk streaming
        ./documentation/fastapi/INDEX_AGENT.md - streaming responses
    """
    if not text:
        return []

    chunks: list[str] = []
    words = text.split()
    current_chunk = ""

    for word in words:
        # Calculate size if we add this word
        test_chunk = current_chunk + (" " if current_chunk else "") + word

        # If adding word exceeds chunk_size and we have content, start new chunk
        if len(test_chunk) > chunk_size and current_chunk:
            chunks.append(current_chunk)
            current_chunk = word
        else:
            current_chunk = test_chunk

    # Add any remaining content
    if current_chunk:
        chunks.append(current_chunk)

    logger.debug(
        "Split response into chunks",
        extra={
            "original_length": len(text),
            "chunk_count": len(chunks),
            "target_chunk_size": chunk_size,
        },
    )

    return chunks


def convert_openai_to_langchain_messages(messages: list[ChatMessage]) -> list[BaseMessage]:
    """
    Convert OpenAI API ChatMessage format to LangChain BaseMessage format.

    Maps message roles to LangChain message types:
    - "system" → SystemMessage
    - "user" → HumanMessage
    - "assistant" → AIMessage

    Args:
        messages: List of ChatMessage objects from OpenAI API request

    Returns:
        List of LangChain BaseMessage objects suitable for use in chain steps

    Raises:
        ValueError: If message role is unknown or content is missing

    Example:
        >>> openai_messages = [
        ...     ChatMessage(role="user", content="What is AI?")
        ... ]
        >>> langchain_messages = convert_openai_to_langchain_messages(openai_messages)
        >>> isinstance(langchain_messages[0], HumanMessage)
        True
    """
    langchain_messages: list[BaseMessage] = []

    for msg in messages:
        role = msg.role.value if hasattr(msg.role, "value") else msg.role
        content = msg.content

        if not content:
            logger.warning(f"Message with role '{role}' has empty content, skipping")
            continue

        try:
            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "user":
                langchain_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))
            else:
                raise ValueError(f"Unknown message role: {role}")
        except Exception as exc:
            logger.error(
                "Failed to convert message",
                extra={
                    "role": role,
                    "error": str(exc),
                },
            )
            raise

    logger.debug(
        "Converted OpenAI messages to LangChain format",
        extra={"input_count": len(messages), "output_count": len(langchain_messages)},
    )

    return langchain_messages


def convert_langchain_chunk_to_openai(
    chunk: dict[str, Any] | BaseMessage | str,
) -> ChatCompletionChunk:
    """
    Convert LangChain message/chunk or LangGraph state update to OpenAI ChatCompletionChunk format.

    Handles various input types:
    - dict from LangGraph stream_mode='updates' state updates (the primary use case)
    - dict with direct "final_response" key (legacy/fallback)
    - BaseMessage with content property
    - Plain string content

    LangGraph stream_mode='updates' format (primary):
    When using astream(stream_mode='updates'), events are dicts like:
      {"synthesize": {"final_response": "text", "step_metadata": {...}}}

    This function extracts content from the synthesize node's final_response field
    and skips analyze/process updates (returns empty content).

    Creates a proper OpenAI-compatible streaming chunk with:
    - Unique ID for the stream
    - Creation timestamp
    - Delta content with role (for first chunk)
    - Proper choice index and finish_reason

    Args:
        chunk: Output from LangChain step or LangGraph execution
               Can be state dict from stream_mode='updates', BaseMessage, or string

    Returns:
        ChatCompletionChunk formatted for OpenAI API compatibility

    Raises:
        ValueError: If chunk cannot be parsed or has invalid structure

    Example:
        >>> # From LangGraph stream_mode='updates'
        >>> event = {"synthesize": {"final_response": "Hello world", "step_metadata": {...}}}
        >>> chunk = convert_langchain_chunk_to_openai(event)
        >>> isinstance(chunk, ChatCompletionChunk)
        True
        >>> "Hello" in chunk.choices[0].delta.content
        True

    Reference:
        ./documentation/langchain/FASTAPI_LANGCHAIN_STREAMING_CHEATSHEET.md - SSE chunk conversion
        src/workflow/chains/graph.py - stream_chain() yields stream_mode='updates' events
    """
    # Extract content based on input type
    content = ""

    try:
        if isinstance(chunk, dict):
            # Handle dict from LangGraph state updates (stream_mode='updates')
            # The event structure is: {"node_name": {"state_key": value, ...}}

            # Try to extract from synthesize node (the one with final_response)
            if "synthesize" in chunk:
                synthesize_update = chunk.get("synthesize", {})
                if isinstance(synthesize_update, dict):
                    # The synthesize_step returns: {"final_response": "text", "step_metadata": {...}}
                    final_response = synthesize_update.get("final_response", "")
                    if final_response:
                        content = final_response

            # Fallback: Direct final_response at top level (for edge cases)
            elif "final_response" in chunk:
                content = chunk.get("final_response", "")

            # Fallback: Try to extract from messages (accumulated state)
            elif "messages" in chunk and chunk["messages"]:
                msg = (
                    chunk["messages"][-1]
                    if isinstance(chunk["messages"], list)
                    else chunk["messages"]
                )
                if hasattr(msg, "content"):
                    content = msg.content
                elif isinstance(msg, dict):
                    content = msg.get("content", "")

            # Note: analyze and process updates don't contain "final_response"
            # so content remains empty for those, which is correct behavior
            # (they're metadata updates, not content for streaming to user)

        elif isinstance(chunk, BaseMessage):
            # Direct message object (legacy support)
            if hasattr(chunk, "content"):
                msg_content = chunk.content
                # Handle both string and list content from BaseMessage
                if isinstance(msg_content, str):
                    content = msg_content
                elif isinstance(msg_content, list) and len(msg_content) > 0:
                    # Extract text from content blocks
                    first_block = msg_content[0]
                    if hasattr(first_block, "text"):
                        content = first_block.text
                    elif hasattr(first_block, "content"):
                        content = first_block.content
                    else:
                        content = str(first_block)
                else:
                    content = str(msg_content)
            else:
                content = str(chunk)

        elif isinstance(chunk, str):
            # Plain string content (direct response)
            content = chunk

        else:
            # Try to convert to string as fallback
            content = str(chunk)

        # Ensure content is string and handle None/empty cases
        if not isinstance(content, str):
            content = str(content) if content else ""

        # Create ChatCompletionChunk with proper format
        # Only include content if non-empty (avoid sending empty chunks)
        delta = ChoiceDelta(
            role=MessageRole.ASSISTANT,  # Assistant is providing the response
            content=content if content else None,
        )

        choice = ChatCompletionStreamChoice(
            index=0,
            delta=delta,
            finish_reason=None,  # Only set in final chunk
        )

        chunk_result = ChatCompletionChunk(
            id=f"chatcmpl-{int(time.time() * 1000)}",
            object="chat.completion.chunk",
            created=int(time.time()),
            model="orchestrator-worker",
            choices=[choice],
        )

        logger.debug(
            "Converted LangChain chunk to OpenAI format",
            extra={
                "chunk_type": type(chunk).__name__,
                "content_length": len(content),
                "has_synthesize_node": "synthesize" in chunk if isinstance(chunk, dict) else False,
            },
        )

        return chunk_result

    except Exception as exc:
        logger.error(
            "Failed to convert LangChain chunk to OpenAI format",
            extra={
                "chunk_type": type(chunk).__name__,
                "error": str(exc),
                "chunk_keys": list(chunk.keys()) if isinstance(chunk, dict) else None,
            },
        )
        raise ValueError(f"Cannot convert chunk to OpenAI format: {exc}") from exc
