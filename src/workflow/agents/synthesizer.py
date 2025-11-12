"""
Synthesizer agent implementation using Claude Agent SDK.

The synthesizer aggregates and polishes results from multiple workers.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from anthropic import AsyncAnthropic

from workflow.agents.base import Agent
from workflow.config import Settings
from workflow.models.internal import TaskResult, TokenUsage
from workflow.models.openai import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionStreamChoice,
    ChoiceDelta,
)
from workflow.utils.anthropic_errors import map_anthropic_exception
from workflow.utils.circuit_breaker import (
    CircuitBreaker,
    create_retryable_anthropic_call,
)
from workflow.utils.errors import ExternalServiceError
from workflow.utils.logging import get_logger
from workflow.utils.prompts import load_prompt
from workflow.utils.request_context import get_request_id
from workflow.utils.token_tracking import calculate_cost

logger = get_logger(__name__)

# Fallback prompt if file not found
FALLBACK_PROMPT = """You are a synthesizer agent responsible for aggregating and polishing results.

Your responsibilities:
1. Receive results from multiple worker agents
2. Analyze and synthesize the information
3. Create a coherent, well-formatted final response
4. Ensure consistency and quality across all inputs

Be clear, concise, and professional. Your output will be delivered directly to the user.
"""

# Load system prompt from file (with fallback)
SYNTHESIZER_SYSTEM_PROMPT = load_prompt("synthesizer", fallback=FALLBACK_PROMPT)


class Synthesizer(Agent):
    """
    Synthesizer agent for aggregating and polishing worker results.

    Uses Claude API to synthesize multiple task results into a cohesive response.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the Synthesizer agent.

        Args:
            settings: Application configuration settings
        """
        super().__init__(
            name="synthesizer",
            model=settings.synthesizer_model,
        )
        self.settings = settings
        self.api_key = settings.anthropic_api_key
        self.client: AsyncAnthropic | None = None
        self.max_tokens = settings.synthesizer_max_tokens
        self.temperature = settings.synthesizer_temperature

        # Circuit breaker for resilience
        self.circuit_breaker = CircuitBreaker(
            service_name="anthropic_synthesizer",
            failure_threshold=settings.circuit_breaker_failure_threshold,
            timeout=settings.circuit_breaker_timeout,
            half_open_attempts=settings.circuit_breaker_half_open_attempts,
        )

        logger.info(
            "Synthesizer agent created",
            extra={
                "agent": self.name,
                "model": self.model,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
            },
        )

    async def initialize(self) -> None:
        """
        Initialize the agent and Claude API client.

        Called before synthesis execution.
        """
        logger.info(
            f"Initializing {self.name} agent",
            extra={"agent": self.name, "model": self.model},
        )
        try:
            self.client = AsyncAnthropic(api_key=self.api_key)
            logger.debug(
                f"{self.name} agent AsyncAnthropic client created successfully",
                extra={"agent": self.name, "model": self.model},
            )
        except Exception as exc:
            logger.critical(
                f"Failed to initialize AsyncAnthropic client for {self.name} agent",
                extra={
                    "agent": self.name,
                    "model": self.model,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            raise

    async def shutdown(self) -> None:
        """
        Shutdown the agent and clean up resources.

        Called after synthesis completion or failure.
        """
        logger.info(f"Shutting down {self.name} agent", extra={"agent": self.name})
        if self.client:
            await self.client.close()
            self.client = None

    async def process(self, request: ChatCompletionRequest) -> AsyncIterator[ChatCompletionChunk]:
        """
        Process method required by Agent base class.

        Synthesizer uses synthesize() instead of process() for synthesis execution.

        Args:
            request: The chat completion request

        Raises:
            NotImplementedError: Always, as Synthesizer uses synthesize() method
        """
        # This maintains the Agent base class interface but directs users to correct method
        raise NotImplementedError("Synthesizer uses synthesize() instead of process()")
        yield  # Make this a generator for type checker

    async def synthesize(
        self, task_results: list[TaskResult]
    ) -> AsyncIterator[ChatCompletionChunk]:
        """
        Synthesize worker results into a final polished response.

        This is the main method for Synthesizer, aggregating and creating a cohesive response from
        multiple worker outputs.

        Args:
            task_results: Raw results from all workers

        Yields:
            Streaming chunks of the synthesized response

        Raises:
            ExternalServiceError: If Claude API call fails or client not initialized
        """
        if not self.client:
            raise ExternalServiceError(
                message="Synthesizer not initialized",
                service_name="anthropic",
                error_code="CLIENT_NOT_INITIALIZED",
            )

        logger.info(
            "Synthesizing results",
            extra={
                "agent": self.name,
                "num_results": len(task_results),
            },
        )

        # Build the synthesis prompt (which includes aggregation logic)
        prompt = self._build_synthesis_prompt(task_results)

        try:
            # Call Claude API with streaming and retry logic
            @create_retryable_anthropic_call(self.settings, self.circuit_breaker)
            async def _call_streaming_api() -> Any:
                """Inner function for retryable streaming API call."""
                request_id = get_request_id()
                extra_headers = {}
                if request_id:
                    extra_headers["X-Request-ID"] = request_id
                    logger.debug(
                        "Propagating request ID to streaming API call",
                        extra={"request_id": request_id},
                    )
                else:
                    logger.debug("No request ID in context for streaming API call")

                return await self.client.messages.create(  # type: ignore
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=SYNTHESIZER_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    extra_headers=extra_headers if extra_headers else None,
                )

            stream = await _call_streaming_api()

            # Generate unique chunk ID for this synthesis session
            chunk_id = f"chatcmpl-{uuid4()}"

            # Stream the response
            async for event in stream:
                # Handle content block delta events
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        # Create streaming chunk
                        chunk = ChatCompletionChunk(
                            id=chunk_id,
                            object="chat.completion.chunk",
                            created=0,  # Timestamp not used for streaming
                            model=self.model,
                            choices=[
                                ChatCompletionStreamChoice(
                                    index=0,
                                    delta=ChoiceDelta(
                                        role="assistant",
                                        content=event.delta.text,
                                    ),
                                    finish_reason=None,
                                )
                            ],
                        )
                        yield chunk

                # Handle stream end
                elif event.type == "message_stop":
                    # Send final chunk with finish_reason
                    final_chunk = ChatCompletionChunk(
                        id=chunk_id,
                        object="chat.completion.chunk",
                        created=0,
                        model=self.model,
                        choices=[
                            ChatCompletionStreamChoice(
                                index=0,
                                delta=ChoiceDelta(),
                                finish_reason="stop",
                            )
                        ],
                    )
                    yield final_chunk

            # After streaming completes, make a non-streaming call to get token usage
            # This is necessary because streaming responses don't include usage data
            await self._capture_and_log_token_usage(prompt)

            logger.info(
                "Synthesis completed",
                extra={
                    "agent": self.name,
                    "num_results": len(task_results),
                },
            )

        except asyncio.CancelledError:
            logger.info(
                "Synthesis cancelled",
                extra={"agent": self.name},
            )
            raise
        except Exception as exc:
            # Map Anthropic exceptions to custom error types
            mapped_exc = map_anthropic_exception(exc)

            # Log at WARNING level for retryable errors (circuit breaker visibility)
            if isinstance(
                mapped_exc,
                (
                    AnthropicConnectionError,
                    AnthropicTimeoutError,
                    AnthropicRateLimitError,
                    AnthropicServerError,
                ),
            ):
                logger.warning(
                    f"Retryable error synthesizing results: {mapped_exc}",
                    extra={
                        "agent": self.name,
                        "error": str(mapped_exc),
                        "error_type": type(mapped_exc).__name__,
                        "original_error_type": type(exc).__name__,
                    },
                )
            else:
                logger.error(
                    f"Failed to synthesize results: {mapped_exc}",
                    extra={
                        "agent": self.name,
                        "error": str(mapped_exc),
                        "error_type": type(mapped_exc).__name__,
                        "original_error_type": type(exc).__name__,
                    },
                )

            # Re-raise mapped exception if it's different, otherwise wrap it
            if mapped_exc is not exc:
                raise mapped_exc from exc

            raise ExternalServiceError(
                message=f"Failed to synthesize results: {str(exc)}",
                service_name="anthropic",
                error_code="SYNTHESIS_ERROR",
            ) from exc

    async def _capture_and_log_token_usage(self, prompt: str) -> None:
        """
        Make a non-streaming call to capture token usage and log costs.

        Since streaming responses don't include usage data, we make a second
        non-streaming call with similar parameters to get accurate token counts.
        This is a small additional cost for monitoring purposes.

        Args:
            prompt: The synthesis prompt that was used for streaming
        """
        if not self.client:
            logger.warning("Cannot capture token usage: client not initialized")
            return

        try:
            # Make non-streaming call with same parameters (with fallback on failure)
            @create_retryable_anthropic_call(self.settings, self.circuit_breaker)
            async def _call_token_capture_api() -> Any:
                """Inner function for token usage capture."""
                request_id = get_request_id()
                extra_headers = {}
                if request_id:
                    extra_headers["X-Request-ID"] = request_id
                    logger.debug(
                        "Propagating request ID to token capture API call",
                        extra={"request_id": request_id},
                    )
                else:
                    logger.debug("No request ID in context for token capture API call")

                return await self.client.messages.create(  # type: ignore
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=SYNTHESIZER_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                    extra_headers=extra_headers if extra_headers else None,
                )

            response = await _call_token_capture_api()

            # Check if response has usage attribute (real API response or proper mock)
            if hasattr(response, "usage"):
                # Extract token usage and calculate costs
                token_usage = TokenUsage(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )
                cost_metrics = calculate_cost(
                    model=self.model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )

                logger.info(
                    "Synthesizer tokens captured",
                    extra={
                        "agent": self.name,
                        "input_tokens": token_usage.input_tokens,
                        "output_tokens": token_usage.output_tokens,
                        "total_tokens": token_usage.total_tokens,
                        "total_cost_usd": cost_metrics.total_cost_usd,
                    },
                )
            else:
                logger.debug(
                    "Could not extract usage from response",
                    extra={"agent": self.name},
                )
        except Exception as exc:
            logger.warning(
                f"Failed to capture synthesizer token usage: {exc}",
                extra={"agent": self.name, "error": str(exc)},
            )

    def _build_synthesis_prompt(self, task_results: list[TaskResult]) -> str:
        """
        Build synthesis prompt from raw worker results with aggregation.

        Constructs a prompt that provides all worker outputs, aggregates metadata,
        and provides context for synthesis.

        Args:
            task_results: Raw results from all workers

        Returns:
            Complete prompt string for Claude API
        """
        # Calculate aggregation statistics
        num_tasks = len(task_results)
        successful_tasks = sum(1 for result in task_results if result.success)
        failed_tasks = num_tasks - successful_tasks

        # Build metadata summary
        metadata_summary = {
            "total_tasks": num_tasks,
            "successful": successful_tasks,
            "failed": failed_tasks,
        }

        prompt_parts = [
            "I have received results from multiple worker agents. Please synthesize these into a cohesive, polished response.",
            "",
            f"Number of tasks: {num_tasks}",
            f"Successful tasks: {successful_tasks}",
            f"Failed tasks: {failed_tasks}",
            "",
            "Worker Results:",
        ]

        # Add each task result
        for result in task_results:
            status = "✓ Success" if result.success else "✗ Failed"
            prompt_parts.append(f"\nTask {result.task_id} ({status}):")
            prompt_parts.append(result.output)
            if result.error:
                prompt_parts.append(f"Error: {result.error}")

        # Add aggregated metadata
        prompt_parts.append("")
        prompt_parts.append("Aggregation Summary:")
        for key, value in metadata_summary.items():
            prompt_parts.append(f"  {key}: {value}")

        prompt = "\n".join(prompt_parts)

        logger.debug(
            "Built synthesis prompt",
            extra={
                "agent": self.name,
                "num_tasks": num_tasks,
                "successful_tasks": successful_tasks,
                "failed_tasks": failed_tasks,
                "prompt_length": len(prompt),
            },
        )

        return prompt
