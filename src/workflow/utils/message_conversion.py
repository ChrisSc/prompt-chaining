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
)
from workflow.utils.logging import get_logger

logger = get_logger(__name__)


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
    Convert LangChain message/chunk to OpenAI ChatCompletionChunk format.

    Handles various input types:
    - dict with "final_response" or accumulated content
    - BaseMessage with content property
    - Plain string content

    Creates a proper OpenAI-compatible streaming chunk with:
    - Unique ID for the stream
    - Creation timestamp
    - Delta content with role (for first chunk)
    - Proper choice index and finish_reason

    Args:
        chunk: Output from LangChain step or LangGraph execution
               Can be a dict with state updates, BaseMessage, or string

    Returns:
        ChatCompletionChunk formatted for OpenAI API compatibility

    Raises:
        ValueError: If chunk cannot be parsed or has invalid structure

    Example:
        >>> from langchain_core.messages import AIMessage
        >>> chunk = AIMessage(content="Hello world")
        >>> openai_chunk = convert_langchain_chunk_to_openai(chunk)
        >>> isinstance(openai_chunk, ChatCompletionChunk)
        True
        >>> "Hello" in openai_chunk.choices[0].delta.content
        True
    """
    # Extract content based on input type
    content = ""

    try:
        if isinstance(chunk, dict):
            # Handle dict from state updates - look for final_response or accumulated text
            if "final_response" in chunk:
                content = chunk.get("final_response", "")
            elif "messages" in chunk and chunk["messages"]:
                # Extract from accumulated messages
                msg = (
                    chunk["messages"][-1]
                    if isinstance(chunk["messages"], list)
                    else chunk["messages"]
                )
                if hasattr(msg, "content"):
                    content = msg.content
                elif isinstance(msg, dict):
                    content = msg.get("content", "")
            else:
                # Look for any string-like content
                for key, value in chunk.items():
                    if isinstance(value, str) and value:
                        content = value
                        break

        elif isinstance(chunk, BaseMessage):
            # Direct message object
            content = chunk.content if hasattr(chunk, "content") else str(chunk)

        elif isinstance(chunk, str):
            # Plain string content
            content = chunk

        else:
            # Try to convert to string as fallback
            content = str(chunk)

        # Ensure content is string
        if not isinstance(content, str):
            content = str(content) if content else ""

        # Create ChatCompletionChunk with proper format
        delta = ChoiceDelta(
            role="assistant",  # Assistant is providing the response
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
            },
        )

        return chunk_result

    except Exception as exc:
        logger.error(
            "Failed to convert LangChain chunk to OpenAI format",
            extra={
                "chunk_type": type(chunk).__name__,
                "error": str(exc),
            },
        )
        raise ValueError(f"Cannot convert chunk to OpenAI format: {exc}") from exc
