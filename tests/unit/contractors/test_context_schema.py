"""Tests for startd8.contractors.context_schema — phase context contract.

Covers:
- Entry validation for each phase (missing keys raise PhaseContextError)
- Exit validation for each phase (invalid output raises PhaseContextError)
- Happy-path validation through all 7 phases
- OrchestratorContext model validation
- Edge cases (empty tasks, None values, extra keys)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from startd8.contractors.context_schema import (
    DesignPhaseOutput,
    FinalizePhaseOutput,
    ImplementPhaseOutput,
    OrchestratorContext,
    PHASE_ENTRY_REQUIREMENTS,
    PhaseContextError,
    PlanPhaseOutput,
    ReviewPhaseOutput,
    ScaffoldPhaseOutput,
    ValidationPhaseOutput,
    validate_phase_entry,
    validate_phase_exit,
)


# ── Test helpers ─────────────────────────────────────────────────────


@dataclass
class FakeSeedTask:
    """Minimal SeedTask stand-in with a task_id attribute."""

    task_id: str = "T1"
    title: str = "Fake task"
    domain: str = "testing"
    estimated_loc: int = 100
    target_files: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    prompt_constraints: list[str] = field(default_factory=list)
    post_generation_validators: list[str] = field(default_factory=list)


class FakePhase:
    """Lightweight stand-in for WorkflowPhase enum members."""

    def __init__(self, value: str) -> None:
        self.value = value


def _make_plan_context(**overrides: Any) -> dict[str, Any]:
    """Build a valid context dict after the PLAN phase."""
    base = {
        "project_root": "/tmp/project",
        "enriched_seed_path": "/tmp/seed.json",
        "tasks": [FakeSeedTask(task_id="T1"), FakeSeedTask(task_id="T2")],
        "task_index": {"T1": FakeSeedTask(task_id="T1"), "T2": FakeSeedTask(task_id="T2")},
        "plan_title": "Test Plan",
        "plan_goals": ["goal-1"],
        "domain_summary": {"testing": 2},
        "preflight_summary": {"pass": 2, "fail": 0},
        "total_estimated_loc": 200,
        "architectural_context": {},
        "design_calibration": {},
        "example_artifacts": {},
    }
    base.update(overrides)
    return base


def _make_scaffold_context(plan_ctx: dict[str, Any]) -> dict[str, Any]:
    """Extend a PLAN context to pass SCAFFOLD validation."""
    plan_ctx["scaffold"] = {
        "directories_needed": ["src"],
        "directories_created": ["src"],
        "project_root": "/tmp/project",
    }
    return plan_ctx


def _make_design_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Extend to pass DESIGN validation."""
    ctx["design_results"] = {"T1": {"status": "agreed"}, "T2": {"status": "agreed"}}
    return ctx


def _make_implement_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Extend to pass IMPLEMENT validation."""
    ctx["implementation"] = {"tasks_processed": 2}
    ctx["generation_results"] = {"T1": {"success": True}, "T2": {"success": True}}
    return ctx


def _make_test_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Extend to pass TEST validation."""
    ctx["test_results"] = {"total_passed": 2, "total_failed": 0}
    return ctx


def _make_review_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Extend to pass REVIEW validation."""
    ctx["review_results"] = {"total_passed": 2, "total_failed": 0}
    return ctx


def _make_finalize_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Extend to pass FINALIZE validation."""
    ctx["workflow_summary"] = {"status": "complete", "artifact_count": 4}
    return ctx


# ── OrchestratorContext ──────────────────────────────────────────────


class TestOrchestratorContext:
    def test_valid(self):
        oc = OrchestratorContext(
            project_root="/tmp/project",
            drafter_model="anthropic:claude-sonnet-4-20250514",
            validator_model="anthropic:claude-sonnet-4-20250514",
            reviewer_model="anthropic:claude-sonnet-4-20250514",
        )
        assert oc.project_root == "/tmp/project"
        assert oc.task_filter is None
        assert oc.abort_on_preflight_fail is False

    def test_missing_required_field(self):
        with pytest.raises(Exception):  # Pydantic ValidationError
            OrchestratorContext(
                project_root="/tmp/project",
                drafter_model="m",
                # missing validator_model and reviewer_model
            )

    def test_extra_field_forbidden(self):
        with pytest.raises(Exception):
            OrchestratorContext(
                project_root="/tmp/project",
                drafter_model="m",
                validator_model="m",
                reviewer_model="m",
                bogus_field="should-fail",
            )

    def test_optional_fields(self):
        oc = OrchestratorContext(
            project_root="/",
            drafter_model="m",
            validator_model="m",
            reviewer_model="m",
            task_filter=["T1", "T2"],
            abort_on_preflight_fail=True,
        )
        assert oc.task_filter == ["T1", "T2"]
        assert oc.abort_on_preflight_fail is True


