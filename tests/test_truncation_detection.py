"""
Tests for truncation detection functionality.

This module tests the truncation detection utilities that prevent
corrupted/incomplete LLM outputs from being saved or passed to
subsequent pipeline steps.
"""

import pytest
from startd8.truncation_detection import (
    detect_truncation,
    TruncationResult,
    get_truncation_warning_message,
    estimate_document_sections,
)
from startd8.exceptions import TruncationError


class TestDetectTruncation:
    """Tests for the detect_truncation function."""
    
    def test_empty_output_is_truncated(self):
        """Empty output should always be detected as truncated."""
        result = detect_truncation("", "Some input")
        assert result.is_truncated
        assert result.confidence == 1.0
        assert "Empty output" in result.indicators
    
    def test_whitespace_only_is_truncated(self):
        """Whitespace-only output should be detected as truncated."""
        result = detect_truncation("   \n\t  ", "Some input")
        assert result.is_truncated
        assert result.confidence == 1.0
    
    def test_complete_output_not_truncated(self):
        """Normal complete output should not be detected as truncated."""
        result = detect_truncation(
            "This is a complete sentence.\n\nEnd of document.",
            "Test input"
        )
        assert not result.is_truncated
        assert result.confidence == 0.0
        assert len(result.indicators) == 0
    
    def test_unclosed_code_block(self):
        """Unclosed code block should be detected."""
        result = detect_truncation(
            "Here is some code:\n```python\ndef hello():\n    print('hi')",
            "Test input"
        )
        assert result.is_truncated
        assert any("code block" in ind.lower() for ind in result.indicators)
    
    def test_closed_code_block_ok(self):
        """Properly closed code block should not trigger truncation."""
        result = detect_truncation(
            "Here is some code:\n```python\ndef hello():\n    print('hi')\n```\nDone.",
            "Test input"
        )
        # Should not be truncated due to code blocks
        code_block_issues = [ind for ind in result.indicators if "code block" in ind.lower()]
        assert len(code_block_issues) == 0
    
    def test_unclosed_json_braces(self):
        """Unclosed JSON braces should be detected."""
        result = detect_truncation(
            '{"key": "value", "nested": {"inner":',
            "Test input"
        )
        assert result.is_truncated
        assert any("brace" in ind.lower() or "json" in ind.lower() for ind in result.indicators)
    
    def test_unclosed_json_brackets(self):
        """Unclosed JSON brackets should be detected."""
        result = detect_truncation(
            '["item1", "item2", ["nested"',
            "Test input"
        )
        assert result.is_truncated
        assert any("bracket" in ind.lower() or "json" in ind.lower() for ind in result.indicators)
    
    def test_mid_sentence_ending_with_comma(self):
        """Ending with comma should be flagged."""
        result = detect_truncation(
            "This is a list of items: one, two,",
            "Test input"
        )
        assert any("comma" in ind.lower() or "mid-sentence" in ind.lower() for ind in result.indicators)
    
    def test_mid_sentence_ending_with_colon(self):
        """Ending with colon should be flagged."""
        result = detect_truncation(
            "The following items are:",
            "Test input"
        )
        assert any("colon" in ind.lower() or "mid-sentence" in ind.lower() for ind in result.indicators)
    
    def test_output_too_short_ratio(self):
        """Output much shorter than input should be flagged."""
        long_input = "A" * 10000
        short_output = "B" * 1000  # 10% of input
        
        result = detect_truncation(
            short_output,
            long_input,
            min_output_ratio=0.3  # Expect at least 30%
        )
        assert result.is_truncated
        assert any("short" in ind.lower() or "ratio" in ind.lower() for ind in result.indicators)
        assert result.details.get("length_ratio") == pytest.approx(0.1, rel=0.01)
    
    def test_output_length_ratio_acceptable(self):
        """Output with acceptable length ratio should not be flagged for length."""
        input_text = "A" * 1000
        output_text = "B" * 500  # 50% of input
        
        result = detect_truncation(
            output_text,
            input_text,
            min_output_ratio=0.3  # Expect at least 30%
        )
        # Should not have length ratio issue
        length_issues = [ind for ind in result.indicators if "short" in ind.lower() and "ratio" in ind.lower()]
        assert len(length_issues) == 0
    
    def test_strict_mode_more_sensitive(self):
        """Strict mode should have lower threshold for detection."""
        # Text with minor issues that might not trigger in normal mode
        text = "This is almost complete but"
        
        normal_result = detect_truncation(text, "Test", strict_mode=False)
        strict_result = detect_truncation(text, "Test", strict_mode=True)
        
        # Strict mode should have same or higher confidence
        assert strict_result.confidence >= normal_result.confidence
        # If confidence is borderline, strict might flag it while normal doesn't
        if 0.3 <= normal_result.confidence < 0.5:
            assert strict_result.is_truncated and not normal_result.is_truncated
    
    def test_missing_expected_sections(self):
        """Missing expected sections should be flagged."""
        result = detect_truncation(
            "# Introduction\n\nSome intro text.",
            "Test input",
            expected_sections=["Introduction", "Methods", "Results", "Conclusion"]
        )
        # Should flag missing sections
        assert "missing_sections" in result.details
        assert len(result.details["missing_sections"]) >= 3  # At least Methods, Results, Conclusion
    
    def test_all_expected_sections_present(self):
        """All expected sections present should not flag."""
        result = detect_truncation(
            "## Introduction\nText\n## Methods\nText\n## Results\nText\n## Conclusion\nText",
            "Test input",
            expected_sections=["Introduction", "Methods", "Results", "Conclusion"]
        )
        # Should not have section issues
        if "missing_sections" in result.details:
            assert len(result.details["missing_sections"]) < 2  # Allow 1 minor mismatch


