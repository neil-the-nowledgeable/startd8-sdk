"""Unit tests for DesignPhaseHandler and DESIGN WorkflowPhase integration.

Post-REQ-DSR-001: dual-review removed, V2 is the sole path.
Tests now mock ``_run_v2_generate`` (single LLM call) instead of the removed
``_run_design_async`` / ``_run_v2_reviews_async`` methods.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.artisan_contractor import (
    ArtisanContractorWorkflow,
    DefaultPhaseHandler,
    WorkflowConfig,
    WorkflowPhase,
    WorkflowStatus,
)
from startd8.contractors.context_seed_handlers import (
    ContextSeedHandlers,
    DesignPhaseHandler,
    HandlerConfig,
    SeedTask,
)


# ============================================================================
# Fixtures
# ============================================================================

# V2 design document with all required section headers.
_V2_DESIGN_TEXT = (
    "## What to Build\nImplement feature\n\n"
    "## Files\nsrc/feature.py\n\n"
    "## API Surface\ndef do_thing() -> bool\n\n"
    "## Constraints\nUse type hints\n"
)

# V2 design document missing the Constraints section.
_V2_DESIGN_MISSING_SECTION = (
    "## What to Build\nImplement feature\n\n"
    "## Files\nsrc/feature.py\n\n"
    "## API Surface\ndef do_thing() -> bool\n"
)


def _seed_task(
    task_id: str = "T1",
    env_fail: bool = False,
    target_files: list[str] | None = None,
) -> SeedTask:
    """Create a SeedTask for testing."""
    env_checks = []
    if env_fail:
        env_checks.append({"check": "python_version", "status": "fail", "detail": "3.8"})
    return SeedTask(
        task_id=task_id,
        title=f"Feature {task_id}",
        task_type="task",
        story_points=3,
        priority="medium",
        labels=[],
        depends_on=[],
        description=f"Implement feature {task_id}",
        target_files=target_files if target_files is not None else ["src/feature.py"],
        estimated_loc=50,
        feature_id=f"F-{task_id}",
        domain="backend",
        domain_reasoning="test",
        environment_checks=env_checks,
        prompt_constraints=["Use type hints", "Add docstrings"],
        post_generation_validators=["ruff"],
        available_siblings=["sibling1"],
        existing_content_hash=None,
        design_doc_sections=[],
        artifact_types_addressed=[],
        file_scope={},
    )


# ============================================================================
# WorkflowPhase enum tests
# ============================================================================


class TestWorkflowPhaseDesign:
    """Tests for DESIGN in WorkflowPhase enum."""

    def test_design_value(self):
        assert WorkflowPhase.DESIGN.value == "design"

    def test_ordered_returns_eight_phases(self):
        phases = WorkflowPhase.ordered()
        assert len(phases) == 8

    def test_ordered_design_after_scaffold(self):
        phases = WorkflowPhase.ordered()
        scaffold_idx = phases.index(WorkflowPhase.SCAFFOLD)
        design_idx = phases.index(WorkflowPhase.DESIGN)
        implement_idx = phases.index(WorkflowPhase.IMPLEMENT)
        assert design_idx == scaffold_idx + 1
        assert implement_idx == design_idx + 1

    def test_from_value_design(self):
        assert WorkflowPhase.from_value("design") == WorkflowPhase.DESIGN

    def test_from_value_design_case_insensitive(self):
        assert WorkflowPhase.from_value("DESIGN") == WorkflowPhase.DESIGN
        assert WorkflowPhase.from_value("Design") == WorkflowPhase.DESIGN


# ============================================================================
# DesignPhaseHandler dry-run tests
# ============================================================================


class TestDesignPhaseHandlerDryRun:
    """Tests for DesignPhaseHandler in dry-run mode."""

    def test_dry_run_returns_expected_structure(self):
        handler = DesignPhaseHandler()
        context = {"tasks": [_seed_task("T1"), _seed_task("T2")]}
        result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=True)

        assert result["cost"] == 0.0
        assert "output" in result
        assert "design_results" in context

        for task_id in ("T1", "T2"):
            dr = context["design_results"][task_id]
            assert dr["status"] == "dry_run_skipped"
            assert dr["title"] == f"Feature {task_id}"

    def test_dry_run_skips_env_blocked_tasks(self):
        handler = DesignPhaseHandler()
        context = {"tasks": [_seed_task("T1", env_fail=True), _seed_task("T2")]}
        result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=True)

        assert context["design_results"]["T1"]["status"] == "env_blocked"
        assert context["design_results"]["T2"]["status"] == "dry_run_skipped"

    def test_dry_run_handles_empty_target_files(self):
        handler = DesignPhaseHandler()
        task = _seed_task("T1", target_files=[])
        context = {"tasks": [task]}
        result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=True)

        assert context["design_results"]["T1"]["target_file"] == ""


# ============================================================================
# DesignPhaseHandler real-mode tests (REQ-DSR-001: V2 single-pass)
# ============================================================================


class TestDesignPhaseHandlerRealMode:
    """Tests for DesignPhaseHandler in real mode (mocked LLM).

    After REQ-DSR-001, the DESIGN phase uses a single ``_run_v2_generate()``
    call.  ``agreed`` is always ``True``; quality is gated by parameter
    completeness and structure validation only.
    """

    def test_single_pass_design_no_review(self):
        """Generate doc, assert agreed=True, design_gate_passed=True, no verdict fields."""
        handler = DesignPhaseHandler(handler_config=HandlerConfig())
        context = {"tasks": [_seed_task("T1")]}
        mock_backend = MagicMock(total_cost_usd=0.05)

        with patch(
            "startd8.contractors.artisan_phases.design_prompts.assemble_design_prompt",
            return_value=("sys", "user", 1024),
        ), patch.object(
            DesignPhaseHandler, "_run_v2_generate", return_value=_V2_DESIGN_TEXT
        ), patch.object(
            DesignPhaseHandler, "_get_llm_backend", return_value=mock_backend
        ):
            result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        entry = context["design_results"]["T1"]
        assert entry["status"] == "designed"
        assert entry["agreed"] is True
        assert entry.get("design_gate_passed") is True
        assert entry["prompt_version"] == "v2"
        # No verdict fields after dual-review removal
        assert "reviewer_verdict" not in entry
        assert "arbiter_verdict" not in entry
        assert "review_gate" not in entry
        assert result["output"]["tasks_designed"] == 1
        assert result["output"]["tasks_agreed"] == 1

    def test_design_failure_on_llm_exception(self):
        """LLM raises, assert status=design_failed."""
        handler = DesignPhaseHandler(handler_config=HandlerConfig())
        context = {"tasks": [_seed_task("T1")]}
        mock_backend = MagicMock(total_cost_usd=0.0)

        with patch(
            "startd8.contractors.artisan_phases.design_prompts.assemble_design_prompt",
            return_value=("sys", "user", 1024),
        ), patch.object(
            DesignPhaseHandler, "_run_v2_generate",
            side_effect=RuntimeError("LLM timeout"),
        ), patch.object(
            DesignPhaseHandler, "_get_llm_backend", return_value=mock_backend
        ):
            result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        assert context["design_results"]["T1"]["status"] == "design_failed"
        assert "LLM timeout" in context["design_results"]["T1"]["error"]
        assert result["output"]["tasks_failed"] == 1

    def test_real_mode_tracks_cost_delta(self):
        handler = DesignPhaseHandler(handler_config=HandlerConfig())
        context = {"tasks": [_seed_task("T1")]}
        mock_backend = MagicMock()
        mock_backend.total_cost_usd = 0.0

        def bump_cost(*args, **kwargs):
            mock_backend.total_cost_usd = 0.03
            return _V2_DESIGN_TEXT

        with patch(
            "startd8.contractors.artisan_phases.design_prompts.assemble_design_prompt",
            return_value=("sys", "user", 1024),
        ), patch.object(
            DesignPhaseHandler, "_run_v2_generate", side_effect=bump_cost
        ), patch.object(
            DesignPhaseHandler, "_get_llm_backend", return_value=mock_backend
        ):
            result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        assert context["design_results"]["T1"]["cost"] == pytest.approx(0.03)
        assert result["cost"] == pytest.approx(0.03)

    def test_real_mode_writes_output_files(self, tmp_path: Path):
        handler = DesignPhaseHandler(
            handler_config=HandlerConfig(),
            output_dir=str(tmp_path),
        )
        context = {"tasks": [_seed_task("T1")]}
        mock_backend = MagicMock(total_cost_usd=0.0)

        with patch(
            "startd8.contractors.artisan_phases.design_prompts.assemble_design_prompt",
            return_value=("sys", "user", 1024),
        ), patch.object(
            DesignPhaseHandler, "_run_v2_generate", return_value=_V2_DESIGN_TEXT
        ), patch.object(
            DesignPhaseHandler, "_get_llm_backend", return_value=mock_backend
        ):
            handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        design_file = tmp_path / "T1-design.md"
        assert design_file.exists()
        assert "## What to Build" in design_file.read_text()
        assert context["design_results"]["T1"]["output_file"] == str(design_file)

    def test_real_mode_env_blocked_skipped(self):
        handler = DesignPhaseHandler(handler_config=HandlerConfig())
        context = {"tasks": [_seed_task("T1", env_fail=True)]}

        result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        assert context["design_results"]["T1"]["status"] == "env_blocked"
        assert result["output"]["tasks_designed"] == 0

    def test_design_output_includes_quality_gate_metrics(self):
        handler = DesignPhaseHandler(handler_config=HandlerConfig())
        context = {"tasks": [_seed_task("T1"), _seed_task("T2")]}
        mock_backend = MagicMock(total_cost_usd=0.0)

        with patch(
            "startd8.contractors.artisan_phases.design_prompts.assemble_design_prompt",
            return_value=("sys", "user", 1024),
        ), patch.object(
            DesignPhaseHandler, "_run_v2_generate", return_value=_V2_DESIGN_TEXT
        ), patch.object(
            DesignPhaseHandler, "_get_llm_backend", return_value=mock_backend
        ):
            result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        out = result["output"]
        # Both tasks should pass (agreed=True always, completeness passes trivially)
        assert out["total_passed"] == 2
        assert out["total_failed"] == 0
        assert out["agreement_rate"] == pytest.approx(1.0)

    def test_completeness_pass(self):
        """Parameter completeness passes, design_gate_passed=True."""
        handler = DesignPhaseHandler(handler_config=HandlerConfig())
        context = {"tasks": [_seed_task("T1")]}
        mock_backend = MagicMock(total_cost_usd=0.0)

        with patch(
            "startd8.contractors.artisan_phases.design_prompts.assemble_design_prompt",
            return_value=("sys", "user", 1024),
        ), patch.object(
            DesignPhaseHandler, "_run_v2_generate", return_value=_V2_DESIGN_TEXT
        ), patch.object(
            DesignPhaseHandler, "_get_llm_backend", return_value=mock_backend
        ):
            handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        entry = context["design_results"]["T1"]
        assert entry.get("design_gate_passed") is True
        assert entry["status"] == "designed"

    def test_completeness_fail_warn_mode(self):
        """Completeness fails in warn mode, continues with design_gate_passed=False."""
        handler = DesignPhaseHandler(handler_config=HandlerConfig())
        task = _seed_task("T1")
        task.artifact_types_addressed = ["dashboard"]
        context = {
            "tasks": [task],
            "onboarding_resolved_parameters": {
                "dashboard.main": {"namespace": "prod-observability"},
            },
            "quality_gate_summary": {"policy_mode": "warn"},
        }
        mock_backend = MagicMock(total_cost_usd=0.0)

        with patch(
            "startd8.contractors.artisan_phases.design_prompts.assemble_design_prompt",
            return_value=("sys", "user", 1024),
        ), patch.object(
            DesignPhaseHandler, "_run_v2_generate", return_value=_V2_DESIGN_TEXT
        ), patch.object(
            DesignPhaseHandler, "_get_llm_backend", return_value=mock_backend
        ):
            result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        entry = context["design_results"]["T1"]
        assert entry["status"] == "designed"
        assert entry["parameter_completeness"]["passed"] is False
        assert entry["parameter_completeness"]["missing_count"] >= 1
        assert entry["completeness_gate_decision"] == "degraded"
        assert entry["quality_failure_reason"] == "PARAMETER_COMPLETENESS_DEGRADED"
        assert result["output"]["total_failed"] == 1

    def test_completeness_fail_block_mode(self):
        """Completeness fails in block mode, design_failed=True."""
        handler = DesignPhaseHandler(handler_config=HandlerConfig())
        task = _seed_task("T1")
        task.artifact_types_addressed = ["dashboard"]
        context = {
            "tasks": [task],
            "onboarding_resolved_parameters": {
                "dashboard.main": {"namespace": "prod-observability"},
            },
            "quality_gate_summary": {"policy_mode": "block"},
        }
        mock_backend = MagicMock(total_cost_usd=0.0)

        with patch(
            "startd8.contractors.artisan_phases.design_prompts.assemble_design_prompt",
            return_value=("sys", "user", 1024),
        ), patch.object(
            DesignPhaseHandler, "_run_v2_generate", return_value=_V2_DESIGN_TEXT
        ), patch.object(
            DesignPhaseHandler, "_get_llm_backend", return_value=mock_backend
        ):
            result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        entry = context["design_results"]["T1"]
        assert entry["status"] == "design_failed"
        assert entry["parameter_completeness"]["passed"] is False
        assert entry["completeness_gate_decision"] == "blocked"
        assert result["output"]["total_failed"] == 1

    def test_v2_structure_validation(self):
        """Missing sections detected via _validate_v2_structure."""
        result = DesignPhaseHandler._validate_v2_structure(_V2_DESIGN_MISSING_SECTION)
        assert result["passed"] is False
        assert "## Constraints" in result["missing_sections"]

        result_ok = DesignPhaseHandler._validate_v2_structure(_V2_DESIGN_TEXT)
        assert result_ok["passed"] is True
        assert result_ok["missing_sections"] == []


# ============================================================================
# Factory tests
# ============================================================================


class TestContextSeedHandlersFactory:
    """Tests for the create_all factory including DESIGN."""

    def test_create_all_returns_eight_handlers(self, tmp_path: Path):
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({
            "tasks": [{"task_id": "T1", "title": "X", "config": {}}],
        }))

        with patch(
            "startd8.contractors.context_seed_handlers.HandlerConfig.from_config",
            return_value=HandlerConfig(),
        ):
            handlers = ContextSeedHandlers.create_all(
                enriched_seed_path=str(seed),
            )

        assert len(handlers) == 8
        assert WorkflowPhase.DESIGN in handlers
        assert isinstance(handlers[WorkflowPhase.DESIGN], DesignPhaseHandler)

    def test_factory_passes_output_dir_to_design_handler(self, tmp_path: Path):
        seed = tmp_path / "seed.json"
        seed.write_text(json.dumps({
            "tasks": [{"task_id": "T1", "title": "X", "config": {}}],
        }))

        with patch(
            "startd8.contractors.context_seed_handlers.HandlerConfig.from_config",
            return_value=HandlerConfig(),
        ):
            handlers = ContextSeedHandlers.create_all(
                enriched_seed_path=str(seed),
                output_dir="/tmp/designs",
            )

        design_handler = handlers[WorkflowPhase.DESIGN]
        assert design_handler.output_dir == "/tmp/designs"


# ============================================================================
# Full orchestrator integration test
# ============================================================================


class TestOrchestratorWithDesign:
    """Integration tests for the orchestrator with DESIGN phase."""

    def test_full_dry_run_with_design_phase(self, tmp_path: Path):
        """Feature-serial dry-run records global phases; DESIGN runs inside feature loop."""
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps({
            "plan": {"title": "Test Plan", "goals": []},
            "_preflight": {"check_summary": {"pass": 1, "fail": 0}},
            "tasks": [{
                "task_id": "T1",
                "title": "Feature T1",
                "config": {
                    "task_description": "Build it",
                    "context": {"target_files": ["src/f.py"], "estimated_loc": 10, "feature_id": "F1"},
                },
                "_enrichment": {
                    "domain": "backend",
                    "domain_reasoning": "test",
                    "environment_checks": [],
                    "prompt_constraints": [],
                    "post_generation_validators": [],
                    "available_siblings": [],
                },
            }],
        }))

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
        for wp_phase, handler in handlers.items():
            workflow.register_handler(wp_phase, handler)

        run_context: dict[str, Any] = {"enriched_seed_path": str(seed_path)}
        result = workflow.execute(context=run_context)

        assert result.status == WorkflowStatus.COMPLETED
        phase_names = [pr.phase.value for pr in result.phase_results]
        assert phase_names == ["plan", "scaffold", "finalize"]
        assert "design" not in phase_names

        # DESIGN still runs per-feature and populates design_results.
        assert "design_results" in run_context
        assert run_context["design_results"]["T1"]["status"] == "dry_run_skipped"

    def test_stop_after_design_runs_three_phases(self, tmp_path: Path):
        """Phase list gates global phases; feature-serial inner phases still execute."""
        config = WorkflowConfig(dry_run=True, project_root=str(tmp_path))
        phases = [WorkflowPhase.PLAN, WorkflowPhase.SCAFFOLD, WorkflowPhase.DESIGN]
        workflow = ArtisanContractorWorkflow(config=config, phases=phases)

        # Register simple no-op handlers
        for p in phases:
            workflow.register_handler(p, DefaultPhaseHandler())

        from dataclasses import dataclass as _dc

        @_dc
        class _FakeTask:
            task_id: str = "T1"

        context: dict[str, Any] = {
            # PLAN entry + exit
            "enriched_seed_path": str(tmp_path / "seed.json"),
            "tasks": [_FakeTask()],
            "task_index": {"T1": _FakeTask()},
            "plan_title": "Test",
            "plan_goals": [],
            "domain_summary": {"backend": 1},
            "preflight_summary": {},
            "total_estimated_loc": 0,
            # SCAFFOLD exit
            "scaffold": {
                "directories_needed": [],
                "directories_created": [],
                "project_root": str(tmp_path),
            },
            # DESIGN exit + IMPLEMENT entry
            "design_results": {"T1": {"status": "designed", "agreed": True}},
            # IMPLEMENT exit + INTEGRATE/TEST/REVIEW entry
            "implementation": {"tasks_processed": 0, "generation_results": {}},
            "generation_results": {},
            # INTEGRATE exit
            "integration_results": {
                "T1": {"success": True, "integrated_files": [], "errors": []},
            },
            # TEST exit
            "test_results": {
                "test_plan": [],
                "total_passed": 0,
                "total_failed": 0,
                "per_task": {},
            },
            # REVIEW exit
            "review_results": {
                "review_items": [],
                "total_passed": 0,
                "total_failed": 0,
                "per_task": {},
            },
        }
        result = workflow.execute(context=context)

        assert result.status == WorkflowStatus.COMPLETED
        assert [pr.phase for pr in result.phase_results] == [
            WorkflowPhase.PLAN,
            WorkflowPhase.SCAFFOLD,
        ]
