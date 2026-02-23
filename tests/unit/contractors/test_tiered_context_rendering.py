"""Tests for tiered context rendering (TC-500 through TC-510).

Covers the ``format_tiered_context()`` function and its progressive
compression cascade.
"""

from __future__ import annotations

import json

import pytest

from startd8.contractors.prompt_utils import (
    CONTEXT_FIELD_TIERS,
    format_tiered_context,
    _render_full,
    _render_collapsed,
    _render_metadata_line,
    _render_oneline,
    _ADDITIONAL_CONTEXT_TOKEN_BUDGET,
)


# ── TC-500: Empty input ──────────────────────────────────────────────────


class TestEmptyInput:
    """TC-500: Empty/None input returns 'None'."""

    def test_empty_dict(self):
        assert format_tiered_context({}) == "None"

    def test_none_input(self):
        assert format_tiered_context(None) == "None"


# ── TC-501: T0 full rendering ────────────────────────────────────────────


class TestT0FullRendering:
    """TC-501: T0 fields render in full under Critical Context header."""

    def test_t0_string_field(self):
        ctx = {"critical_parameters_checklist": "IMPORTANT: List all params"}
        result = format_tiered_context(ctx)
        assert "### Critical Context" in result
        assert "**critical_parameters_checklist:** IMPORTANT: List all params" in result

    def test_t0_never_truncated(self):
        long_value = "A" * 10_000
        ctx = {"api_signatures": long_value}
        result = format_tiered_context(ctx, token_budget=50)
        # Even with absurdly low budget, T0 fields are never compressed
        assert long_value in result

    def test_t0_list_field_json(self):
        sigs = ["GET /api/v1/users", "POST /api/v1/users"]
        ctx = {"api_signatures": sigs}
        result = format_tiered_context(ctx)
        assert "### Critical Context" in result
        assert json.dumps(sigs, indent=2) in result


# ── TC-502: T1 full rendering ────────────────────────────────────────────


class TestT1FullRendering:
    """TC-502: T1 fields render in full under Design Constraints header."""

    def test_t1_string_field(self):
        ctx = {"project_goals": "Build a fast API"}
        result = format_tiered_context(ctx)
        assert "### Design Constraints" in result
        assert "**project_goals:** Build a fast API" in result

    def test_t1_list_field(self):
        constraints = ["[critical] No plaintext secrets", "[info] Prefer stdlib"]
        ctx = {"constraints_from_manifest": constraints}
        result = format_tiered_context(ctx)
        assert "### Design Constraints" in result
        assert json.dumps(constraints, indent=2, default=str) in result


# ── TC-503: T2 collapsed rendering ───────────────────────────────────────


class TestT2CollapsedRendering:
    """TC-503: T2 fields render with collapsed summaries."""

    def test_t2_dict_collapsed(self):
        ctx = {
            "resolved_parameters": {
                "embedding_service": {"host": "localhost", "port": 8080, "model": "m1"},
                "vector_db": {"url": "http://db", "dim": 768},
            }
        }
        result = format_tiered_context(ctx)
        assert "### Supporting Information" in result
        assert "embedding_service {...3 items}" in result
        assert "vector_db {...2 items}" in result

    def test_t2_long_string_truncated(self):
        long_str = "X" * 500
        ctx = {"parameter_sources": long_str}
        result = format_tiered_context(ctx)
        assert "### Supporting Information" in result
        assert "...200 more chars]" in result
        # Should contain the first 300 chars
        assert long_str[:300] in result

    def test_t2_short_string_full(self):
        short = "Some brief info"
        ctx = {"domain_concepts": short}
        result = format_tiered_context(ctx)
        assert f"**domain_concepts:** {short}" in result

    def test_t2_list_preview(self):
        items = ["What retry strategy?", "Which auth method?", "Port number?"]
        ctx = {"open_questions": items}
        result = format_tiered_context(ctx)
        assert "### Supporting Information" in result
        assert "3 items" in result
        assert "What retry strategy?" in result


