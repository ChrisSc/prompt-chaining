"""
Orchestrator agent implementation using Claude Agent SDK.

The orchestrator coordinates multiple worker agents to complete complex tasks.
This is a simple example - customize for your specific use case.
"""

import asyncio
from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from workflow.agents.base import Agent
from workflow.agents.synthesizer import Synthesizer
from workflow.agents.worker import Worker
from workflow.config import Settings
from workflow.models.internal import TaskRequest, TaskResult
from workflow.models.openai import (
    ChatCompletionChunk,
    ChatCompletionRequest,
)
from workflow.utils.errors import ExternalServiceError, StreamingTimeoutError
from workflow.utils.logging import get_logger
from workflow.utils.prompts import load_prompt
from workflow.utils.request_context import get_request_id
from workflow.utils.token_tracking import aggregate_token_metrics

logger = get_logger(__name__)

# Fallback prompt if file not found (kept for safety)
FALLBACK_PROMPT = """You are an orchestrator agent coordinating multiple worker agents.

Your responsibilities:
1. Analyze the user's request
2. Determine how many workers are needed (typically 2-3 for demonstration)
3. Assign specific tasks to each worker
4. Aggregate their results into a coherent response

This is a simple demonstration - customize for your use case.

Example: User says "Hello, world!" - you spawn 2 workers:
- Worker 1: Echo the greeting
- Worker 2: Add a friendly response
Then combine their outputs.
"""

# Load system prompt from file (with fallback)
ORCHESTRATOR_SYSTEM_PROMPT = load_prompt("orchestrator", fallback=FALLBACK_PROMPT)


