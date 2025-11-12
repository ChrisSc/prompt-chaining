"""
OpenAI-compatible data models for chat completions API.

These models ensure compatibility with OpenAI API clients and tools like Open WebUI.
"""

from enum import Enum

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Enumeration of valid message roles."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    """
    A message in the chat completions API.

    Compatible with OpenAI API message format.
    """

    role: MessageRole = Field(description="Role of the message sender")
    content: str = Field(description="Message content")


class ChatCompletionRequest(BaseModel):
    """
    Request model for chat completions endpoint.

    Follows OpenAI API specification for maximum compatibility.
    """

    model: str = Field(description="Model identifier (e.g., 'claude-sonnet-4-5-20250929')")
    messages: list[ChatMessage] = Field(description="List of messages in the conversation")
    temperature: float | None = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for model diversity",
    )
    max_tokens: int | None = Field(
        default=4096,
        ge=1,
        le=8000,
        description="Maximum tokens in the response",
    )
    top_p: float | None = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling parameter",
    )
    stream: bool | None = Field(
        default=False,
        description="Stream response tokens",
    )


class ChoiceDelta(BaseModel):
    """
    Delta content in a streaming chunk.

    Contains incremental content updates during streaming responses.
    """

    role: MessageRole | None = Field(default=None, description="Role (only in first chunk)")
    content: str | None = Field(default=None, description="Incremental text content")


class ChatCompletionStreamChoice(BaseModel):
    """
    A choice in a streaming chat completion chunk.

    Represents one streaming update from the model.
    """

    index: int = Field(description="Index of this choice in the stream")
    delta: ChoiceDelta = Field(description="Incremental content delta")
    finish_reason: str | None = Field(
        default=None, description="Why generation stopped (only in final chunk)"
    )


class ChatCompletionChunk(BaseModel):
    """
    Streaming chunk compatible with OpenAI SSE format.

    Sent as individual Server-Sent Events during streaming responses.
    """

    id: str = Field(description="Unique identifier for this completion stream")
    object: str = Field(default="chat.completion.chunk", description="Object type")
    created: int = Field(description="Unix timestamp of creation")
    model: str = Field(description="Model used for completion")
    choices: list[ChatCompletionStreamChoice] = Field(description="List of streaming choices")
    usage: dict[str, int] | None = Field(
        default=None,
        description="Token usage (only in final chunk with finish_reason)",
    )


# Legacy models - deprecated in streaming-only mode but kept for reference
class ChatCompletionChoice(BaseModel):
    """
    A single choice in a chat completion response.

    Represents one possible completion from the model.

    DEPRECATED: Only used in non-streaming mode (Phase 1). Phase 1.5+ uses streaming only.
    """

    index: int = Field(description="Index of this choice in the response")
    message: ChatMessage = Field(description="The message content")
    finish_reason: str = Field(description="Why the model stopped generating (e.g., 'stop')")


class ChatCompletionResponse(BaseModel):
    """
    Response model for chat completions endpoint.

    Follows OpenAI API specification for maximum compatibility.

    DEPRECATED: Only used in non-streaming mode (Phase 1). Phase 1.5+ uses streaming only.
    """

    id: str = Field(description="Unique identifier for this completion")
    object: str = Field(default="chat.completion", description="Object type")
    created: int = Field(description="Unix timestamp of creation")
    model: str = Field(description="Model used for completion")
    choices: list[ChatCompletionChoice] = Field(description="List of completion choices")
    usage: dict[str, int] = Field(
        description="Token usage (prompt_tokens, completion_tokens, total_tokens)"
    )