# ── Entry validation ─────────────────────────────────────────────────


class TestValidatePhaseEntry:
    """Test validate_phase_entry for each phase."""

    @pytest.mark.parametrize(
        "phase_value, required_keys",
        list(PHASE_ENTRY_REQUIREMENTS.items()),
    )
    def test_entry_raises_on_missing_keys(self, phase_value, required_keys):
        """Each phase should raise PhaseContextError when its required keys are missing."""
        phase = FakePhase(phase_value)
        empty_ctx: dict[str, Any] = {}

        with pytest.raises(PhaseContextError) as exc_info:
            validate_phase_entry(phase, empty_ctx)

        assert exc_info.value.phase == phase_value
        assert exc_info.value.direction == "entry"
        # All required keys should be reported as missing.
        assert set(exc_info.value.missing_keys) == set(required_keys)

    @pytest.mark.parametrize(
        "phase_value, required_keys",
        list(PHASE_ENTRY_REQUIREMENTS.items()),
    )
    def test_entry_raises_on_none_values(self, phase_value, required_keys):
        """Keys present but set to None should be treated as missing."""
        phase = FakePhase(phase_value)
        ctx = {k: None for k in required_keys}

        with pytest.raises(PhaseContextError) as exc_info:
            validate_phase_entry(phase, ctx)

        assert set(exc_info.value.missing_keys) == set(required_keys)

    def test_plan_entry_passes_with_project_root(self):
        phase = FakePhase("plan")
        validate_phase_entry(phase, {"project_root": "/tmp"})

    def test_scaffold_entry_passes(self):
        phase = FakePhase("scaffold")
        ctx = {
            "tasks": [FakeSeedTask()],
            "task_index": {"T1": FakeSeedTask()},
            "project_root": "/tmp",
        }
        validate_phase_entry(phase, ctx)

    def test_implement_entry_passes(self):
        phase = FakePhase("implement")
        ctx = {
            "tasks": [FakeSeedTask()],
            "design_results": {"T1": {}},
        }
        validate_phase_entry(phase, ctx)


# ── Exit validation ──────────────────────────────────────────────────


