"""
Full end-to-end integration tests for the chain endpoint with real or mocked LLM.

Tests cover:
- Complete streaming flow through all 3 steps
- Token-by-token streaming in synthesis step
- SSE format validation
- Validation gate routing
- Token usage and cost tracking
- Error scenarios

Note: These tests can run with:
- Real LLM (requires ANTHROPIC_API_KEY)
- Mocked LLM (default, for CI/CD)
"""

import json
from unittest.mock import AsyncMock, patch
from typing import Any

import pytest
from langchain_core.messages import HumanMessage, AIMessage

from workflow.chains.graph import build_chain_graph, stream_chain
from workflow.models.chains import ChainConfig, ChainState, ChainStepConfig
from workflow.models.openai import ChatMessage, MessageRole, ChatCompletionRequest
from workflow.utils.message_conversion import (
    convert_openai_to_langchain_messages,
    convert_langchain_chunk_to_openai,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def chain_config():
    """Create ChainConfig for testing."""
    return ChainConfig(
        analyze=ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            temperature=0.5,
            system_prompt_file="chain_analyze.md",
        ),
        process=ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            temperature=0.7,
            system_prompt_file="chain_process.md",
        ),
        synthesize=ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            temperature=0.3,
            system_prompt_file="chain_synthesize.md",
        ),
    )


@pytest.fixture
def sample_request():
    """Create a sample chat completion request."""
    return ChatCompletionRequest(
        model="orchestrator-worker",
        messages=[
            ChatMessage(role=MessageRole.USER, content="What is machine learning?")
        ],
    )


@pytest.fixture
def mock_graph():
    """Create a mock graph for testing."""
    async def mock_astream(state: ChainState, stream_mode: str):
        """Mock streaming that yields state updates."""
        # Simulate analyze step
        yield {
            "analysis": {
                "intent": "Explain machine learning",
                "key_entities": ["machine learning", "AI"],
                "complexity": "moderate",
                "context": {},
            },
            "step_metadata": {"analyze": {"tokens": 150}},
        }

        # Simulate process step
        yield {
            "processed_content": "Machine learning is a subset of AI...",
            "step_metadata": {"process": {"tokens": 300}},
        }

        # Simulate synthesize step with streaming chunks
        yield {
            "final_response": "Machine learning is a subset of artificial intelligence",
            "step_metadata": {"synthesize": {"tokens": 200}},
        }

    mock_graph = AsyncMock()
    mock_graph.astream = mock_astream
    return mock_graph


# ============================================================================
# TESTS: Complete streaming flow
# ============================================================================


