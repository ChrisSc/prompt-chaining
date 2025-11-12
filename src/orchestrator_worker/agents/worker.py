"""
Worker agent implementation using Claude Agent SDK.

The worker executes specific tasks assigned by the orchestrator.
This is a simple example - customize for your specific use case.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from anthropic import AsyncAnthropic

from orchestrator_worker.agents.base import Agent
from orchestrator_worker.config import Settings
from orchestrator_worker.models.internal import TaskRequest, TaskResult, TokenUsage
from orchestrator_worker.models.openai import ChatCompletionChunk, ChatCompletionRequest
from orchestrator_worker.utils.anthropic_errors import map_anthropic_exception
from orchestrator_worker.utils.circuit_breaker import (
    CircuitBreaker,
    create_retryable_anthropic_call,
)
from orchestrator_worker.utils.errors import (
    AnthropicConnectionError,
    AnthropicRateLimitError,
    AnthropicServerError,
    AnthropicTimeoutError,
    ExternalServiceError,
)
from orchestrator_worker.utils.logging import get_logger
from orchestrator_worker.utils.prompts import load_prompt
from orchestrator_worker.utils.request_context import get_request_id
from orchestrator_worker.utils.token_tracking import calculate_cost

logger = get_logger(__name__)

# Fallback prompt if file not found (kept for safety)
FALLBACK_PROMPT = """You are a worker agent executing a specific task.

Your responsibilities:
1. Receive a focused instruction from the orchestrator
2. Execute it precisely and concisely
3. Return a clear result

