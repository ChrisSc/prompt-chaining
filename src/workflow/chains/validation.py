"""
Validation gates for the prompt-chaining workflow.

This module implements validation logic for the outputs of each step in the
prompt-chaining pipeline. Validation gates are used to check that agent outputs
conform to expected schemas and business logic before proceeding to the next step.

Components:
- ValidationGate: Base class for all validation gates
- AnalysisValidationGate: Validates analysis step outputs
- ProcessValidationGate: Validates processing step outputs
- Conditional edge functions for LangGraph integration
"""

import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from workflow.models.chains import AnalysisOutput, ChainState, ProcessOutput

logger = logging.getLogger(__name__)


class ValidationGate:
    """
    Base class for validation gates in the prompt-chaining workflow.

    A validation gate checks that outputs from workflow steps conform to
    expected schemas and satisfy business logic constraints. Subclasses
    override the validate() method to add domain-specific validation rules.
    """

    def __init__(self, schema: type[BaseModel]) -> None:
        """
        Initialize a validation gate with a Pydantic schema.

        Args:
            schema: The Pydantic BaseModel class to use for schema validation
        """
        self.schema = schema
        self.schema_name = schema.__name__

    def validate(self, data: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate data against the configured schema.

        Args:
            data: Dictionary of data to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self.schema.model_validate(data)
            return True, None
        except ValidationError as e:
            # Format Pydantic validation errors into readable message
            error_details = []
            for error in e.errors():
                field = ".".join(str(loc) for loc in error["loc"])
                message = error["msg"]
                error_details.append(f"{field}: {message}")

            error_message = f"Schema validation failed: {', '.join(error_details)}"
            return False, error_message


class AnalysisValidationGate(ValidationGate):
    """
    Validation gate for analysis step outputs.

    Validates that the analysis step produces valid AnalysisOutput with:
    - Valid schema conformance (via parent class)
    - Non-empty intent field
    - Properly structured analysis results
    """

    def __init__(self) -> None:
        """Initialize the analysis validation gate."""
        super().__init__(AnalysisOutput)

    def validate(self, data: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate analysis step output.

        Checks schema conformance and ensures intent is non-empty.

        Args:
            data: Dictionary containing analysis output

        Returns:
            Tuple of (is_valid, error_message)
        """
        # First perform schema validation
        is_valid, error_message = super().validate(data)
        if not is_valid:
            return False, error_message

        # Business logic validation: intent must be non-empty
        intent = data.get("intent", "").strip() if isinstance(data.get("intent"), str) else ""

        if not intent:
            error_msg = (
                "Analysis validation failed: 'intent' field is required and must be non-empty. "
                "The analysis step must extract a clear user intent from the request."
            )
            return False, error_msg

        # All validations passed
        logger.debug(
            "Analysis output validated successfully",
            extra={
                "schema": self.schema_name,
                "intent_length": len(intent),
            },
        )
        return True, None


class ProcessValidationGate(ValidationGate):
    """
    Validation gate for processing step outputs.

    Validates that the processing step produces valid ProcessOutput with:
    - Valid schema conformance (via parent class)
    - Non-empty content
    - Confidence score >= configured threshold (default 0.5)
    - Properly structured process results
    """

    def __init__(self, min_confidence: float = 0.5) -> None:
        """
        Initialize the processing validation gate.

        Args:
            min_confidence: Minimum confidence threshold (0.0-1.0)
        """
        super().__init__(ProcessOutput)
        self.min_confidence = min_confidence

    def validate(self, data: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate processing step output.

        Checks schema conformance, content non-empty, and confidence >= 0.5.

        Args:
            data: Dictionary containing process output

        Returns:
            Tuple of (is_valid, error_message)
        """
        # First perform schema validation
        is_valid, error_message = super().validate(data)
        if not is_valid:
            return False, error_message

        # Business logic validation: content must be non-empty
        content = data.get("content", "").strip() if isinstance(data.get("content"), str) else ""

        if not content:
            error_msg = (
                "Processing validation failed: 'content' field is required and must be non-empty. "
                "The processing step must generate meaningful content based on the analysis."
            )
            return False, error_msg

        # Business logic validation: confidence must be >= configured threshold
        confidence = data.get("confidence")
        if not isinstance(confidence, (int, float)) or confidence < self.min_confidence:
            error_msg = (
                f"Processing validation failed: 'confidence' must be >= {self.min_confidence}. "
                f"Current value: {confidence}. "
                f"The processing step must produce content with at least {self.min_confidence*100:.0f}% confidence in its quality."
            )
            return False, error_msg

        # All validations passed
        logger.debug(
            "Processing output validated successfully",
            extra={
                "schema": self.schema_name,
                "content_length": len(content),
                "confidence": confidence,
            },
        )
        return True, None


def should_proceed_to_process(state: ChainState) -> str:
    """
    Conditional edge function: validate analysis output before proceeding to processing.

    This function is used by LangGraph as a conditional edge function. It validates
    the output from the analysis step and returns the next node to execute.

    Args:
        state: Current state of the LangGraph execution

    Returns:
        str: "process" if analysis validation passed, "error" if it failed
    """
    analysis_data = state.get("analysis")

    if analysis_data is None:
        logger.warning(
            "Analysis validation gate triggered: analysis output is None",
            extra={"step": "analysis_validation"},
        )
        return "error"

    # Convert to dict if needed (in case it's already a Pydantic model)
    if isinstance(analysis_data, BaseModel):
        analysis_dict = analysis_data.model_dump()
    else:
        analysis_dict = analysis_data

    # Validate analysis output
    gate = AnalysisValidationGate()
    is_valid, error_message = gate.validate(analysis_dict)

    if not is_valid:
        logger.warning(
            f"Analysis validation failed: {error_message}",
            extra={
                "step": "analysis_validation",
                "error": error_message,
            },
        )
        return "error"

    logger.info(
        "Analysis validation passed, proceeding to processing",
        extra={"step": "analysis_validation"},
    )
    return "process"


def should_proceed_to_synthesize(state: ChainState, min_confidence: float = 0.5) -> str:
    """
    Conditional edge function: validate processing output before proceeding to synthesis.

    This function is used by LangGraph as a conditional edge function. It validates
    the output from the processing step and returns the next node to execute.

    Args:
        state: Current state of the LangGraph execution
        min_confidence: Minimum confidence threshold (0.0-1.0)

    Returns:
        str: "synthesize" if processing validation passed, "error" if it failed
    """
    processed_content = state.get("processed_content")

    # Handle None case - processed_content might be a string, dict, or Pydantic model
    if processed_content is None:
        logger.warning(
            "Processing validation gate triggered: processed_content is None",
            extra={"step": "process_validation"},
        )
        return "error"

    # If processed_content is a string, wrap it in the expected dict format
    if isinstance(processed_content, str):
        processed_dict = {
            "content": processed_content,
            "confidence": 0.8,  # Default confidence for string output
            "metadata": {},
        }
    elif isinstance(processed_content, BaseModel):
        processed_dict = processed_content.model_dump()
    else:
        processed_dict = processed_content

    # Validate processing output with configured threshold
    gate = ProcessValidationGate(min_confidence=min_confidence)
    is_valid, error_message = gate.validate(processed_dict)

    if not is_valid:
        logger.warning(
            f"Processing validation failed: {error_message}",
            extra={
                "step": "process_validation",
                "error": error_message,
            },
        )
        return "error"

    logger.info(
        "Processing validation passed, proceeding to synthesis",
        extra={"step": "process_validation"},
    )
    return "synthesize"
