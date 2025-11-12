"""
Comprehensive unit and integration tests for prompt-chaining step functions.

This test module covers the three core step functions from workflow.chains.steps:
- analyze_step: Parses user intent and extracts key information
- process_step: Generates content based on analysis results
- synthesize_step: Polishes and formats the final response (streaming)

Tests include happy paths, edge cases, error conditions, JSON parsing variations,
token tracking, state preservation, and full chain integration.

Target: >80% code coverage for all three step functions.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import ValidationError

from workflow.chains.steps import analyze_step, load_system_prompt, process_step, synthesize_step
from workflow.models.chains import (
    ChainConfig,
    ChainState,
    ChainStepConfig,
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_mock_ai_message(
    content: str, input_tokens: int = 50, output_tokens: int = 100
) -> AIMessage:
    """Create a mock AIMessage with proper usage_metadata."""
    return AIMessage(
        content=content,
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


def create_mock_ai_message_chunk(
    content: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> AIMessageChunk:
    """Create a mock AIMessageChunk with optional usage_metadata."""
    if input_tokens is not None and output_tokens is not None:
        return AIMessageChunk(
            content=content,
            usage_metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        )
    return AIMessageChunk(content=content)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_chain_config():
    """Create ChainConfig with reasonable defaults for testing."""
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
def sample_chain_state():
    """Create minimal valid ChainState for testing."""
    state: ChainState = {
        "messages": [HumanMessage(content="What is machine learning?")],
        "analysis": None,
        "processed_content": None,
        "final_response": None,
        "step_metadata": {},
    }
    return state


@pytest.fixture
def sample_analysis_output():
    """Create valid AnalysisOutput for testing."""
    return {
        "intent": "Learn about machine learning",
        "key_entities": ["machine learning", "AI", "algorithms"],
        "complexity": "moderate",
        "context": {"domain": "AI", "level": "introductory"},
    }


@pytest.fixture
def sample_process_output():
    """Create valid ProcessOutput for testing."""
    return {
        "content": "Machine learning is a subset of AI that enables systems to learn from data.",
        "confidence": 0.85,
        "metadata": {"source_type": "definition", "length": "short"},
    }


@pytest.fixture
def sample_synthesis_output():
    """Create valid SynthesisOutput for testing."""
    return {
        "final_text": "Machine learning is a powerful technology that enables computers to learn patterns from data without explicit programming.",
        "formatting": "markdown",
    }


# ============================================================================
# LOAD_SYSTEM_PROMPT TESTS
# ============================================================================


class TestLoadSystemPrompt:
    """Test suite for load_system_prompt helper function."""

    def test_load_system_prompt_success(self):
        """Test loading a system prompt file that exists."""
        prompt = load_system_prompt("chain_analyze.md")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_load_system_prompt_nonexistent_file(self):
        """Test that loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_system_prompt("nonexistent_prompt.md")

    def test_load_system_prompt_returns_string(self):
        """Test that load_system_prompt returns a string."""
        prompt = load_system_prompt("chain_analyze.md")
        assert isinstance(prompt, str)

    def test_load_system_prompt_analyze(self):
        """Test loading the analyze system prompt."""
        prompt = load_system_prompt("chain_analyze.md")
        assert len(prompt) > 0

    def test_load_system_prompt_process(self):
        """Test loading the process system prompt."""
        prompt = load_system_prompt("chain_process.md")
        assert len(prompt) > 0

    def test_load_system_prompt_synthesize(self):
        """Test loading the synthesize system prompt."""
        prompt = load_system_prompt("chain_synthesize.md")
        assert len(prompt) > 0


# ============================================================================
# ANALYZE_STEP TESTS
# ============================================================================