class Orchestrator(Agent):
    """
    Orchestrator agent for coordinating worker agents.

    Uses Claude API for intelligent task decomposition and coordination.
    Spawns multiple Worker instances to execute tasks in parallel.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the Orchestrator agent.

        Args:
            settings: Application configuration settings
        """
        super().__init__(
            name="orchestrator",
            model=settings.orchestrator_model,
        )
        self.settings = settings
        self.api_key = settings.anthropic_api_key
        self.client: AsyncAnthropic | None = None
        self.max_tokens = settings.orchestrator_max_tokens
        self.temperature = settings.orchestrator_temperature
        # Friendly model name for API responses (from config)
        self.display_model = settings.service_model_name

    async def initialize(self) -> None:
        """
        Initialize the agent and Claude API client.

        Called during application startup.
        """
        logger.info(
            f"Initializing {self.name} agent", extra={"agent": self.name, "model": self.model}
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

        Called during application shutdown.
        """
        logger.info(f"Shutting down {self.name} agent", extra={"agent": self.name})
        if self.client:
            await self.client.close()
            self.client = None

    def _determine_task_count(self, request: ChatCompletionRequest) -> int:
        """
        Determine how many worker tasks are needed.

        Simple heuristic: 2-3 tasks for demonstration.
        Customize this for your use case.

        Args:
            request: The chat completion request

        Returns:
            Number of tasks to create (and workers to spawn)
        """
        # Get latest user message
        user_messages = [msg for msg in request.messages if msg.role.value == "user"]
        if not user_messages:
            return 2

        message_length = len(user_messages[-1].content)

        # Simple heuristic: longer messages get more workers
        if message_length > 200:
            return 3
        if message_length > 50:
            return 2
        return 2

    async def _coordinate_workers(
        self,
        num_tasks: int,
        user_message: str,
    ) -> list[TaskResult]:
        """
        Coordinate multiple Worker instances to complete tasks in parallel.

        Spawns N Worker instances, executes them in parallel using asyncio.gather,
        and returns raw task results.

        Args:
            num_tasks: Number of tasks (and workers) to create
            user_message: The user's message to process

        Returns:
            List of task results from all workers

        Raises:
            ExternalServiceError: If any worker fails
        """
        logger.info(
            f"Coordinating {num_tasks} workers",
            extra={"num_tasks": num_tasks, "user_message_length": len(user_message)},
        )

        # Create Worker instances (one per task)
        workers = [Worker(self.settings) for _ in range(num_tasks)]

        # Initialize all workers in parallel
        await asyncio.gather(*[worker.initialize() for worker in workers])

        # Create TaskRequests - simple example that processes the user message
        task_requests = [
            TaskRequest(
                task_id=task_num + 1,
                instruction=f"Process part {task_num + 1} of {num_tasks}: {user_message}",
                data={
                    "original_message": user_message,
                    "part": task_num + 1,
                    "total_parts": num_tasks,
                },
            )
            for task_num in range(num_tasks)
        ]

        # Execute all workers in parallel
        logger.info(f"Executing {num_tasks} workers in parallel")

        # Use return_exceptions=True to prevent one failure from canceling others
        results = await asyncio.gather(
            *[worker.process_task(request) for worker, request in zip(workers, task_requests)],
            return_exceptions=True,
        )

        # Separate successful results from exceptions
        task_results: list[TaskResult] = []
        errors: list[tuple[int, Exception]] = []

        for task_num, result in enumerate(results, start=1):
            if isinstance(result, Exception):
                logger.error(
                    f"Task {task_num} failed: {result}",
                    extra={"task_id": task_num, "error": str(result)},
                )
                errors.append((task_num, result))
            else:
                task_results.append(result)

        # Shut down all workers (success or failure)
        await asyncio.gather(*[worker.shutdown() for worker in workers], return_exceptions=True)

        # If any tasks failed, raise the first error
        if errors:
            task_num, error = errors[0]
            raise ExternalServiceError(
                message=f"Failed to execute task {task_num}: {error}",
                service_name="anthropic",
                error_code="TASK_EXECUTION_ERROR",
            ) from error

        logger.info(f"All {num_tasks} workers completed successfully")

        # Aggregate and log worker token metrics
        self._log_worker_tokens(task_results)

        # Return raw task results (Synthesizer will aggregate)
        return task_results

    def _log_worker_tokens(self, task_results: list[TaskResult]) -> None:
        """
        Aggregate and log token usage from all workers.

        Calculates total tokens and costs used by all workers and logs them
        for monitoring and cost tracking.

        Args:
            task_results: List of task results from all workers
        """
        if not task_results:
            return

        # Extract token usage from each result
        usages = []
        models = []
        for result in task_results:
            if result.token_usage:
                usages.append(
                    {
                        "input_tokens": result.token_usage.input_tokens,
                        "output_tokens": result.token_usage.output_tokens,
                    }
                )
                models.append(self.settings.worker_model)

        if usages and models:
            total_tokens, total_cost = aggregate_token_metrics(usages, models)

            logger.info(
                "Worker tokens aggregated",
                extra={
                    "agent": self.name,
                    "num_workers": len(usages),
                    "total_tokens": total_tokens,
                    "total_cost_usd": total_cost,
                },
            )

    async def _invoke_synthesizer(
        self,
        task_results: list[TaskResult],
    ) -> AsyncIterator[ChatCompletionChunk]:
        """
        Invoke the Synthesizer to aggregate and polish worker results.

        Initializes a Synthesizer instance, processes the task results,
        and streams the synthesized response.

        Args:
            task_results: Raw results from all workers

        Yields:
            Streaming chunks of synthesized response

        Raises:
            ExternalServiceError: If synthesizer fails
        """
        logger.info(
            "Invoking synthesizer",
            extra={"num_results": len(task_results)},
        )

        # Create and initialize synthesizer
        synthesizer = Synthesizer(self.settings)
        await synthesizer.initialize()

        try:
            # Stream synthesized results
            async for chunk in synthesizer.synthesize(task_results):
                yield chunk

            logger.info(
                "Synthesizer completed successfully",
                extra={"num_results": len(task_results)},
            )
        except Exception as exc:
            logger.error(
                f"Synthesizer failed: {exc}",
                extra={"error": str(exc)},
            )
            raise
        finally:
            # Clean up synthesizer
            await synthesizer.shutdown()

    async def process(self, request: ChatCompletionRequest) -> AsyncIterator[ChatCompletionChunk]:
        """
        Process a chat completion request with streaming response.

        Determines task count, coordinates workers in parallel, and streams synthesized results.

        Args:
            request: The chat completion request

        Yields:
            Streaming chunks of the chat completion response

        Raises:
            ExternalServiceError: If Claude API call fails or client not initialized
        """
        if not self.client:
            raise ExternalServiceError(
                message="Orchestrator not initialized",
                service_name="anthropic",
                error_code="CLIENT_NOT_INITIALIZED",
            )

        # Validate request
        if not request.messages:
            raise ValueError("Request must contain at least one message")

        # Get user message
        user_messages = [msg for msg in request.messages if msg.role.value == "user"]
        user_message = user_messages[-1].content if user_messages else "Hello"

        # Determine how many tasks we need
        num_tasks = self._determine_task_count(request)

        request_id = get_request_id()
        logger.info(
            f"Processing request with {num_tasks} workers",
            extra={"num_tasks": num_tasks, "request_id": request_id},
        )

        # Coordinate workers to execute tasks in parallel with timeout enforcement
        try:
            task_results = await asyncio.wait_for(
                self._coordinate_workers(num_tasks, user_message),
                timeout=self.settings.worker_coordination_timeout,
            )
        except asyncio.TimeoutError:
            raise StreamingTimeoutError(
                phase="worker coordination",
                timeout_seconds=self.settings.worker_coordination_timeout,
            )

        # Invoke synthesizer to aggregate and polish results with timeout enforcement
        try:
            # For async generators, we need to apply timeout to the entire stream collection
            # Create a task that will be cancelled if it exceeds the timeout
            async def _get_all_chunks():
                chunks = []
                async for chunk in self._invoke_synthesizer(task_results):
                    chunks.append(chunk)
                return chunks

            # Execute with timeout
            all_chunks = await asyncio.wait_for(
                _get_all_chunks(),
                timeout=self.settings.synthesis_timeout,
            )

            # Yield all collected chunks
            for chunk in all_chunks:
                yield chunk
        except asyncio.TimeoutError:
            raise StreamingTimeoutError(
                phase="synthesis",
                timeout_seconds=self.settings.synthesis_timeout,
            )
