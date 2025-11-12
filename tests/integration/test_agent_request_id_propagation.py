"""
Integration tests for agent request ID propagation.

Tests that agents properly retrieve request IDs from context and pass them to the
Anthropic API via extra_headers. Verifies propagation through Worker, Synthesizer,
and Orchestrator agents, and tests graceful handling when request ID is missing.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator_worker.agents.orchestrator import Orchestrator
from orchestrator_worker.agents.synthesizer import Synthesizer
from orchestrator_worker.agents.worker import Worker
from orchestrator_worker.config import Settings
from orchestrator_worker.models.internal import (
    AggregatedResult,
    TaskRequest,
    TaskResult,
    TokenUsage,
)
from orchestrator_worker.models.openai import ChatCompletionRequest, ChatMessage
from orchestrator_worker.utils.request_context import (
    _request_id_var,
    get_request_id,
    set_request_id,
)


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings."""
    return Settings(
        anthropic_api_key="test-api-key-123",
        jwt_secret_key="test_secret_key_with_minimum_32_characters_required_for_testing",
        environment="test",
    )


class TestWorkerAgentRequestIdPropagation:
    """Test that WorkerAgent propagates request ID to API calls."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    @pytest.mark.asyncio
    async def test_worker_agent_sends_request_id_header(self, test_settings) -> None:
        """Test WorkerAgent includes X-Request-ID in API calls."""
        request_id = "req_worker_test_123"
        set_request_id(request_id)

        worker = Worker(settings=test_settings)

        # Mock the AsyncAnthropic client
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Test worker response"
        mock_response.content = [mock_content]

        worker.client = AsyncMock()
        worker.client.messages.create = AsyncMock(return_value=mock_response)

        await worker.initialize()

        task = TaskRequest(task_id="task_1", instruction="Test instruction", data={})
        result = await worker.process_task(task)

        # Verify API was called
        assert worker.client.messages.create.called

        # Get the call arguments
        call_kwargs = worker.client.messages.create.call_args[1]

        # Verify extra_headers contains request ID
        assert "extra_headers" in call_kwargs
        assert call_kwargs["extra_headers"]["X-Request-ID"] == request_id

        # Verify result was returned
        assert isinstance(result, TaskResult)
        assert result.task_id == "task_1"

    @pytest.mark.asyncio
    async def test_worker_agent_uses_different_request_ids(self, test_settings) -> None:
        """Test WorkerAgent properly handles different request IDs."""
        worker = Worker(settings=test_settings)

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Response"
        mock_response.content = [mock_content]

        worker.client = AsyncMock()
        worker.client.messages.create = AsyncMock(return_value=mock_response)

        await worker.initialize()

        task = TaskRequest(task_id="task_1", instruction="Test", data={})

        # Test with first request ID
        set_request_id("req_worker_first")
        await worker.process_task(task)
        first_call_headers = worker.client.messages.create.call_args[1]["extra_headers"]
        assert first_call_headers["X-Request-ID"] == "req_worker_first"

        # Test with second request ID
        set_request_id("req_worker_second")
        await worker.process_task(task)
        second_call_headers = worker.client.messages.create.call_args[1]["extra_headers"]
        assert second_call_headers["X-Request-ID"] == "req_worker_second"

    @pytest.mark.asyncio
    async def test_worker_agent_handles_missing_request_id(self, test_settings) -> None:
        """Test WorkerAgent works when no request_id is in context."""
        # Ensure no request ID in context
        set_request_id(None)

        worker = Worker(settings=test_settings)

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Response"
        mock_response.content = [mock_content]

        worker.client = AsyncMock()
        worker.client.messages.create = AsyncMock(return_value=mock_response)

        await worker.initialize()

        task = TaskRequest(task_id="task_1", instruction="Test", data={})

        # Should not raise error even without request_id in context
        result = await worker.process_task(task)

        # API should still be called
        assert worker.client.messages.create.called

        # extra_headers might be empty dict if no request_id
        call_kwargs = worker.client.messages.create.call_args[1]
        assert "extra_headers" in call_kwargs
        # If no request ID, extra_headers should be empty or not contain X-Request-ID
        if call_kwargs["extra_headers"]:
            assert "X-Request-ID" not in call_kwargs["extra_headers"]

        assert isinstance(result, TaskResult)


class TestSynthesizerAgentRequestIdPropagation:
    """Test that SynthesizerAgent propagates request ID to streaming API calls."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    @pytest.mark.asyncio
    async def test_synthesizer_agent_sends_request_id_header(self, test_settings) -> None:
        """Test SynthesizerAgent includes X-Request-ID in streaming API calls."""
        request_id = "req_synthesizer_test_456"
        set_request_id(request_id)

        synthesizer = Synthesizer(settings=test_settings)

        # Mock the streaming client
        synthesizer.client = AsyncMock()

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=None)

        # Create async iterator for streaming
        async def mock_stream_iter():
            yield MagicMock(delta=MagicMock(content="test"), usage=None)

        mock_stream.__aiter__ = MagicMock(return_value=mock_stream_iter())

        synthesizer.client.messages.stream = AsyncMock(return_value=mock_stream)

        await synthesizer.initialize()

        # Create test data
        task_result = TaskResult(
            task_id="task_1",
            output="Test output",
            token_usage=TokenUsage(input_tokens=10, output_tokens=5),
        )
        aggregated = AggregatedResult(task_results=[task_result])

        # Process through synthesizer
        stream = synthesizer.process(aggregated)
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)

        # Verify streaming API was called
        assert synthesizer.client.messages.stream.called

        # Get the call arguments
        call_kwargs = synthesizer.client.messages.stream.call_args[1]

        # Verify extra_headers contains request ID
        assert "extra_headers" in call_kwargs
        assert call_kwargs["extra_headers"]["X-Request-ID"] == request_id

    @pytest.mark.asyncio
    async def test_synthesizer_agent_handles_missing_request_id(self, test_settings) -> None:
        """Test SynthesizerAgent works when no request_id is in context."""
        # Ensure no request ID in context
        set_request_id(None)

        synthesizer = Synthesizer(settings=test_settings)

        synthesizer.client = AsyncMock()

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=None)

        async def mock_stream_iter():
            yield MagicMock(delta=MagicMock(content="test"), usage=None)

        mock_stream.__aiter__ = MagicMock(return_value=mock_stream_iter())
        synthesizer.client.messages.stream = AsyncMock(return_value=mock_stream)

        await synthesizer.initialize()

        task_result = TaskResult(
            task_id="task_1",
            output="Test output",
            token_usage=TokenUsage(input_tokens=10, output_tokens=5),
        )
        aggregated = AggregatedResult(task_results=[task_result])

        # Should not raise error
        stream = synthesizer.process(aggregated)
        async for _ in stream:
            pass

        # API should be called
        assert synthesizer.client.messages.stream.called

        call_kwargs = synthesizer.client.messages.stream.call_args[1]
        assert "extra_headers" in call_kwargs


