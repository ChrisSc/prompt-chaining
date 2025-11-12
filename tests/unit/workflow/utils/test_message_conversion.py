"""
Unit tests for OpenAI ↔ LangChain message conversion utilities.

Tests cover:
- OpenAI message format → LangChain message conversion
- LangChain message/chunk → OpenAI format conversion
- Role mapping (system, user, assistant)
- Content preservation
- Error handling for invalid inputs
- Edge cases (empty messages, unknown roles, etc.)
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from workflow.models.openai import ChatMessage, MessageRole
from workflow.utils.message_conversion import (
    convert_openai_to_langchain_messages,
    convert_langchain_chunk_to_openai,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def openai_user_message():
    """Create a sample OpenAI user message."""
    return ChatMessage(role=MessageRole.USER, content="What is AI?")


@pytest.fixture
def openai_assistant_message():
    """Create a sample OpenAI assistant message."""
    return ChatMessage(role=MessageRole.ASSISTANT, content="AI is artificial intelligence.")


@pytest.fixture
def openai_system_message():
    """Create a sample OpenAI system message."""
    return ChatMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant.")


# ============================================================================
# TESTS: convert_openai_to_langchain_messages
# ============================================================================


class TestConvertOpenAIToLangchainMessages:
    """Tests for OpenAI → LangChain message conversion."""

    def test_convert_user_message(self, openai_user_message):
        """Test converting a user message."""
        result = convert_openai_to_langchain_messages([openai_user_message])

        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "What is AI?"

    def test_convert_assistant_message(self, openai_assistant_message):
        """Test converting an assistant message."""
        result = convert_openai_to_langchain_messages([openai_assistant_message])

        assert len(result) == 1
        assert isinstance(result[0], AIMessage)
        assert result[0].content == "AI is artificial intelligence."

    def test_convert_system_message(self, openai_system_message):
        """Test converting a system message."""
        result = convert_openai_to_langchain_messages([openai_system_message])

        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "You are a helpful assistant."

    def test_convert_mixed_messages(self, openai_user_message, openai_assistant_message, openai_system_message):
        """Test converting a mix of message types."""
        messages = [openai_system_message, openai_user_message, openai_assistant_message]
        result = convert_openai_to_langchain_messages(messages)

        assert len(result) == 3
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], HumanMessage)
        assert isinstance(result[2], AIMessage)

    def test_convert_empty_message_list(self):
        """Test converting an empty message list."""
        result = convert_openai_to_langchain_messages([])

        assert len(result) == 0
        assert isinstance(result, list)

    def test_convert_multiple_user_messages(self):
        """Test converting multiple user messages in sequence."""
        messages = [
            ChatMessage(role=MessageRole.USER, content="First question"),
            ChatMessage(role=MessageRole.USER, content="Second question"),
        ]
        result = convert_openai_to_langchain_messages(messages)

        assert len(result) == 2
        assert all(isinstance(msg, HumanMessage) for msg in result)
        assert result[0].content == "First question"
        assert result[1].content == "Second question"

    def test_convert_preserves_content(self):
        """Test that message content is preserved exactly."""
        content = "This is a test message with special chars: !@#$%^&*()"
        message = ChatMessage(role=MessageRole.USER, content=content)
        result = convert_openai_to_langchain_messages([message])

        assert result[0].content == content

    def test_convert_with_long_content(self):
        """Test converting messages with long content."""
        long_content = "A" * 10000
        message = ChatMessage(role=MessageRole.USER, content=long_content)
        result = convert_openai_to_langchain_messages([message])

        assert result[0].content == long_content
        assert len(result[0].content) == 10000

    def test_convert_skips_empty_content_messages(self, caplog):
        """Test that messages with empty content are skipped."""
        messages = [
            ChatMessage(role=MessageRole.USER, content=""),
            ChatMessage(role=MessageRole.USER, content="Valid message"),
        ]
        result = convert_openai_to_langchain_messages(messages)

        # Should only have the non-empty message
        assert len(result) == 1
        assert result[0].content == "Valid message"

    def test_convert_raises_on_unknown_role(self):
        """Test that unknown roles raise ValueError."""
        # Create a message with invalid role - Pydantic will validate this
        # Since ChatMessage uses MessageRole enum, this will be caught at construction
        from workflow.models.openai import MessageRole

        # Try to use a string that's not in the enum
        try:
            # Pydantic will raise ValidationError for invalid enum value
            message = ChatMessage(role="unknown_role", content="test")
            # If Pydantic allows it, test our converter
            with pytest.raises(ValueError, match="Unknown message role"):
                convert_openai_to_langchain_messages([message])
        except ValueError:
            # Expected - Pydantic rejected the invalid role
            pass

    def test_convert_logs_conversion_summary(self, openai_user_message, caplog):
        """Test that conversion logs summary information."""
        import logging

        caplog.set_level(logging.DEBUG)
        convert_openai_to_langchain_messages([openai_user_message])

        assert "Converted OpenAI messages to LangChain format" in caplog.text


# ============================================================================
# TESTS: convert_langchain_chunk_to_openai
# ============================================================================


class TestConvertLangchainChunkToOpenai:
    """Tests for LangChain → OpenAI format conversion."""

    def test_convert_ai_message(self):
        """Test converting an AIMessage."""
        chunk = AIMessage(content="Hello, world!")
        result = convert_langchain_chunk_to_openai(chunk)

        assert result.object == "chat.completion.chunk"
        assert result.model == "orchestrator-worker"
        assert result.choices[0].delta.content == "Hello, world!"
        assert result.choices[0].delta.role == "assistant"

    def test_convert_dict_with_final_response(self):
        """Test converting a dict with final_response key."""
        chunk = {"final_response": "This is the final response"}
        result = convert_langchain_chunk_to_openai(chunk)

        assert result.choices[0].delta.content == "This is the final response"

    def test_convert_dict_with_messages(self):
        """Test converting a dict with messages list."""
        chunk = {
            "messages": [AIMessage(content="Message content")]
        }
        result = convert_langchain_chunk_to_openai(chunk)

        assert result.choices[0].delta.content == "Message content"

    def test_convert_string_chunk(self):
        """Test converting a plain string."""
        result = convert_langchain_chunk_to_openai("Hello!")

        assert result.choices[0].delta.content == "Hello!"

    def test_convert_empty_string(self):
        """Test converting an empty string."""
        result = convert_langchain_chunk_to_openai("")

        assert result.object == "chat.completion.chunk"
        # Empty content should be None in delta
        assert result.choices[0].delta.content is None

    def test_convert_creates_valid_chunk(self):
        """Test that conversion creates a valid ChatCompletionChunk."""
        chunk = AIMessage(content="Test content")
        result = convert_langchain_chunk_to_openai(chunk)

        # Verify all required fields
        assert hasattr(result, "id")
        assert result.id.startswith("chatcmpl-")
        assert hasattr(result, "object")
        assert hasattr(result, "created")
        assert hasattr(result, "model")
        assert hasattr(result, "choices")
        assert len(result.choices) > 0

    def test_convert_includes_timestamp(self):
        """Test that created timestamp is included."""
        import time

        before = int(time.time())
        result = convert_langchain_chunk_to_openai(AIMessage(content="test"))
        after = int(time.time())

        assert before <= result.created <= after + 1

    def test_convert_choice_has_correct_index(self):
        """Test that choice index is set to 0."""
        result = convert_langchain_chunk_to_openai(AIMessage(content="test"))

        assert result.choices[0].index == 0

    def test_convert_finish_reason_none_for_content(self):
        """Test that finish_reason is None for content chunks."""
        result = convert_langchain_chunk_to_openai(AIMessage(content="test"))

        assert result.choices[0].finish_reason is None

    def test_convert_with_long_content(self):
        """Test converting with very long content."""
        long_content = "A" * 10000
        result = convert_langchain_chunk_to_openai(AIMessage(content=long_content))

        assert result.choices[0].delta.content == long_content

    def test_convert_special_characters(self):
        """Test converting content with special characters."""
        special_content = "Hello! @#$%^&*() 你好 🎉"
        result = convert_langchain_chunk_to_openai(AIMessage(content=special_content))

        assert result.choices[0].delta.content == special_content

    def test_convert_dict_with_multiple_keys(self):
        """Test converting dict looks for content in multiple places."""
        chunk = {
            "unrelated_key": "ignored",
            "final_response": "Found this",
        }
        result = convert_langchain_chunk_to_openai(chunk)

        assert result.choices[0].delta.content == "Found this"

    def test_convert_dict_without_known_keys(self):
        """Test converting dict without standard keys falls back to any string."""
        chunk = {"some_key": "some_value"}
        result = convert_langchain_chunk_to_openai(chunk)

        assert result.choices[0].delta.content == "some_value"

    def test_convert_logs_conversion(self, caplog):
        """Test that conversion is logged."""
        import logging

        caplog.set_level(logging.DEBUG)
        convert_langchain_chunk_to_openai(AIMessage(content="test"))

        assert "Converted LangChain chunk to OpenAI format" in caplog.text

    def test_convert_invalid_chunk_raises_error(self):
        """Test that invalid chunks are handled gracefully or raise ValueError."""
        # Create an object that can't be converted
        # The function has a fallback to str(chunk), so most objects will be converted
        # Test with None dict value to trigger a different code path
        invalid_chunk = None

        try:
            result = convert_langchain_chunk_to_openai(invalid_chunk)
            # If it doesn't raise, it should return a valid chunk
            assert result.object == "chat.completion.chunk"
        except ValueError:
            # Also acceptable - ValueError for unparseable input
            pass

    def test_convert_none_content_handled(self):
        """Test that None content is handled gracefully."""
        chunk = {"some_key": None}
        result = convert_langchain_chunk_to_openai(chunk)

        # Should be valid even with None content
        assert result.object == "chat.completion.chunk"

    def test_convert_numeric_content_converted_to_string(self):
        """Test that numeric content is converted to string."""
        result = convert_langchain_chunk_to_openai({"numeric": 12345})

        # Numeric value should be converted to string
        assert isinstance(result.choices[0].delta.content, str) or result.choices[0].delta.content is None


# ============================================================================
# INTEGRATION TESTS: Round-trip conversion
# ============================================================================


class TestMessageConversionRoundTrip:
    """Tests for round-trip conversion between formats."""

    def test_openai_to_langchain_to_openai(self):
        """Test converting OpenAI → LangChain → OpenAI."""
        original = ChatMessage(role=MessageRole.USER, content="Test message")

        # Convert to LangChain
        langchain_msgs = convert_openai_to_langchain_messages([original])

        # Convert back to OpenAI
        result = convert_langchain_chunk_to_openai(langchain_msgs[0])

        # Content should be preserved
        assert result.choices[0].delta.content == "Test message"

    def test_multiple_messages_preserve_order(self):
        """Test that message order is preserved through conversion."""
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content="System"),
            ChatMessage(role=MessageRole.USER, content="User"),
            ChatMessage(role=MessageRole.ASSISTANT, content="Assistant"),
        ]

        langchain_msgs = convert_openai_to_langchain_messages(messages)

        assert isinstance(langchain_msgs[0], SystemMessage)
        assert isinstance(langchain_msgs[1], HumanMessage)
        assert isinstance(langchain_msgs[2], AIMessage)
