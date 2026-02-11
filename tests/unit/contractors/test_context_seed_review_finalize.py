"""Unit tests for context-seed review/finalize critical paths."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from startd8.contractors.context_seed_handlers import (
    FinalizePhaseHandler,
    HandlerConfig,
    ReviewPhaseHandler,
    SeedTask,
    TestPhaseHandler as ContextSeedTestPhaseHandler,
)
from startd8.contractors.protocols import GenerationResult
from startd8.contractors.artisan_contractor import WorkflowPhase


def _seed_task(task_id: str = "T1") -> SeedTask:
    return SeedTask(
        task_id=task_id,
        title="Implement feature",
        task_type="task",
        story_points=3,
        priority="medium",
        labels=[],
        depends_on=[],
        description="Create implementation",
        target_files=["src/feature.py"],
        estimated_loc=50,
        feature_id="F1",
        domain="backend",
        domain_reasoning="test",
        environment_checks=[],
        prompt_constraints=["Use type hints"],
        post_generation_validators=["ruff"],
        available_siblings=[],
        existing_content_hash=None,
    )


def _generation_result(path: Path) -> GenerationResult:
    return GenerationResult(
        success=True,
        generated_files=[path],
        error=None,
        input_tokens=100,
        output_tokens=60,
        cost_usd=0.02,
        iterations=1,
        model="mock:model",
    )


def test_review_phase_real_mode_populates_per_task(tmp_path: Path):
    code_path = tmp_path / "src" / "feature.py"
    code_path.parent.mkdir(parents=True, exist_ok=True)
    code_path.write_text("def f() -> int:\n    return 1\n", encoding="utf-8")

    context = {
        "tasks": [_seed_task("T1")],
        "generation_results": {"T1": _generation_result(code_path)},
        "test_results": {"test_plan": [{"task_id": "T1", "status": "passed"}]},
    }

    mock_agent = MagicMock()
    mock_agent.generate.return_value = (
        "### Score: 92\n### Verdict: PASS\n### Strengths\n- clear\n### Issues\n- none\n### Suggestions\n- keep",
        50,
        SimpleNamespace(input=12, output=8, cost_estimate=0.01),
    )

    with patch(
        "startd8.utils.agent_resolution.resolve_agent_spec",
        return_value=mock_agent,
    ):
        handler = ReviewPhaseHandler(handler_config=HandlerConfig())
        result = handler.execute(WorkflowPhase.REVIEW, context, dry_run=False)

    per_task = result["output"]["per_task"]
    assert per_task["T1"]["status"] == "reviewed"
    assert per_task["T1"]["passed"] is True
    assert per_task["T1"]["score"] == 92


def test_finalize_manifest_rolls_up_test_and_review_status(tmp_path: Path):
    code_path = tmp_path / "src" / "feature.py"
    code_path.parent.mkdir(parents=True, exist_ok=True)
    code_path.write_text("def f() -> int:\n    return 1\n", encoding="utf-8")

    context = {
        "plan_title": "Test Plan",
        "tasks": [_seed_task("T1")],
        "domain_summary": {"backend": 1},
        "preflight_summary": {},
        "scaffold": {},
        "implementation": {"tasks_processed": 1, "total_estimated_loc": 50, "total_cost": 0.02},
        "generation_results": {"T1": _generation_result(code_path)},
        "test_results": {
            "total_validators": 1,
            "tasks_with_tests": 1,
            "total_passed": 1,
            "total_failed": 0,
            "per_task": {"T1": {"status": "passed", "passed": True}},
        },
        "review_results": {
            "tasks_with_env_issues": 0,
            "total_passed": 1,
            "total_failed": 0,
            "total_cost": 0.01,
            "per_task": {
                "T1": {"status": "reviewed", "passed": True, "score": 92, "verdict": "PASS"},
            },
        },
    }

    handler = FinalizePhaseHandler(output_dir=str(tmp_path), handler_config=HandlerConfig())
    handler.execute(WorkflowPhase.FINALIZE, context, dry_run=False)

    manifest_path = tmp_path / "generation-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    task_status = manifest["task_status"]["T1"]
    assert task_status["tests_passed"] is True
    assert task_status["review_score"] == 92
    assert task_status["review_passed"] is True


def test_test_phase_uses_arg_list_without_shell(tmp_path: Path):
    code_path = tmp_path / "src" / "feature.py"
    code_path.parent.mkdir(parents=True, exist_ok=True)
    code_path.write_text("def f() -> int:\n    return 1\n", encoding="utf-8")

    task = _seed_task("T1")
    task.post_generation_validators = ["ruff"]
    context = {
        "tasks": [task],
        "project_root": str(tmp_path),
        "generation_results": {"T1": _generation_result(code_path)},
    }

    with patch("startd8.contractors.context_seed_handlers.subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        handler = ContextSeedTestPhaseHandler(handler_config=HandlerConfig(test_timeout_seconds=5))
        handler.execute(WorkflowPhase.TEST, context, dry_run=False)

    args, kwargs = mock_run.call_args
    assert isinstance(args[0], list)
    assert kwargs.get("shell") is None
