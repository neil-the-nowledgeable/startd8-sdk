"""Unit tests for DesignPhaseHandler and DESIGN WorkflowPhase integration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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


@dataclass
class _FakeDesignDocument:
    """Minimal stand-in for DesignDocument."""
    feature_name: str
    raw_text: str
    sections: dict = None
    generated_at: datetime = None
    iteration: int = 1

    def __post_init__(self):
        if self.sections is None:
            self.sections = {}
        if self.generated_at is None:
            self.generated_at = datetime.now(timezone.utc)


@dataclass
class _FakeDesignResult:
    """Minimal stand-in for DesignDocumentResult."""
    design_document: _FakeDesignDocument
    reviewer_verdict: Any = None
    arbiter_verdict: Any = None
    escalation_report: Any = None
    resolution_decision: Any = None
    agreed: bool = True
    iterations: int = 1
    completed_at: datetime = None

    def __post_init__(self):
        if self.completed_at is None:
            self.completed_at = datetime.now(timezone.utc)


def _make_fake_result(feature_name: str = "Feature T1", agreed: bool = True) -> _FakeDesignResult:
    return _FakeDesignResult(
        design_document=_FakeDesignDocument(
            feature_name=feature_name,
            raw_text="## Overview\nDesign for feature\n## Architecture\nClean arch",
        ),
        agreed=agreed,
        iterations=2,
    )


# ============================================================================
# WorkflowPhase enum tests
# ============================================================================


class TestWorkflowPhaseDesign:
    """Tests for DESIGN in WorkflowPhase enum."""

    def test_design_value(self):
        assert WorkflowPhase.DESIGN.value == "design"

    def test_ordered_returns_seven_phases(self):
        phases = WorkflowPhase.ordered()
        assert len(phases) == 7

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
# SeedTask → FeatureContext mapping tests
# ============================================================================


class TestTaskToFeatureContext:
    """Tests for the SeedTask → FeatureContext conversion."""

    def test_maps_all_fields(self):
        task = _seed_task("T1")
        fc = DesignPhaseHandler._task_to_feature_context(task)

        assert fc.feature_name == "Feature T1"
        assert fc.description == "Implement feature T1"
        assert fc.target_file == "src/feature.py"
        assert fc.constraints == ["Use type hints", "Add docstrings"]
        assert fc.additional_context["domain"] == "backend"
        assert fc.additional_context["feature_id"] == "F-T1"

    def test_empty_target_files_maps_to_empty_string(self):
        task = _seed_task("T1", target_files=[])
        fc = DesignPhaseHandler._task_to_feature_context(task)
        assert fc.target_file == ""

    def test_unknown_domain_excluded_from_context(self):
        task = _seed_task("T1")
        task.domain = "unknown"
        fc = DesignPhaseHandler._task_to_feature_context(task)
        assert "domain" not in fc.additional_context

    def test_siblings_included_in_context(self):
        task = _seed_task("T1")
        fc = DesignPhaseHandler._task_to_feature_context(task)
        assert "siblings" in fc.additional_context
        assert "sibling1" in fc.additional_context["siblings"]

    def test_multiple_target_files_uses_first(self):
        task = _seed_task("T1", target_files=["scripts/fetch.py", "data/output.csv"])
        fc = DesignPhaseHandler._task_to_feature_context(task)
        assert fc.target_file == "scripts/fetch.py"


# ============================================================================
# DesignPhaseHandler real-mode tests (with mocked async)
# ============================================================================


class TestDesignPhaseHandlerRealMode:
    """Tests for DesignPhaseHandler in real mode (mocked LLM)."""

    def test_real_mode_processes_tasks(self):
        handler = DesignPhaseHandler(handler_config=HandlerConfig())
        context = {"tasks": [_seed_task("T1")]}

        fake_result = _make_fake_result()

        # Mock the async bridge and LLM backend
        with patch.object(
            DesignPhaseHandler, "_run_design_async", return_value=fake_result
        ), patch.object(
            DesignPhaseHandler, "_get_llm_backend"
        ) as mock_backend:
            mock_backend.return_value = MagicMock(total_cost_usd=0.05)
            result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        assert context["design_results"]["T1"]["status"] == "designed"
        assert context["design_results"]["T1"]["agreed"] is True
        assert result["output"]["tasks_designed"] == 1
        assert result["output"]["tasks_agreed"] == 1

    def test_real_mode_tracks_cost_delta(self):
        handler = DesignPhaseHandler(handler_config=HandlerConfig())
        context = {"tasks": [_seed_task("T1")]}

        fake_result = _make_fake_result()
        mock_backend = MagicMock()
        # Simulate cost: 0.0 before, 0.03 after
        mock_backend.total_cost_usd = 0.0

        def bump_cost(*args, **kwargs):
            mock_backend.total_cost_usd = 0.03
            return fake_result

        with patch.object(
            DesignPhaseHandler, "_run_design_async", side_effect=bump_cost
        ), patch.object(
            DesignPhaseHandler, "_get_llm_backend", return_value=mock_backend
        ):
            result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        assert context["design_results"]["T1"]["cost"] == pytest.approx(0.03)
        assert result["cost"] == pytest.approx(0.03)

    def test_real_mode_handles_design_failure(self):
        handler = DesignPhaseHandler(handler_config=HandlerConfig())
        context = {"tasks": [_seed_task("T1")]}

        mock_backend = MagicMock(total_cost_usd=0.0)

        with patch.object(
            DesignPhaseHandler, "_run_design_async",
            side_effect=RuntimeError("LLM timeout"),
        ), patch.object(
            DesignPhaseHandler, "_get_llm_backend", return_value=mock_backend
        ):
            result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        assert context["design_results"]["T1"]["status"] == "design_failed"
        assert "LLM timeout" in context["design_results"]["T1"]["error"]
        assert result["output"]["tasks_failed"] == 1

    def test_real_mode_writes_output_files(self, tmp_path: Path):
        handler = DesignPhaseHandler(
            handler_config=HandlerConfig(),
            output_dir=str(tmp_path),
        )
        context = {"tasks": [_seed_task("T1")]}

        fake_result = _make_fake_result()
        mock_backend = MagicMock(total_cost_usd=0.0)

        with patch.object(
            DesignPhaseHandler, "_run_design_async", return_value=fake_result
        ), patch.object(
            DesignPhaseHandler, "_get_llm_backend", return_value=mock_backend
        ):
            handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        design_file = tmp_path / "T1-design.md"
        assert design_file.exists()
        assert "## Overview" in design_file.read_text()
        assert context["design_results"]["T1"]["output_file"] == str(design_file)

    def test_real_mode_env_blocked_skipped(self):
        handler = DesignPhaseHandler(handler_config=HandlerConfig())
        context = {"tasks": [_seed_task("T1", env_fail=True)]}

        result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        assert context["design_results"]["T1"]["status"] == "env_blocked"
        assert result["output"]["tasks_designed"] == 0


# ============================================================================
# Serialization tests
# ============================================================================


class TestSerializeResult:
    """Tests for DesignPhaseHandler._serialize_result."""

    def test_serializes_all_fields(self):
        fake_result = _make_fake_result(agreed=False)
        serialized = DesignPhaseHandler._serialize_result(fake_result)

        assert serialized["agreed"] is False
        assert serialized["iterations"] == 2
        assert serialized["feature_name"] == "Feature T1"
        assert "## Overview" in serialized["design_document"]
        assert "completed_at" in serialized


# ============================================================================
# Factory tests
# ============================================================================


class TestContextSeedHandlersFactory:
    """Tests for the create_all factory including DESIGN."""

    def test_create_all_returns_seven_handlers(self, tmp_path: Path):
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

        assert len(handlers) == 7
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
        """Full workflow dry-run produces 7 phase results including DESIGN."""
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

        result = workflow.execute(
            context={"enriched_seed_path": str(seed_path)},
        )

        assert result.status == WorkflowStatus.COMPLETED
        phase_names = [pr.phase.value for pr in result.phase_results]
        assert "design" in phase_names
        assert len(result.phase_results) == 7

        # DESIGN phase result should exist
        design_pr = [pr for pr in result.phase_results if pr.phase == WorkflowPhase.DESIGN][0]
        assert design_pr.status.value == "dry_run"

    def test_stop_after_design_runs_three_phases(self, tmp_path: Path):
        """--stop-after design runs only PLAN, SCAFFOLD, DESIGN."""
        config = WorkflowConfig(dry_run=True, project_root=str(tmp_path))
        phases = [WorkflowPhase.PLAN, WorkflowPhase.SCAFFOLD, WorkflowPhase.DESIGN]
        workflow = ArtisanContractorWorkflow(config=config, phases=phases)

        # Register simple no-op handlers
        for p in phases:
            workflow.register_handler(p, DefaultPhaseHandler())

        # Pre-populate context with keys required by phase entry/exit
        # validation (context_schema.py).  DefaultPhaseHandler is a no-op
        # that doesn't write context keys, so we supply them upfront.
        from dataclasses import dataclass as _dc, field as _f

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
            "domain_summary": {},
            "preflight_summary": {},
            "total_estimated_loc": 0,
            # SCAFFOLD exit
            "scaffold": {
                "directories_needed": [],
                "directories_created": [],
                "project_root": str(tmp_path),
            },
            # DESIGN exit
            "design_results": {"T1": {"status": "agreed"}},
        }
        result = workflow.execute(context=context)

        assert result.status == WorkflowStatus.COMPLETED
        assert len(result.phase_results) == 3
        assert [pr.phase for pr in result.phase_results] == phases
