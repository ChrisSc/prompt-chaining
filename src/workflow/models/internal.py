"""
Internal data models for the Template Service application.

These models represent domain-specific concepts not exposed via the OpenAI API.
This is a generic template - customize for your specific use case.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, NonNegativeInt


class Message(BaseModel):
    """
    Internal representation of a message.

    Tracks metadata beyond what's needed for the API.
    """

    role: str = Field(description="Message role (system, user, assistant)")
    content: str = Field(description="Message content")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When the message was created"
    )
    session_id: str | None = Field(default=None, description="Associated session ID")


class SessionMessage(BaseModel):
    """
    Message within a session context.

    Links messages to specific user sessions for conversation history.
    """

    message: Message
    turn_number: int = Field(ge=0, description="Turn number in the conversation")


class ServiceRequest(BaseModel):
    """
    Generic service request with user messages.

    Used internally to structure requests for processing.
    """

    messages: list[dict[str, str]] = Field(description="Chat messages from the user")
    context: dict[str, Any] = Field(default={}, description="Additional context for processing")
    user_id: str | None = Field(default=None, description="Optional user identifier")


# Multi-step coordination models
# Template domain models for prompt-chaining workflow.
# Customize these classes for your specific use case.


class TokenUsage(BaseModel):
    """
    Token usage statistics from a single API call.

    Tracks the number of input tokens, output tokens, and total tokens consumed.
    """

    input_tokens: NonNegativeInt = Field(description="Number of input tokens used")
    output_tokens: NonNegativeInt = Field(description="Number of output tokens used")

    @property
    def total_tokens(self) -> int:
        """Calculate total tokens used."""
        return self.input_tokens + self.output_tokens


class CostMetrics(BaseModel):
    """
    Cost metrics calculated from token usage.

    Stores costs in USD for input, output, and total tokens.
    """

    input_cost_usd: float = Field(ge=0, description="Cost for input tokens in USD")
    output_cost_usd: float = Field(ge=0, description="Cost for output tokens in USD")

    @property
    def total_cost_usd(self) -> float:
        """Calculate total cost in USD."""
        return self.input_cost_usd + self.output_cost_usd


class AggregatedTokenMetrics(BaseModel):
    """
    Aggregated token metrics for an entire request.

    Combines metrics from analyze, process, and synthesize steps.
    """

    analyze_tokens: NonNegativeInt = Field(default=0, description="Tokens used by analyze step")
    process_tokens: NonNegativeInt = Field(default=0, description="Tokens used by process step")
    synthesizer_tokens: NonNegativeInt = Field(
        default=0, description="Tokens used by synthesize step"
    )

    @property
    def total_tokens(self) -> int:
        """Calculate total tokens used across all steps."""
        return self.analyze_tokens + self.process_tokens + self.synthesizer_tokens

    analyze_cost_usd: float = Field(default=0, ge=0, description="Cost for analyze step in USD")
    process_cost_usd: float = Field(default=0, ge=0, description="Cost for process step in USD")
    synthesizer_cost_usd: float = Field(
        default=0, ge=0, description="Cost for synthesize step in USD"
    )

    @property
    def total_cost_usd(self) -> float:
        """Calculate total cost in USD."""
        return self.analyze_cost_usd + self.process_cost_usd + self.synthesizer_cost_usd


class TaskRequest(BaseModel):
    """
    Example model - customize for your domain.

    Template model showing how to structure requests for multi-step processing.
    Customize for your specific use case and domain requirements.
    """

    task_id: int = Field(ge=1, description="Unique task identifier")
    instruction: str = Field(description="Specific instruction for this task")
    data: dict[str, Any] = Field(
        default={},
        description="Additional data or context for the task",
    )
    metadata: dict[str, Any] = Field(
        default={},
        description="Optional metadata (priority, tags, etc.)",
    )


class TaskResult(BaseModel):
    """
    Example model - customize for your domain.

    Template model showing how to structure results from task execution.
    Customize for your specific use case and domain requirements.
    """

    task_id: int = Field(ge=1, description="Task identifier this result corresponds to")
    output: str = Field(description="Result of task execution")
    metadata: dict[str, Any] = Field(
        default={},
        description="Optional result metadata (execution time, tokens used, etc.)",
    )
    success: bool = Field(default=True, description="Whether the task completed successfully")
    error: str | None = Field(default=None, description="Error message if task failed")
    token_usage: TokenUsage | None = Field(
        default=None, description="Token usage statistics for this task"
    )
    cost_metrics: CostMetrics | None = Field(default=None, description="Cost metrics for this task")


class AggregatedResult(BaseModel):
    """
    Example model - customize for your domain.

    Template model showing how to aggregate results from all steps.
    Customize for your specific use case and domain requirements.
    """

    num_tasks: int = Field(ge=1, description="Number of tasks executed")
    task_results: list[TaskResult] = Field(description="All individual task results")
    summary: str = Field(description="Summary or synthesis of all results")
    metadata: dict[str, Any] = Field(
        default={},
        description="Aggregated metadata (total execution time, total tokens, etc.)",
    )