class TestValidatePhaseExit:
    """Test validate_phase_exit for each phase."""

    def test_plan_exit_valid(self):
        ctx = _make_plan_context()
        validate_phase_exit(FakePhase("plan"), ctx)

    def test_plan_exit_missing_tasks(self):
        ctx = _make_plan_context()
        del ctx["tasks"]
        with pytest.raises(PhaseContextError) as exc_info:
            validate_phase_exit(FakePhase("plan"), ctx)
        assert exc_info.value.direction == "exit"
        assert exc_info.value.phase == "plan"

    def test_plan_exit_empty_tasks(self):
        ctx = _make_plan_context(tasks=[])
        with pytest.raises(PhaseContextError):
            validate_phase_exit(FakePhase("plan"), ctx)

    def test_plan_exit_tasks_without_task_id(self):
        ctx = _make_plan_context(tasks=[{"no_task_id": True}])
        with pytest.raises(PhaseContextError):
            validate_phase_exit(FakePhase("plan"), ctx)

    def test_plan_exit_empty_enriched_seed_path(self):
        ctx = _make_plan_context(enriched_seed_path="   ")
        with pytest.raises(PhaseContextError):
            validate_phase_exit(FakePhase("plan"), ctx)

    def test_scaffold_exit_valid(self):
        ctx = _make_plan_context()
        _make_scaffold_context(ctx)
        validate_phase_exit(FakePhase("scaffold"), ctx)

    def test_scaffold_exit_missing_required_key(self):
        ctx = _make_plan_context()
        ctx["scaffold"] = {"directories_needed": ["src"]}  # missing directories_created, project_root
        with pytest.raises(PhaseContextError):
            validate_phase_exit(FakePhase("scaffold"), ctx)

    def test_design_exit_valid(self):
        ctx = _make_plan_context()
        _make_design_context(ctx)
        validate_phase_exit(FakePhase("design"), ctx)

    def test_design_exit_empty_results(self):
        ctx = _make_plan_context()
        ctx["design_results"] = {}
        with pytest.raises(PhaseContextError):
            validate_phase_exit(FakePhase("design"), ctx)

    def test_implement_exit_valid(self):
        ctx = _make_plan_context()
        _make_implement_context(ctx)
        validate_phase_exit(FakePhase("implement"), ctx)

    def test_implement_exit_missing_generation_results(self):
        ctx = _make_plan_context()
        ctx["implementation"] = {"tasks_processed": 1}
        # generation_results missing
        with pytest.raises(PhaseContextError):
            validate_phase_exit(FakePhase("implement"), ctx)

    def test_test_exit_valid(self):
        ctx = _make_plan_context()
        _make_test_context(ctx)
        validate_phase_exit(FakePhase("test"), ctx)

    def test_review_exit_valid(self):
        ctx = _make_plan_context()
        _make_review_context(ctx)
        validate_phase_exit(FakePhase("review"), ctx)

    def test_finalize_exit_valid(self):
        ctx = _make_plan_context()
        _make_finalize_context(ctx)
        validate_phase_exit(FakePhase("finalize"), ctx)

    def test_unknown_phase_skips_exit(self):
        """An unregistered phase value should pass (no model to validate against)."""
        validate_phase_exit(FakePhase("unknown_future_phase"), {"anything": True})


# ── Happy-path full-workflow validation ──────────────────────────────


class TestFullWorkflowHappyPath:
    """Validate a context dict incrementally through all 7 phases."""

    def test_all_phases_entry_and_exit(self):
        ctx = _make_plan_context()

        # PLAN
        validate_phase_entry(FakePhase("plan"), ctx)
        validate_phase_exit(FakePhase("plan"), ctx)

        # SCAFFOLD
        _make_scaffold_context(ctx)
        validate_phase_entry(FakePhase("scaffold"), ctx)
        validate_phase_exit(FakePhase("scaffold"), ctx)

        # DESIGN
        _make_design_context(ctx)
        validate_phase_entry(FakePhase("design"), ctx)
        validate_phase_exit(FakePhase("design"), ctx)

        # IMPLEMENT
        _make_implement_context(ctx)
        validate_phase_entry(FakePhase("implement"), ctx)
        validate_phase_exit(FakePhase("implement"), ctx)

        # TEST
        _make_test_context(ctx)
        validate_phase_entry(FakePhase("test"), ctx)
        validate_phase_exit(FakePhase("test"), ctx)

        # REVIEW
        _make_review_context(ctx)
        validate_phase_entry(FakePhase("review"), ctx)
        validate_phase_exit(FakePhase("review"), ctx)

        # FINALIZE
        _make_finalize_context(ctx)
        validate_phase_entry(FakePhase("finalize"), ctx)
        validate_phase_exit(FakePhase("finalize"), ctx)


# ── Phase output model unit tests ────────────────────────────────────


class TestPlanPhaseOutput:
    def test_valid(self):
        model = PlanPhaseOutput(
            enriched_seed_path="/tmp/seed.json",
            tasks=[FakeSeedTask()],
            task_index={"T1": FakeSeedTask()},
            plan_title="Title",
            plan_goals=["g1"],
            domain_summary={"core": 1},
            preflight_summary={"pass": 1},
            total_estimated_loc=100,
        )
        assert model.enriched_seed_path == "/tmp/seed.json"

    def test_empty_tasks_rejected(self):
        with pytest.raises(Exception):
            PlanPhaseOutput(
                enriched_seed_path="/tmp/seed.json",
                tasks=[],
                task_index={},
                plan_title="Title",
                plan_goals=[],
                domain_summary={},
                preflight_summary={},
                total_estimated_loc=0,
            )

    def test_tasks_without_task_id_rejected(self):
        with pytest.raises(Exception):
            PlanPhaseOutput(
                enriched_seed_path="/tmp/seed.json",
                tasks=["not-a-seed-task"],
                task_index={"T1": "x"},
                plan_title="Title",
                plan_goals=[],
                domain_summary={},
                preflight_summary={},
                total_estimated_loc=0,
            )


