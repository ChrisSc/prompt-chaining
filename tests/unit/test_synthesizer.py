"""
Unit tests for Synthesizer agent.

Tests the synthesizer's ability to aggregate and polish worker results.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator_worker.agents.synthesizer import Synthesizer
from orchestrator_worker.config import Settings
from orchestrator_worker.models.internal import TaskResult
from orchestrator_worker.models.openai import ChatCompletionRequest, ChatMessage, MessageRole
from orchestrator_worker.utils.errors import ExternalServiceError


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        anthropic_api_key="test-key-123",
        environment="development",
        log_level="DEBUG",
        synthesizer_model="claude-haiku-4-5-20251001",
        synthesizer_max_tokens=2048,
        synthesizer_temperature=0.5,
    )


@pytest.fixture
def synthesizer(settings: Settings) -> Synthesizer:
    """Create a Synthesizer instance for testing."""
    return Synthesizer(settings)


@pytest.fixture
def sample_task_results() -> list[TaskResult]:
    """Create a sample list of task results for testing."""
    return [
        TaskResult(
            task_id=1,
            output="Worker 1 output: Core machine learning concepts",
            success=True,
            metadata={"tokens": 100},
        ),
        TaskResult(
            task_id=2,
            output="Worker 2 output: Real-world ML applications",
            success=True,
            metadata={"tokens": 120},
        ),
    ]


class TestSynthesizerInitialization:
    """Test Synthesizer initialization and lifecycle."""

    def test_synthesizer_init(self, synthesizer: Synthesizer, settings: Settings):
        """Test Synthesizer initialization."""
        assert synthesizer.name == "synthesizer"
        assert synthesizer.model == settings.synthesizer_model
        assert synthesizer.settings == settings
        assert synthesizer.max_tokens == settings.synthesizer_max_tokens
        assert synthesizer.temperature == settings.synthesizer_temperature
        assert synthesizer.client is None

    async def test_synthesizer_initialize(self, synthesizer: Synthesizer):
        """Test Synthesizer initialization."""
        with patch("orchestrator_worker.agents.synthesizer.AsyncAnthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client

            await synthesizer.initialize()

            assert synthesizer.client is not None
            mock_anthropic.assert_called_once_with(api_key=synthesizer.api_key)

    async def test_synthesizer_shutdown(self, synthesizer: Synthesizer):
        """Test Synthesizer shutdown."""
        with patch("orchestrator_worker.agents.synthesizer.AsyncAnthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client
            synthesizer.client = mock_client

            await synthesizer.shutdown()

            mock_client.close.assert_called_once()
            assert synthesizer.client is None


class TestSynthesizerProcess:
    """Test Synthesizer process method."""

    async def test_process_not_implemented(self, synthesizer: Synthesizer):
        """Test that process method raises NotImplementedError."""
        request = ChatCompletionRequest(
            model="test",
            messages=[ChatMessage(role=MessageRole.USER, content="test")],
        )

        with pytest.raises(NotImplementedError):
            async for _ in synthesizer.process(request):
                pass


class TestSynthesizerSynthesize:
    """Test Synthesizer synthesize method."""

    async def test_synthesize_not_initialized(
        self, synthesizer: Synthesizer, sample_task_results: list[TaskResult]
    ):
        """Test synthesize raises error when not initialized."""
        with pytest.raises(ExternalServiceError) as exc_info:
            async for _ in synthesizer.synthesize(sample_task_results):
                pass

        assert "not initialized" in str(exc_info.value)
        assert exc_info.value.error_code == "CLIENT_NOT_INITIALIZED"

    async def test_synthesize_success(
        self, synthesizer: Synthesizer, sample_task_results: list[TaskResult]
    ):
        """Test successful synthesis with streaming response."""
        # Mock the Claude API
        with patch("orchestrator_worker.agents.synthesizer.AsyncAnthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client

            # Create mock stream events for streaming call
            mock_events = [
                MagicMock(type="content_block_delta", delta=MagicMock(text="Synthesized ")),
                MagicMock(type="content_block_delta", delta=MagicMock(text="output ")),
                MagicMock(type="content_block_delta", delta=MagicMock(text="here.")),
                MagicMock(type="message_stop"),
            ]

            async def mock_stream():
                for event in mock_events:
                    yield event

            # Setup mock to return stream for streaming call and a response for the token capture call
            mock_response = MagicMock()
            mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

            mock_client.messages.create.side_effect = [mock_stream(), mock_response]
            synthesizer.client = mock_client

            # Collect all chunks
            chunks = []
            async for chunk in synthesizer.synthesize(sample_task_results):
                chunks.append(chunk)

            # Verify we got chunks
            assert len(chunks) > 0

            # Verify the API was called twice (streaming + token capture)
            assert mock_client.messages.create.call_count == 2

            # Check first call (streaming)
            first_call_kwargs = mock_client.messages.create.call_args_list[0][1]
            assert first_call_kwargs["model"] == synthesizer.model
            assert first_call_kwargs["max_tokens"] == synthesizer.max_tokens
            assert first_call_kwargs["temperature"] == synthesizer.temperature
            assert first_call_kwargs["stream"] is True

            # Verify content chunks
            content_chunks = [c for c in chunks if c.choices[0].delta.content is not None]
            assert len(content_chunks) == 3
            assert content_chunks[0].choices[0].delta.content == "Synthesized "
            assert content_chunks[1].choices[0].delta.content == "output "
            assert content_chunks[2].choices[0].delta.content == "here."

            # Verify final chunk has finish_reason
            final_chunk = chunks[-1]
            assert final_chunk.choices[0].finish_reason == "stop"

    async def test_synthesize_with_failed_tasks(self, synthesizer: Synthesizer):
        """Test synthesize with some failed tasks."""
        task_results = [
            TaskResult(
                task_id=1,
                output="Worker 1 output",
                success=True,
            ),
            TaskResult(
                task_id=2,
                output="",
                success=False,
                error="Worker 2 failed: API timeout",
            ),
        ]

        with patch("orchestrator_worker.agents.synthesizer.AsyncAnthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client

            mock_events = [
                MagicMock(type="content_block_delta", delta=MagicMock(text="Result")),
                MagicMock(type="message_stop"),
            ]

            async def mock_stream():
                for event in mock_events:
                    yield event

            # Setup mock for streaming and token capture calls
            mock_response = MagicMock()
            mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

            mock_client.messages.create.side_effect = [mock_stream(), mock_response]
            synthesizer.client = mock_client

            chunks = []
            async for chunk in synthesizer.synthesize(task_results):
                chunks.append(chunk)

            # Verify we got chunks despite one failed task
            assert len(chunks) > 0

            # Verify the prompt includes error information (from first call)
            first_call_kwargs = mock_client.messages.create.call_args_list[0][1]
            messages = first_call_kwargs["messages"]
            prompt = messages[0]["content"]
            assert "✗ Failed" in prompt or "Failed" in prompt or "error" in prompt.lower()

    async def test_synthesize_api_error(
        self, synthesizer: Synthesizer, sample_task_results: list[TaskResult]
    ):
        """Test synthesize handles API errors gracefully."""
        with patch("orchestrator_worker.agents.synthesizer.AsyncAnthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_anthropic.return_value = mock_client

            # Make the API call raise an exception
            mock_client.messages.create.side_effect = Exception("API Error: Rate limited")
            synthesizer.client = mock_client

            with pytest.raises(ExternalServiceError) as exc_info:
                async for _ in synthesizer.synthesize(sample_task_results):
                    pass

            assert "Failed to synthesize results" in str(exc_info.value)
            assert exc_info.value.error_code == "SYNTHESIS_ERROR"


class TestSynthesizerPromptBuilding:
    """Test Synthesizer prompt building."""

    def test_build_synthesis_prompt_basic(
        self, synthesizer: Synthesizer, sample_task_results: list[TaskResult]
    ):
        """Test basic prompt building."""
        prompt = synthesizer._build_synthesis_prompt(sample_task_results)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "Worker Results:" in prompt
        assert "Task 1" in prompt
        assert "Task 2" in prompt
        assert "Worker 1 output" in prompt
        assert "Worker 2 output" in prompt
        assert "Aggregation Summary:" in prompt

    def test_build_synthesis_prompt_with_multiple_tasks(self, synthesizer: Synthesizer):
        """Test prompt building with multiple tasks."""
        task_results = [
            TaskResult(
                task_id=1,
                output="Result 1",
                success=True,
            ),
            TaskResult(
                task_id=2,
                output="Result 2",
                success=True,
            ),
        ]

        prompt = synthesizer._build_synthesis_prompt(task_results)

        assert "Aggregation Summary:" in prompt
        assert "total_tasks: 2" in prompt
        assert "successful: 2" in prompt
        assert "failed: 0" in prompt

    def test_build_synthesis_prompt_with_failures(self, synthesizer: Synthesizer):
        """Test prompt building with failed tasks."""
        task_results = [
            TaskResult(
                task_id=1,
                output="Result",
                success=True,
            ),
            TaskResult(
                task_id=2,
                output="",
                success=False,
                error="Task failed",
            ),
        ]

        prompt = synthesizer._build_synthesis_prompt(task_results)

        assert isinstance(prompt, str)
        assert "Result" in prompt
        assert "✗ Failed" in prompt
        assert "total_tasks: 2" in prompt
        assert "successful: 1" in prompt
        assert "failed: 1" in prompt

    def test_build_synthesis_prompt_single_result(self, synthesizer: Synthesizer):
        """Test prompt building with single result."""
        task_results = [
            TaskResult(
                task_id=1,
                output="Single task result",
                success=True,
            )
        ]

        prompt = synthesizer._build_synthesis_prompt(task_results)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "Number of tasks: 1" in prompt
        assert "Single task result" in prompt
        assert "Aggregation Summary:" in prompt
        assert "total_tasks: 1" in prompt
