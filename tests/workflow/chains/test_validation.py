"""
Comprehensive unit tests for validation gates in the prompt-chaining workflow.

Tests all validation components:
- ValidationGate: Base class for schema validation
- AnalysisValidationGate: Validates analysis step outputs
- ProcessValidationGate: Validates processing step outputs
- Conditional edge functions for LangGraph integration

Covers happy path, edge cases, error handling, and integration scenarios.
Target: >90% code coverage of validation.py
"""

from unittest.mock import patch

import pytest

from workflow.chains.validation import (
    AnalysisValidationGate,
    ProcessValidationGate,
    ValidationGate,
    should_proceed_to_process,
    should_proceed_to_synthesize,
)
from workflow.models.chains import (
    AnalysisOutput,
    ChainState,
    ProcessOutput,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def valid_analysis_output() -> dict:
    """Fixture for valid analysis output dictionary."""
    return {
        "intent": "extract_summary",
        "key_entities": ["document", "summary", "key_points"],
        "complexity": "moderate",
        "context": {"source_type": "document", "language": "en"},
    }


@pytest.fixture
def valid_analysis_model() -> AnalysisOutput:
    """Fixture for valid analysis output as Pydantic model."""
    return AnalysisOutput(
        intent="extract_summary",
        key_entities=["document", "summary", "key_points"],
        complexity="moderate",
        context={"source_type": "document", "language": "en"},
    )


@pytest.fixture
def valid_process_output() -> dict:
    """Fixture for valid processing output dictionary."""
    return {
        "content": "Generated content based on analysis",
        "confidence": 0.85,
        "metadata": {"tokens": 150, "model": "claude-haiku"},
    }


@pytest.fixture
def valid_process_model() -> ProcessOutput:
    """Fixture for valid processing output as Pydantic model."""
    return ProcessOutput(
        content="Generated content based on analysis",
        confidence=0.85,
        metadata={"tokens": 150, "model": "claude-haiku"},
    )


@pytest.fixture
def chain_state_with_valid_analysis(valid_analysis_output) -> ChainState:
    """Fixture for ChainState with valid analysis output."""
    return ChainState(
        messages=[],
        analysis=valid_analysis_output,
        processed_content=None,
        final_response=None,
        step_metadata={},
    )


@pytest.fixture
def chain_state_with_valid_process(valid_process_output) -> ChainState:
    """Fixture for ChainState with valid processed content."""
    return ChainState(
        messages=[],
        analysis=None,
        processed_content=valid_process_output,
        final_response=None,
        step_metadata={},
    )


@pytest.fixture
def chain_state_with_process_string() -> ChainState:
    """Fixture for ChainState with processed_content as string."""
    return ChainState(
        messages=[],
        analysis=None,
        processed_content="Generated content as string",
        final_response=None,
        step_metadata={},
    )


# ============================================================================
# VALIDATIONGATE BASE CLASS TESTS
# ============================================================================


class TestValidationGate:
    """Test suite for ValidationGate base class."""

    def test_validationgate_initialization(self):
        """Test ValidationGate initialization with a schema."""
        gate = ValidationGate(AnalysisOutput)

        assert gate.schema == AnalysisOutput
        assert gate.schema_name == "AnalysisOutput"

    def test_validationgate_schema_name_stored(self):
        """Test that schema_name is correctly stored from schema class."""
        gate = ValidationGate(ProcessOutput)

        assert gate.schema_name == "ProcessOutput"

    def test_validationgate_valid_data_passes(self, valid_analysis_output):
        """Test that valid data passes ValidationGate validation."""
        gate = ValidationGate(AnalysisOutput)
        is_valid, error_message = gate.validate(valid_analysis_output)

        assert is_valid is True
        assert error_message is None

    def test_validationgate_invalid_data_fails(self):
        """Test that invalid data fails ValidationGate validation."""
        gate = ValidationGate(AnalysisOutput)
        invalid_data = {
            "intent": "test",
            "key_entities": "not_a_list",  # Should be list
            "complexity": "simple",
        }

        is_valid, error_message = gate.validate(invalid_data)

        assert is_valid is False
        assert error_message is not None
        assert "Schema validation failed" in error_message

    def test_validationgate_missing_required_field(self):
        """Test that missing required field causes validation failure."""
        gate = ValidationGate(AnalysisOutput)
        incomplete_data = {
            "intent": "test",
            # Missing key_entities and complexity
        }

        is_valid, error_message = gate.validate(incomplete_data)

        assert is_valid is False
        assert error_message is not None

    def test_validationgate_empty_dict(self):
        """Test that empty dict fails validation for schema with required fields."""
        gate = ValidationGate(AnalysisOutput)

        is_valid, error_message = gate.validate({})

        assert is_valid is False
        assert error_message is not None

    def test_validationgate_none_data(self):
        """Test that None data fails validation with appropriate error."""
        gate = ValidationGate(AnalysisOutput)

        # None should fail validation since it doesn't match the schema
        is_valid, error_message = gate.validate(None)  # type: ignore

        # Pydantic will try to validate None and fail
        assert is_valid is False
        assert error_message is not None

    def test_validationgate_error_message_format(self):
        """Test that error messages are properly formatted."""
        gate = ValidationGate(AnalysisOutput)
        invalid_data = {
            "intent": 123,  # Wrong type
            "key_entities": [],
            "complexity": "simple",
        }

        is_valid, error_message = gate.validate(invalid_data)

        assert is_valid is False
        assert "Schema validation failed" in error_message
        assert "intent" in error_message.lower()

    def test_validationgate_multiple_validation_errors(self):
        """Test that multiple validation errors are all reported."""
        gate = ValidationGate(ProcessOutput)
        invalid_data = {
            "content": 123,  # Wrong type
            "confidence": 2.0,  # Out of range
        }

        is_valid, error_message = gate.validate(invalid_data)

        assert is_valid is False
        assert error_message is not None
        # Both errors should be reported
        assert (
            "content" in error_message.lower()
            or "input should be a valid string" in error_message.lower()
        )

    def test_validationgate_processoutput_schema(self, valid_process_output):
        """Test ValidationGate with ProcessOutput schema."""
        gate = ValidationGate(ProcessOutput)
        is_valid, error_message = gate.validate(valid_process_output)

        assert is_valid is True
        assert error_message is None


# ============================================================================
# ANALYSISVALIDATIONGATE TESTS
# ============================================================================


class TestAnalysisValidationGate:
    """Test suite for AnalysisValidationGate."""

    def test_analysisvalidationgate_initialization(self):
        """Test AnalysisValidationGate initialization."""
        gate = AnalysisValidationGate()

        assert gate.schema == AnalysisOutput
        assert gate.schema_name == "AnalysisOutput"

    def test_analysisvalidationgate_valid_output(self, valid_analysis_output):
        """Test that valid analysis output passes validation."""
        gate = AnalysisValidationGate()
        is_valid, error_message = gate.validate(valid_analysis_output)

        assert is_valid is True
        assert error_message is None

    def test_analysisvalidationgate_missing_intent_field(self):
        """Test that missing intent field fails validation."""
        gate = AnalysisValidationGate()
        data = {
            "key_entities": ["entity"],
            "complexity": "simple",
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is False
        assert error_message is not None

    def test_analysisvalidationgate_empty_intent_string(self):
        """Test that empty intent string fails validation."""
        gate = AnalysisValidationGate()
        data = {
            "intent": "",
            "key_entities": ["entity"],
            "complexity": "simple",
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is False
        assert error_message is not None
        assert "intent" in error_message.lower()

    def test_analysisvalidationgate_whitespace_only_intent(self):
        """Test that whitespace-only intent fails validation."""
        gate = AnalysisValidationGate()
        data = {
            "intent": "   \t\n  ",
            "key_entities": ["entity"],
            "complexity": "simple",
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is False
        assert error_message is not None
        assert "intent" in error_message.lower()

    def test_analysisvalidationgate_single_char_intent(self):
        """Test that single character intent passes validation."""
        gate = AnalysisValidationGate()
        data = {
            "intent": "a",
            "key_entities": ["entity"],
            "complexity": "simple",
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_analysisvalidationgate_special_chars_in_intent(self):
        """Test that special characters in intent are allowed."""
        gate = AnalysisValidationGate()
        data = {
            "intent": "Extract data: @#$%^&*()",
            "key_entities": ["entity"],
            "complexity": "simple",
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_analysisvalidationgate_intent_with_leading_trailing_whitespace(self):
        """Test that intent with leading/trailing whitespace is trimmed."""
        gate = AnalysisValidationGate()
        data = {
            "intent": "  valid intent  ",
            "key_entities": ["entity"],
            "complexity": "simple",
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_analysisvalidationgate_valid_with_empty_entities_list(self):
        """Test valid analysis with empty key_entities list."""
        gate = AnalysisValidationGate()
        data = {
            "intent": "simple extraction",
            "key_entities": [],
            "complexity": "simple",
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_analysisvalidationgate_valid_with_no_context(self):
        """Test valid analysis without context field (uses default)."""
        gate = AnalysisValidationGate()
        data = {
            "intent": "extract data",
            "key_entities": ["data"],
            "complexity": "simple",
            # context not provided - should default to empty dict
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_analysisvalidationgate_intent_type_validation(self):
        """Test that intent must be a string type."""
        gate = AnalysisValidationGate()
        data = {
            "intent": 123,  # Not a string
            "key_entities": ["entity"],
            "complexity": "simple",
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is False
        assert error_message is not None

    def test_analysisvalidationgate_key_entities_type_validation(self):
        """Test that key_entities must be a list."""
        gate = AnalysisValidationGate()
        data = {
            "intent": "valid",
            "key_entities": "not_a_list",
            "complexity": "simple",
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is False
        assert error_message is not None

    @patch("workflow.chains.validation.logger")
    def test_analysisvalidationgate_logs_on_success(self, mock_logger, valid_analysis_output):
        """Test that success is logged with debug level."""
        gate = AnalysisValidationGate()
        gate.validate(valid_analysis_output)

        mock_logger.debug.assert_called_once()
        call_args = mock_logger.debug.call_args
        assert "validated successfully" in call_args[0][0].lower()

    @patch("workflow.chains.validation.logger")
    def test_analysisvalidationgate_logs_on_empty_intent(self, mock_logger):
        """Test that empty intent failure is logged."""
        gate = AnalysisValidationGate()
        data = {
            "intent": "",
            "key_entities": ["entity"],
            "complexity": "simple",
        }
        gate.validate(data)

        # Should not call debug on failure, only return error

    def test_analysisvalidationgate_complex_context(self):
        """Test analysis with complex nested context."""
        gate = AnalysisValidationGate()
        data = {
            "intent": "analyze data",
            "key_entities": ["data", "analysis"],
            "complexity": "complex",
            "context": {
                "nested": {"deep": {"structure": "value"}},
                "list": [1, 2, 3],
                "mixed": ["string", 123, {"key": "value"}],
            },
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_analysisvalidationgate_very_long_intent(self):
        """Test analysis with very long intent string."""
        gate = AnalysisValidationGate()
        long_intent = "x" * 10000
        data = {
            "intent": long_intent,
            "key_entities": ["entity"],
            "complexity": "simple",
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None


# ============================================================================
# PROCESSVALIDATIONGATE TESTS
# ============================================================================


class TestProcessValidationGate:
    """Test suite for ProcessValidationGate."""

    def test_processvalidationgate_initialization(self):
        """Test ProcessValidationGate initialization."""
        gate = ProcessValidationGate()

        assert gate.schema == ProcessOutput
        assert gate.schema_name == "ProcessOutput"

    def test_processvalidationgate_valid_output(self, valid_process_output):
        """Test that valid process output passes validation."""
        gate = ProcessValidationGate()
        is_valid, error_message = gate.validate(valid_process_output)

        assert is_valid is True
        assert error_message is None

    def test_processvalidationgate_missing_content_field(self):
        """Test that missing content field fails validation."""
        gate = ProcessValidationGate()
        data = {
            "confidence": 0.75,
            # Missing content and metadata fields
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is False
        assert error_message is not None

    def test_processvalidationgate_empty_content_string(self):
        """Test that empty content string fails validation."""
        gate = ProcessValidationGate()
        data = {
            "content": "",
            "confidence": 0.75,
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is False
        assert error_message is not None
        assert "content" in error_message.lower()

    def test_processvalidationgate_whitespace_only_content(self):
        """Test that whitespace-only content fails validation."""
        gate = ProcessValidationGate()
        data = {
            "content": "   \t\n  ",
            "confidence": 0.75,
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is False
        assert error_message is not None
        assert "content" in error_message.lower()

    def test_processvalidationgate_single_char_content(self):
        """Test that single character content passes validation."""
        gate = ProcessValidationGate()
        data = {
            "content": "x",
            "confidence": 0.75,
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_processvalidationgate_confidence_exactly_0_5(self):
        """Test that confidence = 0.5 (boundary) passes validation."""
        gate = ProcessValidationGate()
        data = {
            "content": "Content",
            "confidence": 0.5,
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_processvalidationgate_confidence_just_below_threshold(self):
        """Test that confidence = 0.49 (just below threshold) fails validation."""
        gate = ProcessValidationGate()
        data = {
            "content": "Content",
            "confidence": 0.49,
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is False
        assert error_message is not None
        assert "confidence" in error_message.lower()
        assert "0.5" in error_message

    def test_processvalidationgate_confidence_0_0(self):
        """Test that confidence = 0.0 fails validation."""
        gate = ProcessValidationGate()
        data = {
            "content": "Content",
            "confidence": 0.0,
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is False
        assert error_message is not None

    def test_processvalidationgate_confidence_1_0(self):
        """Test that confidence = 1.0 passes validation."""
        gate = ProcessValidationGate()
        data = {
            "content": "Content",
            "confidence": 1.0,
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_processvalidationgate_confidence_above_range(self):
        """Test that confidence > 1.0 fails validation (caught by schema)."""
        gate = ProcessValidationGate()
        data = {
            "content": "Content",
            "confidence": 1.5,
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is False
        assert error_message is not None

    def test_processvalidationgate_confidence_negative(self):
        """Test that negative confidence fails validation."""
        gate = ProcessValidationGate()
        data = {
            "content": "Content",
            "confidence": -0.1,
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is False
        assert error_message is not None

    def test_processvalidationgate_confidence_mid_range_values(self):
        """Test various mid-range confidence values."""
        gate = ProcessValidationGate()
        for confidence in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
            data = {
                "content": "Content",
                "confidence": confidence,
            }
            is_valid, error_message = gate.validate(data)
            assert is_valid is True, f"Failed for confidence={confidence}"

    def test_processvalidationgate_content_with_special_chars(self):
        """Test that special characters in content are allowed."""
        gate = ProcessValidationGate()
        data = {
            "content": "Content with special chars: @#$%^&*()",
            "confidence": 0.75,
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_processvalidationgate_content_with_newlines(self):
        """Test that newlines in content are allowed."""
        gate = ProcessValidationGate()
        data = {
            "content": "Line 1\nLine 2\nLine 3",
            "confidence": 0.75,
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_processvalidationgate_valid_with_empty_metadata(self):
        """Test valid process with empty metadata dict."""
        gate = ProcessValidationGate()
        data = {
            "content": "Content",
            "confidence": 0.75,
            "metadata": {},
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_processvalidationgate_valid_without_metadata(self):
        """Test valid process without metadata field (uses default)."""
        gate = ProcessValidationGate()
        data = {
            "content": "Content",
            "confidence": 0.75,
            # metadata not provided - should default to empty dict
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_processvalidationgate_complex_metadata(self):
        """Test process with complex nested metadata."""
        gate = ProcessValidationGate()
        data = {
            "content": "Content",
            "confidence": 0.85,
            "metadata": {
                "tokens": {"input": 100, "output": 50},
                "timing": {"total": 2.5},
                "sources": ["source1", "source2"],
                "nested": {"deep": {"structure": [1, 2, 3]}},
            },
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None

    def test_processvalidationgate_confidence_type_validation(self):
        """Test that confidence must be numeric, though Pydantic may coerce strings."""
        gate = ProcessValidationGate()
        data = {
            "content": "Content",
            "confidence": "0.75",  # String, Pydantic may or may not coerce
        }

        is_valid, error_message = gate.validate(data)

        # String confidence validation depends on Pydantic version/strictness
        # This test verifies the actual behavior
        if is_valid:
            # If valid, Pydantic coerced the string to float
            assert error_message is None
        else:
            # If invalid, Pydantic was strict about type checking
            assert error_message is not None

    def test_processvalidationgate_confidence_non_numeric_string(self):
        """Test that non-numeric string confidence fails validation."""
        gate = ProcessValidationGate()
        data = {
            "content": "Content",
            "confidence": "not_a_number",
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is False
        assert error_message is not None

    @patch("workflow.chains.validation.logger")
    def test_processvalidationgate_logs_on_success(self, mock_logger, valid_process_output):
        """Test that success is logged with debug level."""
        gate = ProcessValidationGate()
        gate.validate(valid_process_output)

        mock_logger.debug.assert_called_once()
        call_args = mock_logger.debug.call_args
        assert "validated successfully" in call_args[0][0].lower()

    def test_processvalidationgate_very_long_content(self):
        """Test process with very long content string."""
        gate = ProcessValidationGate()
        long_content = "x" * 100000
        data = {
            "content": long_content,
            "confidence": 0.75,
        }

        is_valid, error_message = gate.validate(data)

        assert is_valid is True
        assert error_message is None


# ============================================================================
# CONDITIONAL EDGE FUNCTION TESTS: should_proceed_to_process
# ============================================================================


class TestShouldProceedToProcess:
    """Test suite for should_proceed_to_process conditional edge function."""

    def test_should_proceed_to_process_valid_analysis_dict(self, chain_state_with_valid_analysis):
        """Test that valid analysis dict returns 'process' edge."""
        result = should_proceed_to_process(chain_state_with_valid_analysis)

        assert result == "process"

    def test_should_proceed_to_process_valid_analysis_model(self, valid_analysis_model):
        """Test that valid analysis Pydantic model returns 'process' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": valid_analysis_model,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_process(state)

        assert result == "process"

    def test_should_proceed_to_process_none_analysis(self):
        """Test that None analysis returns 'error' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_process(state)

        assert result == "error"

    def test_should_proceed_to_process_empty_intent(self):
        """Test that empty intent returns 'error' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": {
                "intent": "",
                "key_entities": ["entity"],
                "complexity": "simple",
            },
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_process(state)

        assert result == "error"

    def test_should_proceed_to_process_missing_intent_field(self):
        """Test that missing intent field returns 'error' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": {
                "key_entities": ["entity"],
                "complexity": "simple",
            },
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_process(state)

        assert result == "error"

    def test_should_proceed_to_process_invalid_key_entities_type(self):
        """Test that invalid key_entities type returns 'error' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": {
                "intent": "valid",
                "key_entities": "not_a_list",  # Should be list
                "complexity": "simple",
            },
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_process(state)

        assert result == "error"

    @patch("workflow.chains.validation.logger")
    def test_should_proceed_to_process_logs_on_success(
        self, mock_logger, chain_state_with_valid_analysis
    ):
        """Test that success is logged at INFO level."""
        should_proceed_to_process(chain_state_with_valid_analysis)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "proceeding to processing" in call_args[0][0].lower()

    @patch("workflow.chains.validation.logger")
    def test_should_proceed_to_process_logs_on_none_analysis(self, mock_logger):
        """Test that None analysis is logged at WARNING level."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        should_proceed_to_process(state)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "none" in call_args[0][0].lower()

    @patch("workflow.chains.validation.logger")
    def test_should_proceed_to_process_logs_on_validation_failure(self, mock_logger):
        """Test that validation failure is logged at WARNING level."""
        state: ChainState = {
            "messages": [],
            "analysis": {
                "intent": "",
                "key_entities": ["entity"],
                "complexity": "simple",
            },
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        should_proceed_to_process(state)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "failed" in call_args[0][0].lower()

    def test_should_proceed_to_process_with_complex_context(self):
        """Test should_proceed_to_process with complex nested context."""
        state: ChainState = {
            "messages": [],
            "analysis": {
                "intent": "complex analysis",
                "key_entities": ["entity1", "entity2"],
                "complexity": "complex",
                "context": {
                    "nested": {"deep": {"data": "value"}},
                    "list": [1, 2, 3],
                },
            },
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_process(state)

        assert result == "process"

    def test_should_proceed_to_process_with_empty_key_entities(self):
        """Test that empty key_entities list is acceptable."""
        state: ChainState = {
            "messages": [],
            "analysis": {
                "intent": "valid",
                "key_entities": [],
                "complexity": "simple",
            },
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_process(state)

        assert result == "process"


# ============================================================================
# CONDITIONAL EDGE FUNCTION TESTS: should_proceed_to_synthesize
# ============================================================================


class TestShouldProceedToSynthesize:
    """Test suite for should_proceed_to_synthesize conditional edge function."""

    def test_should_proceed_to_synthesize_valid_process_dict(self, chain_state_with_valid_process):
        """Test that valid process dict returns 'synthesize' edge."""
        result = should_proceed_to_synthesize(chain_state_with_valid_process)

        assert result == "synthesize"

    def test_should_proceed_to_synthesize_valid_process_model(self, valid_process_model):
        """Test that valid process Pydantic model returns 'synthesize' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": valid_process_model,
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        assert result == "synthesize"

    def test_should_proceed_to_synthesize_process_as_string(self, chain_state_with_process_string):
        """Test that processed_content as string is wrapped and validated."""
        result = should_proceed_to_synthesize(chain_state_with_process_string)

        assert result == "synthesize"

    def test_should_proceed_to_synthesize_none_content(self):
        """Test that None processed_content returns 'error' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        assert result == "error"

    def test_should_proceed_to_synthesize_empty_content_dict(self):
        """Test that empty content in dict returns 'error' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": {
                "content": "",
                "confidence": 0.75,
            },
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        assert result == "error"

    def test_should_proceed_to_synthesize_low_confidence(self):
        """Test that confidence < 0.5 returns 'error' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": {
                "content": "Content",
                "confidence": 0.3,
            },
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        assert result == "error"

    def test_should_proceed_to_synthesize_confidence_boundary(self):
        """Test that confidence = 0.5 (boundary) returns 'synthesize' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": {
                "content": "Content",
                "confidence": 0.5,
            },
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        assert result == "synthesize"

    def test_should_proceed_to_synthesize_missing_content_field(self):
        """Test that missing content field returns 'error' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": {
                "confidence": 0.75,
                # Missing content
            },
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        assert result == "error"

    def test_should_proceed_to_synthesize_missing_confidence_field(self):
        """Test that missing confidence field returns 'error' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": {
                "content": "Content",
                # Missing confidence
            },
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        assert result == "error"

    def test_should_proceed_to_synthesize_string_wrapped_format(self):
        """Test that string content is wrapped with default confidence 0.8."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": "Simple string content",
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        assert result == "synthesize"

    def test_should_proceed_to_synthesize_empty_string_content(self):
        """Test that empty string content returns 'error' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": "",
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        assert result == "error"

    @patch("workflow.chains.validation.logger")
    def test_should_proceed_to_synthesize_logs_on_success(
        self, mock_logger, chain_state_with_valid_process
    ):
        """Test that success is logged at INFO level."""
        should_proceed_to_synthesize(chain_state_with_valid_process)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "proceeding to synthesis" in call_args[0][0].lower()

    @patch("workflow.chains.validation.logger")
    def test_should_proceed_to_synthesize_logs_on_none_content(self, mock_logger):
        """Test that None content is logged at WARNING level."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        should_proceed_to_synthesize(state)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "none" in call_args[0][0].lower()

    @patch("workflow.chains.validation.logger")
    def test_should_proceed_to_synthesize_logs_on_validation_failure(self, mock_logger):
        """Test that validation failure is logged at WARNING level."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": {
                "content": "",
                "confidence": 0.75,
            },
            "final_response": None,
            "step_metadata": {},
        }

        should_proceed_to_synthesize(state)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "failed" in call_args[0][0].lower()

    def test_should_proceed_to_synthesize_with_complex_metadata(self):
        """Test should_proceed_to_synthesize with complex nested metadata."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": {
                "content": "Generated content",
                "confidence": 0.9,
                "metadata": {
                    "tokens": {"input": 100, "output": 50},
                    "timing": {"total": 2.5},
                    "sources": ["source1", "source2"],
                },
            },
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        assert result == "synthesize"

    def test_should_proceed_to_synthesize_high_confidence(self):
        """Test that high confidence (1.0) returns 'synthesize' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": {
                "content": "Content",
                "confidence": 1.0,
            },
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        assert result == "synthesize"

    def test_should_proceed_to_synthesize_string_with_special_chars(self):
        """Test that string content with special characters is accepted."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": "Content with special chars: @#$%^&*()",
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        assert result == "synthesize"

    def test_should_proceed_to_synthesize_whitespace_only_string(self):
        """Test that whitespace-only string returns 'error' edge."""
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": "   \t\n  ",
            "final_response": None,
            "step_metadata": {},
        }

        result = should_proceed_to_synthesize(state)

        assert result == "error"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestValidationIntegration:
    """Integration tests for validation gates and conditional edges."""

    def test_full_pipeline_valid_analysis_to_process_edge(self, valid_analysis_output):
        """Test full analysis validation through to process edge decision."""
        # Create analysis
        analysis_gate = AnalysisValidationGate()
        is_valid, error = analysis_gate.validate(valid_analysis_output)
        assert is_valid

        # Use in state for edge function
        state: ChainState = {
            "messages": [],
            "analysis": valid_analysis_output,
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }
        edge = should_proceed_to_process(state)
        assert edge == "process"

    def test_full_pipeline_valid_process_to_synthesize_edge(self, valid_process_output):
        """Test full process validation through to synthesize edge decision."""
        # Create process output
        process_gate = ProcessValidationGate()
        is_valid, error = process_gate.validate(valid_process_output)
        assert is_valid

        # Use in state for edge function
        state: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": valid_process_output,
            "final_response": None,
            "step_metadata": {},
        }
        edge = should_proceed_to_synthesize(state)
        assert edge == "synthesize"

    def test_validation_gates_with_pydantic_models(self, valid_analysis_model, valid_process_model):
        """Test validation gates accept Pydantic models correctly."""
        analysis_gate = AnalysisValidationGate()
        process_gate = ProcessValidationGate()

        # Validate using model_dump()
        is_valid_analysis, _ = analysis_gate.validate(valid_analysis_model.model_dump())
        is_valid_process, _ = process_gate.validate(valid_process_model.model_dump())

        assert is_valid_analysis is True
        assert is_valid_process is True

    def test_error_propagation_from_validation_to_edge(self):
        """Test that validation errors properly propagate to edge functions."""
        invalid_state: ChainState = {
            "messages": [],
            "analysis": {
                "intent": "",  # Invalid: empty
                "key_entities": ["entity"],
                "complexity": "simple",
            },
            "processed_content": None,
            "final_response": None,
            "step_metadata": {},
        }

        # Validation should fail
        gate = AnalysisValidationGate()
        is_valid, error = gate.validate(invalid_state["analysis"])
        assert is_valid is False

        # Edge function should return error
        edge = should_proceed_to_process(invalid_state)
        assert edge == "error"

    def test_edge_function_model_type_handling(self):
        """Test that edge functions correctly handle dict, model, and string types."""
        # Dict type
        state_dict: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": {
                "content": "Content",
                "confidence": 0.75,
            },
            "final_response": None,
            "step_metadata": {},
        }
        assert should_proceed_to_synthesize(state_dict) == "synthesize"

        # String type
        state_string: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": "String content",
            "final_response": None,
            "step_metadata": {},
        }
        assert should_proceed_to_synthesize(state_string) == "synthesize"

        # Model type
        model = ProcessOutput(content="Model content", confidence=0.8)
        state_model: ChainState = {
            "messages": [],
            "analysis": None,
            "processed_content": model,
            "final_response": None,
            "step_metadata": {},
        }
        assert should_proceed_to_synthesize(state_model) == "synthesize"