class TestTruncationResult:
    """Tests for TruncationResult dataclass."""
    
    def test_bool_true_when_truncated(self):
        """TruncationResult should be truthy when truncated."""
        result = TruncationResult(
            is_truncated=True,
            confidence=0.8,
            indicators=["Test"],
            details={}
        )
        assert bool(result) is True
    
    def test_bool_false_when_not_truncated(self):
        """TruncationResult should be falsy when not truncated."""
        result = TruncationResult(
            is_truncated=False,
            confidence=0.2,
            indicators=[],
            details={}
        )
        assert bool(result) is False


class TestTruncationError:
    """Tests for TruncationError exception."""
    
    def test_error_attributes(self):
        """TruncationError should store all attributes."""
        error = TruncationError(
            message="Test truncation",
            step_name="polish",
            input_length=10000,
            output_length=2000,
            truncation_indicators=["Unclosed code block"],
            original_input="Test input"
        )
        
        assert error.step_name == "polish"
        assert error.input_length == 10000
        assert error.output_length == 2000
        assert "Unclosed code block" in error.truncation_indicators
        assert error.original_input == "Test input"
    
    def test_error_str_includes_details(self):
        """TruncationError string representation should include details."""
        error = TruncationError(
            message="Test truncation",
            step_name="polish",
            input_length=10000,
            output_length=2000,
            truncation_indicators=["Unclosed code block"]
        )
        
        error_str = str(error)
        assert "polish" in error_str
        assert "10000" in error_str or "10,000" in error_str
        assert "2000" in error_str or "2,000" in error_str


class TestGetTruncationWarningMessage:
    """Tests for get_truncation_warning_message function."""
    
    def test_returns_empty_for_non_truncated(self):
        """Should return empty string for non-truncated result."""
        result = TruncationResult(
            is_truncated=False,
            confidence=0.1,
            indicators=[],
            details={}
        )
        message = get_truncation_warning_message(result)
        assert message == ""
    
    def test_includes_indicators_for_truncated(self):
        """Should include indicators in warning message."""
        result = TruncationResult(
            is_truncated=True,
            confidence=0.8,
            indicators=["Unclosed code block", "Mid-sentence ending"],
            details={"length_ratio": 0.2}
        )
        message = get_truncation_warning_message(result, step_name="polish")
        
        assert "TRUNCATION" in message
        assert "polish" in message
        assert "Unclosed code block" in message
        assert "Mid-sentence ending" in message


class TestEstimateDocumentSections:
    """Tests for estimate_document_sections function."""
    
    def test_extracts_markdown_headers(self):
        """Should extract section names from markdown headers."""
        doc = """
# Introduction
Some text

## Methods
More text

### Data Collection
Details

## Results
Findings
"""
        sections = estimate_document_sections(doc)
        assert "Introduction" in sections
        assert "Methods" in sections
        assert "Results" in sections
    
    def test_handles_empty_document(self):
        """Should return empty list for empty document."""
        sections = estimate_document_sections("")
        assert sections == []
    
    def test_handles_no_sections(self):
        """Should return empty list for document without sections."""
        doc = "Just some plain text without any headers or structure."
        sections = estimate_document_sections(doc)
        assert len(sections) == 0