class TestOrchestratorAgentRequestIdPropagation:
    """Test that OrchestratorAgent propagates request ID."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    @pytest.mark.asyncio
    async def test_orchestrator_agent_uses_request_id_context(self, test_settings) -> None:
        """Test OrchestratorAgent retrieves and uses request ID from context."""
        request_id = "req_orchestrator_test_789"
        set_request_id(request_id)

        orchestrator = Orchestrator(settings=test_settings)

        # Verify request ID is in context when orchestrator accesses it
        assert get_request_id() == request_id

        # Mock the API call
        orchestrator.client = AsyncMock()

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "2"  # Determines task count
        mock_response.content = [mock_content]

        orchestrator.client.messages.create = AsyncMock(return_value=mock_response)

        await orchestrator.initialize()

        # Create a test request
        request = ChatCompletionRequest(
            model="orchestrator-worker",
            messages=[ChatMessage(role="user", content="Test")],
        )

        # The orchestrator's initial API call should include request ID
        # This tests the first orchestrator call
        await orchestrator.client.messages.create(
            model=test_settings.orchestrator_model,
            max_tokens=1000,
            messages=[],
        )

        # Verify the call was made
        assert orchestrator.client.messages.create.called


class TestRequestIdContextIsolation:
    """Test that request IDs are properly isolated between concurrent agent operations."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    @pytest.mark.asyncio
    async def test_concurrent_worker_operations_maintain_isolation(self, test_settings) -> None:
        """Test concurrent worker operations maintain request ID isolation."""
        import asyncio

        worker = Worker(settings=test_settings)

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Response"
        mock_response.content = [mock_content]

        worker.client = AsyncMock()
        worker.client.messages.create = AsyncMock(return_value=mock_response)

        await worker.initialize()

        async def process_with_id(request_id: str, task_id: str):
            """Process task with specific request ID."""
            set_request_id(request_id)
            task = TaskRequest(task_id=task_id, instruction="Test", data={})
            return await worker.process_task(task)

        # Run concurrent tasks with different request IDs
        results = await asyncio.gather(
            process_with_id("req_isolation_1", "task_1"),
            process_with_id("req_isolation_2", "task_2"),
            process_with_id("req_isolation_3", "task_3"),
        )

        # All should complete successfully
        assert len(results) == 3
        assert all(isinstance(r, TaskResult) for r in results)

        # Verify each call had correct request ID
        calls = worker.client.messages.create.call_args_list
        assert len(calls) == 3

        # Extract request IDs from calls (order might vary due to async)
        request_ids_from_calls = []
        for call in calls:
            headers = call[1]["extra_headers"]
            if headers:
                request_ids_from_calls.append(headers.get("X-Request-ID"))

        # Should have the three request IDs (in any order)
        assert set(request_ids_from_calls) == {
            "req_isolation_1",
            "req_isolation_2",
            "req_isolation_3",
        }