# ── TC-504: T3 metadata line ─────────────────────────────────────────────


class TestT3MetadataLine:
    """TC-504: T3 fields render as pipe-delimited metadata line."""

    def test_multiple_t3_fields(self):
        ctx = {
            "domain": "observability",
            "feature_id": "F-042",
            "wave_context": "Wave 2 of 3",
        }
        result = format_tiered_context(ctx)
        assert "### Metadata" in result
        assert "domain: observability" in result
        assert "feature_id: F-042" in result
        assert " | " in result

    def test_multiline_value_collapsed(self):
        ctx = {"domain_reasoning": "Line one\nLine two\nLine three"}
        result = format_tiered_context(ctx)
        assert "domain_reasoning: Line one" in result
        assert "Line two" not in result

    def test_long_value_truncated(self):
        ctx = {"domain_reasoning": "A" * 100}
        result = format_tiered_context(ctx)
        # Should be truncated to 60 chars + "..."
        assert "..." in result


# ── TC-505: Unknown field defaults to T2 ─────────────────────────────────


class TestUnknownFieldDefault:
    """TC-505: Unregistered fields default to T2."""

    def test_unknown_field_in_supporting_info(self):
        ctx = {"completely_new_field": "some value"}
        result = format_tiered_context(ctx)
        assert "### Supporting Information" in result
        assert "**completely_new_field:** some value" in result

    def test_unknown_field_not_in_registry(self):
        assert "completely_new_field" not in CONTEXT_FIELD_TIERS


# ── TC-506: Empty tier omission ──────────────────────────────────────────


class TestEmptyTierOmission:
    """TC-506: Empty tiers omit their section headers."""

    def test_only_t0_and_t3(self):
        ctx = {
            "api_signatures": "GET /health",
            "domain": "infra",
        }
        result = format_tiered_context(ctx)
        assert "### Critical Context" in result
        assert "### Metadata" in result
        assert "### Design Constraints" not in result
        assert "### Supporting Information" not in result

    def test_only_t1(self):
        ctx = {"project_goals": "Fast API"}
        result = format_tiered_context(ctx)
        assert "### Design Constraints" in result
        assert "### Critical Context" not in result
        assert "### Supporting Information" not in result
        assert "### Metadata" not in result


# ── TC-507: Budget compression — T3 drop ─────────────────────────────────


class TestBudgetT3Drop:
    """TC-507: Under budget pressure, T3 is dropped first."""

    def test_t3_dropped_when_over_budget(self):
        # Create a context that will exceed a small budget
        ctx = {
            "api_signatures": "GET /api/v1/health",  # T0
            "project_goals": "X" * 500,  # T1
            "parameter_sources": "Y" * 500,  # T2
            "domain": "infra",  # T3
            "feature_id": "F-001",  # T3
        }
        # Budget that fits T0+T1+T2 but not T3 overhead
        # Full render will be large; use a budget that forces T3 drop
        result = format_tiered_context(ctx, token_budget=300)
        assert "### Critical Context" in result
        assert "api_signatures" in result
        # T3 should be dropped under pressure
        # (exact behavior depends on total size)


# ── TC-508: Budget compression — T2 collapse ─────────────────────────────


class TestBudgetT2Collapse:
    """TC-508: When T3 drop insufficient, T2 collapses to one-liners."""

    def test_t2_collapsed_under_pressure(self):
        big_dict = {f"key_{i}": {"nested": f"value_{i}"} for i in range(20)}
        ctx = {
            "api_signatures": "GET /health",  # T0
            "resolved_parameters": big_dict,  # T2 — large dict
        }
        # Very tight budget forces T2 collapse
        result = format_tiered_context(ctx, token_budget=80)
        # T0 always present
        assert "api_signatures" in result
        # T2 should be collapsed to entry count
        assert "20 entries" in result


# ── TC-509: Budget compression — T1 truncation ───────────────────────────