Be brief and to the point. You are one of multiple workers handling parts of a larger task.
"""

# Load system prompt from file (with fallback)
WORKER_SYSTEM_PROMPT = load_prompt("worker", fallback=FALLBACK_PROMPT)


class Worker(Agent):
    """
    Worker agent for executing specific tasks.

    Uses Claude API to process individual tasks assigned by the Orchestrator.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the Worker agent.

        Args:
            settings: Application configuration settings
        """
        super().__init__(
            name="worker",
            model=settings.worker_model,
        )
        self.settings = settings
        self.api_key = settings.anthropic_api_key
        self.client: AsyncAnthropic | None = None
        self.max_tokens = settings.worker_max_tokens
        self.temperature = settings.worker_temperature

        # Circuit breaker for resilience
        self.circuit_breaker = CircuitBreaker(
            service_name="anthropic_worker",
            failure_threshold=settings.circuit_breaker_failure_threshold,
            timeout=settings.circuit_breaker_timeout,
            half_open_attempts=settings.circuit_breaker_half_open_attempts,
        )

        logger.info(
            "Worker agent created",
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

        Called before task execution.
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

        Called after task completion or failure.
        """
        logger.info(f"Shutting down {self.name} agent", extra={"agent": self.name})
        if self.client:
            await self.client.close()
            self.client = None

    async def process(self, request: ChatCompletionRequest) -> AsyncIterator[ChatCompletionChunk]:
        """
        Process method required by Agent base class.

        Worker uses process_task() instead of process() for task execution.

        Args:
            request: The chat completion request

        Raises:
            NotImplementedError: Always, as Worker uses process_task() method
        """
        # This maintains the Agent base class interface but directs users to correct method
        raise NotImplementedError("Worker uses process_task() instead of process()")
        yield  # Make this a generator for type checker

    async def process_task(self, request: TaskRequest) -> TaskResult:
        """
        Process a task request and generate result.

        This is the main method for Worker, executing a specific task assigned
        by the Orchestrator.

        Args:
            request: Request containing task ID, instruction, and data

        Returns:
            Task result with output

        Raises:
            ExternalServiceError: If Claude API call fails or client not initialized
        """
        if not self.client:
            raise ExternalServiceError(
                message="Worker not initialized",
                service_name="anthropic",
                error_code="CLIENT_NOT_INITIALIZED",
            )

        logger.info(
            f"Processing task {request.task_id}",
            extra={
                "agent": self.name,
                "task_id": request.task_id,
                "instruction_length": len(request.instruction),
            },
        )

        # Build the user prompt from request
        prompt = self._build_prompt(request)

        try:
            # Call Claude API with retry logic (non-streaming for simple text response)
            @create_retryable_anthropic_call(self.settings, self.circuit_breaker)
            async def _call_api() -> Any:
                """Inner function for retryable API call."""
                request_id = get_request_id()
                extra_headers = {}
                if request_id:
                    extra_headers["X-Request-ID"] = request_id
                    logger.debug(
                        f"Propagating request ID to API call",
                        extra={"request_id": request_id, "task_id": request.task_id},
                    )
                else:
                    logger.debug(
                        "No request ID in context for API call",
                        extra={"task_id": request.task_id},
                    )

                return await self.client.messages.create(  # type: ignore
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=WORKER_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                    extra_headers=extra_headers if extra_headers else None,
                )

            response = await _call_api()

            # Extract text from response
            if not response.content:
                raise ValueError(f"Empty response.content for task {request.task_id}")

            first_block = response.content[0]
            if hasattr(first_block, "text"):
                response_text = first_block.text
            else:
                raise ValueError(f"Expected TextBlock but got {type(first_block).__name__}")

            logger.debug(
                f"Received response for task {request.task_id}: "
                f"length={len(response_text)}, "
                f"output_tokens={response.usage.output_tokens}"
            )

            # Check if response text is empty
            if not response_text or not response_text.strip():
                logger.error(
                    f"Empty response text for task {request.task_id}: "
                    f"stop_reason={response.stop_reason}, "
                    f"output_tokens={response.usage.output_tokens}"
                )
                raise ValueError(f"Empty response text for task {request.task_id}")

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

            # Create TaskResult
            task_result = TaskResult(
                task_id=request.task_id,
                output=response_text.strip(),
                metadata={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "model": response.model,
                },
                success=True,
                token_usage=token_usage,
                cost_metrics=cost_metrics,
            )

            logger.info(
                f"Completed task {request.task_id}",
                extra={
                    "agent": self.name,
                    "task_id": request.task_id,
                    "output_length": len(response_text),
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": token_usage.total_tokens,
                    "total_cost_usd": cost_metrics.total_cost_usd,
                },
            )

            return task_result

        except asyncio.CancelledError:
            logger.info(
                f"Processing cancelled for task {request.task_id}",
                extra={"agent": self.name, "task_id": request.task_id},
            )
            raise
        except Exception as exc:
            # Map Anthropic exceptions to custom error types
            mapped_exc = map_anthropic_exception(exc)

            # Log at WARNING level for retryable errors (circuit breaker visibility)
            if isinstance(mapped_exc, (AnthropicConnectionError, AnthropicTimeoutError,
                                       AnthropicRateLimitError, AnthropicServerError)):
                logger.warning(
                    f"Retryable error processing task {request.task_id}: {mapped_exc}",
                    extra={
                        "agent": self.name,
                        "task_id": request.task_id,
                        "error": str(mapped_exc),
                        "error_type": type(mapped_exc).__name__,
                        "original_error_type": type(exc).__name__,
                    },
                )
            else:
                logger.error(
                    f"Failed to process task {request.task_id}: {mapped_exc}",
                    extra={
                        "agent": self.name,
                        "task_id": request.task_id,
                        "error": str(mapped_exc),
                        "error_type": type(mapped_exc).__name__,
                        "original_error_type": type(exc).__name__,
                    },
                )

            # Re-raise mapped exception if it's different, otherwise wrap it
            if mapped_exc is not exc:
                raise mapped_exc from exc

            raise ExternalServiceError(
                message=f"Failed to execute task {request.task_id}: {str(exc)}",
                service_name="anthropic",
                error_code="TASK_EXECUTION_ERROR",
            ) from exc

    def _build_prompt(self, request: TaskRequest) -> str:
        """
        Build user prompt from task request.

        Constructs a prompt that includes the instruction and any relevant data.

        Args:
            request: Task request with instruction and data

        Returns:
            Complete prompt string for Claude API
        """
        prompt_parts = [request.instruction]

        # Add data if present
        if request.data:
            data_str = "\n".join([f"{key}: {value}" for key, value in request.data.items()])
            prompt_parts.append(f"\nContext:\n{data_str}")

        prompt = "\n\n".join(prompt_parts)

        logger.debug(
            f"Built prompt for task {request.task_id}",
            extra={
                "agent": self.name,
                "task_id": request.task_id,
                "prompt_length": len(prompt),
            },
        )

        return prompt