class TestScaffoldPhaseOutput:
    def test_valid(self):
        model = ScaffoldPhaseOutput(
            scaffold={
                "directories_needed": ["src"],
                "directories_created": ["src"],
                "project_root": "/tmp",
            }
        )
        assert "directories_needed" in model.scaffold

    def test_missing_required_scaffold_keys(self):
        with pytest.raises(Exception):
            ScaffoldPhaseOutput(scaffold={"directories_needed": ["src"]})


class TestDesignPhaseOutput:
    def test_valid(self):
        model = DesignPhaseOutput(design_results={"T1": {"status": "agreed"}})
        assert "T1" in model.design_results

    def test_empty_rejected(self):
        with pytest.raises(Exception):
            DesignPhaseOutput(design_results={})


class TestImplementPhaseOutput:
    def test_valid(self):
        model = ImplementPhaseOutput(
            implementation={"tasks_processed": 1},
            generation_results={"T1": {"success": True}},
        )
        assert model.implementation["tasks_processed"] == 1

    def test_empty_allowed(self):
        """Both dicts can be empty (no eligible tasks path)."""
        model = ImplementPhaseOutput(implementation={}, generation_results={})
        assert model.generation_results == {}


class TestValidationPhaseOutput:
    def test_valid(self):
        model = ValidationPhaseOutput(test_results={"total_passed": 5})
        assert model.test_results["total_passed"] == 5


class TestReviewPhaseOutput:
    def test_valid(self):
        model = ReviewPhaseOutput(review_results={"total_passed": 3})
        assert model.review_results["total_passed"] == 3


class TestFinalizePhaseOutput:
    def test_valid(self):
        model = FinalizePhaseOutput(workflow_summary={"status": "done"})
        assert model.workflow_summary["status"] == "done"


# ── PhaseContextError attributes ─────────────────────────────────────


class TestPhaseContextError:
    def test_attributes(self):
        err = PhaseContextError(
            "test error",
            phase="plan",
            missing_keys=["tasks"],
            validation_errors=[{"loc": ["tasks"], "msg": "missing"}],
            direction="entry",
        )
        assert err.phase == "plan"
        assert err.missing_keys == ["tasks"]
        assert len(err.validation_errors) == 1
        assert err.direction == "entry"
        assert "test error" in str(err)

    def test_defaults(self):
        err = PhaseContextError("basic")
        assert err.phase == ""
        assert err.missing_keys == []
        assert err.validation_errors == []
        assert err.direction == ""

    def test_is_startd8_error(self):
        from startd8.exceptions import Startd8Error

        err = PhaseContextError("test")
        assert isinstance(err, Startd8Error)


# ── Edge cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    def test_extra_keys_in_context_ignored(self):
        """Extra context keys should not cause validation to fail."""
        ctx = _make_plan_context()
        ctx["some_extra_key"] = "whatever"
        ctx["_internal_tracking"] = 42
        validate_phase_exit(FakePhase("plan"), ctx)

    def test_none_required_key_fails_entry(self):
        """A key set to None should fail entry validation."""
        ctx = {"project_root": None}
        with pytest.raises(PhaseContextError):
            validate_phase_entry(FakePhase("plan"), ctx)

    def test_string_phase_value_works(self):
        """validate_phase_entry should work with raw string phases too."""
        validate_phase_entry("plan", {"project_root": "/tmp"})

    def test_plan_exit_with_optional_enrichment_defaults(self):
        """PlanPhaseOutput should work without optional enrichment keys."""
        model = PlanPhaseOutput(
            enriched_seed_path="/seed.json",
            tasks=[FakeSeedTask()],
            task_index={"T1": FakeSeedTask()},
            plan_title="T",
            plan_goals=[],
            domain_summary={},
            preflight_summary={},
            total_estimated_loc=0,
            # architectural_context, design_calibration, example_artifacts not provided
        )
        assert model.architectural_context == {}
        assert model.design_calibration == {}
        assert model.example_artifacts == {}