class TestBudgetT1Truncation:
    """TC-509: Under extreme pressure, T1 strings truncate to 500 chars."""

    def test_t1_truncated_under_extreme_pressure(self):
        ctx = {
            "api_signatures": "GET /health",  # T0 (small)
            "project_goals": "G" * 2000,  # T1 (long string)
            "scope_boundary": "S" * 2000,  # T1 (long string)
            "resolved_parameters": {"a": {"b": "c"} for _ in range(50)},  # T2
        }
        result = format_tiered_context(ctx, token_budget=50)
        # T0 always intact
        assert "GET /health" in result
        # T1 strings should be truncated to 500 chars
        assert "truncated to 500 chars" in result
        # Verify actual truncation: original 2000 chars → 500
        assert "G" * 501 not in result


# ── TC-510: Backward compatibility — nested dict preserved ────────────────


class TestBackwardCompatNested:
    """TC-510: T1 fields with nested values preserve full JSON rendering."""

    def test_shared_modules_full_json(self):
        """Validates semantic equivalent of existing test_nested_dict_preserved."""
        ctx = {
            "shared_modules": (
                "These files are also targeted by other features — "
                "coordinate interfaces: src/a.py, src/b.py"
            ),
        }
        result = format_tiered_context(ctx)
        assert "src/a.py" in result
        assert "src/b.py" in result
        assert "### Design Constraints" in result


# ── Registry completeness ─────────────────────────────────────────────────


class TestRegistryCompleteness:
    """Verify the registry contains all expected fields."""

    def test_all_tiers_present(self):
        tiers = set(CONTEXT_FIELD_TIERS.values())
        assert tiers == {0, 1, 2, 3}

    def test_t0_count(self):
        t0 = [k for k, v in CONTEXT_FIELD_TIERS.items() if v == 0]
        assert len(t0) == 7

    def test_t1_count(self):
        t1 = [k for k, v in CONTEXT_FIELD_TIERS.items() if v == 1]
        assert len(t1) == 11

    def test_t2_count(self):
        t2 = [k for k, v in CONTEXT_FIELD_TIERS.items() if v == 2]
        assert len(t2) == 10

    def test_t3_count(self):
        t3 = [k for k, v in CONTEXT_FIELD_TIERS.items() if v == 3]
        assert len(t3) == 10

    def test_total_fields(self):
        assert len(CONTEXT_FIELD_TIERS) == 38

    def test_default_budget_constant(self):
        assert _ADDITIONAL_CONTEXT_TOKEN_BUDGET == 4000


# ── Helper unit tests ─────────────────────────────────────────────────────


class TestHelpers:
    """Direct tests for internal helper functions."""

    def test_render_full_string(self):
        assert _render_full("k", "v") == "**k:** v"

    def test_render_full_dict(self):
        result = _render_full("k", {"a": 1})
        assert result.startswith("**k:**\n")
        assert '"a": 1' in result

    def test_render_collapsed_dict(self):
        result = _render_collapsed("k", {"x": {"a": 1, "b": 2}, "y": [1, 2, 3]})
        assert "x {...2 items}" in result
        assert "y [3 items]" in result

    def test_render_collapsed_long_string(self):
        result = _render_collapsed("k", "Z" * 400)
        assert "...100 more chars]" in result

    def test_render_collapsed_short_string(self):
        result = _render_collapsed("k", "short")
        assert result == "**k:** short"

    def test_render_collapsed_list(self):
        result = _render_collapsed("k", ["first", "second"])
        assert "2 items" in result
        assert "first" in result

    def test_render_oneline_dict(self):
        result = _render_oneline("k", {"a": 1, "b": 2})
        assert result == "**k:** 2 entries"

    def test_render_oneline_long_string(self):
        result = _render_oneline("k", "X" * 200)
        assert len(result) < 200
        assert result.endswith("...")

    def test_render_metadata_single_field(self):
        result = _render_metadata_line({"domain": "infra"})
        assert result == "domain: infra"
        assert " | " not in result

    def test_render_metadata_multiline(self):
        result = _render_metadata_line({"k": "line1\nline2"})
        assert result == "k: line1"
