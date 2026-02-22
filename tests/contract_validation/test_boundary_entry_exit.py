"""Tests for BoundaryValidator entry/exit validation at every phase boundary.

Validates that:
- Entry validation passes with required context keys present
- Entry validation fails (blocking_failures) when required keys are missing
- Exit validation passes when phase output is complete
- Exit validation fails when required output keys are missing
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from contextcore.contracts.propagation import BoundaryValidator
from contextcore.contracts.propagation.schema import ContextContract
from contextcore.contracts.propagation.validator import ContractValidationResult
from contextcore.contracts.types import PropagationStatus

from .conftest import (
    build_design_exit_context,
    build_finalize_exit_context,
    build_full_pipeline_context,
    build_implement_exit_context,
    build_integrate_exit_context,
    build_plan_exit_context,
    build_review_exit_context,
    build_scaffold_exit_context,
    build_test_exit_context,
)


# ============================================================================
# PLAN phase
# ============================================================================


class TestPlanBoundary:

    def test_entry_passes_with_project_root(
        self, loaded_contract: ContextContract, validator: BoundaryValidator,
    ) -> None:
        ctx = {"project_root": "/tmp/test"}
        result = validator.validate_entry("plan", ctx, loaded_contract)
        assert result.passed is True
        assert not result.blocking_failures

    def test_entry_fails_without_project_root(
        self, loaded_contract: ContextContract, validator: BoundaryValidator,
    ) -> None:
        ctx: dict[str, Any] = {}
        result = validator.validate_entry("plan", ctx, loaded_contract)
        assert result.passed is False
        assert "project_root" in result.blocking_failures

    def test_exit_passes_with_full_plan_output(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        result = validator.validate_exit("plan", ctx, loaded_contract)
        assert result.passed is True
        assert not result.blocking_failures

    def test_exit_fails_without_tasks(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        del ctx["tasks"]
        result = validator.validate_exit("plan", ctx, loaded_contract)
        assert result.passed is False
        assert "tasks" in result.blocking_failures


# ============================================================================
# SCAFFOLD phase
# ============================================================================


class TestScaffoldBoundary:

    def test_entry_passes_with_required_keys(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        result = validator.validate_entry("scaffold", ctx, loaded_contract)
        assert result.passed is True

    def test_entry_fails_without_tasks(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        del ctx["tasks"]
        result = validator.validate_entry("scaffold", ctx, loaded_contract)
        assert result.passed is False
        assert "tasks" in result.blocking_failures

    def test_exit_passes_with_scaffold_dict(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        result = validator.validate_exit("scaffold", ctx, loaded_contract)
        assert result.passed is True

    def test_exit_fails_without_scaffold(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        # No scaffold key
        result = validator.validate_exit("scaffold", ctx, loaded_contract)
        assert result.passed is False
        assert "scaffold" in result.blocking_failures


# ============================================================================
# DESIGN phase
# ============================================================================


class TestDesignBoundary:

    def test_entry_passes_with_tasks_and_index(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        result = validator.validate_entry("design", ctx, loaded_contract)
        assert result.passed is True

    def test_entry_fails_without_task_index(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        del ctx["task_index"]
        result = validator.validate_entry("design", ctx, loaded_contract)
        assert result.passed is False
        assert "task_index" in result.blocking_failures

    def test_exit_passes_with_design_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        result = validator.validate_exit("design", ctx, loaded_contract)
        assert result.passed is True

    def test_exit_fails_without_design_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        result = validator.validate_exit("design", ctx, loaded_contract)
        assert result.passed is False
        assert "design_results" in result.blocking_failures


# ============================================================================
# IMPLEMENT phase
# ============================================================================


class TestImplementBoundary:

    def test_entry_warns_on_quality_gate_for_dict(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """IMPLEMENT entry has a warning line_count >= 50 quality gate on
        design_results (downgraded from blocking per CV-500). Since
        design_results is a dict, str(dict) produces ~1 line → quality
        check reports line_count=1.0 < 50.0 as a warning, not blocking.
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

    def test_entry_fails_without_design_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        result = validator.validate_entry("implement", ctx, loaded_contract)
        assert result.passed is False
        assert "design_results" in result.blocking_failures

    def test_exit_passes_with_implementation_and_gen_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        result = validator.validate_exit("implement", ctx, loaded_contract)
        assert result.passed is True

    def test_exit_fails_without_generation_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        ctx["implementation"] = {"task_reports": {}}
        result = validator.validate_exit("implement", ctx, loaded_contract)
        assert result.passed is False
        assert "generation_results" in result.blocking_failures