class TestAnalyzeStep:
    """Test suite for analyze_step function."""

    @pytest.mark.asyncio
    async def test_analyze_step_happy_path(self, sample_chain_state, sample_chain_config):
        """Test analyze_step with valid input and LLM response."""
        valid_json = json.dumps(
            {
                "intent": "test intent",
                "key_entities": ["entity1", "entity2"],
                "complexity": "simple",
                "context": {},
            }
        )

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.ainvoke = AsyncMock(return_value=create_mock_ai_message(valid_json, 50, 100))
            mock_chat.return_value = mock_llm

            result = await analyze_step(sample_chain_state, sample_chain_config)

            assert "analysis" in result
            assert "messages" in result
            assert "step_metadata" in result
            assert result["analysis"]["intent"] == "test intent"
            assert result["analysis"]["key_entities"] == ["entity1", "entity2"]
            assert len(result["messages"]) == 1

    @pytest.mark.asyncio
    async def test_analyze_step_json_in_markdown(self, sample_chain_state, sample_chain_config):
        """Test analyze_step handles JSON wrapped in markdown code blocks."""
        valid_json = json.dumps(
            {
                "intent": "markdown test",
                "key_entities": ["entity"],
                "complexity": "moderate",
                "context": {"test": "value"},
            }
        )
        markdown_response = f"```json\n{valid_json}\n```"

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.ainvoke = AsyncMock(
                return_value=create_mock_ai_message(markdown_response, 50, 100)
            )
            mock_chat.return_value = mock_llm

            result = await analyze_step(sample_chain_state, sample_chain_config)

            assert result["analysis"]["intent"] == "markdown test"
            assert result["analysis"]["context"]["test"] == "value"

    @pytest.mark.asyncio
    async def test_analyze_step_missing_messages(self, sample_chain_config):
        """Test analyze_step raises ValueError when state has no messages."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        with pytest.raises(ValueError, match="No messages found in state"):
            await analyze_step(state, sample_chain_config)

    @pytest.mark.asyncio
    async def test_analyze_step_invalid_json(self, sample_chain_state, sample_chain_config):
        """Test analyze_step raises error when LLM response is invalid JSON."""
        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.ainvoke = AsyncMock(
                return_value=create_mock_ai_message("not valid json at all", 50, 100)
            )
            mock_chat.return_value = mock_llm

            with pytest.raises((json.JSONDecodeError, ValueError)):
                await analyze_step(sample_chain_state, sample_chain_config)

    @pytest.mark.asyncio
    async def test_analyze_step_missing_required_field(
        self, sample_chain_state, sample_chain_config
    ):
        """Test analyze_step raises ValidationError when required field is missing."""
        invalid_json = json.dumps(
            {
                "key_entities": ["entity"],
                "complexity": "simple",
                # Missing 'intent' field
            }
        )

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.ainvoke = AsyncMock(return_value=create_mock_ai_message(invalid_json, 50, 100))
            mock_chat.return_value = mock_llm

            with pytest.raises((ValidationError, ValueError)):
                await analyze_step(sample_chain_state, sample_chain_config)

    @pytest.mark.asyncio
    async def test_analyze_step_token_tracking(self, sample_chain_state, sample_chain_config):
        """Test analyze_step correctly tracks tokens and cost."""
        valid_json = json.dumps(
            {
                "intent": "test",
                "key_entities": ["entity"],
                "complexity": "simple",
                "context": {},
            }
        )

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.ainvoke = AsyncMock(return_value=create_mock_ai_message(valid_json, 100, 200))
            mock_chat.return_value = mock_llm

            result = await analyze_step(sample_chain_state, sample_chain_config)

            metadata = result["step_metadata"]["analyze"]
            assert metadata["input_tokens"] == 100
            assert metadata["output_tokens"] == 200
            assert metadata["total_tokens"] == 300
            assert "cost_usd" in metadata
            assert metadata["cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_analyze_step_message_accumulation(self, sample_chain_state, sample_chain_config):
        """Test analyze_step appends response to messages using add_messages."""
        valid_json = json.dumps(
            {
                "intent": "test",
                "key_entities": ["entity"],
                "complexity": "simple",
                "context": {},
            }
        )

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            response_msg = create_mock_ai_message(valid_json, 50, 100)
            mock_llm.ainvoke = AsyncMock(return_value=response_msg)
            mock_chat.return_value = mock_llm

            result = await analyze_step(sample_chain_state, sample_chain_config)

            # Should append the response message
            assert len(result["messages"]) == 1
            assert isinstance(result["messages"][0], AIMessage)

    @pytest.mark.asyncio
    async def test_analyze_step_missing_usage_metadata(
        self, sample_chain_state, sample_chain_config
    ):
        """Test analyze_step handles response without usage_metadata gracefully."""
        valid_json = json.dumps(
            {
                "intent": "test",
                "key_entities": ["entity"],
                "complexity": "simple",
                "context": {},
            }
        )

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            # Create a basic message without usage_metadata
            response = AIMessage(content=valid_json)
            mock_llm.ainvoke = AsyncMock(return_value=response)
            mock_chat.return_value = mock_llm

            result = await analyze_step(sample_chain_state, sample_chain_config)

            metadata = result["step_metadata"]["analyze"]
            # Should default to 0 tokens
            assert metadata["input_tokens"] == 0
            assert metadata["output_tokens"] == 0


# ============================================================================
# PROCESS_STEP TESTS
# ============================================================================


class TestProcessStep:
    """Test suite for process_step function."""

    @pytest.mark.asyncio
    async def test_process_step_happy_path(
        self, sample_chain_state, sample_chain_config, sample_analysis_output
    ):
        """Test process_step with valid analysis and process output."""
        sample_chain_state["analysis"] = sample_analysis_output

        valid_json = json.dumps(
            {
                "content": "Generated content here",
                "confidence": 0.8,
                "metadata": {"key": "value"},
            }
        )

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.ainvoke = AsyncMock(return_value=create_mock_ai_message(valid_json, 100, 150))
            mock_chat.return_value = mock_llm

            result = await process_step(sample_chain_state, sample_chain_config)

            assert "processed_content" in result
            assert "messages" in result
            assert "step_metadata" in result
            assert result["processed_content"]["content"] == "Generated content here"
            assert result["processed_content"]["confidence"] == 0.8

    @pytest.mark.asyncio
    async def test_process_step_missing_analysis(self, sample_chain_state, sample_chain_config):
        """Test process_step raises ValueError when analysis is missing from state."""
        with pytest.raises(ValueError, match="Analysis not found in state"):
            await process_step(sample_chain_state, sample_chain_config)

    @pytest.mark.asyncio
    async def test_process_step_confidence_score(
        self, sample_chain_state, sample_chain_config, sample_analysis_output
    ):
        """Test process_step extracts and logs confidence score."""
        sample_chain_state["analysis"] = sample_analysis_output

        valid_json = json.dumps(
            {
                "content": "Content",
                "confidence": 0.65,
                "metadata": {},
            }
        )

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.ainvoke = AsyncMock(return_value=create_mock_ai_message(valid_json, 100, 150))
            mock_chat.return_value = mock_llm

            result = await process_step(sample_chain_state, sample_chain_config)

            metadata = result["step_metadata"]["process"]
            assert metadata["confidence"] == 0.65

    @pytest.mark.asyncio
    async def test_process_step_token_tracking(
        self, sample_chain_state, sample_chain_config, sample_analysis_output
    ):
        """Test process_step correctly tracks tokens and cost."""
        sample_chain_state["analysis"] = sample_analysis_output

        valid_json = json.dumps(
            {
                "content": "Content",
                "confidence": 0.8,
                "metadata": {},
            }
        )

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.ainvoke = AsyncMock(return_value=create_mock_ai_message(valid_json, 200, 300))
            mock_chat.return_value = mock_llm

            result = await process_step(sample_chain_state, sample_chain_config)

            metadata = result["step_metadata"]["process"]
            assert metadata["input_tokens"] == 200
            assert metadata["output_tokens"] == 300
            assert metadata["total_tokens"] == 500
            assert "cost_usd" in metadata


# ============================================================================
# SYNTHESIZE_STEP TESTS
# ============================================================================


class TestSynthesizeStep:
    """Test suite for synthesize_step function (streaming)."""

    @pytest.mark.asyncio
    async def test_synthesize_step_happy_path_streaming(
        self, sample_chain_state, sample_chain_config, sample_process_output
    ):
        """Test synthesize_step with valid streaming response."""
        sample_chain_state["processed_content"] = sample_process_output

        async def mock_stream():
            yield create_mock_ai_message_chunk('{"fi')
            yield create_mock_ai_message_chunk('nal_text": "Final polished response"')
            yield create_mock_ai_message_chunk('", "formatting": "markdown"}', 100, 200)

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.astream = AsyncMock(return_value=mock_stream())
            mock_chat.return_value = mock_llm

            result_list = []
            async for chunk in synthesize_step(sample_chain_state, sample_chain_config):
                result_list.append(chunk)

            # Should have at least 3 yields (3 chunks)
            assert len(result_list) >= 3

            # Final result should have the complete synthesis
            final_result = result_list[-1]
            assert "final_response" in final_result
            assert "step_metadata" in final_result
            assert "Final polished response" in final_result["final_response"]

    @pytest.mark.asyncio
    async def test_synthesize_step_missing_processed_content(
        self, sample_chain_state, sample_chain_config
    ):
        """Test synthesize_step raises ValueError when processed_content is missing."""
        with pytest.raises(ValueError, match="Processed content not found in state"):
            async for _ in synthesize_step(sample_chain_state, sample_chain_config):
                pass

    @pytest.mark.asyncio
    async def test_synthesize_step_multiple_chunks(
        self, sample_chain_state, sample_chain_config, sample_process_output
    ):
        """Test synthesize_step correctly yields multiple chunks."""
        sample_chain_state["processed_content"] = sample_process_output

        async def mock_stream():
            chunks = [
                '{"fi',
                'nal_text": "Response',
                " part one. Response",
                " part two. Response part three.",
                '", "formatting": "markdown"}',
            ]
            for i, chunk_text in enumerate(chunks):
                if i == len(chunks) - 1:
                    yield create_mock_ai_message_chunk(chunk_text, 100, 200)
                else:
                    yield create_mock_ai_message_chunk(chunk_text)

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.astream = AsyncMock(return_value=mock_stream())
            mock_chat.return_value = mock_llm

            result_list = []
            async for chunk in synthesize_step(sample_chain_state, sample_chain_config):
                result_list.append(chunk)

            # Should have at least 5 yields
            assert len(result_list) >= 5

            # Each yield should have final_response updated
            for i, result in enumerate(result_list):
                assert "final_response" in result
                # Each accumulation should be at least as long as the one before it (with some buffer for final parsing)
                if (
                    i > 0 and i < len(result_list) - 1
                ):  # Skip last one since it might be parsed differently
                    assert len(result["final_response"]) >= len(
                        result_list[i - 1]["final_response"]
                    )

    @pytest.mark.asyncio
    async def test_synthesize_step_graceful_fallback_invalid_json(
        self, sample_chain_state, sample_chain_config, sample_process_output
    ):
        """Test synthesize_step falls back gracefully when final JSON is invalid."""
        sample_chain_state["processed_content"] = sample_process_output

        async def mock_stream():
            yield create_mock_ai_message_chunk("This is not valid JSON at all")
            yield create_mock_ai_message_chunk(" but it has content", 100, 200)

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.astream = AsyncMock(return_value=mock_stream())
            mock_chat.return_value = mock_llm

            result_list = []
            async for chunk in synthesize_step(sample_chain_state, sample_chain_config):
                result_list.append(chunk)

            final_result = result_list[-1]
            # Should use accumulated text as fallback
            assert (
                "This is not valid JSON at all but it has content" in final_result["final_response"]
            )

    @pytest.mark.asyncio
    async def test_synthesize_step_dict_processed_content(
        self, sample_chain_state, sample_chain_config
    ):
        """Test synthesize_step handles processed_content as dict."""
        sample_chain_state["processed_content"] = {
            "content": "Generated content",
            "confidence": 0.8,
            "metadata": {"key": "value"},
        }

        async def mock_stream():
            yield create_mock_ai_message_chunk('{"fi')
            yield create_mock_ai_message_chunk('nal_text": "Final"')
            yield create_mock_ai_message_chunk('", "formatting": "markdown"}', 100, 200)

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.astream = AsyncMock(return_value=mock_stream())
            mock_chat.return_value = mock_llm

            result_list = []
            async for chunk in synthesize_step(sample_chain_state, sample_chain_config):
                result_list.append(chunk)

            # Should work without error
            assert len(result_list) > 0


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestChainStepsIntegration:
    """Integration tests for the full prompt-chaining workflow."""

    @pytest.mark.asyncio
    async def test_cost_aggregation(self, sample_chain_state, sample_chain_config):
        """Test that costs are correctly calculated across steps."""
        # Analyze with specific token counts
        analysis_json = json.dumps(
            {
                "intent": "Test",
                "key_entities": ["test"],
                "complexity": "simple",
                "context": {},
            }
        )

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.ainvoke = AsyncMock(
                return_value=create_mock_ai_message(analysis_json, 100, 200)
            )
            mock_chat.return_value = mock_llm

            analyze_result = await analyze_step(sample_chain_state, sample_chain_config)

        analyze_cost = analyze_result["step_metadata"]["analyze"]["cost_usd"]
        assert analyze_cost > 0

        # Process with different token counts
        sample_chain_state["analysis"] = analyze_result["analysis"]
        process_json = json.dumps(
            {
                "content": "Content",
                "confidence": 0.8,
                "metadata": {},
            }
        )

        with patch("workflow.chains.steps.ChatAnthropic") as mock_chat:
            mock_llm = AsyncMock()
            mock_llm.ainvoke = AsyncMock(
                return_value=create_mock_ai_message(process_json, 200, 400)
            )
            mock_chat.return_value = mock_llm

            process_result = await process_step(sample_chain_state, sample_chain_config)

        process_cost = process_result["step_metadata"]["process"]["cost_usd"]
        assert process_cost > 0
        # Process cost should be higher due to more tokens
        assert process_cost > analyze_cost
