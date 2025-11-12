"""
Data models for the Template Service.

This module contains both OpenAI-compatible models (external API)
and internal domain models.
"""

from orchestrator_worker.models.internal import (
    AggregatedResult,
    Message,
    ServiceRequest,
    SessionMessage,
    TaskRequest,
    TaskResult,
)
from orchestrator_worker.models.openai import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionStreamChoice,
    ChatMessage,
    ChoiceDelta,
    MessageRole,
)

__all__ = [
    # Internal models
    "Message",
    "SessionMessage",
    "ServiceRequest",
    "TaskRequest",
    "TaskResult",
    "AggregatedResult",
    # OpenAI models
    "MessageRole",
    "ChatMessage",
    "ChatCompletionRequest",
    "ChoiceDelta",
    "ChatCompletionStreamChoice",
    "ChatCompletionChunk",
]
