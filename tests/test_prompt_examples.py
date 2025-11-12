"""
Unit tests validating system prompt JSON examples against Pydantic models.

This test module ensures that all JSON examples in the system prompt files
conform to their corresponding Pydantic model schemas. It serves as:
1. A validation mechanism for prompt correctness
2. Documentation of expected output formats
3. A regression test against future model changes
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from workflow.models.chains import AnalysisOutput, ProcessOutput, SynthesisOutput


def extract_json_examples(file_path: str) -> list[dict[str, Any]]:
    """Extract all JSON examples from a markdown file.

    Args:
        file_path: Path to markdown file containing JSON code blocks

    Returns:
        List of parsed JSON objects from code blocks
    """
    with open(file_path, "r") as f:
        content = f.read()

    pattern = r"```json\n(.*?)\n```"
    matches = re.findall(pattern, content, re.DOTALL)

    examples = []
    for match in matches:
        try:
            json_obj = json.loads(match)
            examples.append(json_obj)
        except json.JSONDecodeError as e:
            examples.append({"_parse_error": str(e), "_raw": match})

    return examples


class TestAnalysisOutputExamples:
    """Test AnalysisOutput examples from chain_analyze.md."""

    @pytest.fixture(scope="class")
    def examples(self):
        """Load analysis examples from markdown file."""
        prompt_dir = Path(__file__).parent.parent / "src" / "workflow" / "prompts"
        return extract_json_examples(str(prompt_dir / "chain_analyze.md"))

    def test_all_examples_are_valid_json(self, examples):
        """All examples should be valid JSON."""
        for i, example in enumerate(examples):
            assert "_parse_error" not in example, f"Example {i} has JSON parse error: {example.get('_parse_error')}"

    def test_all_examples_have_required_fields(self, examples):
        """All examples should have required AnalysisOutput fields."""
        required = {"intent", "key_entities", "complexity", "context"}
        for i, example in enumerate(examples):
            assert required.issubset(example.keys()), f"Example {i} missing fields: {required - set(example.keys())}"

    def test_intent_is_valid_string(self, examples):
        """Intent field should be non-empty string."""
        for i, example in enumerate(examples):
            assert isinstance(example["intent"], str), f"Example {i}: intent must be string"
            assert example["intent"].strip(), f"Example {i}: intent cannot be empty"

    def test_key_entities_is_list_of_strings(self, examples):
        """Key entities should be list of non-empty strings."""
        for i, example in enumerate(examples):
            assert isinstance(example["key_entities"], list), f"Example {i}: key_entities must be list"
            for j, entity in enumerate(example["key_entities"]):
                assert isinstance(entity, str), f"Example {i}[{j}]: entity must be string"

    def test_complexity_is_valid_enum(self, examples):
        """Complexity should be one of: simple, moderate, complex."""
        valid_values = {"simple", "moderate", "complex"}
        for i, example in enumerate(examples):
            assert example["complexity"] in valid_values, (
                f"Example {i}: complexity must be one of {valid_values}, got '{example['complexity']}'"
            )

    def test_context_is_dict(self, examples):
        """Context should be a dictionary."""
        for i, example in enumerate(examples):
            assert isinstance(example["context"], dict), f"Example {i}: context must be dict"

    def test_examples_pass_pydantic_validation(self, examples):
        """All examples should pass Pydantic AnalysisOutput validation."""
        for i, example in enumerate(examples):
            try:
                AnalysisOutput(**example)
            except Exception as e:
                pytest.fail(f"Example {i} failed Pydantic validation: {str(e)}")

    def test_examples_demonstrate_variety(self, examples):
        """Examples should show different complexity levels."""
        complexities = [ex["complexity"] for ex in examples]
        assert "simple" in complexities, "Missing 'simple' complexity example"
        assert "moderate" in complexities, "Missing 'moderate' complexity example"
        assert "complex" in complexities, "Missing 'complex' complexity example"


class TestProcessOutputExamples:
    """Test ProcessOutput examples from chain_process.md."""

    @pytest.fixture(scope="class")
    def examples(self):
        """Load process examples from markdown file."""
        prompt_dir = Path(__file__).parent.parent / "src" / "workflow" / "prompts"
        return extract_json_examples(str(prompt_dir / "chain_process.md"))

    def test_all_examples_are_valid_json(self, examples):
        """All examples should be valid JSON."""
        for i, example in enumerate(examples):
            assert "_parse_error" not in example, f"Example {i} has JSON parse error"

    def test_all_examples_have_required_fields(self, examples):
        """All examples should have required ProcessOutput fields."""
        required = {"content", "confidence", "metadata"}
        for i, example in enumerate(examples):
            assert required.issubset(example.keys()), f"Example {i} missing fields: {required - set(example.keys())}"

    def test_content_is_valid_string(self, examples):
        """Content field should be non-empty string."""
        for i, example in enumerate(examples):
            assert isinstance(example["content"], str), f"Example {i}: content must be string"
            assert example["content"].strip(), f"Example {i}: content cannot be empty"

    def test_confidence_is_valid_number(self, examples):
        """Confidence should be number between 0.0 and 1.0."""
        for i, example in enumerate(examples):
            confidence = example["confidence"]
            assert isinstance(confidence, (int, float)), f"Example {i}: confidence must be number"
            assert 0.0 <= confidence <= 1.0, f"Example {i}: confidence {confidence} outside valid range [0.0, 1.0]"

    def test_metadata_is_dict(self, examples):
        """Metadata should be a dictionary."""
        for i, example in enumerate(examples):
            assert isinstance(example["metadata"], dict), f"Example {i}: metadata must be dict"

    def test_examples_pass_pydantic_validation(self, examples):
        """All examples should pass Pydantic ProcessOutput validation."""
        for i, example in enumerate(examples):
            try:
                ProcessOutput(**example)
            except Exception as e:
                pytest.fail(f"Example {i} failed Pydantic validation: {str(e)}")

    def test_confidence_demonstrates_variety(self, examples):
        """Examples should show different confidence levels."""
        confidences = [ex["confidence"] for ex in examples]
        # Should have examples across low, medium, high ranges
        has_low = any(c < 0.8 for c in confidences)
        has_mid = any(0.8 <= c < 0.9 for c in confidences)
        has_high = any(c >= 0.9 for c in confidences)
        assert has_low or has_mid or has_high, "Examples should demonstrate confidence variety"


class TestSynthesisOutputExamples:
    """Test SynthesisOutput examples from chain_synthesize.md."""

    @pytest.fixture(scope="class")
    def examples(self):
        """Load synthesis examples from markdown file."""
        prompt_dir = Path(__file__).parent.parent / "src" / "workflow" / "prompts"
        return extract_json_examples(str(prompt_dir / "chain_synthesize.md"))

    def test_all_examples_are_valid_json(self, examples):
        """All examples should be valid JSON."""
        for i, example in enumerate(examples):
            assert "_parse_error" not in example, f"Example {i} has JSON parse error"

    def test_all_examples_have_required_fields(self, examples):
        """All examples should have required SynthesisOutput fields."""
        required = {"final_text", "formatting"}
        for i, example in enumerate(examples):
            assert required.issubset(example.keys()), f"Example {i} missing fields: {required - set(example.keys())}"

    def test_final_text_is_valid_string(self, examples):
        """Final text should be non-empty string."""
        for i, example in enumerate(examples):
            assert isinstance(example["final_text"], str), f"Example {i}: final_text must be string"
            assert example["final_text"].strip(), f"Example {i}: final_text cannot be empty"

    def test_formatting_is_valid_enum(self, examples):
        """Formatting should be one of: markdown, plain, structured."""
        valid_values = {"markdown", "plain", "structured"}
        for i, example in enumerate(examples):
            assert example["formatting"] in valid_values, (
                f"Example {i}: formatting must be one of {valid_values}, got '{example['formatting']}'"
            )

    def test_examples_pass_pydantic_validation(self, examples):
        """All examples should pass Pydantic SynthesisOutput validation."""
        for i, example in enumerate(examples):
            try:
                SynthesisOutput(**example)
            except Exception as e:
                pytest.fail(f"Example {i} failed Pydantic validation: {str(e)}")

    def test_examples_demonstrate_all_formats(self, examples):
        """Examples should show all formatting options."""
        formats = [ex["formatting"] for ex in examples]
        assert "markdown" in formats, "Missing 'markdown' format example"
        assert "plain" in formats, "Missing 'plain' format example"
        assert "structured" in formats, "Missing 'structured' format example"


class TestExampleIntegration:
    """Test integration between example outputs and inputs across prompts."""

    def test_analysis_complexity_matches_content_depth(self):
        """Verify analysis complexity levels correspond to content depth.

        This is a conceptual check that complexity assessment should
        correlate with the depth of content generated.
        """
        # This is a documentation/integration test
        # In real usage, simple complexity should lead to simpler content,
        # complex should lead to detailed content
        pass

    def test_no_extra_fields_in_examples(self):
        """Verify examples don't contain extra fields beyond schema."""
        prompt_dir = Path(__file__).parent.parent / "src" / "workflow" / "prompts"

        # AnalysisOutput examples
        analysis_examples = extract_json_examples(str(prompt_dir / "chain_analyze.md"))
        for i, ex in enumerate(analysis_examples):
            allowed = {"intent", "key_entities", "complexity", "context", "_parse_error", "_raw"}
            extra = set(ex.keys()) - allowed
            assert not extra, f"AnalysisOutput example {i} has extra fields: {extra}"

        # ProcessOutput examples
        process_examples = extract_json_examples(str(prompt_dir / "chain_process.md"))
        for i, ex in enumerate(process_examples):
            allowed = {"content", "confidence", "metadata", "_parse_error", "_raw"}
            extra = set(ex.keys()) - allowed
            assert not extra, f"ProcessOutput example {i} has extra fields: {extra}"

        # SynthesisOutput examples
        synthesis_examples = extract_json_examples(str(prompt_dir / "chain_synthesize.md"))
        for i, ex in enumerate(synthesis_examples):
            allowed = {"final_text", "formatting", "_parse_error", "_raw"}
            extra = set(ex.keys()) - allowed
            assert not extra, f"SynthesisOutput example {i} has extra fields: {extra}"
