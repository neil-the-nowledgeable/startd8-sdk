"""Dry-run integration test exercising all 7 ArtisanContractorWorkflow phases.

Verifies the full PLAN -> SCAFFOLD -> DESIGN -> IMPLEMENT -> TEST -> REVIEW -> FINALIZE
pipeline wires together correctly by:

1. Loading a minimal enriched context seed from a tmp_path fixture.
2. Using ContextSeedHandlers.create_all() to build all 7 handlers.
3. Registering them with ArtisanContractorWorkflow.
4. Executing with dry_run=True (no LLM calls needed).
5. Asserting that every phase produced the expected context keys per
   the context dict contract at the top of context_seed_handlers.py.

Context dict contract (keys populated by each phase):
    After PLAN:      tasks, task_index, plan_title, preflight_summary, domain_summary,
                     enriched_seed_path
    After SCAFFOLD:  scaffold (summary dict)
    After DESIGN:    design_results (Dict[task_id, dict])
    After IMPLEMENT: implementation (output dict), generation_results (Dict)
    After TEST:      test_results (Dict with test_plan, per_task, total_cost)
    After REVIEW:    review_results (Dict with review_items, per_task, total_cost)
    After FINALIZE:  workflow_summary (final manifest dict)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from startd8.contractors.artisan_contractor import (
    ArtisanContractorWorkflow,
    PhaseStatus,
    WorkflowConfig,
    WorkflowPhase,
    WorkflowStatus,
)
from startd8.contractors.context_seed_handlers import (
    ContextSeedHandlers,
    HandlerConfig,
)


# ============================================================================
# Fixtures
# ============================================================================


def _build_enriched_seed(tmp_path: Path) -> Path:
    """Create a minimal enriched context seed JSON file with 2 tasks.

    The seed structure mirrors what PlanIngestionWorkflow + DomainPreflightWorkflow
    produce: top-level ``plan``, ``_preflight``, and ``tasks`` keys.
    """
    seed_data = {
        "plan": {
            "title": "Test Integration Plan",
            "goals": ["Verify 8-phase pipeline integration"],
        },
        "_preflight": {
            "check_summary": {"pass": 2, "fail": 0, "warn": 0},
        },
        "tasks": [
            {
                "task_id": "T1",
                "title": "Add user authentication",
                "task_type": "task",
                "story_points": 3,
                "priority": "high",
                "labels": ["auth"],
                "depends_on": [],
                "config": {
                    "task_description": "Implement JWT-based user authentication",
                    "context": {
                        "target_files": ["src/auth/login.py"],
                        "estimated_loc": 80,
                        "feature_id": "F-AUTH-001",
                    },
                },
                "_enrichment": {
                    "domain": "backend",
                    "domain_reasoning": "Server-side auth logic",
                    "environment_checks": [],
                    "prompt_constraints": ["Use type hints", "Add docstrings"],
                    "post_generation_validators": ["ruff", "mypy"],
                    "available_siblings": ["src/auth/__init__.py"],
                    "existing_content_hash": None,
                },
            },
            {
                "task_id": "T2",
                "title": "Create dashboard component",
                "task_type": "task",
                "story_points": 5,
                "priority": "medium",
                "labels": ["frontend"],
                "depends_on": ["T1"],
                "config": {
                    "task_description": "Build the main dashboard UI component",
                    "context": {
                        "target_files": ["src/ui/dashboard.py"],
                        "estimated_loc": 120,
                        "feature_id": "F-DASH-001",
                    },
                },
                "_enrichment": {
                    "domain": "frontend",
                    "domain_reasoning": "UI component logic",
                    "environment_checks": [],
                    "prompt_constraints": ["Follow component patterns"],
                    "post_generation_validators": ["ruff"],
                    "available_siblings": [],
                    "existing_content_hash": None,
                },
            },
        ],
    }

    seed_path = tmp_path / "enriched-seed.json"
    seed_path.write_text(json.dumps(seed_data), encoding="utf-8")
    return seed_path


def _create_workflow_and_handlers(
    tmp_path: Path,
    seed_path: Path,
) -> tuple[ArtisanContractorWorkflow, dict[WorkflowPhase, Any]]:
    """Build a dry-run workflow with all 7 handlers registered.

    Patches HandlerConfig.from_config to avoid touching the real config
    manager / env vars.
    """
    config = WorkflowConfig(
        dry_run=True,
        project_root=str(tmp_path),
    )
    workflow = ArtisanContractorWorkflow(config=config)

    with patch(
        "startd8.contractors.context_seed_handlers.HandlerConfig.from_config",
        return_value=HandlerConfig(),
    ):
        handlers = ContextSeedHandlers.create_all(
            enriched_seed_path=str(seed_path),
        )

    for phase, handler in handlers.items():
        workflow.register_handler(phase, handler)

    return workflow, handlers


# ============================================================================
# Test class
# ============================================================================


class TestSevenPhaseIntegration:
    """Dry-run integration tests for the full 8-phase workflow pipeline."""

    # ------------------------------------------------------------------
    # test_create_all_returns_all_phases
    # ------------------------------------------------------------------

    def test_create_all_returns_all_phases(self, tmp_path: Path) -> None:
        """Verify create_all() returns exactly 8 WorkflowPhase entries."""
        seed_path = _build_enriched_seed(tmp_path)

        with patch(
            "startd8.contractors.context_seed_handlers.HandlerConfig.from_config",
            return_value=HandlerConfig(),
        ):
            handlers = ContextSeedHandlers.create_all(
                enriched_seed_path=str(seed_path),
            )

        expected_phases = set(WorkflowPhase.ordered())
        assert set(handlers.keys()) == expected_phases
        assert len(handlers) == 8

    # ------------------------------------------------------------------
    # test_all_phases_execute_in_order
    # ------------------------------------------------------------------

    def test_all_phases_execute_in_order(self, tmp_path: Path) -> None:
        """Verify all 8 phases run in order and context accumulates expected keys."""
        seed_path = _build_enriched_seed(tmp_path)
        workflow, _handlers = _create_workflow_and_handlers(tmp_path, seed_path)

        # Execute the full pipeline in dry-run mode
        context: dict[str, Any] = {"enriched_seed_path": str(seed_path)}
        result = workflow.execute(context=context)

        # -- Workflow-level assertions --
        assert result.status == WorkflowStatus.COMPLETED
        assert result.dry_run is True
        # Feature-serial mode records global phases (PLAN, SCAFFOLD, FINALIZE)
        # as PhaseResult entries.  Inner phases (DESIGN through REVIEW) are
        # tracked per-feature inside context, not in the phase_results list.
        assert len(result.phase_results) == 3

        # Every global phase should have DRY_RUN status
        for pr in result.phase_results:
            assert pr.status == PhaseStatus.DRY_RUN, (
                f"Phase {pr.phase.value} has status {pr.status.value}, expected dry_run"
            )

        # Verify canonical global-phase order
        phase_order = [pr.phase for pr in result.phase_results]
        assert phase_order == [
            WorkflowPhase.PLAN,
            WorkflowPhase.SCAFFOLD,
            WorkflowPhase.FINALIZE,
        ]

        # -- After PLAN: tasks, task_index, plan_title, preflight_summary,
        #    domain_summary, enriched_seed_path --
        assert "tasks" in context
        assert len(context["tasks"]) == 2
        assert "task_index" in context
        assert "T1" in context["task_index"]
        assert "T2" in context["task_index"]
        assert context["plan_title"] == "Test Integration Plan"
        assert "preflight_summary" in context
        assert context["preflight_summary"]["pass"] == 2
        assert context["preflight_summary"]["fail"] == 0
        assert "domain_summary" in context
        assert "backend" in context["domain_summary"]
        assert "frontend" in context["domain_summary"]
        assert context["enriched_seed_path"] == str(seed_path)

        # -- After SCAFFOLD: scaffold dict --
        assert "scaffold" in context
        scaffold = context["scaffold"]
        assert "directories_needed" in scaffold
        assert "directories_exist" in scaffold
        assert "project_root" in scaffold
        assert scaffold["project_root"] == str(tmp_path)

        # -- After DESIGN: design_results dict --
        # In feature-serial mode, each feature runs DESIGN independently.
        # The last feature's run overwrites context["design_results"], so
        # only T2 (the last feature) is guaranteed present.
        assert "design_results" in context
        design_results = context["design_results"]
        assert "T2" in design_results
        assert design_results["T2"]["status"] == "dry_run_skipped"
        assert design_results["T2"]["domain"] == "frontend"

        # -- After IMPLEMENT: implementation dict, generation_results --
        # In feature-serial mode, each feature runs IMPLEMENT independently.
        # The last feature's run overwrites context, so tasks_processed == 1.
        assert "implementation" in context
        implementation = context["implementation"]
        assert "task_reports" in implementation
        assert implementation["tasks_processed"] == 1
        assert "total_cost" in implementation
        assert implementation["total_cost"] == 0.0
        assert "generation_results" in context

        # -- After INTEGRATE: integration_results dict --
        assert "integration_results" in context
        assert isinstance(context["integration_results"], dict)

        # -- After TEST: test_results dict --
        assert "test_results" in context
        test_results = context["test_results"]
        assert "test_plan" in test_results
        # Last feature's TEST run: 1 task in plan
        assert len(test_results["test_plan"]) == 1
        for entry in test_results["test_plan"]:
            assert entry["status"] == "dry_run_planned"
        assert "unique_validators" in test_results

        # -- After REVIEW: review_results dict --
        assert "review_results" in context
        review_results = context["review_results"]
        assert "review_items" in review_results
        # Last feature's REVIEW run: 1 item
        assert len(review_results["review_items"]) == 1
        for item in review_results["review_items"]:
            assert item["review_status"] == "dry_run_pending"
        assert "total_cost" in review_results
        assert review_results["total_cost"] == 0.0

        # -- After FINALIZE: workflow_summary dict --
        assert "workflow_summary" in context
        summary = context["workflow_summary"]
        assert summary["plan_title"] == "Test Integration Plan"
        assert summary["task_count"] == 2
        assert "cost_summary" in summary
        assert "dry_run" in summary
        assert summary["dry_run"] is True
        assert "domain_summary" in summary
        assert "scaffold_summary" in summary
        assert "implementation_summary" in summary
        assert "test_summary" in summary
        assert "review_summary" in summary

    # ------------------------------------------------------------------
    # test_dry_run_produces_complete_report
    # ------------------------------------------------------------------

    def test_dry_run_produces_complete_report(self, tmp_path: Path) -> None:
        """Verify FINALIZE output has workflow_summary with cost_summary."""
        seed_path = _build_enriched_seed(tmp_path)
        workflow, _handlers = _create_workflow_and_handlers(tmp_path, seed_path)

        context: dict[str, Any] = {"enriched_seed_path": str(seed_path)}
        result = workflow.execute(context=context)

        assert result.status == WorkflowStatus.COMPLETED

        # FINALIZE is the last phase result
        finalize_pr = result.phase_results[-1]
        assert finalize_pr.phase == WorkflowPhase.FINALIZE
        assert finalize_pr.status == PhaseStatus.DRY_RUN

        # The FINALIZE handler returns the summary as its output
        finalize_output = finalize_pr.output
        assert finalize_output is not None
        assert "cost_summary" in finalize_output

        cost_summary = finalize_output["cost_summary"]
        assert "implementation_cost" in cost_summary
        assert "test_cost" in cost_summary
        assert "review_cost" in cost_summary
        assert "total_cost" in cost_summary
        assert cost_summary["currency"] == "USD"

        # In dry-run, all costs should be zero
        assert cost_summary["implementation_cost"] == 0.0
        assert cost_summary["test_cost"] == 0.0
        assert cost_summary["review_cost"] == 0.0
        assert cost_summary["total_cost"] == 0.0

        # Total workflow cost should also be zero
        assert result.total_cost == 0.0

        # workflow_summary should be in context
        assert "workflow_summary" in context
        assert context["workflow_summary"]["status"] in ("success", "partial", "failed")

    # ------------------------------------------------------------------
    # test_phase_results_have_zero_cost_in_dry_run
    # ------------------------------------------------------------------

    def test_phase_results_have_zero_cost_in_dry_run(self, tmp_path: Path) -> None:
        """In dry-run mode, every phase should report zero cost."""
        seed_path = _build_enriched_seed(tmp_path)
        workflow, _handlers = _create_workflow_and_handlers(tmp_path, seed_path)

        context: dict[str, Any] = {"enriched_seed_path": str(seed_path)}
        result = workflow.execute(context=context)

        for pr in result.phase_results:
            assert pr.cost == 0.0, (
                f"Phase {pr.phase.value} reported non-zero cost: {pr.cost}"
            )

    # ------------------------------------------------------------------
    # test_context_keys_accumulate_monotonically
    # ------------------------------------------------------------------

    def test_context_keys_accumulate_monotonically(self, tmp_path: Path) -> None:
        """Keys added by earlier phases are still present after later phases."""
        seed_path = _build_enriched_seed(tmp_path)
        workflow, _handlers = _create_workflow_and_handlers(tmp_path, seed_path)

        context: dict[str, Any] = {"enriched_seed_path": str(seed_path)}
        result = workflow.execute(context=context)

        assert result.status == WorkflowStatus.COMPLETED

        # All expected keys from every phase should be present in the final context
        expected_keys = {
            # PLAN
            "tasks", "task_index", "plan_title", "preflight_summary",
            "domain_summary", "enriched_seed_path",
            # SCAFFOLD
            "scaffold",
            # DESIGN
            "design_results",
            # IMPLEMENT
            "implementation", "generation_results",
            # INTEGRATE
            "integration_results",
            # TEST
            "test_results",
            # REVIEW
            "review_results",
            # FINALIZE
            "workflow_summary",
        }

        missing = expected_keys - set(context.keys())
        assert not missing, f"Context is missing keys: {missing}"
