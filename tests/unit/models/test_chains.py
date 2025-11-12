"""
Comprehensive unit tests for prompt-chaining workflow models.

Tests all 6 models in workflow.models.chains:
- ChainState (TypedDict)
- AnalysisOutput (Pydantic)
- ProcessOutput (Pydantic)
- SynthesisOutput (Pydantic)
- ChainStepConfig (Pydantic)
- ChainConfig (Pydantic)

Covers happy path, edge cases, validation constraints, and serialization.
Target: >95% code coverage.
"""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from workflow.models.chains import (
    AnalysisOutput,
    ChainConfig,
    ChainState,
    ChainStepConfig,
    ProcessOutput,
    SynthesisOutput,
)


# ============================================================================
# CHAINSTATE TYPEDDICT TESTS
# ============================================================================


class TestChainState:
    """Test suite for ChainState TypedDict."""

    def test_chainstate_instantiation_full(self):
        """Test ChainState instantiation with all fields populated."""
        state: ChainState = {
            "messages": [
                HumanMessage("Hello"),
                AIMessage("Hi there"),
            ],
            "analysis": {
                "intent": "greeting",
                "entities": ["greeting"],
            },
            "processed_content": "Generated response content",
            "final_response": "Final polished response",
            "step_metadata": {
                "analyze_time": 1.5,
                "process_time": 2.0,
                "synthesize_time": 1.0,
            },
        }

        assert len(state["messages"]) == 2
        assert isinstance(state["messages"][0], HumanMessage)
        assert isinstance(state["messages"][1], AIMessage)
        assert state["analysis"]["intent"] == "greeting"
        assert state["processed_content"] == "Generated response content"
        assert state["final_response"] == "Final polished response"
        assert state["step_metadata"]["analyze_time"] == 1.5

    def test_chainstate_with_none_values(self):
        """Test ChainState with None values for optional fields."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        assert state["analysis"] is None
        assert state["processed_content"] is None
        assert state["final_response"] is None
        assert state["step_metadata"] == {}

    def test_chainstate_messages_accumulation(self):
        """Test that messages field properly accumulates messages."""
        messages = [
            HumanMessage("First message"),
            AIMessage("First response"),
            HumanMessage("Second message"),
            AIMessage("Second response"),
        ]

        state: ChainState = {
            "messages": messages,
            "analysis": None,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        assert len(state["messages"]) == 4
        assert state["messages"][0].content == "First message"
        assert state["messages"][3].content == "Second response"

    def test_chainstate_messages_type_validation(self):
        """Test that messages field contains BaseMessage instances."""
        state: ChainState = {
            "messages": [
                HumanMessage("Test"),
                AIMessage("Response"),
            ],
            "analysis": None,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        # All items should be BaseMessage instances
        for msg in state["messages"]:
            assert hasattr(msg, "content")
            assert isinstance(msg.content, str)

    def test_chainstate_step_metadata_operations(self):
        """Test step_metadata dictionary operations."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {
                "step1": {"duration": 1.5, "tokens": 100},
                "step2": {"duration": 2.0, "tokens": 200},
            },
        }

        assert "step1" in state["step_metadata"]
        assert state["step_metadata"]["step1"]["duration"] == 1.5
        assert state["step_metadata"]["step2"]["tokens"] == 200
        assert len(state["step_metadata"]) == 2

    def test_chainstate_empty_messages_list(self):
        """Test ChainState with empty messages list."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        assert isinstance(state["messages"], list)
        assert len(state["messages"]) == 0

    def test_chainstate_complex_analysis_data(self):
        """Test ChainState with complex nested analysis data."""
        state: ChainState = {
            "messages": [],
            "analysis": {
                "intent": "data_analysis",
                "entities": ["dataset", "metrics", "visualization"],
                "complexity": "high",
                "sub_intent": {
                    "primary": "summarize",
                    "secondary": ["filter", "sort"],
                },
            },
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        assert state["analysis"]["entities"] == ["dataset", "metrics", "visualization"]
        assert state["analysis"]["sub_intent"]["primary"] == "summarize"


# ============================================================================
# ANALYSISOUTPUT PYDANTIC MODEL TESTS
# ============================================================================


class TestAnalysisOutput:
    """Test suite for AnalysisOutput Pydantic model."""

    def test_analysisoutput_valid_instantiation(self):
        """Test valid AnalysisOutput creation with all fields."""
        output = AnalysisOutput(
            intent="extract_summary",
            key_entities=["document", "summary", "key_points"],
            complexity="moderate",
            context={"source_type": "document", "language": "en"},
        )

        assert output.intent == "extract_summary"
        assert output.key_entities == ["document", "summary", "key_points"]
        assert output.complexity == "moderate"
        assert output.context["source_type"] == "document"

    def test_analysisoutput_minimal_instantiation(self):
        """Test AnalysisOutput with required fields only (context defaults)."""
        output = AnalysisOutput(
            intent="simple_task",
            key_entities=["task"],
            complexity="simple",
        )

        assert output.intent == "simple_task"
        assert output.key_entities == ["task"]
        assert output.complexity == "simple"
        assert output.context == {}

    def test_analysisoutput_context_default(self):
        """Test that context defaults to empty dict."""
        output = AnalysisOutput(
            intent="test",
            key_entities=["entity"],
            complexity="simple",
        )

        assert isinstance(output.context, dict)
        assert len(output.context) == 0

    def test_analysisoutput_key_entities_list_validation(self):
        """Test key_entities accepts list of strings."""
        output = AnalysisOutput(
            intent="test",
            key_entities=["entity1", "entity2", "entity3"],
            complexity="moderate",
        )

        assert isinstance(output.key_entities, list)
        assert all(isinstance(e, str) for e in output.key_entities)
        assert len(output.key_entities) == 3

    def test_analysisoutput_empty_key_entities(self):
        """Test AnalysisOutput with empty key_entities list."""
        output = AnalysisOutput(
            intent="minimal",
            key_entities=[],
            complexity="simple",
        )

        assert output.key_entities == []

    def test_analysisoutput_complexity_values(self):
        """Test different complexity values."""
        for complexity in ["simple", "moderate", "complex"]:
            output = AnalysisOutput(
                intent="test",
                key_entities=["entity"],
                complexity=complexity,
            )
            assert output.complexity == complexity

    def test_analysisoutput_invalid_intent_type(self):
        """Test that invalid intent type raises ValidationError."""
        with pytest.raises(ValidationError):
            AnalysisOutput(
                intent=123,  # Should be string
                key_entities=["entity"],
                complexity="simple",
            )

    def test_analysisoutput_invalid_key_entities_type(self):
        """Test that non-list key_entities raises ValidationError."""
        with pytest.raises(ValidationError):
            AnalysisOutput(
                intent="test",
                key_entities="not_a_list",  # Should be list
                complexity="simple",
            )

    def test_analysisoutput_invalid_entity_type(self):
        """Test that non-string entity in key_entities raises ValidationError."""
        with pytest.raises(ValidationError):
            AnalysisOutput(
                intent="test",
                key_entities=["entity1", 123, "entity2"],  # 123 should be string
                complexity="simple",
            )

    def test_analysisoutput_serialization_dump(self):
        """Test AnalysisOutput model_dump serialization."""
        output = AnalysisOutput(
            intent="test_intent",
            key_entities=["entity1", "entity2"],
            complexity="complex",
            context={"key": "value"},
        )

        dumped = output.model_dump()
        assert dumped["intent"] == "test_intent"
        assert dumped["key_entities"] == ["entity1", "entity2"]
        assert dumped["complexity"] == "complex"
        assert dumped["context"]["key"] == "value"

    def test_analysisoutput_json_serialization(self):
        """Test AnalysisOutput model_dump_json serialization."""
        output = AnalysisOutput(
            intent="json_test",
            key_entities=["entity"],
            complexity="moderate",
            context={"test": "data"},
        )

        json_str = output.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["intent"] == "json_test"
        assert parsed["key_entities"] == ["entity"]
        assert parsed["complexity"] == "moderate"
        assert parsed["context"]["test"] == "data"

    def test_analysisoutput_deserialization(self):
        """Test creating AnalysisOutput from dict."""
        data = {
            "intent": "from_dict",
            "key_entities": ["e1", "e2"],
            "complexity": "simple",
            "context": {"source": "test"},
        }

        output = AnalysisOutput(**data)
        assert output.intent == "from_dict"
        assert output.key_entities == ["e1", "e2"]

    def test_analysisoutput_long_entity_list(self):
        """Test AnalysisOutput with many key_entities."""
        entities = [f"entity_{i}" for i in range(100)]
        output = AnalysisOutput(
            intent="test",
            key_entities=entities,
            complexity="complex",
        )

        assert len(output.key_entities) == 100
        assert output.key_entities[0] == "entity_0"
        assert output.key_entities[99] == "entity_99"


# ============================================================================
# PROCESSOUTPUT PYDANTIC MODEL TESTS
# ============================================================================


class TestProcessOutput:
    """Test suite for ProcessOutput Pydantic model."""

    def test_processoutput_valid_instantiation(self):
        """Test valid ProcessOutput creation with all fields."""
        output = ProcessOutput(
            content="Generated content here",
            confidence=0.85,
            metadata={"tokens": 150, "model": "claude-haiku"},
        )

        assert output.content == "Generated content here"
        assert output.confidence == 0.85
        assert output.metadata["tokens"] == 150

    def test_processoutput_minimal_instantiation(self):
        """Test ProcessOutput with required fields only (metadata defaults)."""
        output = ProcessOutput(
            content="Content",
            confidence=0.5,
        )

        assert output.content == "Content"
        assert output.confidence == 0.5
        assert output.metadata == {}

    def test_processoutput_confidence_zero(self):
        """Test ProcessOutput with confidence at minimum boundary (0.0)."""
        output = ProcessOutput(
            content="Content",
            confidence=0.0,
        )

        assert output.confidence == 0.0

    def test_processoutput_confidence_one(self):
        """Test ProcessOutput with confidence at maximum boundary (1.0)."""
        output = ProcessOutput(
            content="Content",
            confidence=1.0,
        )

        assert output.confidence == 1.0

    def test_processoutput_confidence_mid_range(self):
        """Test ProcessOutput with mid-range confidence values."""
        for confidence in [0.25, 0.5, 0.75]:
            output = ProcessOutput(
                content="Content",
                confidence=confidence,
            )
            assert output.confidence == confidence

    def test_processoutput_confidence_below_zero(self):
        """Test that confidence < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ProcessOutput(
                content="Content",
                confidence=-0.1,
            )

    def test_processoutput_confidence_above_one(self):
        """Test that confidence > 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ProcessOutput(
                content="Content",
                confidence=1.1,
            )

    def test_processoutput_confidence_extreme_values(self):
        """Test confidence constraint with various invalid values."""
        invalid_values = [-1.0, -0.5, 1.5, 2.0, 100.0]
        for confidence in invalid_values:
            with pytest.raises(ValidationError):
                ProcessOutput(
                    content="Content",
                    confidence=confidence,
                )

    def test_processoutput_metadata_default(self):
        """Test that metadata defaults to empty dict."""
        output = ProcessOutput(
            content="Content",
            confidence=0.5,
        )

        assert isinstance(output.metadata, dict)
        assert len(output.metadata) == 0

    def test_processoutput_metadata_complex_nested(self):
        """Test ProcessOutput with complex nested metadata."""
        output = ProcessOutput(
            content="Content",
            confidence=0.9,
            metadata={
                "tokens": {"input": 100, "output": 50},
                "timing": {"total": 2.5},
                "sources": ["source1", "source2"],
            },
        )

        assert output.metadata["tokens"]["input"] == 100
        assert output.metadata["timing"]["total"] == 2.5
        assert "source1" in output.metadata["sources"]

    def test_processoutput_invalid_content_type(self):
        """Test that non-string content raises ValidationError."""
        with pytest.raises(ValidationError):
            ProcessOutput(
                content=123,  # Should be string
                confidence=0.5,
            )

    def test_processoutput_confidence_string_coercion(self):
        """Test that string confidence can be coerced to float by Pydantic."""
        # Pydantic v2 coerces "0.5" to float 0.5
        output = ProcessOutput(
            content="Content",
            confidence="0.5",  # Will be coerced to float
        )
        assert output.confidence == 0.5

    def test_processoutput_invalid_confidence_non_numeric_string(self):
        """Test that non-numeric string confidence raises ValidationError."""
        with pytest.raises(ValidationError):
            ProcessOutput(
                content="Content",
                confidence="not_a_number",  # Cannot be coerced to float
            )

    def test_processoutput_empty_content(self):
        """Test ProcessOutput with empty string content."""
        output = ProcessOutput(
            content="",
            confidence=0.5,
        )

        assert output.content == ""

    def test_processoutput_long_content(self):
        """Test ProcessOutput with very long content."""
        long_content = "x" * 10000
        output = ProcessOutput(
            content=long_content,
            confidence=0.8,
        )

        assert len(output.content) == 10000

    def test_processoutput_serialization_dump(self):
        """Test ProcessOutput model_dump serialization."""
        output = ProcessOutput(
            content="Test content",
            confidence=0.75,
            metadata={"key": "value"},
        )

        dumped = output.model_dump()
        assert dumped["content"] == "Test content"
        assert dumped["confidence"] == 0.75
        assert dumped["metadata"]["key"] == "value"

    def test_processoutput_json_serialization(self):
        """Test ProcessOutput model_dump_json serialization."""
        output = ProcessOutput(
            content="JSON test",
            confidence=0.8,
            metadata={"test": "data"},
        )

        json_str = output.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["content"] == "JSON test"
        assert parsed["confidence"] == 0.8
        assert parsed["metadata"]["test"] == "data"

    def test_processoutput_deserialization(self):
        """Test creating ProcessOutput from dict."""
        data = {
            "content": "From dict",
            "confidence": 0.9,
            "metadata": {"source": "dict"},
        }

        output = ProcessOutput(**data)
        assert output.content == "From dict"
        assert output.confidence == 0.9


# ============================================================================
# SYNTHESISOUTPUT PYDANTIC MODEL TESTS
# ============================================================================


class TestSynthesisOutput:
    """Test suite for SynthesisOutput Pydantic model."""

    def test_synthesisoutput_valid_instantiation(self):
        """Test valid SynthesisOutput creation with all fields."""
        output = SynthesisOutput(
            final_text="Polished and formatted final response",
            formatting="markdown",
        )

        assert output.final_text == "Polished and formatted final response"
        assert output.formatting == "markdown"

    def test_synthesisoutput_minimal_instantiation(self):
        """Test SynthesisOutput with required fields."""
        output = SynthesisOutput(
            final_text="Final text",
            formatting="plain",
        )

        assert output.final_text == "Final text"
        assert output.formatting == "plain"

    def test_synthesisoutput_formatting_values(self):
        """Test SynthesisOutput with various formatting values."""
        formatting_styles = ["markdown", "html", "plain", "json", "xml"]
        for style in formatting_styles:
            output = SynthesisOutput(
                final_text="Text",
                formatting=style,
            )
            assert output.formatting == style

    def test_synthesisoutput_invalid_final_text_type(self):
        """Test that non-string final_text raises ValidationError."""
        with pytest.raises(ValidationError):
            SynthesisOutput(
                final_text=123,  # Should be string
                formatting="markdown",
            )

    def test_synthesisoutput_invalid_formatting_type(self):
        """Test that non-string formatting raises ValidationError."""
        with pytest.raises(ValidationError):
            SynthesisOutput(
                final_text="Text",
                formatting=True,  # Should be string
            )

    def test_synthesisoutput_empty_final_text(self):
        """Test SynthesisOutput with empty final_text."""
        output = SynthesisOutput(
            final_text="",
            formatting="plain",
        )

        assert output.final_text == ""

    def test_synthesisoutput_empty_formatting(self):
        """Test SynthesisOutput with empty formatting string."""
        output = SynthesisOutput(
            final_text="Text",
            formatting="",
        )

        assert output.formatting == ""

    def test_synthesisoutput_long_final_text(self):
        """Test SynthesisOutput with very long final_text."""
        long_text = "x" * 50000
        output = SynthesisOutput(
            final_text=long_text,
            formatting="markdown",
        )

        assert len(output.final_text) == 50000

    def test_synthesisoutput_multiline_final_text(self):
        """Test SynthesisOutput with multiline final_text."""
        multiline_text = "Line 1\nLine 2\nLine 3\n" * 100
        output = SynthesisOutput(
            final_text=multiline_text,
            formatting="markdown",
        )

        assert output.final_text.count("\n") == 300

    def test_synthesisoutput_serialization_dump(self):
        """Test SynthesisOutput model_dump serialization."""
        output = SynthesisOutput(
            final_text="Test synthesis",
            formatting="html",
        )

        dumped = output.model_dump()
        assert dumped["final_text"] == "Test synthesis"
        assert dumped["formatting"] == "html"

    def test_synthesisoutput_json_serialization(self):
        """Test SynthesisOutput model_dump_json serialization."""
        output = SynthesisOutput(
            final_text="JSON synthesis",
            formatting="json",
        )

        json_str = output.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["final_text"] == "JSON synthesis"
        assert parsed["formatting"] == "json"

    def test_synthesisoutput_deserialization(self):
        """Test creating SynthesisOutput from dict."""
        data = {
            "final_text": "From dict",
            "formatting": "markdown",
        }

        output = SynthesisOutput(**data)
        assert output.final_text == "From dict"
        assert output.formatting == "markdown"

    def test_synthesisoutput_unicode_support(self):
        """Test SynthesisOutput with unicode characters."""
        output = SynthesisOutput(
            final_text="Unicode test: 你好世界 مرحبا العالم",
            formatting="unicode",
        )

        assert "你好世界" in output.final_text
        assert "مرحبا" in output.final_text


# ============================================================================
# CHAINSTEPCONFIG PYDANTIC MODEL TESTS
# ============================================================================


class TestChainStepConfig:
    """Test suite for ChainStepConfig Pydantic model."""

    def test_chainstepconfig_valid_instantiation(self):
        """Test valid ChainStepConfig creation with all fields."""
        config = ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            temperature=0.7,
            system_prompt_file="analyze_system.md",
        )

        assert config.model == "claude-haiku-4-5-20251001"
        assert config.max_tokens == 1000
        assert config.temperature == 0.7
        assert config.system_prompt_file == "analyze_system.md"

    def test_chainstepconfig_temperature_zero(self):
        """Test ChainStepConfig with temperature at minimum boundary (0.0)."""
        config = ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            temperature=0.0,
            system_prompt_file="test.md",
        )

        assert config.temperature == 0.0

    def test_chainstepconfig_temperature_two(self):
        """Test ChainStepConfig with temperature at maximum boundary (2.0)."""
        config = ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            temperature=2.0,
            system_prompt_file="test.md",
        )

        assert config.temperature == 2.0

    def test_chainstepconfig_temperature_mid_range(self):
        """Test ChainStepConfig with mid-range temperature values."""
        for temp in [0.5, 1.0, 1.5]:
            config = ChainStepConfig(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                temperature=temp,
                system_prompt_file="test.md",
            )
            assert config.temperature == temp

    def test_chainstepconfig_temperature_below_zero(self):
        """Test that temperature < 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainStepConfig(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                temperature=-0.1,
                system_prompt_file="test.md",
            )

    def test_chainstepconfig_temperature_above_two(self):
        """Test that temperature > 2.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainStepConfig(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                temperature=2.1,
                system_prompt_file="test.md",
            )

    def test_chainstepconfig_max_tokens_one(self):
        """Test ChainStepConfig with max_tokens at minimum boundary (1)."""
        config = ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            temperature=0.7,
            system_prompt_file="test.md",
        )

        assert config.max_tokens == 1

    def test_chainstepconfig_max_tokens_large_value(self):
        """Test ChainStepConfig with large max_tokens value."""
        config = ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=100000,
            temperature=0.7,
            system_prompt_file="test.md",
        )

        assert config.max_tokens == 100000

    def test_chainstepconfig_max_tokens_zero(self):
        """Test that max_tokens = 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainStepConfig(
                model="claude-haiku-4-5-20251001",
                max_tokens=0,
                temperature=0.7,
                system_prompt_file="test.md",
            )

    def test_chainstepconfig_max_tokens_negative(self):
        """Test that negative max_tokens raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainStepConfig(
                model="claude-haiku-4-5-20251001",
                max_tokens=-100,
                temperature=0.7,
                system_prompt_file="test.md",
            )

    def test_chainstepconfig_invalid_model_type(self):
        """Test that non-string model raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainStepConfig(
                model=123,  # Should be string
                max_tokens=500,
                temperature=0.7,
                system_prompt_file="test.md",
            )

    def test_chainstepconfig_temperature_string_coercion(self):
        """Test that string temperature can be coerced to float by Pydantic."""
        # Pydantic v2 coerces "0.7" to float 0.7
        config = ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            temperature="0.7",  # Will be coerced to float
            system_prompt_file="test.md",
        )
        assert config.temperature == 0.7

    def test_chainstepconfig_invalid_temperature_non_numeric_string(self):
        """Test that non-numeric string temperature raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainStepConfig(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                temperature="not_a_number",  # Cannot be coerced to float
                system_prompt_file="test.md",
            )

    def test_chainstepconfig_invalid_max_tokens_type(self):
        """Test that non-integer max_tokens raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainStepConfig(
                model="claude-haiku-4-5-20251001",
                max_tokens=500.5,  # Should be int
                temperature=0.7,
                system_prompt_file="test.md",
            )

    def test_chainstepconfig_invalid_system_prompt_file_type(self):
        """Test that non-string system_prompt_file raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainStepConfig(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                temperature=0.7,
                system_prompt_file=123,  # Should be string
            )

    def test_chainstepconfig_various_model_names(self):
        """Test ChainStepConfig with various valid model names."""
        models = [
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-5-20250929",
            "claude-opus",
            "gpt-4",
        ]
        for model in models:
            config = ChainStepConfig(
                model=model,
                max_tokens=500,
                temperature=0.7,
                system_prompt_file="test.md",
            )
            assert config.model == model

    def test_chainstepconfig_various_prompt_filenames(self):
        """Test ChainStepConfig with various system_prompt_file names."""
        filenames = [
            "analyze.md",
            "process.md",
            "synthesize.md",
            "system_prompt_v1.md",
            "my-prompt-file.txt",
        ]
        for filename in filenames:
            config = ChainStepConfig(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                temperature=0.7,
                system_prompt_file=filename,
            )
            assert config.system_prompt_file == filename

    def test_chainstepconfig_serialization_dump(self):
        """Test ChainStepConfig model_dump serialization."""
        config = ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            temperature=0.8,
            system_prompt_file="analyze.md",
        )

        dumped = config.model_dump()
        assert dumped["model"] == "claude-haiku-4-5-20251001"
        assert dumped["max_tokens"] == 1000
        assert dumped["temperature"] == 0.8
        assert dumped["system_prompt_file"] == "analyze.md"

    def test_chainstepconfig_json_serialization(self):
        """Test ChainStepConfig model_dump_json serialization."""
        config = ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            temperature=0.8,
            system_prompt_file="analyze.md",
        )

        json_str = config.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["model"] == "claude-haiku-4-5-20251001"
        assert parsed["max_tokens"] == 1000
        assert parsed["temperature"] == 0.8
        assert parsed["system_prompt_file"] == "analyze.md"

    def test_chainstepconfig_deserialization(self):
        """Test creating ChainStepConfig from dict."""
        data = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 2000,
            "temperature": 1.5,
            "system_prompt_file": "custom.md",
        }

        config = ChainStepConfig(**data)
        assert config.model == "claude-haiku-4-5-20251001"
        assert config.max_tokens == 2000
        assert config.temperature == 1.5


# ============================================================================
# CHAINCONFIG PYDANTIC MODEL TESTS
# ============================================================================


class TestChainConfig:
    """Test suite for ChainConfig Pydantic model."""

    @pytest.fixture
    def valid_step_config(self) -> ChainStepConfig:
        """Fixture for valid ChainStepConfig."""
        return ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            temperature=0.7,
            system_prompt_file="test.md",
        )

    def test_chainconfig_valid_instantiation(self, valid_step_config):
        """Test valid ChainConfig creation with all required step configs."""
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
        )

        assert config.analyze.model == "claude-haiku-4-5-20251001"
        assert config.process.max_tokens == 1000
        assert config.synthesize.temperature == 0.7
        assert config.analyze_timeout == 15  # default
        assert config.process_timeout == 30  # default
        assert config.synthesize_timeout == 20  # default

    def test_chainconfig_with_custom_timeouts(self, valid_step_config):
        """Test ChainConfig with custom timeout values."""
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
            analyze_timeout=20,
            process_timeout=40,
            synthesize_timeout=25,
        )

        assert config.analyze_timeout == 20
        assert config.process_timeout == 40
        assert config.synthesize_timeout == 25

    def test_chainconfig_timeout_minimum_boundary(self, valid_step_config):
        """Test ChainConfig with timeout at minimum boundary (1)."""
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
            analyze_timeout=1,
            process_timeout=1,
            synthesize_timeout=1,
        )

        assert config.analyze_timeout == 1
        assert config.process_timeout == 1
        assert config.synthesize_timeout == 1

    def test_chainconfig_timeout_maximum_boundary(self, valid_step_config):
        """Test ChainConfig with timeout at maximum boundary (270)."""
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
            analyze_timeout=270,
            process_timeout=270,
            synthesize_timeout=270,
        )

        assert config.analyze_timeout == 270
        assert config.process_timeout == 270
        assert config.synthesize_timeout == 270

    def test_chainconfig_timeout_mid_range(self, valid_step_config):
        """Test ChainConfig with mid-range timeout values."""
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
            analyze_timeout=100,
            process_timeout=150,
            synthesize_timeout=200,
        )

        assert config.analyze_timeout == 100
        assert config.process_timeout == 150
        assert config.synthesize_timeout == 200

    def test_chainconfig_analyze_timeout_below_minimum(self, valid_step_config):
        """Test that analyze_timeout < 1 raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainConfig(
                analyze=valid_step_config,
                process=valid_step_config,
                synthesize=valid_step_config,
                analyze_timeout=0,
            )

    def test_chainconfig_process_timeout_above_maximum(self, valid_step_config):
        """Test that process_timeout > 270 raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainConfig(
                analyze=valid_step_config,
                process=valid_step_config,
                synthesize=valid_step_config,
                process_timeout=271,
            )

    def test_chainconfig_synthesize_timeout_negative(self, valid_step_config):
        """Test that negative synthesize_timeout raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainConfig(
                analyze=valid_step_config,
                process=valid_step_config,
                synthesize=valid_step_config,
                synthesize_timeout=-1,
            )

    def test_chainconfig_enable_validation_default(self, valid_step_config):
        """Test that enable_validation defaults to True."""
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
        )

        assert config.enable_validation is True

    def test_chainconfig_enable_validation_false(self, valid_step_config):
        """Test ChainConfig with enable_validation set to False."""
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
            enable_validation=False,
        )

        assert config.enable_validation is False

    def test_chainconfig_strict_validation_default(self, valid_step_config):
        """Test that strict_validation defaults to False."""
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
        )

        assert config.strict_validation is False

    def test_chainconfig_strict_validation_true(self, valid_step_config):
        """Test ChainConfig with strict_validation set to True."""
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
            strict_validation=True,
        )

        assert config.strict_validation is True

    def test_chainconfig_validation_flags_combinations(self, valid_step_config):
        """Test all combinations of validation flags."""
        combinations = [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]

        for enable, strict in combinations:
            config = ChainConfig(
                analyze=valid_step_config,
                process=valid_step_config,
                synthesize=valid_step_config,
                enable_validation=enable,
                strict_validation=strict,
            )
            assert config.enable_validation == enable
            assert config.strict_validation == strict

    def test_chainconfig_different_step_configs(self):
        """Test ChainConfig with different configurations for each step."""
        analyze_config = ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            temperature=0.5,
            system_prompt_file="analyze.md",
        )

        process_config = ChainStepConfig(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            temperature=0.7,
            system_prompt_file="process.md",
        )

        synthesize_config = ChainStepConfig(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            temperature=0.3,
            system_prompt_file="synthesize.md",
        )

        config = ChainConfig(
            analyze=analyze_config,
            process=process_config,
            synthesize=synthesize_config,
        )

        assert config.analyze.model == "claude-haiku-4-5-20251001"
        assert config.process.model == "claude-sonnet-4-5-20250929"
        assert config.analyze.max_tokens == 500
        assert config.process.max_tokens == 2000
        assert config.synthesize.temperature == 0.3

    def test_chainconfig_missing_analyze_step(self, valid_step_config):
        """Test that missing analyze step raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainConfig(
                analyze=None,  # type: ignore
                process=valid_step_config,
                synthesize=valid_step_config,
            )

    def test_chainconfig_missing_process_step(self, valid_step_config):
        """Test that missing process step raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainConfig(
                analyze=valid_step_config,
                process=None,  # type: ignore
                synthesize=valid_step_config,
            )

    def test_chainconfig_missing_synthesize_step(self, valid_step_config):
        """Test that missing synthesize step raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainConfig(
                analyze=valid_step_config,
                process=valid_step_config,
                synthesize=None,  # type: ignore
            )

    def test_chainconfig_invalid_step_config_analyze(self, valid_step_config):
        """Test that invalid ChainStepConfig for analyze raises ValidationError."""
        invalid_config = {"model": "claude", "max_tokens": 500}  # Missing required fields

        with pytest.raises((ValidationError, TypeError)):
            ChainConfig(
                analyze=invalid_config,  # type: ignore
                process=valid_step_config,
                synthesize=valid_step_config,
            )

    def test_chainconfig_timeout_string_coercion(self, valid_step_config):
        """Test that string timeout can be coerced to int by Pydantic."""
        # Pydantic v2 coerces "20" to int 20
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
            analyze_timeout="20",  # Will be coerced to int
        )
        assert config.analyze_timeout == 20

    def test_chainconfig_invalid_timeout_non_numeric_string(self, valid_step_config):
        """Test that non-numeric string timeout raises ValidationError."""
        with pytest.raises(ValidationError):
            ChainConfig(
                analyze=valid_step_config,
                process=valid_step_config,
                synthesize=valid_step_config,
                analyze_timeout="not_a_number",  # Cannot be coerced to int
            )

    def test_chainconfig_enable_validation_string_coercion(self, valid_step_config):
        """Test that string "1" can be coerced to bool by Pydantic."""
        # Pydantic v2 coerces "1" and truthy strings to bool
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
            enable_validation="1",  # Will be coerced to bool True
        )
        assert config.enable_validation is True

    def test_chainconfig_invalid_enable_validation_type(self, valid_step_config):
        """Test that non-coercible types for enable_validation raise ValidationError."""
        with pytest.raises(ValidationError):
            ChainConfig(
                analyze=valid_step_config,
                process=valid_step_config,
                synthesize=valid_step_config,
                enable_validation=123,  # Non-string, non-bool
            )

    def test_chainconfig_serialization_dump(self, valid_step_config):
        """Test ChainConfig model_dump serialization."""
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
            analyze_timeout=20,
            process_timeout=40,
            synthesize_timeout=25,
            enable_validation=False,
            strict_validation=True,
        )

        dumped = config.model_dump()
        assert dumped["analyze_timeout"] == 20
        assert dumped["process_timeout"] == 40
        assert dumped["synthesize_timeout"] == 25
        assert dumped["enable_validation"] is False
        assert dumped["strict_validation"] is True
        assert "analyze" in dumped
        assert "process" in dumped
        assert "synthesize" in dumped

    def test_chainconfig_json_serialization(self, valid_step_config):
        """Test ChainConfig model_dump_json serialization."""
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
        )

        json_str = config.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["analyze_timeout"] == 15
        assert parsed["process_timeout"] == 30
        assert parsed["synthesize_timeout"] == 20
        assert parsed["enable_validation"] is True
        assert parsed["strict_validation"] is False

    def test_chainconfig_deserialization(self):
        """Test creating ChainConfig from dict."""
        data = {
            "analyze": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 500,
                "temperature": 0.5,
                "system_prompt_file": "analyze.md",
            },
            "process": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1000,
                "temperature": 0.7,
                "system_prompt_file": "process.md",
            },
            "synthesize": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 800,
                "temperature": 0.3,
                "system_prompt_file": "synthesize.md",
            },
            "analyze_timeout": 25,
            "process_timeout": 50,
            "synthesize_timeout": 30,
        }

        config = ChainConfig(**data)
        assert config.analyze.model == "claude-haiku-4-5-20251001"
        assert config.analyze_timeout == 25
        assert config.process_timeout == 50
        assert config.synthesize_timeout == 30

    def test_chainconfig_nested_validation(self, valid_step_config):
        """Test that invalid ChainStepConfig for process raises ValidationError."""
        # Create an invalid step config before passing to ChainConfig
        with pytest.raises(ValidationError):
            # This should fail when creating the invalid_step itself
            invalid_step = ChainStepConfig(
                model="claude",
                max_tokens=-100,  # Invalid: negative
                temperature=0.5,
                system_prompt_file="test.md",
            )
            # If we get here, the step is invalid for use with ChainConfig
            ChainConfig(
                analyze=valid_step_config,
                process=invalid_step,
                synthesize=valid_step_config,
            )

    def test_chainconfig_all_timeouts_one_second(self, valid_step_config):
        """Test ChainConfig with all timeouts set to 1 second."""
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
            analyze_timeout=1,
            process_timeout=1,
            synthesize_timeout=1,
        )

        assert config.analyze_timeout == 1
        assert config.process_timeout == 1
        assert config.synthesize_timeout == 1

    def test_chainconfig_all_timeouts_270_seconds(self, valid_step_config):
        """Test ChainConfig with all timeouts set to max 270 seconds."""
        config = ChainConfig(
            analyze=valid_step_config,
            process=valid_step_config,
            synthesize=valid_step_config,
            analyze_timeout=270,
            process_timeout=270,
            synthesize_timeout=270,
        )

        assert config.analyze_timeout == 270
        assert config.process_timeout == 270
        assert config.synthesize_timeout == 270
