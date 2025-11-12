"""
Chains module for prompt-chaining workflow components.

This module contains the validation gates and conditional edge functions
used to implement the prompt-chaining pattern with LangGraph.
"""

from workflow.chains.validation import (
    AnalysisValidationGate,
    ProcessValidationGate,
    ValidationGate,
    should_proceed_to_process,
    should_proceed_to_synthesize,
)

__all__ = [
    "ValidationGate",
    "AnalysisValidationGate",
    "ProcessValidationGate",
    "should_proceed_to_process",
    "should_proceed_to_synthesize",
]
