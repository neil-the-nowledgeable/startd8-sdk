"""Tests for QualitySpec threshold validation in the contract system.

Validates that:
- DESIGN exit section_count threshold works (>= 2 sections)
- IMPLEMENT entry line_count threshold works (>= 50 lines on design_results)
- IMPLEMENT exit line_count threshold works (>= 10 lines on generation_results)
- Unknown metrics (success_rate, total_passed) are skipped gracefully

The ``_QUALITY_EXTRACTORS`` dict only supports: line_count, char_count,
section_count, length. Metrics like ``success_rate`` and ``total_passed``
declared in the contract YAML have no corresponding extractor and are
silently skipped — tests document this gap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from contextcore.contracts.propagation import BoundaryValidator
from contextcore.contracts.propagation.schema import ContextContract
from contextcore.contracts.propagation.validator import QualityViolation

from .conftest import (
    build_design_exit_context,
    build_full_pipeline_context,
    build_implement_exit_context,
    build_plan_exit_context,
    build_scaffold_exit_context,
)


class TestDesignExitQuality:
    """DESIGN exit: design_results quality metric = section_count, threshold = 2."""

    def test_section_count_on_dict_always_zero(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """design_results is a dict → str(dict) has no ``##`` headers.

        The quality extractor runs ``section_count`` on the stringified
        dict, which is a Python repr — no Markdown headers present.
        This documents a gap: section_count is meaningful for prose strings,
        not for dicts.  Exit still passes (warning severity).
        """
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        result = validator.validate_exit("design", ctx, loaded_contract)
        # Warning severity: exit still passes
        assert result.passed is True
        # But there IS a quality violation (section_count=0 < 2)
        design_violations = [
            v for v in result.quality_violations
            if v.field == "design_results" and v.metric == "section_count"
        ]
        assert len(design_violations) == 1
        assert design_violations[0].actual == 0.0

    def test_warns_with_insufficient_sections(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """Design doc with 0-1 ## headers triggers warning violation."""
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        # Create design_results with minimal content (no ## headers)
        ctx["design_results"] = {
            "T1": {"status": "completed", "domain": "backend", "design_doc": "Just a line"},
            "T2": {"status": "completed", "domain": "frontend", "design_doc": "Another line"},
        }
        result = validator.validate_exit("design", ctx, loaded_contract)
        # Warning severity: should still pass but with quality violations
        assert result.passed is True
        violations = [
            v for v in result.quality_violations if v.metric == "section_count"
        ]
        assert len(violations) > 0
        assert violations[0].actual < 2.0


class TestImplementEntryQuality:
    """IMPLEMENT entry: design_results quality metric = line_count, threshold = 50, blocking."""

    def test_line_count_on_dict_always_low(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """design_results is a dict → str(dict) is ~1 line.

        The quality extractor runs ``line_count`` on the stringified dict
        repr, which is a single line regardless of content inside.
        Blocking severity → entry fails.  This documents a gap: line_count
        is meaningful for prose/code strings, not for dicts.
        """
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        result = validator.validate_entry("implement", ctx, loaded_contract)
        # Blocking severity: entry fails
        assert result.passed is False
        violations = [v for v in result.quality_violations if v.metric == "line_count"]
        assert len(violations) > 0
        assert violations[0].actual < 50.0

    def test_fails_with_too_few_lines(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """Design results with <50 lines fails as blocking."""
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        # Create design_results with very short content
        ctx["design_results"] = {
            "T1": {"status": "completed", "domain": "backend", "design_doc": "short"},
        }
        result = validator.validate_entry("implement", ctx, loaded_contract)
        # This is a blocking quality gate
        assert result.passed is False
        violations = [
            v for v in result.quality_violations if v.metric == "line_count"
        ]
        assert len(violations) > 0
        assert violations[0].threshold == 50.0


class TestImplementExitQuality:
    """IMPLEMENT exit: generation_results quality metric = line_count, threshold = 10, warning."""

    def test_passes_with_enough_gen_content(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        result = validator.validate_exit("implement", ctx, loaded_contract)
        assert result.passed is True

    def test_warns_with_minimal_gen_content(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """generation_results with <10 lines triggers warning (not blocking)."""
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        ctx["implementation"] = {"task_reports": {}}
        ctx["generation_results"] = {"T1": "x"}  # Minimal content
        ctx["truncation_flags"] = {}
        result = validator.validate_exit("implement", ctx, loaded_contract)
        # Warning severity: should still pass
        assert result.passed is True
        violations = [
            v for v in result.quality_violations
            if v.metric == "line_count" and v.field == "generation_results"
        ]
        assert len(violations) > 0


class TestUnknownQualityMetrics:
    """Metrics declared in YAML but not in _QUALITY_EXTRACTORS are skipped.

    The contract declares ``success_rate`` (integrate exit) and
    ``total_passed`` (test exit, review exit) but these have no
    corresponding extractor in the validator — they are silently
    skipped rather than raising errors.
    """

    def test_integrate_exit_success_rate_skipped_gracefully(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """integrate exit declares success_rate metric — no crash."""
        ctx = build_full_pipeline_context(tmp_path)
        result = validator.validate_exit("integrate", ctx, loaded_contract)
        # Should pass without crashing despite unknown metric
        assert result.passed is True
        # No quality violations for success_rate (metric unknown → skipped)
        success_rate_violations = [
            v for v in result.quality_violations if v.metric == "success_rate"
        ]
        assert len(success_rate_violations) == 0

    def test_test_exit_total_passed_skipped_gracefully(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """test exit declares total_passed metric — no crash."""
        ctx = build_full_pipeline_context(tmp_path)
        result = validator.validate_exit("test", ctx, loaded_contract)
        assert result.passed is True
        total_passed_violations = [
            v for v in result.quality_violations if v.metric == "total_passed"
        ]
        assert len(total_passed_violations) == 0

    def test_review_exit_total_passed_skipped_gracefully(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """review exit declares total_passed metric — no crash."""
        ctx = build_full_pipeline_context(tmp_path)
        result = validator.validate_exit("review", ctx, loaded_contract)
        assert result.passed is True
        total_passed_violations = [
            v for v in result.quality_violations if v.metric == "total_passed"
        ]
        assert len(total_passed_violations) == 0
