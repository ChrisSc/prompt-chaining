"""
Integration tests for the full orchestrator-worker-synthesizer pipeline.

Tests the complete flow from user request through orchestration, worker execution,
and synthesis of results.
"""

from unittest.mock import AsyncMock, patch

import pytest

from orchestrator_worker.agents.orchestrator import Orchestrator
from orchestrator_worker.config import Settings
from orchestrator_worker.models.internal import TaskResult
from orchestrator_worker.models.openai import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionStreamChoice,
    ChatMessage,
    ChoiceDelta,
    MessageRole,
)
from orchestrator_worker.utils.errors import ExternalServiceError


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        anthropic_api_key="test-key-123",
        environment="development",
        log_level="DEBUG",
        orchestrator_model="claude-sonnet-4-5-20250929",
        orchestrator_max_tokens=4096,
        orchestrator_temperature=0.7,
        worker_model="claude-haiku-4-5-20251001",
        worker_max_tokens=4096,
        worker_temperature=0.5,
        synthesizer_model="claude-haiku-4-5-20251001",
        synthesizer_max_tokens=2048,
        synthesizer_temperature=0.5,
        service_model_name="test-service-v1",
    )


@pytest.fixture
def orchestrator(settings: Settings) -> Orchestrator:
    """Create an Orchestrator instance for testing."""
    return Orchestrator(settings)