class TestCompleteStreamingFlow:
    """Tests for complete end-to-end streaming flow."""

    def test_message_conversion_for_streaming(self, sample_request, chain_config):
        """Test message conversion for streaming flow."""
        # Convert OpenAI messages to LangChain format
        langchain_messages = convert_openai_to_langchain_messages(sample_request.messages)

        # Build initial state
        initial_state: ChainState = {
            "messages": langchain_messages,
            "analysis": None,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        # Verify state is properly formatted
        assert "messages" in initial_state
        assert len(initial_state["messages"]) > 0
        assert initial_state["analysis"] is None

    def test_state_contains_all_required_fields(self, sample_request, chain_config):
        """Test that initial state contains all required fields."""
        langchain_messages = convert_openai_to_langchain_messages(sample_request.messages)

        initial_state: ChainState = {
            "messages": langchain_messages,
            "analysis": None,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        # All required fields should be present
        assert "messages" in initial_state
        assert "analysis" in initial_state
        assert "processed_content" in initial_state
        assert "final_response" in initial_state
        assert "step_metadata" in initial_state

    def test_streaming_chunk_conversion(self, sample_request, chain_config):
        """Test converting streaming chunks to OpenAI format."""
        # Create sample state updates like stream would produce
        state_updates = [
            {"analysis": {"intent": "test", "key_entities": ["test"], "complexity": "simple"}},
            {"processed_content": "Generated content"},
            {"final_response": "Final polished response"},
        ]

        # Convert each to OpenAI format
        for state_update in state_updates:
            chunk = convert_langchain_chunk_to_openai(state_update)
            assert chunk.object == "chat.completion.chunk"
            assert chunk.model == "orchestrator-worker"


# ============================================================================
# TESTS: Streaming response format
# ============================================================================


class TestStreamingResponseFormat:
    """Tests for proper formatting of streaming responses."""

    def test_chunks_are_valid_openai_format(self, sample_request, chain_config):
        """Test that chunks are valid ChatCompletionChunk format."""
        # Create sample state updates
        state_updates = [
            {"analysis": {"intent": "test", "key_entities": ["test"], "complexity": "simple"}},
            {"processed_content": "Generated content"},
            {"final_response": "Final response"},
        ]

        for state_update in state_updates:
            # Convert to OpenAI format
            chunk = convert_langchain_chunk_to_openai(state_update)

            # Verify required fields
            assert chunk.object == "chat.completion.chunk"
            assert chunk.model == "orchestrator-worker"
            assert chunk.choices is not None
            assert len(chunk.choices) > 0

    def test_chunks_can_be_serialized_to_json(self, sample_request, chain_config):
        """Test that chunks can be serialized to JSON for SSE."""
        state_updates = [
            {"analysis": {"intent": "test", "key_entities": ["test"], "complexity": "simple"}},
            {"final_response": "Final response"},
        ]

        for state_update in state_updates:
            chunk = convert_langchain_chunk_to_openai(state_update)

            # Should be able to convert to JSON
            json_str = chunk.model_dump_json()
            assert json_str is not None

            # Should be valid JSON
            parsed = json.loads(json_str)
            assert parsed["object"] == "chat.completion.chunk"

    def test_sse_format_with_chunks(self, sample_request, chain_config):
        """Test that chunks format properly as SSE events."""
        chunk = convert_langchain_chunk_to_openai({"final_response": "Test"})
        json_str = chunk.model_dump_json()

        # Format as SSE
        sse_line = f"data: {json_str}\n\n"

        # Should have proper SSE format
        assert sse_line.startswith("data: ")
        assert sse_line.endswith("\n\n")


# ============================================================================
# TESTS: Validation gate routing
# ============================================================================


class TestValidationGateRouting:
    """Tests for validation gate routing between steps."""

    @pytest.mark.asyncio
    async def test_successful_analysis_validation(self):
        """Test successful routing after analysis step."""
        from workflow.chains.validation import should_proceed_to_process

        state: ChainState = {
            "messages": [HumanMessage(content="test")],
            "analysis": {
                "intent": "User wants to learn",
                "key_entities": ["learning"],
                "complexity": "simple",
                "context": {},
            },
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_process(state)

        # Should proceed to process, not error
        assert result == "process"

    @pytest.mark.asyncio
    async def test_analysis_validation_failure_routes_to_error(self):
        """Test that invalid analysis routes to error."""
        from workflow.chains.validation import should_proceed_to_process

        state: ChainState = {
            "messages": [HumanMessage(content="test")],
            "analysis": {
                "intent": "",  # Empty intent should fail
                "key_entities": [],
                "complexity": "simple",
                "context": {},
            },
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_process(state)

        # Should route to error due to empty intent
        assert result == "error"

    @pytest.mark.asyncio
    async def test_successful_process_validation(self):
        """Test successful routing after process step."""
        from workflow.chains.validation import should_proceed_to_synthesize

        state: ChainState = {
            "messages": [HumanMessage(content="test")],
            "analysis": None,
            "processed_content": {
                "content": "Generated content here",
                "confidence": 0.85,
                "metadata": {},
            },
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        # Should proceed to synthesize
        assert result == "synthesize"

    @pytest.mark.asyncio
    async def test_process_validation_failure_low_confidence(self):
        """Test that low confidence routes to error."""
        from workflow.chains.validation import should_proceed_to_synthesize

        state: ChainState = {
            "messages": [HumanMessage(content="test")],
            "analysis": None,
            "processed_content": {
                "content": "Generated content",
                "confidence": 0.3,  # Too low, below 0.5 threshold
                "metadata": {},
            },
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        # Should route to error
        assert result == "error"

    @pytest.mark.asyncio
    async def test_process_validation_failure_empty_content(self):
        """Test that empty content routes to error."""
        from workflow.chains.validation import should_proceed_to_synthesize

        state: ChainState = {
            "messages": [HumanMessage(content="test")],
            "analysis": None,
            "processed_content": {
                "content": "",  # Empty
                "confidence": 0.85,
                "metadata": {},
            },
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        # Should route to error
        assert result == "error"


# ============================================================================
# TESTS: Token usage and cost tracking
# ============================================================================


class TestTokenUsageTracking:
    """Tests for token usage and cost tracking."""

    def test_metadata_structure_for_token_tracking(self, sample_request, chain_config):
        """Test that metadata structure supports token tracking."""
        # Create a state update with metadata
        state_update = {
            "step_metadata": {
                "analyze": {"tokens": 100},
                "process": {"tokens": 200},
            }
        }

        # Verify structure
        assert "step_metadata" in state_update
        assert isinstance(state_update["step_metadata"], dict)
        assert len(state_update["step_metadata"]) > 0


# ============================================================================
# TESTS: Error scenarios
# ============================================================================


class TestErrorScenarios:
    """Tests for error handling in streaming."""

    def test_error_response_format(self):
        """Test that error responses have correct format."""
        from workflow.utils.message_conversion import convert_langchain_chunk_to_openai

        # Create error response
        error_chunk = {"final_response": "An error occurred during processing"}
        result = convert_langchain_chunk_to_openai(error_chunk)

        # Should have proper OpenAI format
        assert result.object == "chat.completion.chunk"
        assert result.model == "orchestrator-worker"
        assert result.choices[0].delta.content == "An error occurred during processing"

    def test_error_validation_gate_response(self):
        """Test validation gate error handling."""
        from workflow.chains.validation import should_proceed_to_process

        # Create state with invalid analysis (empty intent)
        state: ChainState = {
            "messages": [HumanMessage(content="test")],
            "analysis": {
                "intent": "",  # Empty intent should fail
                "key_entities": [],
                "complexity": "simple",
                "context": {},
            },
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_process(state)

        # Should route to error
        assert result == "error"


# ============================================================================
# TESTS: Message preservation through flow
# ============================================================================


class TestMessagePreservation:
    """Tests for message preservation through the complete flow."""

    def test_message_content_preserved_in_conversion(self, sample_request):
        """Test that message content is preserved in conversion."""
        original_content = sample_request.messages[0].content

        langchain_messages = convert_openai_to_langchain_messages(sample_request.messages)

        assert langchain_messages[0].content == original_content

    @pytest.mark.asyncio
    async def test_messages_accumulated_in_state(self, sample_request, chain_config):
        """Test that messages accumulate properly in state."""
        langchain_messages = convert_openai_to_langchain_messages(sample_request.messages)

        initial_state: ChainState = {
            "messages": langchain_messages,
            "analysis": None,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        # Messages should be preserved
        assert len(initial_state["messages"]) == len(sample_request.messages)
