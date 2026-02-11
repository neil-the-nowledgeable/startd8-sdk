"""
Integration tests for refactored ImplementPhaseHandler.

Tests cover:
- SeedTask → DevelopmentChunk conversion via _tasks_to_chunks()
- Environment-blocked task filtering
- DevelopmentResult → context mapping via _map_development_result()
- Downstream contract: context["generation_results"] contains GenerationResult objects
- Dry-run mode preservation
- End-to-end delegation to DevelopmentPhase (mocked)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

from startd8.contractors.artisan_phases.development import (
    ChunkState,
    ChunkStatus,
    DevelopmentChunk,
    DevelopmentResult,
)
from startd8.contractors.context_seed_handlers import (
    ImplementPhaseHandler,
    SeedTask,
    WorkflowPhase,
)
from startd8.contractors.protocols import GenerationResult


# ============================================================================
# Fixtures
# ============================================================================


def _make_seed_task(
    task_id: str = "T1",
    title: str = "Implement feature",
    description: str = "Build the feature module",
    target_files: list[str] | None = None,
    depends_on: list[str] | None = None,
    env_checks: list[dict[str, Any]] | None = None,
    prompt_constraints: list[str] | None = None,
    domain: str = "backend",
) -> SeedTask:
    """Create a SeedTask for testing."""
    return SeedTask(
        task_id=task_id,
        title=title,
        task_type="task",
        story_points=3,
        priority="high",
        labels=["feature"],
        depends_on=depends_on or [],
        description=description,
        target_files=target_files or ["src/feature.py"],
        estimated_loc=100,
        feature_id="F1",
        domain=domain,
        domain_reasoning="Backend logic",
        environment_checks=env_checks or [],
        prompt_constraints=prompt_constraints or ["Use type hints"],
        post_generation_validators=["ruff", "mypy"],
        available_siblings=[],
        existing_content_hash=None,
    )


def _make_env_fail_task(task_id: str = "T-FAIL") -> SeedTask:
    """Create a SeedTask with a failing environment check."""
    return _make_seed_task(
        task_id=task_id,
        title="Env-blocked task",
        env_checks=[
            {"name": "python_version", "status": "fail", "message": "Python < 3.9"},
        ],
    )


def _make_gen_result(
    success: bool = True,
    cost: float = 0.05,
    error: str | None = None,
) -> GenerationResult:
    """Create a GenerationResult for testing."""
    return GenerationResult(
        success=success,
        generated_files=[Path("generated/feature.py")] if success else [],
        error=error,
        input_tokens=1000,
        output_tokens=500,
        cost_usd=cost,
        iterations=2,
        model="anthropic:claude-sonnet-4-5-20250927",
    )


# ============================================================================
# Tests: _tasks_to_chunks()
# ============================================================================


class TestTasksToChunks:
    """Tests for SeedTask → DevelopmentChunk conversion."""

    def test_basic_conversion(self):
        """Basic task converts to a DevelopmentChunk with correct fields."""
        tasks = [_make_seed_task(task_id="T1")]
        chunks, skipped = ImplementPhaseHandler._tasks_to_chunks(tasks)

        assert len(chunks) == 1
        assert len(skipped) == 0

        chunk = chunks[0]
        assert chunk.chunk_id == "T1"
        assert chunk.description == "Build the feature module"
        assert chunk.file_targets == ["src/feature.py"]
        assert chunk.dependencies == []
        assert chunk.max_retries == 2
        assert chunk.metadata["feature_id"] == "F1"
        assert chunk.metadata["domain"] == "backend"
        assert chunk.metadata["prompt_constraints"] == ["Use type hints"]

    def test_env_blocked_task_filtered(self):
        """Tasks with failing env checks are filtered to skipped list."""
        tasks = [
            _make_seed_task(task_id="T1"),
            _make_env_fail_task(task_id="T2"),
        ]
        chunks, skipped = ImplementPhaseHandler._tasks_to_chunks(tasks)

        assert len(chunks) == 1
        assert chunks[0].chunk_id == "T1"
        assert len(skipped) == 1
        assert skipped[0]["task_id"] == "T2"
        assert skipped[0]["status"] == "env_blocked"

    def test_all_tasks_env_blocked(self):
        """All tasks env-blocked results in empty chunks list."""
        tasks = [_make_env_fail_task("T1"), _make_env_fail_task("T2")]
        chunks, skipped = ImplementPhaseHandler._tasks_to_chunks(tasks)

        assert len(chunks) == 0
        assert len(skipped) == 2

    def test_dependencies_preserved(self):
        """Task dependencies are carried over to chunks."""
        tasks = [
            _make_seed_task(task_id="T1"),
            _make_seed_task(task_id="T2", depends_on=["T1"]),
        ]
        chunks, skipped = ImplementPhaseHandler._tasks_to_chunks(tasks)

        assert len(chunks) == 2
        assert chunks[1].chunk_id == "T2"
        assert chunks[1].dependencies == ["T1"]

    def test_dependencies_on_env_blocked_task_are_blocked(self):
        """Tasks depending on env-blocked tasks are skipped, not executed."""
        tasks = [
            _make_env_fail_task(task_id="T1"),
            _make_seed_task(task_id="T2", depends_on=["T1"]),
        ]
        chunks, skipped = ImplementPhaseHandler._tasks_to_chunks(tasks)

        assert len(chunks) == 0
        assert len(skipped) == 2
        skip_by_id = {s["task_id"]: s for s in skipped}
        assert skip_by_id["T1"]["status"] == "env_blocked"
        assert skip_by_id["T2"]["status"] == "dep_blocked_env"
        assert skip_by_id["T2"]["blocked_dependencies"] == ["T1"]

    def test_custom_max_retries(self):
        """Custom max_retries is propagated to chunks."""
        tasks = [_make_seed_task()]
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(tasks, max_retries=5)

        assert chunks[0].max_retries == 5

    def test_metadata_fields_complete(self):
        """All enrichment metadata fields are stored in chunk metadata."""
        tasks = [_make_seed_task(
            prompt_constraints=["c1", "c2"],
            env_checks=[{"name": "check", "status": "pass"}],
        )]
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(tasks)

        meta = chunks[0].metadata
        assert meta["title"] == "Implement feature"
        assert meta["estimated_loc"] == 100
        assert meta["post_generation_validators"] == ["ruff", "mypy"]
        assert meta["environment_checks"] == [{"name": "check", "status": "pass"}]


# ============================================================================
# Tests: _map_development_result()
# ============================================================================


class TestMapDevelopmentResult:
    """Tests for DevelopmentResult → output dict mapping."""

    def _make_dev_result(
        self,
        chunk_states: Dict[str, ChunkState],
        success: bool = True,
    ) -> DevelopmentResult:
        """Create a DevelopmentResult for testing."""
        return DevelopmentResult(
            plan_id="test-plan",
            success=success,
            chunk_states=chunk_states,
            execution_order=[list(chunk_states.keys())],
            total_duration_seconds=1.5,
            summary="Test summary",
        )

    def test_successful_result_mapping(self):
        """Successful chunks produce 'generated' status and GenerationResult."""
        gen_result = _make_gen_result(success=True, cost=0.05)

        chunk = DevelopmentChunk(
            chunk_id="T1",
            description="test",
            dependencies=[],
            file_targets=["f.py"],
            implementation_prompt="test",
            test_commands=[],
            metadata={
                "feature_id": "F1",
                "title": "Test",
                "domain": "backend",
                "estimated_loc": 50,
                "prompt_constraints": [],
                "post_generation_validators": [],
                "_generation_result": gen_result,
            },
        )

        state = ChunkState(chunk_id="T1", status=ChunkStatus.PASSED, attempts=1)
        dev_result = self._make_dev_result({"T1": state})

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="T1")]

        output, gen_results, total_cost = handler._map_development_result(
            dev_result, [chunk], tasks, [],
        )

        assert "T1" in gen_results
        assert gen_results["T1"].success is True
        assert total_cost == pytest.approx(0.05)

        # Check task report
        reports = output["task_reports"]
        assert len(reports) == 1
        assert reports[0]["status"] == "generated"
        assert reports[0]["cost"] == 0.05

    def test_failed_result_mapping(self):
        """Failed chunks produce 'generation_failed' status."""
        gen_result = _make_gen_result(success=False, error="LLM error")

        chunk = DevelopmentChunk(
            chunk_id="T1",
            description="test",
            dependencies=[],
            file_targets=["f.py"],
            implementation_prompt="test",
            test_commands=[],
            metadata={
                "feature_id": "F1",
                "title": "Test",
                "domain": "backend",
                "estimated_loc": 50,
                "prompt_constraints": [],
                "post_generation_validators": [],
                "_generation_result": gen_result,
            },
        )

        state = ChunkState(
            chunk_id="T1", status=ChunkStatus.FAILED, attempts=3,
            last_error="LLM error",
        )
        dev_result = self._make_dev_result({"T1": state}, success=False)

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="T1")]

        output, gen_results, total_cost = handler._map_development_result(
            dev_result, [chunk], tasks, [],
        )

        reports = output["task_reports"]
        assert reports[0]["status"] == "generation_failed"
        assert reports[0]["error"] == "LLM error"

    def test_skipped_result_mapping(self):
        """Skipped chunks produce 'dep_blocked' status."""
        chunk = DevelopmentChunk(
            chunk_id="T2",
            description="test",
            dependencies=["T1"],
            file_targets=["f.py"],
            implementation_prompt="test",
            test_commands=[],
            metadata={
                "feature_id": "F1",
                "title": "Test",
                "domain": "backend",
                "estimated_loc": 50,
                "prompt_constraints": [],
                "post_generation_validators": [],
            },
        )

        state = ChunkState(
            chunk_id="T2", status=ChunkStatus.SKIPPED, attempts=0,
            last_error="Dependency T1 failed",
        )
        dev_result = self._make_dev_result({"T2": state}, success=False)

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="T2")]

        output, gen_results, _ = handler._map_development_result(
            dev_result, [chunk], tasks, [],
        )

        assert "T2" not in gen_results
        reports = output["task_reports"]
        assert reports[0]["status"] == "dep_blocked"

    def test_skipped_reports_included(self):
        """Pre-filtered env-blocked reports are included in output."""
        dev_result = self._make_dev_result({})

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="T1")]
        skipped = [{"task_id": "T0", "title": "Blocked", "status": "env_blocked"}]

        output, _, _ = handler._map_development_result(
            dev_result, [], tasks, skipped,
        )

        assert output["task_reports"][0]["task_id"] == "T0"
        assert output["task_reports"][0]["status"] == "env_blocked"

    def test_domain_breakdown(self):
        """Domain breakdown is computed from original task list."""
        dev_result = self._make_dev_result({})

        handler = ImplementPhaseHandler()
        tasks = [
            _make_seed_task(task_id="T1", domain="backend"),
            _make_seed_task(task_id="T2", domain="frontend"),
            _make_seed_task(task_id="T3", domain="backend"),
        ]

        output, _, _ = handler._map_development_result(
            dev_result, [], tasks, [],
        )

        assert output["domain_breakdown"] == {"backend": 2, "frontend": 1}


# ============================================================================
# Tests: execute() dry-run
# ============================================================================


class TestExecuteDryRun:
    """Tests for execute() in dry-run mode."""

    def test_dry_run_produces_reports(self):
        """Dry-run creates task reports without generating code."""
        handler = ImplementPhaseHandler()
        tasks = [
            _make_seed_task(task_id="T1"),
            _make_seed_task(task_id="T2"),
        ]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": "/tmp/test",
        }

        result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=True)

        assert result["cost"] == 0.0
        output = result["output"]
        assert output["tasks_processed"] == 2
        assert all(r["status"] == "dry_run_skipped" for r in output["task_reports"])

    def test_dry_run_populates_context(self):
        """Dry-run populates context['implementation'] and context['generation_results']."""
        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task()]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": "/tmp/test",
        }

        handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=True)

        assert "implementation" in context
        assert "generation_results" in context
        assert context["generation_results"] == {}

    def test_dry_run_env_issues_reported(self):
        """Dry-run includes environment issues in task reports."""
        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(
            env_checks=[{"name": "check", "status": "warn", "message": "old version"}],
        )]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": "/tmp/test",
        }

        result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=True)

        report = result["output"]["task_reports"][0]
        assert "environment_issues" in report


# ============================================================================
# Tests: execute() real mode (mocked DevelopmentPhase)
# ============================================================================


class TestExecuteRealMode:
    """Tests for execute() in real mode with mocked DevelopmentPhase."""

    def test_all_env_blocked_short_circuit(self):
        """When all tasks are env-blocked, returns immediately without DevelopmentPhase."""
        handler = ImplementPhaseHandler()
        tasks = [_make_env_fail_task("T1"), _make_env_fail_task("T2")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": "/tmp/test",
        }

        result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        assert result["cost"] == 0.0
        assert result["output"]["tasks_processed"] == 2
        assert context["generation_results"] == {}

    @patch.object(ImplementPhaseHandler, "_run_development_phase")
    def test_delegates_to_development_phase(self, mock_run_development_phase):
        """Real mode creates DevelopmentPhase and runs it."""
        # Set up mock DevelopmentResult
        gen_result = _make_gen_result(success=True, cost=0.10)
        chunk_state = ChunkState(chunk_id="T1", status=ChunkStatus.PASSED, attempts=1)
        dev_result = DevelopmentResult(
            plan_id="test",
            success=True,
            chunk_states={"T1": chunk_state},
            execution_order=[["T1"]],
            total_duration_seconds=2.0,
            summary="1 passed",
        )
        mock_run_development_phase.return_value = dev_result

        handler = ImplementPhaseHandler()

        tasks = [_make_seed_task(task_id="T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": "/tmp/test",
        }

        # Patch _tasks_to_chunks to return a chunk with _generation_result
        # already in metadata (simulating what the executor would do)
        chunk = DevelopmentChunk(
            chunk_id="T1",
            description="test",
            dependencies=[],
            file_targets=["src/feature.py"],
            implementation_prompt="test",
            test_commands=[],
            metadata={
                "feature_id": "F1",
                "title": "Implement feature",
                "domain": "backend",
                "estimated_loc": 100,
                "prompt_constraints": ["Use type hints"],
                "post_generation_validators": ["ruff", "mypy"],
                "_generation_result": gen_result,
            },
        )

        with patch.object(
            ImplementPhaseHandler, "_tasks_to_chunks",
            return_value=([chunk], []),
        ):
            result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        # Verify DevelopmentPhase bridge was called
        mock_run_development_phase.assert_called_once()

        # Verify downstream contract
        assert "generation_results" in context
        assert "T1" in context["generation_results"]
        assert context["generation_results"]["T1"].success is True
        assert result["cost"] == pytest.approx(0.10)

    def test_context_generation_results_has_generation_result_objects(self):
        """context['generation_results'] must contain GenerationResult objects."""
        handler = ImplementPhaseHandler()
        tasks = [_make_env_fail_task("T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": "/tmp/test",
        }

        handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        # With all env-blocked, generation_results should be empty dict
        gen_results = context["generation_results"]
        assert isinstance(gen_results, dict)
        # Verify that if there were results, they'd be GenerationResult instances
        for v in gen_results.values():
            assert isinstance(v, GenerationResult)