class TestOrchestratorWorkerIntegration:
    """Test orchestrator and worker coordination."""

    async def test_orchestrator_determines_task_count(self, orchestrator: Orchestrator):
        """Test task count determination based on request."""
        # Short message
        short_request = ChatCompletionRequest(
            model="test",
            messages=[ChatMessage(role=MessageRole.USER, content="Hi")],
        )
        assert orchestrator._determine_task_count(short_request) == 2

        # Medium message
        medium_request = ChatCompletionRequest(
            model="test",
            messages=[ChatMessage(role=MessageRole.USER, content="x" * 100)],
        )
        assert orchestrator._determine_task_count(medium_request) == 2

        # Long message
        long_request = ChatCompletionRequest(
            model="test",
            messages=[ChatMessage(role=MessageRole.USER, content="x" * 300)],
        )
        assert orchestrator._determine_task_count(long_request) == 3

    async def test_coordinate_workers_success(self, orchestrator: Orchestrator):
        """Test successful worker coordination."""
        with patch("orchestrator_worker.agents.orchestrator.Worker") as mock_worker_class:
            # Create mock workers
            mock_workers = [AsyncMock() for _ in range(2)]

            # Setup worker mocks to return TaskResults
            mock_workers[0].process_task.return_value = TaskResult(
                task_id=1,
                output="Worker 1 result",
                success=True,
            )
            mock_workers[1].process_task.return_value = TaskResult(
                task_id=2,
                output="Worker 2 result",
                success=True,
            )

            mock_worker_class.side_effect = mock_workers

            # Execute
            result = await orchestrator._coordinate_workers(2, "Test message")

            # Verify it's a list of TaskResults
            assert isinstance(result, list)
            assert len(result) == 2
            assert all(isinstance(r, TaskResult) for r in result)
            assert result[0].output == "Worker 1 result"
            assert result[1].output == "Worker 2 result"

            # Verify initialization and shutdown were called
            for worker in mock_workers:
                worker.initialize.assert_called_once()
                worker.shutdown.assert_called_once()

    async def test_coordinate_workers_partial_failure(self, orchestrator: Orchestrator):
        """Test worker coordination with one failed worker."""
        with patch("orchestrator_worker.agents.orchestrator.Worker") as mock_worker_class:
            mock_workers = [AsyncMock(), AsyncMock()]

            # First worker succeeds, second fails
            mock_workers[0].process_task.return_value = TaskResult(
                task_id=1,
                output="Worker 1 result",
                success=True,
            )
            mock_workers[1].process_task.side_effect = Exception("Worker 2 failed")

            mock_worker_class.side_effect = mock_workers

            # Should raise exception on first failure
            with pytest.raises(ExternalServiceError) as exc_info:
                await orchestrator._coordinate_workers(2, "Test message")

            assert "Failed to execute task" in str(exc_info.value)
            assert exc_info.value.error_code == "TASK_EXECUTION_ERROR"

    async def test_orchestrator_initialization(self, orchestrator: Orchestrator):
        """Test orchestrator initialization."""
        with patch("orchestrator_worker.agents.orchestrator.AsyncAnthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client

            await orchestrator.initialize()

            assert orchestrator.client is not None
            mock_anthropic.assert_called_once()

    async def test_orchestrator_shutdown(self, orchestrator: Orchestrator):
        """Test orchestrator shutdown."""
        with patch("orchestrator_worker.agents.orchestrator.AsyncAnthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client
            orchestrator.client = mock_client

            await orchestrator.shutdown()

            mock_client.close.assert_called_once()
            assert orchestrator.client is None


class TestOrchestratorSynthesizerIntegration:
    """Test orchestrator and synthesizer integration."""

    async def test_invoke_synthesizer(self, orchestrator: Orchestrator):
        """Test invoking synthesizer from orchestrator."""
        task_results = [
            TaskResult(task_id=1, output="Result 1", success=True),
            TaskResult(task_id=2, output="Result 2", success=True),
        ]

        with patch("orchestrator_worker.agents.orchestrator.Synthesizer") as mock_synth_class:
            mock_synthesizer = AsyncMock()
            mock_synth_class.return_value = mock_synthesizer

            # Mock the synthesize method to return chunks
            async def mock_synthesize(results):
                yield ChatCompletionChunk(
                    id="test",
                    created=0,
                    model="test",
                    choices=[
                        ChatCompletionStreamChoice(
                            index=0,
                            delta=ChoiceDelta(role="assistant", content="Synthesized"),
                            finish_reason=None,
                        )
                    ],
                )
                yield ChatCompletionChunk(
                    id="test",
                    created=0,
                    model="test",
                    choices=[
                        ChatCompletionStreamChoice(
                            index=0,
                            delta=ChoiceDelta(content=None),
                            finish_reason="stop",
                        )
                    ],
                )

            mock_synthesizer.synthesize = mock_synthesize

            # Collect chunks
            chunks = []
            async for chunk in orchestrator._invoke_synthesizer(task_results):
                chunks.append(chunk)

            # Verify
            assert len(chunks) == 2
            assert chunks[0].choices[0].delta.content == "Synthesized"
            assert chunks[-1].choices[0].finish_reason == "stop"

            # Verify initialization and shutdown
            mock_synthesizer.initialize.assert_called_once()
            mock_synthesizer.shutdown.assert_called_once()


class TestFullPipelineIntegration:
    """Test the complete orchestrator-worker-synthesizer pipeline."""

    async def test_full_pipeline_process(self, orchestrator: Orchestrator):
        """Test complete pipeline from request to synthesized response."""
        request = ChatCompletionRequest(
            model="test",
            messages=[ChatMessage(role=MessageRole.USER, content="Test query")],
        )

        with (
            patch("orchestrator_worker.agents.orchestrator.AsyncAnthropic") as mock_anthropic_orch,
            patch("orchestrator_worker.agents.orchestrator.Worker") as mock_worker_class,
            patch("orchestrator_worker.agents.orchestrator.Synthesizer") as mock_synth_class,
        ):

            # Setup orchestrator client
            mock_orch_client = AsyncMock()
            mock_anthropic_orch.return_value = mock_orch_client
            orchestrator.client = mock_orch_client

            # Setup workers
            mock_workers = [AsyncMock() for _ in range(2)]
            mock_workers[0].process_task.return_value = TaskResult(
                task_id=1,
                output="Worker 1: First perspective",
                success=True,
            )
            mock_workers[1].process_task.return_value = TaskResult(
                task_id=2,
                output="Worker 2: Second perspective",
                success=True,
            )
            mock_worker_class.side_effect = mock_workers

            # Setup synthesizer
            mock_synthesizer = AsyncMock()
            mock_synth_class.return_value = mock_synthesizer

            async def mock_synthesize(results):
                yield ChatCompletionChunk(
                    id="test-1",
                    created=0,
                    model="test",
                    choices=[
                        ChatCompletionStreamChoice(
                            index=0,
                            delta=ChoiceDelta(role="assistant", content="Final "),
                            finish_reason=None,
                        )
                    ],
                )
                yield ChatCompletionChunk(
                    id="test-2",
                    created=0,
                    model="test",
                    choices=[
                        ChatCompletionStreamChoice(
                            index=0,
                            delta=ChoiceDelta(content="synthesized "),
                            finish_reason=None,
                        )
                    ],
                )
                yield ChatCompletionChunk(
                    id="test-3",
                    created=0,
                    model="test",
                    choices=[
                        ChatCompletionStreamChoice(
                            index=0,
                            delta=ChoiceDelta(content="response."),
                            finish_reason=None,
                        )
                    ],
                )
                yield ChatCompletionChunk(
                    id="test-4",
                    created=0,
                    model="test",
                    choices=[
                        ChatCompletionStreamChoice(
                            index=0,
                            delta=ChoiceDelta(),
                            finish_reason="stop",
                        )
                    ],
                )

            mock_synthesizer.synthesize = mock_synthesize

            # Execute the pipeline
            chunks = []
            async for chunk in orchestrator.process(request):
                chunks.append(chunk)

            # Verify chunks were collected
            assert len(chunks) == 4

            # Verify final chunk has finish_reason
            assert chunks[-1].choices[0].finish_reason == "stop"

            # Verify workers were coordinated
            assert mock_workers[0].initialize.called
            assert mock_workers[1].initialize.called
            assert mock_workers[0].shutdown.called
            assert mock_workers[1].shutdown.called

            # Verify synthesizer was invoked
            mock_synthesizer.initialize.assert_called_once()
            mock_synthesizer.shutdown.assert_called_once()

    async def test_full_pipeline_with_empty_messages(self, orchestrator: Orchestrator):
        """Test pipeline handles requests with no user messages."""
        request = ChatCompletionRequest(
            model="test",
            messages=[],
        )

        orchestrator.client = AsyncMock()

        with pytest.raises(ValueError):
            async for _ in orchestrator.process(request):
                pass

    async def test_full_pipeline_with_assistant_messages(self, orchestrator: Orchestrator):
        """Test pipeline correctly extracts user message from mixed conversation."""
        request = ChatCompletionRequest(
            model="test",
            messages=[
                ChatMessage(role=MessageRole.USER, content="First message"),
                ChatMessage(role=MessageRole.ASSISTANT, content="Response"),
                ChatMessage(role=MessageRole.USER, content="Second message"),
            ],
        )

        with (
            patch("orchestrator_worker.agents.orchestrator.AsyncAnthropic") as mock_anthropic,
            patch("orchestrator_worker.agents.orchestrator.Worker") as mock_worker_class,
            patch("orchestrator_worker.agents.orchestrator.Synthesizer") as mock_synth_class,
        ):

            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client
            orchestrator.client = mock_client

            mock_workers = [AsyncMock() for _ in range(2)]
            mock_workers[0].process_task.return_value = TaskResult(
                task_id=1, output="Result 1", success=True
            )
            mock_workers[1].process_task.return_value = TaskResult(
                task_id=2, output="Result 2", success=True
            )
            mock_worker_class.side_effect = mock_workers

            mock_synthesizer = AsyncMock()
            mock_synth_class.return_value = mock_synthesizer

            async def mock_synthesize(results):
                yield ChatCompletionChunk(
                    id="test",
                    created=0,
                    model="test",
                    choices=[
                        ChatCompletionStreamChoice(
                            index=0,
                            delta=ChoiceDelta(content="Output"),
                            finish_reason=None,
                        )
                    ],
                )
                yield ChatCompletionChunk(
                    id="test",
                    created=0,
                    model="test",
                    choices=[
                        ChatCompletionStreamChoice(
                            index=0,
                            delta=ChoiceDelta(),
                            finish_reason="stop",
                        )
                    ],
                )

            mock_synthesizer.synthesize = mock_synthesize

            chunks = []
            async for chunk in orchestrator.process(request):
                chunks.append(chunk)

            # Verify the orchestrator extracted the last user message
            worker_call_args = mock_workers[0].process_task.call_args[0][0]
            assert "Second message" in worker_call_args.instruction


class TestErrorHandling:
    """Test error handling in the pipeline."""

    async def test_synthesizer_error_propagates(self, orchestrator: Orchestrator):
        """Test that synthesizer errors propagate correctly."""
        task_results = [TaskResult(task_id=1, output="Result", success=True)]

        with patch("orchestrator_worker.agents.orchestrator.Synthesizer") as mock_synth_class:
            mock_synthesizer = AsyncMock()
            mock_synth_class.return_value = mock_synthesizer

            # Make synthesize raise an error
            async def mock_error(results):
                raise ExternalServiceError(
                    "Synthesizer failed",
                    service_name="anthropic",
                    error_code="SYNTHESIS_ERROR",
                )
                yield  # Make this a generator

            mock_synthesizer.synthesize = mock_error

            with pytest.raises(ExternalServiceError):
                async for _ in orchestrator._invoke_synthesizer(task_results):
                    pass

            # Verify cleanup still happened
            mock_synthesizer.shutdown.assert_called_once()
