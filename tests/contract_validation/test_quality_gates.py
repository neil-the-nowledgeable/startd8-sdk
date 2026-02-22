"""Tests for QualitySpec threshold validation in the contract system.

Validates that:
- DESIGN exit section_count threshold works (>= 2 sections)
- IMPLEMENT entry line_count threshold warns (>= 50 lines on design_results, CV-500)
- IMPLEMENT exit line_count threshold works (>= 10 lines on generation_results)
- INTEGRATE exit success_rate threshold works (>= 0.5, CV-501)
- TEST/REVIEW exit total_passed metric works (CV-501)
"""

from __future__ import annotations

from pathlib import Path

from contextcore.contracts.propagation import BoundaryValidator
from contextcore.contracts.propagation.schema import ContextContract

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
    """IMPLEMENT entry: design_results quality metric = line_count, threshold = 50, warning.

    Downgraded from blocking to warning (CV-500) because line_count on a dict
    value always measures ~1 line (Python repr). Entry still passes.
    """

    def test_line_count_on_dict_warns_but_passes(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """design_results is a dict → str(dict) is ~1 line.

        The quality extractor runs ``line_count`` on the stringified dict
        repr, which is a single line regardless of content inside.
        Warning severity → entry passes with quality violation.
        """
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        result = validator.validate_entry("implement", ctx, loaded_contract)
        # Warning severity: entry passes
        assert result.passed is True
        violations = [v for v in result.quality_violations if v.metric == "line_count"]
        assert len(violations) > 0
        assert violations[0].actual < 50.0

    def test_warns_with_too_few_lines(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """Design results with <50 lines produces a warning violation."""
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        # Create design_results with very short content
        ctx["design_results"] = {
            "T1": {"status": "completed", "domain": "backend", "design_doc": "short"},
        }
        result = validator.validate_entry("implement", ctx, loaded_contract)
        # Warning severity: entry passes
        assert result.passed is True
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


class TestIntegrateExitSuccessRate:
    """INTEGRATE exit: integration_results quality metric = success_rate, threshold = 0.5, warning."""

    def test_passes_with_all_successful(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """All tasks succeed → success_rate = 1.0 → no violation."""
        ctx = build_full_pipeline_context(tmp_path)
        result = validator.validate_exit("integrate", ctx, loaded_contract)
        assert result.passed is True
        sr_violations = [
            v for v in result.quality_violations if v.metric == "success_rate"
        ]
        assert len(sr_violations) == 0

    def test_warns_when_all_fail(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """All tasks fail → success_rate = 0.0 → warning violation (not blocking)."""
        ctx = build_full_pipeline_context(tmp_path)
        ctx["integration_results"] = {
            "T1": {"success": False, "integrated_files": [], "errors": ["syntax error"]},
            "T2": {"success": False, "integrated_files": [], "errors": ["lint error"]},
        }
        result = validator.validate_exit("integrate", ctx, loaded_contract)
        # Warning severity: exit still passes
        assert result.passed is True
        sr_violations = [
            v for v in result.quality_violations if v.metric == "success_rate"
        ]
        assert len(sr_violations) == 1
        assert sr_violations[0].actual == 0.0
        assert sr_violations[0].threshold == 0.5

    def test_warns_when_below_threshold(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """1 of 3 succeeds → success_rate ≈ 0.33 < 0.5 → warning."""
        ctx = build_full_pipeline_context(tmp_path)
        ctx["integration_results"] = {
            "T1": {"success": True, "integrated_files": ["src/auth/login.py"], "errors": []},
            "T2": {"success": False, "integrated_files": [], "errors": ["error"]},
            "T3": {"success": False, "integrated_files": [], "errors": ["error"]},
        }
        result = validator.validate_exit("integrate", ctx, loaded_contract)
        assert result.passed is True
        sr_violations = [
            v for v in result.quality_violations if v.metric == "success_rate"
        ]
        assert len(sr_violations) == 1
        assert sr_violations[0].actual < 0.5


class TestTestReviewExitTotalPassed:
    """TEST and REVIEW exit: total_passed metric is now enforced."""

    def test_test_exit_total_passed_extracted(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """TEST exit: total_passed = 2 → no violation."""
        ctx = build_full_pipeline_context(tmp_path)
        result = validator.validate_exit("test", ctx, loaded_contract)
        assert result.passed is True

    def test_review_exit_total_passed_extracted(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """REVIEW exit: total_passed = 2 → no violation."""
        ctx = build_full_pipeline_context(tmp_path)
        result = validator.validate_exit("review", ctx, loaded_contract)
        assert result.passed is True

    def test_test_exit_warns_when_zero_passed(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """TEST exit: total_passed = 0 → warning violation (threshold >= 1)."""
        ctx = build_full_pipeline_context(tmp_path)
        ctx["test_results"] = {
            "test_plan": [],
            "total_passed": 0,
            "total_failed": 2,
            "per_task": {
                "T1": {"passed": False, "validators_run": ["ruff"]},
                "T2": {"passed": False, "validators_run": ["ruff"]},
            },
            "unique_validators": ["ruff"],
        }
        result = validator.validate_exit("test", ctx, loaded_contract)
        # Warning severity: exit still passes
        assert result.passed is True
        tp_violations = [
            v for v in result.quality_violations if v.metric == "total_passed"
        ]
        assert len(tp_violations) == 1
        assert tp_violations[0].actual == 0.0
        assert tp_violations[0].threshold == 1.0
