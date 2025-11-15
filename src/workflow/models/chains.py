"""
Prompt-chaining pattern models for LangGraph-based multi-step workflows.

This module implements the data structures for the prompt-chaining pattern,
which orchestrates sequential processing steps through LangGraph StateGraph:

1. Analysis Step: Parses user intent and identifies key entities/complexity
2. Processing Step: Generates content based on analysis
3. Synthesis Step: Combines results into polished final response

The ChainState TypedDict maintains state across the entire graph, while
step-specific models (AnalysisOutput, ProcessOutput, SynthesisOutput)
handle outputs from each agent.

Configuration models (ChainStepConfig, ChainConfig) define runtime parameters
for each step, including model selection, token limits, temperature, and
system prompts.
"""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# === TASK 2.1: ChainState TypedDict ===


class ChainState(TypedDict):
    """
    State object for LangGraph prompt-chaining workflow.

    This TypedDict maintains state across all processing steps. The messages
    field accumulates all messages through the chain via add_messages reducer.
    Other fields capture outputs from each step for use in subsequent steps.

    The messages list grows as each step processes the current state,
    enabling conversation-like continuity through the processing pipeline.
    """

    messages: Annotated[
        list[BaseMessage],
        add_messages,
    ]
    """Accumulated messages through chain - uses add_messages reducer for proper merging."""

    request_id: str  # Trace ID for cross-step correlation
    """Request ID for correlation across logs and external API calls."""

    user_id: str  # User identifier from JWT sub claim
    """User ID extracted from JWT token for user-specific tracing."""

    analysis: dict[str, Any] | None
    """Output from analysis step containing intent, entities, complexity."""

    processed_content: str | None
    """Output from processing step containing generated content."""

    final_response: str | None
    """Final synthesized output from synthesis step."""

    step_metadata: dict[str, Any]
    """Tracking metadata for the entire chain execution (timing, costs, etc.)."""


# === TASK 2.2: Step Output Models ===


class AnalysisOutput(BaseModel):
    """
    Output from the analysis step of the prompt-chaining workflow.

    The analysis step parses user intent, extracts key entities,
    assesses task complexity, and provides contextual information
    for subsequent processing steps.
    """

    intent: str = Field(description="User's primary intent or goal extracted from the request")
    key_entities: list[str] = Field(
        description="Key entities, topics, or concepts mentioned in the request"
    )
    complexity: str = Field(
        description="Assessed task complexity level: simple, moderate, or complex"
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional contextual information discovered during analysis",
    )


class ProcessOutput(BaseModel):
    """
    Output from the processing step of the prompt-chaining workflow.

    The processing step generates actual content based on the analysis
    results, producing domain-specific output with a confidence metric
    and optional metadata about the generation process.
    """

    content: str = Field(description="Generated content based on analysis")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for the generated content (0.0 to 1.0)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about content generation (tokens, sources, etc.)",
    )


class SynthesisOutput(BaseModel):
    """
    Output from the synthesis step of the prompt-chaining workflow.

    The synthesis step polishes and formats the processed content,
    combining results into a final, user-ready response with
    specific formatting and styling applied.
    """

    final_text: str = Field(description="Polished and formatted final response text")
    formatting: str = Field(description="Applied formatting style or template used")


# === TASK 2.3: Configuration Models ===


class ChainStepConfig(BaseModel):
    """
    Configuration for a single step in the prompt-chaining workflow.

    Defines runtime parameters for analysis, processing, or synthesis steps,
    including the Claude model to use, token limits, temperature for sampling,
    and the system prompt file that provides step-specific instructions.
    """

    model: str = Field(
        description="Claude model ID for this step (e.g., 'claude-haiku-4-5-20251001')"
    )
    max_tokens: int = Field(ge=1, description="Maximum tokens to generate for this step")
    temperature: float = Field(
        ge=0.0,
        le=2.0,
        description="Temperature for sampling: 0.0 (deterministic) to 2.0 (creative)",
    )
    system_prompt_file: str = Field(
        description="Filename of the system prompt (without path, loaded from prompts/)"
    )


class ChainConfig(BaseModel):
    """
    Complete configuration for the prompt-chaining workflow.

    Orchestrates settings for all three steps (analysis, processing, synthesis),
    including timeouts for each phase and validation gate settings.

    This config is typically loaded from environment variables or a YAML file
    and passed to the workflow initialization.
    """

    analyze: ChainStepConfig = Field(description="Configuration for analysis step")
    process: ChainStepConfig = Field(description="Configuration for processing step")
    synthesize: ChainStepConfig = Field(description="Configuration for synthesis step")
    analyze_timeout: int = Field(
        default=15,
        ge=1,
        le=270,
        description="Timeout in seconds for analysis step (1-270)",
    )
    process_timeout: int = Field(
        default=30,
        ge=1,
        le=270,
        description="Timeout in seconds for processing step (1-270)",
    )
    synthesize_timeout: int = Field(
        default=20,
        ge=1,
        le=270,
        description="Timeout in seconds for synthesis step (1-270)",
    )
    enable_validation: bool = Field(
        default=True,
        description="Enable validation gates between steps",
    )
    strict_validation: bool = Field(
        default=False,
        description="Enforce strict validation - fail on validation errors vs. warnings",
    )
    min_confidence_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score required to pass process validation gate (0.0-1.0)",
    )
