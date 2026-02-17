"""Tests for REVIEW / FINALIZE / SCAFFOLD phase back-patches.

RP-1 (HIGH):  Per-task exception handler in REVIEW loop
RP-2 (MEDIUM): QualitySpec on REVIEW exit contract
RP-3 (HIGH):  ReviewPhaseOutput field validators
RP-5 (MEDIUM): parameter_sources / semantic_conventions forwarded to review prompt
FP-1 (MEDIUM): OSError handling in FINALIZE artifact collection
FP-2 (LOW):   FinalizePhaseOutput field validators
IP-1 (LOW):   ImplementPhaseOutput field validators
SP-1 (LOW):   OSError handling in SCAFFOLD mkdir
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from startd8.contractors.context_schema import (
    FinalizePhaseOutput,
    ImplementPhaseOutput,
    ReviewPhaseOutput,
    ValidationPhaseOutput,
)
from startd8.contractors.protocols import GenerationResult


# ── Helpers ────────────────────────────────────────────────────────────


@dataclass
class _FakeSeedTask:
    """Minimal SeedTask-like object."""

    task_id: str = "T-1"
    title: str = "Generate widget"
    task_type: str = "task"
    story_points: int = 3
    priority: str = "P1"
    labels: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    description: str = "Generate a widget module"
    target_files: list[str] = field(default_factory=list)
    estimated_loc: int = 100
    feature_id: str = "F-1"
    domain: str = "backend"
    domain_reasoning: str = ""
    environment_checks: list[dict] = field(default_factory=list)
    prompt_constraints: list[str] = field(default_factory=list)
    post_generation_validators: list[str] = field(default_factory=lambda: ["python_syntax"])
    available_siblings: list[str] = field(default_factory=list)
    existing_content_hash: Optional[str] = None
    design_doc_sections: list[str] = field(default_factory=list)
    artifact_types_addressed: list[str] = field(default_factory=list)
    file_scope: dict[str, str] = field(default_factory=dict)


def _make_valid_review_results(
    total_passed: int = 1,
    total_failed: int = 0,
) -> dict[str, Any]:
    """Return a minimal valid review_results dict."""
    return {
        "review_items": [],
        "total_passed": total_passed,
        "total_failed": total_failed,
        "per_task": {"T-1": {"status": "reviewed", "passed": True, "score": 90, "verdict": "PASS"}},
        "constraint_coverage": {},
        "tasks_with_env_issues": 0,
        "total_cost": 0.0,
        "preflight_summary": {},
    }


def _make_valid_workflow_summary() -> dict[str, Any]:
    """Return a minimal valid workflow_summary dict."""
    return {
        "plan_title": "Test Plan",
        "task_count": 1,
        "status": "complete",
        "cost_summary": {"total_cost": 0.0},
    }


# ============================================================================
# RP-1: Per-task exception handler in REVIEW loop
# ============================================================================


class TestRP1ReviewPerTaskExceptionHandler:
    """REVIEW phase should not abort when a single task raises."""

    def test_single_task_error_does_not_abort_review(self, tmp_path):
        """If _review_task raises, remaining tasks should still run."""
        from startd8.contractors.context_seed_handlers import (
            HandlerConfig,
            ReviewPhaseHandler,
        )
        from startd8.contractors.artisan_contractor import WorkflowPhase

        handler = ReviewPhaseHandler(handler_config=HandlerConfig())

        task_ok = _FakeSeedTask(task_id="T-ok")
        task_bad = _FakeSeedTask(task_id="T-bad")

        # Create temp generated files
        f1_path = tmp_path / "bad_widget.py"
        f1_path.write_text("# generated code for T-bad\nprint('bad')\n")
        f2_path = tmp_path / "ok_widget.py"
        f2_path.write_text("# generated code for T-ok\nprint('ok')\n")

        gen_bad = GenerationResult(success=True, generated_files=[f1_path])
        gen_ok = GenerationResult(success=True, generated_files=[f2_path])

        context = {
            "tasks": [task_bad, task_ok],
            "task_index": {"T-bad": task_bad, "T-ok": task_ok},
            "project_root": str(tmp_path),
            "generation_results": {"T-bad": gen_bad, "T-ok": gen_ok},
            "test_results": {"per_task": {}},
        }

        call_count = {"n": 0}

        def mock_review(task, generated_code, test_results, **kwargs):
            call_count["n"] += 1
            if task.task_id == "T-bad":
                raise RuntimeError("review agent crashed")
            return {
                "task_id": task.task_id,
                "score": 90,
                "verdict": "PASS",
                "passed": True,
                "cost": 0.0,
                "tokens": {"input": 0, "output": 0},
                "status": "reviewed",
                "strengths": [],
                "issues": [],
                "suggestions": [],
            }

        handler._review_task = mock_review

        result = handler.execute(WorkflowPhase.REVIEW, context, dry_run=False)

        # Both tasks should have been attempted via _review_task
        assert call_count["n"] == 2

        output = result["output"]
        per_task = output["per_task"]
        assert "T-bad" in per_task
        assert "T-ok" in per_task
        assert per_task["T-bad"]["status"] == "error"
        assert per_task["T-bad"]["passed"] is False
        assert per_task["T-ok"]["status"] == "reviewed"

        assert output["total_failed"] >= 1
        assert output["total_passed"] >= 1


# ============================================================================
# RP-2: QualitySpec on REVIEW exit contract
# ============================================================================


class TestRP2QualitySpecInReviewContract:
    """Verify the REVIEW exit contract has a quality spec."""

    def test_quality_spec_present_in_yaml(self):
        import yaml

        contract_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "startd8"
            / "contractors"
            / "contracts"
            / "artisan-pipeline.contract.yaml"
        )
        with open(contract_path) as f:
            contract = yaml.safe_load(f)

        review_exit = contract["phases"]["review"]["exit"]
        review_results_req = next(
            r for r in review_exit["required"] if r["name"] == "review_results"
        )
        assert "quality" in review_results_req, "review_results should have quality spec"
        quality = review_results_req["quality"]
        assert quality["metric"] == "total_passed"
        assert quality["threshold"] == 1
        # Evaluation spec should still be present too
        assert "evaluation" in review_results_req


# ============================================================================
# RP-3: ReviewPhaseOutput field validators
# ============================================================================


class TestRP3ReviewPhaseOutputValidator:
    """ReviewPhaseOutput should reject malformed review_results."""

    def test_valid_review_results_accepted(self):
        data = _make_valid_review_results()
        obj = ReviewPhaseOutput(review_results=data)
        assert obj.review_results["total_passed"] == 1

    def test_missing_required_keys_rejected(self):
        with pytest.raises(Exception, match="missing required keys"):
            ReviewPhaseOutput(review_results={"review_items": []})

    def test_per_task_not_dict_rejected(self):
        data = _make_valid_review_results()
        data["per_task"] = []
        with pytest.raises(Exception, match="per_task.*must be a dict"):
            ReviewPhaseOutput(review_results=data)

    def test_empty_dict_rejected(self):
        with pytest.raises(Exception, match="missing required keys"):
            ReviewPhaseOutput(review_results={})


# ============================================================================
# RP-5: parameter_sources / semantic_conventions in review prompt
# ============================================================================


class TestRP5ParameterSourcesInReviewPrompt:
    """Review prompt should include parameter_sources when provided."""

    def test_parameter_sources_injected(self):
        from startd8.contractors.context_seed_handlers import ReviewPhaseHandler

        handler = ReviewPhaseHandler()
        task = _FakeSeedTask()
        prompt = handler._build_review_prompt(
            task,
            generated_code="print('hello')",
            test_results={},
            parameter_sources={"config_file": "settings.yaml"},
            semantic_conventions={"metric.name": "http_request_duration"},
        )
        assert "Parameter Sources" in prompt
        assert "config_file" in prompt
        assert "Semantic Conventions" in prompt
        assert "metric.name" in prompt

    def test_no_parameter_sources_no_section(self):
        from startd8.contractors.context_seed_handlers import ReviewPhaseHandler

        handler = ReviewPhaseHandler()
        task = _FakeSeedTask()
        prompt = handler._build_review_prompt(
            task, generated_code="print('hello')", test_results={},
        )
        assert "Parameter Sources" not in prompt
        assert "Semantic Conventions" not in prompt


# ============================================================================
# FP-1: FINALIZE artifact collection OSError handling
# ============================================================================


class TestFP1FinalizeArtifactCollectionOSError:
    """FINALIZE should not crash on unreadable files."""

    def test_unreadable_file_produces_read_error(self, tmp_path):
        from startd8.contractors.context_seed_handlers import FinalizePhaseHandler

        handler = FinalizePhaseHandler(output_dir=str(tmp_path))

        # Create a file then make it unreadable
        gen_file = tmp_path / "widget.py"
        gen_file.write_text("print('hello')")

        gen_result = GenerationResult(success=True, generated_files=[gen_file])
        task = _FakeSeedTask()

        context = {
            "tasks": [task],
            "generation_results": {"T-1": gen_result},
        }

        # Should work fine with readable file
        artifacts = handler._collect_generated_artifacts(context)
        assert len(artifacts) == 1
        assert "sha256" in artifacts[0]
        assert "read_error" not in artifacts[0]

    def test_nonexistent_file_handled_gracefully(self, tmp_path):
        from startd8.contractors.context_seed_handlers import FinalizePhaseHandler

        handler = FinalizePhaseHandler(output_dir=str(tmp_path))

        gen_file = tmp_path / "does_not_exist.py"
        gen_result = GenerationResult(success=True, generated_files=[gen_file])
        task = _FakeSeedTask()

        context = {
            "tasks": [task],
            "generation_results": {"T-1": gen_result},
        }

        artifacts = handler._collect_generated_artifacts(context)
        assert len(artifacts) == 1
        assert artifacts[0]["exists"] is False


# ============================================================================
# FP-2: FinalizePhaseOutput field validators
# ============================================================================


class TestFP2FinalizePhaseOutputValidator:
    """FinalizePhaseOutput should reject malformed workflow_summary."""

    def test_valid_workflow_summary_accepted(self):
        data = _make_valid_workflow_summary()
        obj = FinalizePhaseOutput(workflow_summary=data)
        assert obj.workflow_summary["status"] == "complete"

    def test_missing_required_keys_rejected(self):
        with pytest.raises(Exception, match="missing required keys"):
            FinalizePhaseOutput(workflow_summary={"status": "done"})

    def test_empty_dict_rejected(self):
        with pytest.raises(Exception, match="missing required keys"):
            FinalizePhaseOutput(workflow_summary={})


# ============================================================================
# IP-1: ImplementPhaseOutput field validators
# ============================================================================


class TestIP1ImplementPhaseOutputValidator:
    """ImplementPhaseOutput should validate generation_results is a dict."""

    def test_valid_accepted(self):
        obj = ImplementPhaseOutput(
            implementation={"tasks_processed": 1},
            generation_results={"T-1": {"success": True}},
        )
        assert obj.generation_results["T-1"]["success"] is True

    def test_empty_dict_accepted(self):
        """Empty generation_results should be accepted (valid dict)."""
        obj = ImplementPhaseOutput(
            implementation={},
            generation_results={},
        )
        assert obj.generation_results == {}


# ============================================================================
# SP-1: SCAFFOLD mkdir OSError handling
# ============================================================================


class TestSP1ScaffoldMkdirOSError:
    """SCAFFOLD phase should not crash when mkdir fails."""

    def test_scaffold_handles_mkdir_failure(self, tmp_path):
        from startd8.contractors.context_seed_handlers import (
            HandlerConfig,
            ScaffoldPhaseHandler,
        )
        from startd8.contractors.artisan_contractor import WorkflowPhase

        handler = ScaffoldPhaseHandler()

        # Create a task targeting a directory that can't be created
        # (we'll use a path under a file, not a directory)
        blocker = tmp_path / "blocker"
        blocker.write_text("I am a file")  # This blocks mkdir "blocker/subdir"

        task = _FakeSeedTask(
            target_files=["blocker/subdir/widget.py"],
        )

        context = {
            "tasks": [task],
            "task_index": {"T-1": task},
            "project_root": str(tmp_path),
        }

        # Should NOT raise — the OSError should be caught
        result = handler.execute(WorkflowPhase.SCAFFOLD, context, dry_run=False)
        output = result["output"]
        # The directory won't be in dirs_created because mkdir failed
        assert "blocker/subdir" not in output.get("directories_created", [])