# ============================================================================
# INTEGRATE phase
# ============================================================================


class TestIntegrateBoundary:

    def test_entry_passes_with_generation_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        result = validator.validate_entry("integrate", ctx, loaded_contract)
        assert result.passed is True

    def test_entry_fails_without_generation_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        result = validator.validate_entry("integrate", ctx, loaded_contract)
        assert result.passed is False
        assert "generation_results" in result.blocking_failures

    def test_exit_passes_with_integration_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        build_integrate_exit_context(ctx)
        result = validator.validate_exit("integrate", ctx, loaded_contract)
        assert result.passed is True

    def test_exit_fails_without_integration_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        result = validator.validate_exit("integrate", ctx, loaded_contract)
        assert result.passed is False
        assert "integration_results" in result.blocking_failures


# ============================================================================
# TEST phase
# ============================================================================


class TestTestBoundary:

    def test_entry_passes_with_tasks_and_gen_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        result = validator.validate_entry("test", ctx, loaded_contract)
        assert result.passed is True

    def test_entry_fails_without_tasks(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        del ctx["tasks"]
        result = validator.validate_entry("test", ctx, loaded_contract)
        assert result.passed is False
        assert "tasks" in result.blocking_failures

    def test_exit_passes_with_test_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        build_integrate_exit_context(ctx)
        build_test_exit_context(ctx)
        result = validator.validate_exit("test", ctx, loaded_contract)
        assert result.passed is True

    def test_exit_fails_without_test_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        build_integrate_exit_context(ctx)
        result = validator.validate_exit("test", ctx, loaded_contract)
        assert result.passed is False
        assert "test_results" in result.blocking_failures


# ============================================================================
# REVIEW phase
# ============================================================================


class TestReviewBoundary:

    def test_entry_passes_with_generation_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        result = validator.validate_entry("review", ctx, loaded_contract)
        assert result.passed is True

    def test_entry_fails_without_generation_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx: dict[str, Any] = {}
        result = validator.validate_entry("review", ctx, loaded_contract)
        assert result.passed is False
        assert "generation_results" in result.blocking_failures

    def test_exit_passes_with_review_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        build_integrate_exit_context(ctx)
        build_test_exit_context(ctx)
        build_review_exit_context(ctx)
        result = validator.validate_exit("review", ctx, loaded_contract)
        assert result.passed is True

    def test_exit_fails_without_review_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        result = validator.validate_exit("review", ctx, loaded_contract)
        assert result.passed is False
        assert "review_results" in result.blocking_failures


# ============================================================================
# FINALIZE phase
# ============================================================================


class TestFinalizeBoundary:

    def test_entry_passes_with_tasks_and_gen_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        result = validator.validate_entry("finalize", ctx, loaded_contract)
        assert result.passed is True

    def test_entry_fails_without_generation_results(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        result = validator.validate_entry("finalize", ctx, loaded_contract)
        assert result.passed is False
        assert "generation_results" in result.blocking_failures

    def test_exit_passes_with_workflow_summary(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        result = validator.validate_exit("finalize", ctx, loaded_contract)
        assert result.passed is True

    def test_exit_fails_without_workflow_summary(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["workflow_summary"]
        result = validator.validate_exit("finalize", ctx, loaded_contract)
        assert result.passed is False
        assert "workflow_summary" in result.blocking_failures