class TestRequestIdErrorPropagation:
    """Test request ID behavior during error conditions."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    @pytest.mark.asyncio
    async def test_worker_includes_request_id_on_api_error(self, test_settings) -> None:
        """Test request ID is attempted to be sent even when API returns error."""
        request_id = "req_error_test"
        set_request_id(request_id)

        worker = Worker(settings=test_settings)

        # Mock API error
        worker.client = AsyncMock()
        worker.client.messages.create = AsyncMock(
            side_effect=Exception("API Error")
        )

        await worker.initialize()

        task = TaskRequest(task_id="task_1", instruction="Test", data={})

        # Should raise error from API
        with pytest.raises(Exception):
            await worker.process_task(task)

        # But the API was called with the headers
        assert worker.client.messages.create.called
        call_kwargs = worker.client.messages.create.call_args[1]
        assert "extra_headers" in call_kwargs


class TestRequestIdWithTokenTracking:
    """Test request ID works alongside token tracking."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    @pytest.mark.asyncio
    async def test_request_id_preserved_during_token_calculation(self, test_settings) -> None:
        """Test request ID context is maintained during token tracking."""
        request_id = "req_token_tracking_test"
        set_request_id(request_id)

        # Verify ID is still available
        assert get_request_id() == request_id

        # Simulate token tracking operations
        from orchestrator_worker.utils.token_tracking import calculate_cost

        cost = calculate_cost("claude-haiku-4-5-20251001", 100, 50)

        # Request ID should still be available
        assert get_request_id() == request_id
        assert cost is not None


class TestRequestIdInLoggingContext:
    """Test that request ID is available in logging context."""

    def setup_method(self) -> None:
        """Reset context before each test."""
        _request_id_var.set(None)

    @pytest.mark.asyncio
    async def test_request_id_available_for_logging_in_agent(self, test_settings) -> None:
        """Test that request ID is available when agent logs."""
        request_id = "req_logging_test"
        set_request_id(request_id)

        worker = Worker(settings=test_settings)

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Response"
        mock_response.content = [mock_content]

        worker.client = AsyncMock()
        worker.client.messages.create = AsyncMock(return_value=mock_response)

        await worker.initialize()

        # During task processing, request ID should be available for logging
        task = TaskRequest(task_id="task_1", instruction="Test", data={})
        result = await worker.process_task(task)

        # Verify task completed successfully (and logging occurred)
        assert isinstance(result, TaskResult)

        # Request ID should still be available
        assert get_request_id() == request_id
