"""Tests for implementation_engine.budget — constants and truncation utilities."""

import pytest

from startd8.implementation_engine.budget import (
    ARCH_CONTEXT_MAX_CHARS,
    DRAFT_SIZE_REGRESSION_MIN_LINES,
    DRAFT_SIZE_REGRESSION_THRESHOLD,
    EXISTING_FILES_BUDGET_BYTES,
    PLAN_CONTEXT_MAX_CHARS,
    SEARCH_REPLACE_LINE_THRESHOLD,
    SPEC_CONTEXT_BUDGET_CHARS,
    TRUNCATION_MARKER,
    truncate_arch_context,
    truncate_with_marker,
)


# ---------------------------------------------------------------------------
# Constants verification
# ---------------------------------------------------------------------------

class TestBudgetConstants:
    def test_plan_context_max(self):
        assert PLAN_CONTEXT_MAX_CHARS == 16_384

    def test_arch_context_max(self):
        assert ARCH_CONTEXT_MAX_CHARS == 4_096

    def test_spec_context_budget(self):
        assert SPEC_CONTEXT_BUDGET_CHARS == 12_000

    def test_existing_files_budget(self):
        assert EXISTING_FILES_BUDGET_BYTES == 40 * 1024

    def test_search_replace_threshold(self):
        assert SEARCH_REPLACE_LINE_THRESHOLD == 50

    def test_truncation_marker_is_string(self):
        assert isinstance(TRUNCATION_MARKER, str)
        assert len(TRUNCATION_MARKER) > 0

    def test_size_regression_threshold(self):
        assert DRAFT_SIZE_REGRESSION_THRESHOLD == 0.20

    def test_size_regression_min_lines(self):
        assert DRAFT_SIZE_REGRESSION_MIN_LINES == 50


# ---------------------------------------------------------------------------
# truncate_with_marker
# ---------------------------------------------------------------------------

class TestTruncateWithMarker:
    def test_no_truncation_needed(self):
        text = "Short text"
        result = truncate_with_marker(text, 100)
        assert result == text

    def test_exact_length(self):
        text = "x" * 50
        result = truncate_with_marker(text, 50)
        assert result == text

    def test_truncation_appends_marker(self):
        text = "x" * 200
        result = truncate_with_marker(text, 100)
        assert len(result) == 100
        assert result.endswith(TRUNCATION_MARKER)

    def test_custom_marker(self):
        text = "x" * 100
        result = truncate_with_marker(text, 50, marker="...")
        assert len(result) == 50
        assert result.endswith("...")

    def test_max_chars_zero(self):
        assert truncate_with_marker("any text", 0) == ""

    def test_max_chars_negative(self):
        assert truncate_with_marker("any text", -5) == ""

    def test_max_chars_less_than_marker(self):
        result = truncate_with_marker("x" * 100, 5)
        assert len(result) == 5
        assert result == TRUNCATION_MARKER[:5]

    def test_empty_text(self):
        assert truncate_with_marker("", 100) == ""

    def test_none_text(self):
        assert truncate_with_marker(None, 100) is None

    def test_text_shorter_than_max(self):
        assert truncate_with_marker("hello", 1000) == "hello"


# ---------------------------------------------------------------------------
# truncate_arch_context
# ---------------------------------------------------------------------------

class TestTruncateArchContext:
    def test_falsy_returns_empty(self):
        assert truncate_arch_context(None, 100) == ""
        assert truncate_arch_context("", 100) == ""
        assert truncate_arch_context({}, 100) == ""

    def test_string_truncation(self):
        text = "x" * 200
        result = truncate_arch_context(text, 100)
        assert len(result) == 100
        assert result.endswith(TRUNCATION_MARKER)

    def test_string_no_truncation(self):
        text = "Short arch context"
        result = truncate_arch_context(text, 1000)
        assert result == text

    def test_dict_with_objectives_list(self):
        ctx = {"objectives": ["Obj 1", "Obj 2", "Obj 3", "Obj 4"]}
        result = truncate_arch_context(ctx, 5000)
        assert "Objectives" in result
        # Only first 3 objectives
        assert "Obj 1" in result
        assert "Obj 2" in result
        assert "Obj 3" in result

    def test_dict_with_objectives_string(self):
        ctx = {"objectives": "Single objective string"}
        result = truncate_arch_context(ctx, 5000)
        assert "Single objective string" in result

    def test_dict_with_project_objectives_key(self):
        ctx = {"project_objectives": ["PO 1"]}
        result = truncate_arch_context(ctx, 5000)
        assert "PO 1" in result

    def test_dict_with_constraints(self):
        ctx = {
            "constraints": [f"Constraint {i}" for i in range(10)],
        }
        result = truncate_arch_context(ctx, 5000)
        # Only first 5 constraints
        assert "Constraint 0" in result
        assert "Constraint 4" in result

    def test_dict_truncation_overflow(self):
        ctx = {
            "objectives": [f"Very long objective {i}" * 50 for i in range(3)],
        }
        result = truncate_arch_context(ctx, 100)
        assert len(result) == 100

    def test_other_type_stringified(self):
        result = truncate_arch_context(42, 100)
        assert "42" in result

    def test_dict_empty_values(self):
        ctx = {"objectives": None, "constraints": None}
        result = truncate_arch_context(ctx, 5000)
        # No sections means empty result
        assert result == ""
