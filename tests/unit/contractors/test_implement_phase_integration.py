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

import hashlib
import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

from startd8.contractors.artisan_phases.development import (
    ChunkState,
    ChunkStatus,
    DevelopmentChunk,
    DevelopmentResult,
    LLMChunkExecutor,
)
from startd8.contractors.context_seed_handlers import (
    HandlerConfig,
    ImplementPhaseHandler,
    SeedTask,
    WorkflowPhase,
    _CACHE_SCHEMA_VERSION,
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
    artifact_types_addressed: list[str] | None = None,
    file_scope: dict[str, str] | None = None,
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
        design_doc_sections=[],
        artifact_types_addressed=artifact_types_addressed or [],
        file_scope=file_scope or {},
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


def _make_v2_cache(
    task_data: dict[str, dict[str, Any]],
    source_checksum: str | None = None,
) -> dict[str, Any]:
    """Build a v2 cache envelope for testing."""
    return {
        "_cache_meta": {
            "schema_version": _CACHE_SCHEMA_VERSION,
            "created_at": "2026-02-16T00:00:00+00:00",
            "source_checksum": source_checksum,
        },
        "tasks": task_data,
    }


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

    def test_design_failed_task_is_blocked_before_implementation(self):
        """Tasks marked design_failed in DESIGN are skipped in IMPLEMENT."""
        tasks = [_make_seed_task(task_id="T1")]
        design_results = {
            "T1": {
                "status": "design_failed",
                "quality_failure_reason": "REVIEW_THRESHOLD_NOT_MET",
            },
        }

        chunks, skipped = ImplementPhaseHandler._tasks_to_chunks(
            tasks,
            design_results=design_results,
        )

        assert chunks == []
        assert len(skipped) == 1
        assert skipped[0]["task_id"] == "T1"
        assert skipped[0]["status"] == "design_blocked"
        assert skipped[0]["reason"] == "REVIEW_THRESHOLD_NOT_MET"

    def test_ar138_preflight_size_limit_blocks_oversized_task(self):
        """AR-138: oversized tasks are blocked with split guidance."""
        tasks = [
            _make_seed_task(
                task_id="T1",
                description="Large feature generation",
                target_files=["src/huge.py"],
            ),
        ]
        tasks[0].estimated_loc = 5000

        chunks, skipped = ImplementPhaseHandler._tasks_to_chunks(
            tasks,
            preflight_safe_loc_limit=800,
            preflight_safe_token_limit=64000,
        )

        assert chunks == []
        assert len(skipped) == 1
        assert skipped[0]["status"] == "preflight_blocked_size"
        assert skipped[0]["reason"] == "preflight_size_limit_exceeded"
        assert "split" in skipped[0]["split_guidance"].lower()
        assert skipped[0]["preflight_estimate"]["estimated_loc"] > 800

    def test_ar138_provenance_classification_persisted_in_metadata(self, tmp_path):
        """AR-138: per-file provenance classification is captured for audit."""
        existing_file = tmp_path / "src" / "existing.py"
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("print('ok')", encoding="utf-8")

        tasks = [
            _make_seed_task(
                task_id="T1",
                target_files=["src/existing.py", "src/missing.py"],
            ),
        ]
        chunks, skipped = ImplementPhaseHandler._tasks_to_chunks(
            tasks,
            staleness_classification={"src/existing.py": "stale"},
            project_root_path=str(tmp_path),
        )

        assert skipped == []
        assert len(chunks) == 1
        provenance = chunks[0].metadata["artifact_provenance"]
        assert provenance["summary"]["stale"] == 1
        assert provenance["summary"]["missing"] == 1
        assert chunks[0].metadata["reuse_decision"] == "regenerate_required"

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

    def test_calibration_map_populates_max_output_tokens(self):
        """design_calibration implement_max_output_tokens is passed to chunk metadata."""
        tasks = [_make_seed_task(task_id="T1"), _make_seed_task(task_id="T2")]
        calibration_map = {
            "T1": {"implement_max_output_tokens": 8192},
            "T2": {"implement_max_output_tokens": 32768},
        }
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            tasks, design_results={}, calibration_map=calibration_map
        )

        assert chunks[0].metadata["max_output_tokens"] == 8192
        assert chunks[1].metadata["max_output_tokens"] == 32768

    def test_multi_file_task_gets_output_format_constraint(self):
        """Tasks with multiple target files get multi-file output format constraint."""
        tasks = [
            _make_seed_task(
                task_id="T1",
                target_files=["src/pkg/__init__.py", "src/pkg/module.py"],
                prompt_constraints=["Use type hints"],
            ),
        ]
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(tasks)

        constraints = chunks[0].metadata["prompt_constraints"]
        assert "Use type hints" in constraints
        assert any(
            "SEPARATE fenced code block" in c and "__init__.py" in c
            for c in constraints
        )


# ============================================================================
# Tests: _ensure_test_scaffolding_for_artifact_tasks (Item 12)
# ============================================================================


class TestEnsureTestScaffoldingForArtifactTasks:
    """Tests for test-first scaffolding for artifact generator tasks."""

    def test_creates_test_file_when_missing(self, tmp_path):
        """Scaffolding creates tests/test_<stem>.py for artifact tasks."""
        task = _make_seed_task(
            task_id="T1",
            target_files=["src/generators/servicemonitor.py"],
            artifact_types_addressed=["ServiceMonitor"],
        )
        ImplementPhaseHandler._ensure_test_scaffolding_for_artifact_tasks(
            [task], tmp_path
        )
        test_file = tmp_path / "tests" / "test_servicemonitor.py"
        assert test_file.exists()
        content = test_file.read_text()
        assert "Tests for ServiceMonitor" in content
        assert "class TestServicemonitor:" in content
        assert "import pytest" in content

    def test_skips_when_test_exists(self, tmp_path):
        """Scaffolding does not overwrite existing test file."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        existing = tests_dir / "test_servicemonitor.py"
        existing.write_text("# existing content")

        task = _make_seed_task(
            task_id="T1",
            target_files=["src/generators/servicemonitor.py"],
            artifact_types_addressed=["ServiceMonitor"],
        )
        ImplementPhaseHandler._ensure_test_scaffolding_for_artifact_tasks(
            [task], tmp_path
        )
        assert existing.read_text() == "# existing content"

    def test_skips_tasks_without_artifact_types(self, tmp_path):
        """Tasks without artifact_types_addressed are skipped."""
        task = _make_seed_task(
            task_id="T1",
            target_files=["src/feature.py"],
        )
        ImplementPhaseHandler._ensure_test_scaffolding_for_artifact_tasks(
            [task], tmp_path
        )
        # No tests_dir or test files created when no artifact tasks
        assert not (tmp_path / "tests" / "test_feature.py").exists()

    def test_skips_target_with_empty_stem(self, tmp_path):
        """Targets with empty stem (e.g. "." or "") are skipped."""
        task = _make_seed_task(
            task_id="T1",
            target_files=["."],
            artifact_types_addressed=["config"],
        )
        ImplementPhaseHandler._ensure_test_scaffolding_for_artifact_tasks(
            [task], tmp_path
        )
        assert not (tmp_path / "tests" / "test_.py").exists()


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

    def test_all_env_blocked_short_circuit(self, tmp_path):
        """When all tasks are env-blocked, returns immediately without DevelopmentPhase."""
        handler = ImplementPhaseHandler()
        tasks = [_make_env_fail_task("T1"), _make_env_fail_task("T2")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        assert result["cost"] == 0.0
        assert result["output"]["tasks_processed"] == 2
        assert context["generation_results"] == {}

    @patch.object(ImplementPhaseHandler, "_run_development_phase")
    def test_delegates_to_development_phase(self, mock_run_development_phase, tmp_path):
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

        # enable_inner_loop=False to route through the DevelopmentPhase path
        # (the default is True, which takes the inner loop path instead)
        handler = ImplementPhaseHandler(HandlerConfig(enable_inner_loop=False))

        tasks = [_make_seed_task(task_id="T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
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

    def test_context_generation_results_has_generation_result_objects(self, tmp_path):
        """context['generation_results'] must contain GenerationResult objects."""
        handler = ImplementPhaseHandler()
        tasks = [_make_env_fail_task("T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        # With all env-blocked, generation_results should be empty dict
        gen_results = context["generation_results"]
        assert isinstance(gen_results, dict)
        # Verify that if there were results, they'd be GenerationResult instances
        for v in gen_results.values():
            assert isinstance(v, GenerationResult)


# ============================================================================
# Pre-IMPLEMENT validation (defense-in-depth Layer 7)
# ============================================================================


class TestPreImplementValidation:
    """Tests for _validate_multi_file_tasks risk detection."""

    def test_single_file_tasks_no_warnings(self, caplog):
        """Single-file tasks produce no risk warnings."""
        tasks = [
            _make_seed_task(task_id="T1", target_files=["src/a.py"]),
            _make_seed_task(task_id="T2", target_files=["src/b.py"]),
        ]
        import logging
        with caplog.at_level(logging.WARNING):
            ImplementPhaseHandler._validate_multi_file_tasks(tasks)
        assert not any("elevated" in r.message for r in caplog.records)

    def test_multi_file_with_init_py_warns(self, caplog):
        """Multi-file task with __init__.py gets risk warning."""
        tasks = [
            _make_seed_task(
                task_id="T1",
                target_files=[
                    "src/pkg/__init__.py",
                    "src/pkg/module.py",
                ],
            ),
        ]
        import logging
        with caplog.at_level(logging.WARNING):
            ImplementPhaseHandler._validate_multi_file_tasks(tasks)
        warnings = [r for r in caplog.records if "elevated" in r.message]
        assert len(warnings) == 1
        assert "__init__.py" in warnings[0].message

    def test_multi_file_with_shared_module_constraint_warns(self, caplog):
        """Multi-file task with shared-module constraint gets risk warning."""
        tasks = [
            _make_seed_task(
                task_id="T1",
                target_files=["src/a.py", "src/b.py"],
                prompt_constraints=[
                    "Shared module warning: src/a.py (also used by T2)"
                ],
            ),
        ]
        import logging
        with caplog.at_level(logging.WARNING):
            ImplementPhaseHandler._validate_multi_file_tasks(tasks)
        warnings = [r for r in caplog.records if "elevated" in r.message]
        assert len(warnings) == 1
        assert "shared-module constraint" in warnings[0].message

    def test_overlapping_files_across_tasks_warns(self, caplog):
        """Files targeted by multiple tasks get risk warning."""
        shared = "src/shared/registry.py"
        tasks = [
            _make_seed_task(
                task_id="T1",
                target_files=[shared, "src/feat1/impl.py"],
            ),
            _make_seed_task(
                task_id="T2",
                target_files=[shared, "src/feat2/impl.py"],
            ),
        ]
        import logging
        with caplog.at_level(logging.WARNING):
            ImplementPhaseHandler._validate_multi_file_tasks(tasks)
        warnings = [r for r in caplog.records if "overlapping" in r.message]
        assert len(warnings) >= 1

    def test_multi_file_no_risk_factors_info_only(self, caplog):
        """Multi-file task without risk factors just logs info."""
        tasks = [
            _make_seed_task(
                task_id="T1",
                target_files=["src/a.py", "src/b.py"],
            ),
        ]
        import logging
        with caplog.at_level(logging.INFO):
            ImplementPhaseHandler._validate_multi_file_tasks(tasks)
        # Should log info but no warnings
        info_msgs = [
            r for r in caplog.records
            if r.levelno == logging.INFO and "T1 has 2 target files" in r.message
        ]
        assert len(info_msgs) == 1
        warnings = [r for r in caplog.records if "elevated" in r.message]
        assert len(warnings) == 0


# ============================================================================
# _write_generated_files stub recovery path
# ============================================================================

class TestWriteGeneratedFilesStubRecovery:
    """Verify that _write_generated_files generates stubs for unmatched files."""

    def test_stub_injected_for_missing_file(self, tmp_path):
        """When LLM only produces code for one of two target files,
        the second file should get a stub and metadata should be tagged."""
        from startd8.utils.code_extraction import STUB_SENTINEL

        executor = LLMChunkExecutor(output_dir=tmp_path)
        chunk = DevelopmentChunk(
            chunk_id="C-001",
            description="Multi-file chunk",
            dependencies=[],
            implementation_prompt="Generate foo and bar",
            file_targets=["src/foo.py", "src/bar.py"],
            test_commands=[],
            metadata={},
        )

        # LLM only produced code for foo.py (no bar.py marker)
        code = (
            "# src/foo.py\n"
            "def hello():\n"
            "    return 'world'\n"
        )

        written = executor._write_generated_files(code, chunk)

        assert len(written) == 2
        foo_path = tmp_path / "src" / "foo.py"
        bar_path = tmp_path / "src" / "bar.py"
        assert foo_path.exists()
        assert bar_path.exists()

        # bar.py should be a stub
        bar_content = bar_path.read_text()
        assert STUB_SENTINEL in bar_content

        # Metadata should record the stub
        assert "src/bar.py" in chunk.metadata.get("_stubbed_files", [])

    def test_all_files_matched_no_stubs(self, tmp_path):
        """When all target files are matched, no stubs should be generated."""
        executor = LLMChunkExecutor(output_dir=tmp_path)
        chunk = DevelopmentChunk(
            chunk_id="C-002",
            description="Multi-file chunk",
            dependencies=[],
            implementation_prompt="Generate foo and bar",
            file_targets=["src/foo.py", "src/bar.py"],
            test_commands=[],
            metadata={},
        )

        code = (
            "# src/foo.py\n"
            "def hello():\n"
            "    return 'world'\n"
            "\n"
            "# src/bar.py\n"
            "def goodbye():\n"
            "    return 'mars'\n"
        )

        written = executor._write_generated_files(code, chunk)
        assert len(written) == 2
        assert "_stubbed_files" not in chunk.metadata

    def test_single_file_no_stub_logic(self, tmp_path):
        """Single-file chunks should bypass multi-file logic entirely."""
        executor = LLMChunkExecutor(output_dir=tmp_path)
        chunk = DevelopmentChunk(
            chunk_id="C-003",
            description="Single-file chunk",
            dependencies=[],
            implementation_prompt="Generate foo",
            file_targets=["src/only.py"],
            test_commands=[],
            metadata={},
        )

        code = "def only():\n    pass\n"
        written = executor._write_generated_files(code, chunk)

        assert len(written) == 1
        assert (tmp_path / "src" / "only.py").read_text() == code
        assert "_stubbed_files" not in chunk.metadata


# ============================================================================
# Tests: Fix 2 — downstream file constraint injection
# ============================================================================


class TestDownstreamFileConstraint:
    """Tests for downstream file detection in _tasks_to_chunks.

    Fix 2: When the design doc says a file is for downstream tasks,
    the prompt should include a DOWNSTREAM FILE STUBS constraint.
    """

    def test_downstream_file_adds_constraint(self):
        """Multi-file task with downstream file in design doc gets stub constraint."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/artifact_generators.py",
            ],
        )
        # Design doc must be >= 50 lines to pass DP-2 boundary validation
        _substantial_body = "\n".join(
            f"# Line {i}: implementation detail" for i in range(55)
        )
        design_results = {
            "T1": {
                "status": "designed",
                "design_document": (
                    "# Package Design\n"
                    "## File Layout\n"
                    "├── __init__.py   ← THIS FILE\n"
                    "├── artifact_generators.py   ← shared, F-002+\n"
                    "## Implementation\n"
                    + _substantial_body + "\n"
                ),
            },
        }
        # downstream_map mirrors what _reconcile_design_downstream() would
        # have computed in the real pipeline — _detect_downstream_files()
        # is only called there now (no longer duplicated in _tasks_to_chunks).
        downstream_map = {"T1": ["src/pkg/artifact_generators.py"]}
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [task], design_results=design_results,
            downstream_map=downstream_map,
        )
        constraints = chunks[0].metadata["prompt_constraints"]
        downstream_constraints = [
            c for c in constraints if "DOWNSTREAM FILE STUBS" in c
        ]
        assert len(downstream_constraints) == 1
        assert "artifact_generators.py" in downstream_constraints[0]

    def test_no_downstream_no_constraint(self):
        """Multi-file task without downstream design doc references: no stub constraint."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/module.py",
            ],
        )
        design_results = {
            "T1": {
                "status": "designed",
                "design_document": (
                    "├── __init__.py   ← package root\n"
                    "├── module.py     ← core implementation\n"
                ),
            },
        }
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [task], design_results=design_results,
        )
        constraints = chunks[0].metadata["prompt_constraints"]
        downstream_constraints = [
            c for c in constraints if "DOWNSTREAM FILE STUBS" in c
        ]
        assert len(downstream_constraints) == 0

    def test_single_file_no_downstream_check(self):
        """Single-file tasks skip downstream detection entirely."""
        task = _make_seed_task(target_files=["src/module.py"])
        design_results = {
            "T1": {
                "status": "designed",
                "design_document": "module.py — shared, F-002+\n",
            },
        }
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [task], design_results=design_results,
        )
        constraints = chunks[0].metadata["prompt_constraints"]
        downstream_constraints = [
            c for c in constraints if "DOWNSTREAM" in c
        ]
        assert len(downstream_constraints) == 0


# ============================================================================
# Tests: Fix 3 — LOC estimation mismatch detection
# ============================================================================


class TestLocEstimationMismatch:
    """Tests for LOC mismatch detection in _tasks_to_chunks.

    Fix 3: When the design doc implies significantly more LOC than the
    seed estimates, a warning env check should be added.
    """

    def test_large_mismatch_adds_warning(self):
        """Design doc with >3x LOC vs seed estimate adds loc_estimation_mismatch check."""
        # 600 non-empty lines * 0.6 = 360 implied LOC vs 100 estimated (3.6x)
        big_design = "\n".join(
            [f"line {i}: some code content here" for i in range(600)]
        )
        task = _make_seed_task(target_files=["src/module.py"])
        design_results = {
            "T1": {
                "status": "designed",
                "design_document": big_design,
            },
        }
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [task], design_results=design_results,
        )
        env_checks = chunks[0].metadata["environment_checks"]
        loc_checks = [
            c for c in env_checks if c.get("check_name") == "loc_estimation_mismatch"
        ]
        assert len(loc_checks) == 1
        assert "100" in loc_checks[0]["message"]  # _make_seed_task default estimated_loc

    def test_small_design_no_warning(self):
        """Design doc within 3x of seed estimate produces no LOC mismatch warning."""
        small_design = "\n".join(
            [f"line {i}" for i in range(50)]
        )
        task = _make_seed_task(target_files=["src/module.py"])
        design_results = {
            "T1": {
                "status": "designed",
                "design_document": small_design,
            },
        }
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [task], design_results=design_results,
        )
        env_checks = chunks[0].metadata["environment_checks"]
        loc_checks = [
            c for c in env_checks if c.get("check_name") == "loc_estimation_mismatch"
        ]
        assert len(loc_checks) == 0

    def test_no_design_doc_no_warning(self):
        """Without a design doc, no LOC mismatch check is produced."""
        task = _make_seed_task(target_files=["src/module.py"])
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks([task])
        env_checks = chunks[0].metadata["environment_checks"]
        loc_checks = [
            c for c in env_checks if c.get("check_name") == "loc_estimation_mismatch"
        ]
        assert len(loc_checks) == 0


# ============================================================================
# Tests: Gate 3 — _validate_generation_completeness
# ============================================================================


class TestGate3ValidationCompleteness:
    """Tests for ImplementPhaseHandler._validate_generation_completeness.

    Gate 3 (defense-in-depth Principle 1): post-IMPLEMENT validation
    that all multi-file target files were generated on disk.
    """

    def test_single_file_tasks_skipped(self, tmp_path):
        """Single-file tasks are not validated (only multi-file)."""
        task = _make_seed_task(target_files=["src/module.py"])
        gr = _make_gen_result(success=True)
        findings = ImplementPhaseHandler._validate_generation_completeness(
            [task], {"T1": gr}, tmp_path,
        )
        assert findings == []

    def test_all_files_present_no_findings(self, tmp_path):
        """Multi-file task with all files on disk produces no findings."""
        task = _make_seed_task(
            target_files=["src/pkg/__init__.py", "src/pkg/module.py"],
        )
        # Create the files on disk
        (tmp_path / "src" / "pkg").mkdir(parents=True)
        (tmp_path / "src" / "pkg" / "__init__.py").write_text("from .module import Foo\n")
        (tmp_path / "src" / "pkg" / "module.py").write_text("class Foo: pass\n")

        gr = GenerationResult(
            success=True,
            generated_files=[
                tmp_path / "src" / "pkg" / "__init__.py",
                tmp_path / "src" / "pkg" / "module.py",
            ],
            input_tokens=500, output_tokens=300, cost_usd=0.01,
            iterations=1, model="mock:mock",
        )
        findings = ImplementPhaseHandler._validate_generation_completeness(
            [task], {"T1": gr}, tmp_path,
        )
        assert findings == []

    def test_missing_file_produces_finding(self, tmp_path):
        """Multi-file task with a missing file on disk produces a finding."""
        task = _make_seed_task(
            target_files=["src/pkg/__init__.py", "src/pkg/module.py"],
        )
        # Only create one file
        (tmp_path / "src" / "pkg").mkdir(parents=True)
        (tmp_path / "src" / "pkg" / "module.py").write_text("class Foo: pass\n")

        gr = GenerationResult(
            success=True,
            generated_files=[tmp_path / "src" / "pkg" / "module.py"],
            input_tokens=500, output_tokens=300, cost_usd=0.01,
            iterations=1, model="mock:mock",
        )
        findings = ImplementPhaseHandler._validate_generation_completeness(
            [task], {"T1": gr}, tmp_path,
        )
        assert len(findings) == 1
        assert findings[0]["task_id"] == "T1"
        assert "src/pkg/__init__.py" in findings[0]["missing_on_disk"]

    def test_stubbed_file_produces_finding(self, tmp_path):
        """Files with stub sentinel content are flagged."""
        task = _make_seed_task(
            target_files=["src/pkg/__init__.py", "src/pkg/module.py"],
        )
        (tmp_path / "src" / "pkg").mkdir(parents=True)
        (tmp_path / "src" / "pkg" / "__init__.py").write_text(
            "# STUB_PLACEHOLDER — auto-generated\n"
        )
        (tmp_path / "src" / "pkg" / "module.py").write_text("class Foo: pass\n")

        gr = GenerationResult(
            success=True,
            generated_files=[
                tmp_path / "src" / "pkg" / "__init__.py",
                tmp_path / "src" / "pkg" / "module.py",
            ],
            input_tokens=500, output_tokens=300, cost_usd=0.01,
            iterations=1, model="mock:mock",
        )
        findings = ImplementPhaseHandler._validate_generation_completeness(
            [task], {"T1": gr}, tmp_path,
        )
        assert len(findings) == 1
        assert "src/pkg/__init__.py" in findings[0]["stubbed_files"]

    def test_task_not_in_results_skipped(self, tmp_path):
        """Tasks not in generation_results are skipped (dep-blocked etc.)."""
        task = _make_seed_task(
            target_files=["src/pkg/__init__.py", "src/pkg/module.py"],
        )
        findings = ImplementPhaseHandler._validate_generation_completeness(
            [task], {}, tmp_path,
        )
        assert findings == []


# ============================================================================
# Tests: Gate 2c — _reconcile_design_downstream
# ============================================================================


class TestReconcileDesignDownstream:
    """Tests for Gate 2c: design-to-implement reconciliation.

    Gate 2c scans design docs for files designated as downstream/shared,
    pre-creates stub files on disk, and returns a mapping so _tasks_to_chunks
    can exclude them from the drafter's target list.
    """

    def test_detects_downstream_and_prestubs(self, tmp_path):
        """Downstream files are detected and pre-stubbed on disk."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/artifact_generators.py",
            ],
        )
        design_results = {
            "T1": {
                "status": "designed",
                "design_document": (
                    "├── __init__.py   ← THIS FILE\n"
                    "├── artifact_generators.py   ← shared, F-002+\n"
                ),
            },
        }

        result = ImplementPhaseHandler._reconcile_design_downstream(
            [task], design_results, tmp_path,
        )

        assert "T1" in result
        assert "src/pkg/artifact_generators.py" in result["T1"]
        # Verify stub was created on disk
        stub_path = tmp_path / "src/pkg/artifact_generators.py"
        assert stub_path.exists()
        content = stub_path.read_text()
        assert "downstream" in content

    def test_no_downstream_returns_empty(self, tmp_path):
        """No downstream files found → empty mapping."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/module.py",
            ],
        )
        design_results = {
            "T1": {
                "status": "designed",
                "design_document": (
                    "├── __init__.py   ← package root\n"
                    "├── module.py     ← core implementation\n"
                ),
            },
        }

        result = ImplementPhaseHandler._reconcile_design_downstream(
            [task], design_results, tmp_path,
        )

        assert result == {}

    def test_single_file_task_skipped(self, tmp_path):
        """Single-file tasks are always skipped."""
        task = _make_seed_task(target_files=["src/module.py"])
        design_results = {
            "T1": {
                "status": "designed",
                "design_document": "module.py — shared, F-002+\n",
            },
        }

        result = ImplementPhaseHandler._reconcile_design_downstream(
            [task], design_results, tmp_path,
        )
        assert result == {}

    def test_all_downstream_safety_guard(self, tmp_path):
        """If all files are downstream, none are removed (safety guard)."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/a.py",
                "src/pkg/b.py",
            ],
        )
        design_results = {
            "T1": {
                "status": "designed",
                "design_document": (
                    "a.py — shared, F-002+\n"
                    "b.py — shared, F-003+\n"
                ),
            },
        }

        result = ImplementPhaseHandler._reconcile_design_downstream(
            [task], design_results, tmp_path,
        )
        # Safety: should NOT flag when all files are downstream
        assert result == {}

    def test_no_design_results_returns_empty(self, tmp_path):
        """Missing design results → empty mapping."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/module.py",
            ],
        )
        result = ImplementPhaseHandler._reconcile_design_downstream(
            [task], {}, tmp_path,
        )
        assert result == {}

    def test_existing_file_not_overwritten(self, tmp_path):
        """Pre-existing files are not overwritten by stubs."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/artifact_generators.py",
            ],
        )
        # Pre-create the file
        target = tmp_path / "src/pkg/artifact_generators.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# existing content\n")

        design_results = {
            "T1": {
                "status": "designed",
                "design_document": (
                    "├── __init__.py   ← THIS FILE\n"
                    "├── artifact_generators.py   ← shared, F-002+\n"
                ),
            },
        }

        result = ImplementPhaseHandler._reconcile_design_downstream(
            [task], design_results, tmp_path,
        )

        assert "T1" in result
        # File should NOT be overwritten
        assert target.read_text() == "# existing content\n"


# ============================================================================
# Tests: Gate 2c → _tasks_to_chunks integration (downstream_map)
# ============================================================================


class TestTasksToChunksDownstreamMap:
    """Tests that _tasks_to_chunks correctly uses downstream_map."""

    def test_downstream_files_excluded_from_targets(self):
        """Downstream files should be removed from chunk file_targets."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/artifact_generators.py",
            ],
        )
        downstream_map = {"T1": ["src/pkg/artifact_generators.py"]}
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [task], downstream_map=downstream_map,
        )

        assert len(chunks) == 1
        assert chunks[0].file_targets == ["src/pkg/__init__.py"]
        # Metadata should record original targets and downstream info
        assert chunks[0].metadata["downstream_files"] == [
            "src/pkg/artifact_generators.py"
        ]
        assert chunks[0].metadata["original_target_files"] == [
            "src/pkg/__init__.py",
            "src/pkg/artifact_generators.py",
        ]

    def test_no_downstream_preserves_targets(self):
        """Without downstream_map, file_targets are unchanged."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/module.py",
            ],
        )
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks([task])

        assert len(chunks) == 1
        assert chunks[0].file_targets == [
            "src/pkg/__init__.py",
            "src/pkg/module.py",
        ]
        assert chunks[0].metadata["downstream_files"] == []
        assert chunks[0].metadata["original_target_files"] is None


# ============================================================================
# Tests: Gate 3 enhanced — downstream stub classification
# ============================================================================


class TestGate2cFileScopeFromSeed:
    """Tests that Gate 2c uses _file_scope from seed as primary signal."""

    def test_file_scope_stub_detected_without_design_doc(self, tmp_path):
        """When file_scope says 'stub', Gate 2c flags it even without design doc."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/shared.py",
            ],
            file_scope={
                "src/pkg/__init__.py": "primary",
                "src/pkg/shared.py": "stub",
            },
        )
        result = ImplementPhaseHandler._reconcile_design_downstream(
            [task], {}, tmp_path,
        )
        assert "T1" in result
        assert "src/pkg/shared.py" in result["T1"]

    def test_file_scope_shared_detected(self, tmp_path):
        """Files with scope='shared' are flagged for pre-stubbing."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/shared.py",
            ],
            file_scope={
                "src/pkg/__init__.py": "primary",
                "src/pkg/shared.py": "shared",
            },
        )
        result = ImplementPhaseHandler._reconcile_design_downstream(
            [task], {}, tmp_path,
        )
        assert "T1" in result
        assert "src/pkg/shared.py" in result["T1"]

    def test_file_scope_all_primary_no_downstream(self, tmp_path):
        """When all files are primary, no downstream detected."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/module.py",
            ],
            file_scope={
                "src/pkg/__init__.py": "primary",
                "src/pkg/module.py": "primary",
            },
        )
        result = ImplementPhaseHandler._reconcile_design_downstream(
            [task], {}, tmp_path,
        )
        assert result == {}

    def test_file_scope_takes_priority_over_design_doc(self, tmp_path):
        """file_scope from seed overrides design doc parsing."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/generators.py",
            ],
            # file_scope says both are primary
            file_scope={
                "src/pkg/__init__.py": "primary",
                "src/pkg/generators.py": "primary",
            },
        )
        # Design doc says generators.py is downstream
        design_results = {
            "T1": {
                "status": "designed",
                "design_document": (
                    "├── __init__.py   ← THIS FILE\n"
                    "├── generators.py   ← shared, F-002+\n"
                ),
            },
        }
        result = ImplementPhaseHandler._reconcile_design_downstream(
            [task], design_results, tmp_path,
        )
        # file_scope says primary → no downstream (overrides design doc)
        assert result == {}

    def test_empty_file_scope_falls_back_to_design_doc(self, tmp_path):
        """When file_scope is empty, falls back to design doc parsing."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/generators.py",
            ],
            file_scope={},  # Empty — no seed-level info
        )
        design_results = {
            "T1": {
                "status": "designed",
                "design_document": (
                    "├── __init__.py   ← THIS FILE\n"
                    "├── generators.py   ← shared, F-002+\n"
                ),
            },
        }
        result = ImplementPhaseHandler._reconcile_design_downstream(
            [task], design_results, tmp_path,
        )
        assert "T1" in result
        assert "src/pkg/generators.py" in result["T1"]


class TestGate3DownstreamClassification:
    """Tests for Gate 3's ability to distinguish downstream vs failure stubs."""

    def test_downstream_stub_classified_separately(self, tmp_path):
        """Downstream stubs are in 'downstream_stubbed', not 'stubbed_files'."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/artifact_generators.py",
            ],
        )
        gr = GenerationResult(
            success=True,
            generated_files=[
                tmp_path / "src/pkg/__init__.py",
                tmp_path / "src/pkg/artifact_generators.py",
            ],
        )

        # Create both files, downstream one with stub marker
        (tmp_path / "src/pkg").mkdir(parents=True)
        (tmp_path / "src/pkg/__init__.py").write_text("# real code\nclass Foo: pass\n")
        (tmp_path / "src/pkg/artifact_generators.py").write_text(
            '"""stub"""\n# STARTD8_AUTO_STUB  # downstream — will be implemented by later tasks\n'
        )

        downstream_map = {"T1": ["src/pkg/artifact_generators.py"]}
        findings = ImplementPhaseHandler._validate_generation_completeness(
            [task], {"T1": gr}, tmp_path, downstream_map=downstream_map,
        )

        assert len(findings) == 1
        finding = findings[0]
        assert finding["downstream_stubbed"] == ["src/pkg/artifact_generators.py"]
        assert finding["stubbed_files"] == []
        assert finding["has_real_issues"] is False

    def test_non_downstream_stub_still_flagged(self, tmp_path):
        """Non-downstream stubs remain in 'stubbed_files' (real issues)."""
        task = _make_seed_task(
            target_files=[
                "src/pkg/__init__.py",
                "src/pkg/module.py",
            ],
        )
        gr = GenerationResult(
            success=True,
            generated_files=[
                tmp_path / "src/pkg/__init__.py",
                tmp_path / "src/pkg/module.py",
            ],
        )

        (tmp_path / "src/pkg").mkdir(parents=True)
        (tmp_path / "src/pkg/__init__.py").write_text("# real code\n")
        (tmp_path / "src/pkg/module.py").write_text("# STARTD8_AUTO_STUB\n")

        # No downstream_map → stub is a real issue
        findings = ImplementPhaseHandler._validate_generation_completeness(
            [task], {"T1": gr}, tmp_path,
        )

        assert len(findings) == 1
        assert findings[0]["stubbed_files"] == ["src/pkg/module.py"]
        assert findings[0]["downstream_stubbed"] == []
        assert findings[0]["has_real_issues"] is True


# ============================================================================
# Tests: Resume cache partial coverage fix
# ============================================================================


class TestResumeCachePartialCoverage:
    """Verify that IMPLEMENT phase only resumes when ALL current tasks
    are covered by the cached generation_results.json.

    Regression test for the bug where a cache containing only task A
    caused tasks B, C, D to silently skip implementation.
    """

    def test_partial_cache_triggers_fresh_run(self, tmp_path):
        """When cache covers only some current tasks, all tasks run fresh."""
        # Set up a v2 cache with only T1 — T2 is missing
        state_dir = tmp_path / ".startd8" / "state"
        state_dir.mkdir(parents=True)
        cache_data = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [str(tmp_path / "src/feature.py")],
                "error": None,
                "input_tokens": 1000,
                "output_tokens": 500,
                "cost_usd": 0.50,
                "iterations": 1,
                "model": "anthropic:claude-sonnet-4-5-20250929",
            },
        })
        (state_dir / "generation_results.json").write_text(json.dumps(cache_data))

        handler = ImplementPhaseHandler()
        # Disable inner loop so execution reaches _run_development_phase
        handler.config.enable_inner_loop = False
        tasks = [
            _make_seed_task(task_id="T1"),
            _make_seed_task(task_id="T2"),
        ]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        # Mock _run_development_phase to avoid real LLM calls
        gen_result_t1 = _make_gen_result(success=True, cost=0.50)
        gen_result_t2 = _make_gen_result(success=True, cost=0.60)

        chunk_t1 = DevelopmentChunk(
            chunk_id="T1", description="test", dependencies=[],
            file_targets=["src/feature.py"], implementation_prompt="test",
            test_commands=[], metadata={
                "feature_id": "F1", "title": "T1", "domain": "backend",
                "estimated_loc": 100, "prompt_constraints": [],
                "post_generation_validators": [],
                "_generation_result": gen_result_t1,
            },
        )
        chunk_t2 = DevelopmentChunk(
            chunk_id="T2", description="test", dependencies=[],
            file_targets=["src/feature.py"], implementation_prompt="test",
            test_commands=[], metadata={
                "feature_id": "F1", "title": "T2", "domain": "backend",
                "estimated_loc": 100, "prompt_constraints": [],
                "post_generation_validators": [],
                "_generation_result": gen_result_t2,
            },
        )

        state_t1 = ChunkState(chunk_id="T1", status=ChunkStatus.PASSED, attempts=1)
        state_t2 = ChunkState(chunk_id="T2", status=ChunkStatus.PASSED, attempts=1)
        dev_result = DevelopmentResult(
            plan_id="test", success=True,
            chunk_states={"T1": state_t1, "T2": state_t2},
            execution_order=[["T1", "T2"]],
            total_duration_seconds=2.0, summary="2 passed",
        )

        with patch.object(
            ImplementPhaseHandler, "_tasks_to_chunks",
            return_value=([chunk_t1, chunk_t2], []),
        ), patch.object(
            ImplementPhaseHandler, "_run_development_phase",
            return_value=dev_result,
        ) as mock_run:
            result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        # Key assertion: DevelopmentPhase WAS called (cache was invalidated)
        mock_run.assert_called_once()
        # Both tasks should be in generation_results
        assert "T1" in context["generation_results"]
        assert "T2" in context["generation_results"]

    def test_full_cache_allows_resume(self, tmp_path):
        """When cache covers ALL current tasks, resume is used (no fresh run)."""
        state_dir = tmp_path / ".startd8" / "state"
        state_dir.mkdir(parents=True)

        # Write a target file so path validation + file existence passes
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "feature.py").write_text("# generated")

        cache_data = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [str(tmp_path / "src/feature.py")],
                "error": None,
                "input_tokens": 1000,
                "output_tokens": 500,
                "cost_usd": 0.50,
                "iterations": 1,
                "model": "anthropic:claude-sonnet-4-5-20250929",
            },
        })
        (state_dir / "generation_results.json").write_text(json.dumps(cache_data))

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        with patch.object(
            ImplementPhaseHandler, "_run_development_phase",
        ) as mock_run:
            result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        # Key assertion: DevelopmentPhase was NOT called (resume used cache)
        mock_run.assert_not_called()
        # Fix 2: Resumed cost is 0.0 (no LLM calls), historical cost in metadata
        assert result["cost"] == pytest.approx(0.0)
        assert result["metadata"]["resumed"] is True
        assert result["metadata"]["resumed_cost"] == pytest.approx(0.50)

    def test_resumed_cost_scoped_to_current_tasks(self, tmp_path):
        """Resumed cost sums only current tasks, not all cached tasks."""
        state_dir = tmp_path / ".startd8" / "state"
        state_dir.mkdir(parents=True)

        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "feature.py").write_text("# generated")

        # Cache has T1 ($0.50) and T-old ($0.80) from a previous run
        cache_data = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [str(tmp_path / "src/feature.py")],
                "error": None,
                "cost_usd": 0.50,
                "iterations": 1,
                "model": "test",
            },
            "T-old": {
                "success": True,
                "generated_files": [str(tmp_path / "src/old.py")],
                "error": None,
                "cost_usd": 0.80,
                "iterations": 1,
                "model": "test",
            },
        })
        (state_dir / "generation_results.json").write_text(json.dumps(cache_data))

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        with patch.object(ImplementPhaseHandler, "_run_development_phase"):
            result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        # Fix 2: Resumed cost is 0.0 (no LLM calls); historical is T1 only ($0.50)
        assert result["cost"] == pytest.approx(0.0)
        assert result["metadata"]["resumed_cost"] == pytest.approx(0.50)


# ============================================================================
# Tests: Domain-aware output format constraints
# ============================================================================


class TestDomainAwareOutputConstraints:
    """Verify that config-yaml, JSON, and Markdown tasks get domain-specific
    constraints preventing test code generation."""

    def test_yaml_config_gets_format_constraint(self):
        """config-yaml domain with .yaml target gets YAML format constraint."""
        tasks = [_make_seed_task(
            task_id="T1",
            target_files=["alertmanager/notification.yaml"],
            domain="config-yaml",
        )]
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(tasks)

        constraints = chunks[0].metadata["prompt_constraints"]
        yaml_constraints = [c for c in constraints if "TARGET FILE FORMAT" in c]
        assert len(yaml_constraints) == 1
        assert "valid YAML" in yaml_constraints[0]
        assert "Do NOT generate Python test code" in yaml_constraints[0]

    def test_json_target_gets_format_constraint(self):
        """Task with .json target gets JSON format constraint."""
        tasks = [_make_seed_task(
            task_id="T1",
            target_files=["grafana/dashboards/dashboard.json"],
            domain="unknown",
        )]
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(tasks)

        constraints = chunks[0].metadata["prompt_constraints"]
        json_constraints = [c for c in constraints if "TARGET FILE FORMAT" in c]
        assert len(json_constraints) == 1
        assert "valid JSON" in json_constraints[0]

    def test_markdown_target_gets_format_constraint(self):
        """Task with .md target gets Markdown format constraint."""
        tasks = [_make_seed_task(
            task_id="T1",
            target_files=["runbooks/runbook.md"],
            domain="unknown",
        )]
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(tasks)

        constraints = chunks[0].metadata["prompt_constraints"]
        md_constraints = [c for c in constraints if "TARGET FILE FORMAT" in c]
        assert len(md_constraints) == 1
        assert "Markdown document" in md_constraints[0]

    def test_python_target_no_format_constraint(self):
        """Python (.py) targets do NOT get a format constraint."""
        tasks = [_make_seed_task(
            task_id="T1",
            target_files=["src/feature.py"],
            domain="backend",
        )]
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(tasks)

        constraints = chunks[0].metadata["prompt_constraints"]
        format_constraints = [c for c in constraints if "TARGET FILE FORMAT" in c]
        assert len(format_constraints) == 0

    def test_unknown_domain_with_yaml_ext_gets_constraint(self):
        """'unknown' domain with .yaml extension still gets the constraint."""
        tasks = [_make_seed_task(
            task_id="T1",
            target_files=["slo/slo-definition.yaml"],
            domain="unknown",
        )]
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(tasks)

        constraints = chunks[0].metadata["prompt_constraints"]
        yaml_constraints = [c for c in constraints if "TARGET FILE FORMAT" in c]
        assert len(yaml_constraints) == 1


# ============================================================================
# Tests: Defense-in-depth resume cache validation (v2 format)
# ============================================================================


class TestResumeCacheDefenseInDepth:
    """Tests for _validate_resume_cache() — 7-layer validation.

    Each test targets a specific validation layer, verifying that
    the correct failure mode returns None (reject) and valid caches
    return a dict of GenerationResult objects.
    """

    def _make_task_and_file(
        self,
        tmp_path: Path,
        task_id: str = "T1",
        file_rel: str = "src/feature.py",
        file_content: str = "# generated\n",
    ) -> tuple[SeedTask, str]:
        """Create a task and matching file on disk, return (task, abs_path)."""
        fp = tmp_path / file_rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(file_content)
        return _make_seed_task(task_id=task_id, target_files=[file_rel]), str(fp)

    def test_v1_cache_rejected(self, tmp_path):
        """Layer 0: Flat v1 dict (no _cache_meta) is rejected."""
        handler = ImplementPhaseHandler()
        task, fpath = self._make_task_and_file(tmp_path)
        v1_cache = {
            "T1": {
                "success": True,
                "generated_files": [fpath],
            },
        }
        result = handler._validate_resume_cache(
            v1_cache, [task], tmp_path, source_checksum=None,
        )
        assert result is None

    def test_wrong_schema_version_rejected(self, tmp_path):
        """Layer 0: Wrong schema_version is rejected."""
        handler = ImplementPhaseHandler()
        task, fpath = self._make_task_and_file(tmp_path)
        cache = {
            "_cache_meta": {
                "schema_version": 99,
                "created_at": "2026-01-01T00:00:00+00:00",
                "source_checksum": None,
            },
            "tasks": {
                "T1": {
                    "success": True,
                    "generated_files": [fpath],
                },
            },
        }
        result = handler._validate_resume_cache(
            cache, [task], tmp_path, source_checksum=None,
        )
        assert result is None

    def test_valid_v2_cache_accepted(self, tmp_path):
        """Layers 0-6: A fully valid v2 cache passes all layers."""
        handler = ImplementPhaseHandler()
        task, fpath = self._make_task_and_file(tmp_path)
        file_hash = hashlib.sha256(Path(fpath).read_bytes()).hexdigest()
        cache = _make_v2_cache(
            {
                "T1": {
                    "success": True,
                    "generated_files": [fpath],
                    "content_hashes": {fpath: file_hash},
                    "error": None,
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cost_usd": 0.10,
                    "iterations": 1,
                    "model": "test:model",
                },
            },
            source_checksum="abc123",
        )
        result = handler._validate_resume_cache(
            cache, [task], tmp_path, source_checksum="abc123",
        )
        assert result is not None
        assert "T1" in result
        assert result["T1"].success is True
        assert result["T1"].cost_usd == 0.10

    def test_failed_task_causes_coverage_miss(self, tmp_path):
        """Layers 1+2: Failed task filtered out → coverage miss → rejected."""
        handler = ImplementPhaseHandler()
        task1, fpath1 = self._make_task_and_file(tmp_path, "T1", "src/a.py")
        task2 = _make_seed_task(task_id="T2", target_files=["src/b.py"])
        cache = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [fpath1],
            },
            "T2": {
                "success": False,
                "generated_files": [],
                "error": "LLM error",
            },
        })
        result = handler._validate_resume_cache(
            cache, [task1, task2], tmp_path, source_checksum=None,
        )
        assert result is None

    def test_failed_task_not_in_current_ignored(self, tmp_path):
        """Layers 1+2: Failed task for a non-current ID is harmless."""
        handler = ImplementPhaseHandler()
        task, fpath = self._make_task_and_file(tmp_path)
        cache = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [fpath],
            },
            "T-old": {
                "success": False,
                "generated_files": [],
                "error": "old failure",
            },
        })
        result = handler._validate_resume_cache(
            cache, [task], tmp_path, source_checksum=None,
        )
        assert result is not None
        assert "T1" in result

    def test_source_checksum_mismatch_rejected(self, tmp_path):
        """Layer 3: Mismatched source checksums → rejected."""
        handler = ImplementPhaseHandler()
        task, fpath = self._make_task_and_file(tmp_path)
        cache = _make_v2_cache(
            {
                "T1": {
                    "success": True,
                    "generated_files": [fpath],
                },
            },
            source_checksum="old_checksum",
        )
        result = handler._validate_resume_cache(
            cache, [task], tmp_path, source_checksum="new_checksum",
        )
        assert result is None

    def test_source_checksum_absent_accepted(self, tmp_path):
        """Layer 3: When either checksum is None, skip check → accepted."""
        handler = ImplementPhaseHandler()
        task, fpath = self._make_task_and_file(tmp_path)
        # Cached has checksum, current is None → skip
        cache = _make_v2_cache(
            {
                "T1": {
                    "success": True,
                    "generated_files": [fpath],
                },
            },
            source_checksum="some_hash",
        )
        result = handler._validate_resume_cache(
            cache, [task], tmp_path, source_checksum=None,
        )
        assert result is not None

    def test_path_mismatch_rejected(self, tmp_path):
        """Layer 4: Cached files don't match task target_files → rejected."""
        handler = ImplementPhaseHandler()
        task = _make_seed_task(task_id="T1", target_files=["src/feature.py"])
        # Create a different file that's in the cache
        wrong_file = tmp_path / "src" / "other.py"
        wrong_file.parent.mkdir(parents=True, exist_ok=True)
        wrong_file.write_text("# wrong")
        cache = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [str(wrong_file)],
            },
        })
        result = handler._validate_resume_cache(
            cache, [task], tmp_path, source_checksum=None,
        )
        assert result is None

    def test_file_missing_from_disk_rejected(self, tmp_path):
        """Layer 5: Cached file doesn't exist on disk → rejected."""
        handler = ImplementPhaseHandler()
        task = _make_seed_task(task_id="T1", target_files=["src/feature.py"])
        ghost_path = str(tmp_path / "src" / "feature.py")
        # Do NOT create the file on disk
        cache = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [ghost_path],
            },
        })
        result = handler._validate_resume_cache(
            cache, [task], tmp_path, source_checksum=None,
        )
        assert result is None

    def test_content_hash_mismatch_rejected(self, tmp_path):
        """Layer 6: File modified after cache write → hash mismatch → rejected."""
        handler = ImplementPhaseHandler()
        task, fpath = self._make_task_and_file(
            tmp_path, file_content="original content\n",
        )
        # Hash from the original content
        original_hash = hashlib.sha256(b"original content\n").hexdigest()
        cache = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [fpath],
                "content_hashes": {fpath: original_hash},
            },
        })
        # Now modify the file to break the hash
        Path(fpath).write_text("modified content\n")
        result = handler._validate_resume_cache(
            cache, [task], tmp_path, source_checksum=None,
        )
        assert result is None

    def test_content_hashes_absent_accepted(self, tmp_path):
        """Layer 6: Missing content_hashes key → no hash check → accepted."""
        handler = ImplementPhaseHandler()
        task, fpath = self._make_task_and_file(tmp_path)
        cache = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [fpath],
                # No content_hashes key
            },
        })
        result = handler._validate_resume_cache(
            cache, [task], tmp_path, source_checksum=None,
        )
        assert result is not None

    def test_all_layers_pass_returns_generation_results(self, tmp_path):
        """Layers 0-6: Full valid setup returns correct GenerationResult fields."""
        handler = ImplementPhaseHandler()
        content = "def hello(): return 'world'\n"
        task, fpath = self._make_task_and_file(
            tmp_path, file_content=content,
        )
        file_hash = hashlib.sha256(content.encode()).hexdigest()
        cache = _make_v2_cache(
            {
                "T1": {
                    "success": True,
                    "generated_files": [fpath],
                    "content_hashes": {fpath: file_hash},
                    "error": None,
                    "input_tokens": 500,
                    "output_tokens": 250,
                    "cost_usd": 0.25,
                    "iterations": 2,
                    "model": "anthropic:claude-sonnet-4-5-20250929",
                },
            },
            source_checksum="plan_hash_abc",
        )
        result = handler._validate_resume_cache(
            cache, [task], tmp_path, source_checksum="plan_hash_abc",
        )
        assert result is not None
        gr = result["T1"]
        assert gr.success is True
        assert gr.input_tokens == 500
        assert gr.output_tokens == 250
        assert gr.cost_usd == 0.25
        assert gr.iterations == 2
        assert gr.model == "anthropic:claude-sonnet-4-5-20250929"
        assert len(gr.generated_files) == 1
        assert str(gr.generated_files[0]) == fpath


# ============================================================================
# Tests: Resume cache v2 write path
# ============================================================================


class TestResumeCacheWriteV2:
    """Tests for the v2 cache envelope written by execute().

    These run through the full execute() path (with _run_development_phase
    mocked) and verify the cache file written to disk.
    """

    def _run_execute_and_get_cache(
        self, tmp_path: Path, source_checksum: str | None = None,
    ) -> dict[str, Any]:
        """Run execute() in real mode, return the written cache dict."""
        handler = ImplementPhaseHandler()
        task = _make_seed_task(task_id="T1")

        gen_result = _make_gen_result(success=True, cost=0.10)
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
        state = ChunkState(
            chunk_id="T1", status=ChunkStatus.PASSED, attempts=1,
        )
        dev_result = DevelopmentResult(
            plan_id="test",
            success=True,
            chunk_states={"T1": state},
            execution_order=[["T1"]],
            total_duration_seconds=1.0,
            summary="1 passed",
        )

        context: dict[str, Any] = {
            "tasks": [task],
            "project_root": str(tmp_path),
        }
        if source_checksum is not None:
            context["source_checksum"] = source_checksum

        with patch.object(
            ImplementPhaseHandler, "_tasks_to_chunks",
            return_value=([chunk], []),
        ), patch.object(
            ImplementPhaseHandler, "_run_development_phase",
            return_value=dev_result,
        ):
            handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        cache_path = tmp_path / ".startd8" / "state" / "generation_results.json"
        assert cache_path.exists()
        return json.loads(cache_path.read_text())

    def test_write_produces_v2_envelope(self, tmp_path):
        """Written cache has _cache_meta with schema_version=2 and tasks key."""
        cache = self._run_execute_and_get_cache(tmp_path)
        assert "_cache_meta" in cache
        assert cache["_cache_meta"]["schema_version"] == _CACHE_SCHEMA_VERSION
        assert "created_at" in cache["_cache_meta"]
        assert "tasks" in cache
        assert "T1" in cache["tasks"]

    def test_write_includes_content_hashes(self, tmp_path):
        """Written cache has per-task content_hashes matching file SHA-256."""
        cache = self._run_execute_and_get_cache(tmp_path)
        task_data = cache["tasks"]["T1"]
        assert "content_hashes" in task_data
        # The generated file from _make_gen_result is Path("generated/feature.py")
        # which may or may not exist; content_hashes only includes existing files
        for fpath, cached_hash in task_data["content_hashes"].items():
            fp = Path(fpath)
            if fp.exists():
                actual_hash = hashlib.sha256(fp.read_bytes()).hexdigest()
                assert cached_hash == actual_hash

    def test_write_includes_source_checksum(self, tmp_path):
        """Written cache propagates context['source_checksum'] to _cache_meta."""
        cache = self._run_execute_and_get_cache(
            tmp_path, source_checksum="plan_abc_123",
        )
        assert cache["_cache_meta"]["source_checksum"] == "plan_abc_123"

    def test_roundtrip_write_then_validate(self, tmp_path):
        """Write cache → read it back → _validate_resume_cache accepts it."""
        # First, create the generated file on disk so Layer 5 passes
        gen_dir = tmp_path / "generated"
        gen_dir.mkdir(parents=True, exist_ok=True)
        gen_file = gen_dir / "feature.py"
        gen_file.write_text("# feature code\n")

        cache = self._run_execute_and_get_cache(
            tmp_path, source_checksum="roundtrip_test",
        )

        # Update the cache to point to the file that exists on disk
        # (since _make_gen_result uses relative Path("generated/feature.py"))
        task_data = cache["tasks"]["T1"]
        abs_path = str(gen_file)
        file_hash = hashlib.sha256(gen_file.read_bytes()).hexdigest()
        task_data["generated_files"] = [abs_path]
        task_data["content_hashes"] = {abs_path: file_hash}

        handler = ImplementPhaseHandler()
        task = _make_seed_task(
            task_id="T1",
            target_files=["generated/feature.py"],
        )
        result = handler._validate_resume_cache(
            cache, [task], tmp_path, source_checksum="roundtrip_test",
        )
        assert result is not None
        assert "T1" in result
        assert result["T1"].success is True


# ============================================================================
# Tests: Fix 1 — downstream_map persistence in cache
# ============================================================================


class TestResumeCacheDownstreamMapPersistence:
    """Verify downstream_map survives a cache write → resume roundtrip."""

    def test_downstream_map_roundtrip(self, tmp_path):
        """downstream_map written to cache is restored on resume."""
        state_dir = tmp_path / ".startd8" / "state"
        state_dir.mkdir(parents=True)

        (tmp_path / "src" / "pkg").mkdir(parents=True)
        (tmp_path / "src" / "pkg" / "__init__.py").write_text("# init")
        (tmp_path / "src" / "pkg" / "shared.py").write_text("# stub")

        file_path = str(tmp_path / "src" / "pkg" / "__init__.py")
        cache_data = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [file_path],
                "error": None,
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.10,
                "iterations": 1,
                "model": "test:model",
            },
        })
        # Inject downstream_map into cache (simulating what the write path does)
        cache_data["downstream_map"] = {"T1": ["src/pkg/shared.py"]}
        (state_dir / "generation_results.json").write_text(json.dumps(cache_data))

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(
            task_id="T1",
            target_files=["src/pkg/__init__.py"],
        )]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        with patch.object(ImplementPhaseHandler, "_run_development_phase"):
            handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        # downstream_map should be restored in context
        assert context.get("_downstream_map") == {"T1": ["src/pkg/shared.py"]}

    def test_missing_downstream_map_defaults_to_empty(self, tmp_path):
        """Cache without downstream_map key defaults to empty dict."""
        state_dir = tmp_path / ".startd8" / "state"
        state_dir.mkdir(parents=True)

        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "feature.py").write_text("# generated")

        cache_data = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [str(tmp_path / "src/feature.py")],
                "error": None,
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.10,
                "iterations": 1,
                "model": "test:model",
            },
        })
        # No downstream_map key in cache
        (state_dir / "generation_results.json").write_text(json.dumps(cache_data))

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        with patch.object(ImplementPhaseHandler, "_run_development_phase"):
            handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        # No downstream_map → empty dict, so _downstream_map not set in context
        # (the code only sets it when downstream_map is truthy)
        assert context.get("_downstream_map", {}) == {}


# ============================================================================
# Tests: Fix 2 — resumed IMPLEMENT reports zero cost
# ============================================================================


class TestResumeCostReporting:
    """Verify resumed IMPLEMENT reports cost=0.0 with historical cost in metadata."""

    def test_resumed_reports_zero_cost(self, tmp_path):
        """Resumed IMPLEMENT returns cost=0.0 (no LLM calls made)."""
        state_dir = tmp_path / ".startd8" / "state"
        state_dir.mkdir(parents=True)

        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "feature.py").write_text("# generated")

        cache_data = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [str(tmp_path / "src/feature.py")],
                "error": None,
                "input_tokens": 1000,
                "output_tokens": 500,
                "cost_usd": 0.75,
                "iterations": 2,
                "model": "test:model",
            },
        })
        (state_dir / "generation_results.json").write_text(json.dumps(cache_data))

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        with patch.object(ImplementPhaseHandler, "_run_development_phase"):
            result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        assert result["cost"] == pytest.approx(0.0)
        assert result["metadata"]["resumed_cost"] == pytest.approx(0.75)

    def test_fresh_run_reports_actual_cost(self, tmp_path):
        """Fresh (non-resumed) IMPLEMENT reports actual LLM cost."""
        gen_result = _make_gen_result(success=True, cost=0.42)
        chunk = DevelopmentChunk(
            chunk_id="T1", description="test", dependencies=[],
            file_targets=["src/feature.py"], implementation_prompt="test",
            test_commands=[], metadata={
                "feature_id": "F1", "title": "T1", "domain": "backend",
                "estimated_loc": 100, "prompt_constraints": [],
                "post_generation_validators": [],
                "_generation_result": gen_result,
            },
        )
        state = ChunkState(chunk_id="T1", status=ChunkStatus.PASSED, attempts=1)
        dev_result = DevelopmentResult(
            plan_id="test", success=True,
            chunk_states={"T1": state},
            execution_order=[["T1"]],
            total_duration_seconds=1.0, summary="1 passed",
        )

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        with patch.object(
            ImplementPhaseHandler, "_tasks_to_chunks",
            return_value=([chunk], []),
        ), patch.object(
            ImplementPhaseHandler, "_run_development_phase",
            return_value=dev_result,
        ):
            result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        assert result["cost"] == pytest.approx(0.42)
        assert result["metadata"]["resumed"] is False
        assert "resumed_cost" not in result["metadata"]


# ============================================================================
# Tests: Fix 3 — broadened exception handling in cache loading
# ============================================================================


class TestResumeCacheExceptionHandling:
    """Verify corrupt/inaccessible cache files gracefully fall through."""

    def test_corrupt_binary_cache_falls_through(self, tmp_path):
        """Binary garbage in cache file doesn't crash — falls through to fresh run."""
        state_dir = tmp_path / ".startd8" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "generation_results.json").write_bytes(b"\x80\x81\xff\xfe")

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        gen_result = _make_gen_result(success=True, cost=0.10)
        chunk = DevelopmentChunk(
            chunk_id="T1", description="test", dependencies=[],
            file_targets=["src/feature.py"], implementation_prompt="test",
            test_commands=[], metadata={
                "feature_id": "F1", "title": "T1", "domain": "backend",
                "estimated_loc": 100, "prompt_constraints": [],
                "post_generation_validators": [],
                "_generation_result": gen_result,
            },
        )
        state = ChunkState(chunk_id="T1", status=ChunkStatus.PASSED, attempts=1)
        dev_result = DevelopmentResult(
            plan_id="test", success=True,
            chunk_states={"T1": state},
            execution_order=[["T1"]],
            total_duration_seconds=1.0, summary="1 passed",
        )

        with patch.object(
            ImplementPhaseHandler, "_tasks_to_chunks",
            return_value=([chunk], []),
        ), patch.object(
            ImplementPhaseHandler, "_run_development_phase",
            return_value=dev_result,
        ) as mock_run:
            result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        # Should have fallen through to fresh run
        mock_run.assert_called_once()
        assert result["metadata"]["resumed"] is False

    def test_malformed_json_cache_falls_through(self, tmp_path):
        """Syntactically invalid JSON in cache file falls through to fresh run."""
        state_dir = tmp_path / ".startd8" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "generation_results.json").write_text("{not valid json!")

        handler = ImplementPhaseHandler()
        tasks = [_make_env_fail_task("T1")]  # env-blocked so no LLM needed
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        # Should not raise — falls through to fresh run
        result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)
        assert result["metadata"]["resumed"] is False


# ============================================================================
# Tests: force_implement bypasses cache
# ============================================================================


class TestForceImplementBypassesCache:
    """Verify force_implement=True ignores valid cache on disk."""

    def test_force_implement_bypasses_valid_cache(self, tmp_path):
        """force_implement=True → valid cache on disk is ignored → fresh run."""
        state_dir = tmp_path / ".startd8" / "state"
        state_dir.mkdir(parents=True)

        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "feature.py").write_text("# generated")

        cache_data = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [str(tmp_path / "src/feature.py")],
                "error": None,
                "input_tokens": 1000,
                "output_tokens": 500,
                "cost_usd": 0.50,
                "iterations": 1,
                "model": "test:model",
            },
        })
        (state_dir / "generation_results.json").write_text(json.dumps(cache_data))

        handler = ImplementPhaseHandler(HandlerConfig(force_implement=True))
        tasks = [_make_seed_task(task_id="T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        gen_result = _make_gen_result(success=True, cost=0.30)
        chunk = DevelopmentChunk(
            chunk_id="T1", description="test", dependencies=[],
            file_targets=["src/feature.py"], implementation_prompt="test",
            test_commands=[], metadata={
                "feature_id": "F1", "title": "T1", "domain": "backend",
                "estimated_loc": 100, "prompt_constraints": [],
                "post_generation_validators": [],
                "_generation_result": gen_result,
            },
        )
        state = ChunkState(chunk_id="T1", status=ChunkStatus.PASSED, attempts=1)
        dev_result = DevelopmentResult(
            plan_id="test", success=True,
            chunk_states={"T1": state},
            execution_order=[["T1"]],
            total_duration_seconds=1.0, summary="1 passed",
        )

        with patch.object(
            ImplementPhaseHandler, "_tasks_to_chunks",
            return_value=([chunk], []),
        ), patch.object(
            ImplementPhaseHandler, "_run_development_phase",
            return_value=dev_result,
        ) as mock_run:
            result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        # Cache bypassed — _run_development_phase must be called
        mock_run.assert_called_once()
        assert result["metadata"]["resumed"] is False
        assert result["cost"] == pytest.approx(0.30)


# ============================================================================
# Tests: IMPLEMENT resume output structural parity
# ============================================================================


class TestResumeOutputStructuralParity:
    """Verify resumed output dict has the same keys as fresh-run output."""

    def test_resumed_output_has_development_result_summary(self, tmp_path):
        """Resumed output includes development_result_summary and execution_order."""
        state_dir = tmp_path / ".startd8" / "state"
        state_dir.mkdir(parents=True)

        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "feature.py").write_text("# generated")

        cache_data = _make_v2_cache({
            "T1": {
                "success": True,
                "generated_files": [str(tmp_path / "src/feature.py")],
                "error": None,
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.10,
                "iterations": 1,
                "model": "test:model",
            },
        })
        (state_dir / "generation_results.json").write_text(json.dumps(cache_data))

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        with patch.object(ImplementPhaseHandler, "_run_development_phase"):
            result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        output = result["output"]
        assert "development_result_summary" in output
        assert output["development_result_summary"] == "resumed from cache"
        assert "execution_order" in output
        assert isinstance(output["execution_order"], list)


# ============================================================================
# Tests: Cache write failure is non-fatal
# ============================================================================


class TestCacheWriteFailureNonFatal:
    """Verify IMPLEMENT cache write failures don't crash the phase."""

    def test_write_failure_is_non_fatal(self, tmp_path):
        """When atomic_write_json raises, IMPLEMENT completes successfully."""
        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        gen_result = _make_gen_result(success=True, cost=0.10)
        chunk = DevelopmentChunk(
            chunk_id="T1", description="test", dependencies=[],
            file_targets=["src/feature.py"], implementation_prompt="test",
            test_commands=[], metadata={
                "feature_id": "F1", "title": "T1", "domain": "backend",
                "estimated_loc": 100, "prompt_constraints": [],
                "post_generation_validators": [],
                "_generation_result": gen_result,
            },
        )
        state = ChunkState(chunk_id="T1", status=ChunkStatus.PASSED, attempts=1)
        dev_result = DevelopmentResult(
            plan_id="test", success=True,
            chunk_states={"T1": state},
            execution_order=[["T1"]],
            total_duration_seconds=1.0, summary="1 passed",
        )

        with patch.object(
            ImplementPhaseHandler, "_tasks_to_chunks",
            return_value=([chunk], []),
        ), patch.object(
            ImplementPhaseHandler, "_run_development_phase",
            return_value=dev_result,
        ), patch(
            "startd8.contractors.context_seed_handlers.atomic_write_json",
            side_effect=OSError("disk full"),
        ):
            result = handler.execute(WorkflowPhase.IMPLEMENT, context, dry_run=False)

        # Phase should complete successfully despite write failure
        assert result["cost"] == pytest.approx(0.10)
        assert "T1" in context["generation_results"]


# ============================================================================
# Tests: All-tasks-failed guard (API overload / auth error propagation)
# ============================================================================


class TestAllTasksFailedGuard:
    """IMPLEMENT phase raises RuntimeError when all tasks fail generation.

    Covers the scenario where chunks are dispatched to DevelopmentPhase
    but every task fails (e.g. API 529 overloaded, auth error). Without
    this guard, the phase silently reports "completed" with empty results,
    and downstream phases (INTEGRATE/TEST/REVIEW) run with nothing to do.
    """

    @patch.object(ImplementPhaseHandler, "_run_development_phase")
    def test_all_tasks_failed_raises_runtime_error(
        self, mock_run_dev, tmp_path,
    ):
        """When every chunk fails and gen_result is None, raise RuntimeError."""
        # Chunk with no _generation_result (API never responded)
        chunk = DevelopmentChunk(
            chunk_id="T1",
            description="test",
            dependencies=[],
            file_targets=["src/feature.py"],
            implementation_prompt="test",
            test_commands=[],
            metadata={
                "feature_id": "F1",
                "title": "Test feature",
                "domain": "backend",
                "estimated_loc": 100,
                "prompt_constraints": [],
                "post_generation_validators": [],
                # No _generation_result — API error before response
            },
        )

        state = ChunkState(
            chunk_id="T1",
            status=ChunkStatus.FAILED,
            attempts=3,
            last_error="Error code: 529 - overloaded",
        )
        dev_result = DevelopmentResult(
            plan_id="test",
            success=False,
            chunk_states={"T1": state},
            execution_order=[["T1"]],
            total_duration_seconds=45.0,
            summary="0 passed, 1 failed",
        )
        mock_run_dev.return_value = dev_result

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="T1")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        with patch.object(
            ImplementPhaseHandler, "_tasks_to_chunks",
            return_value=([chunk], []),
        ):
            with pytest.raises(RuntimeError, match="all 1 task.*failed generation"):
                handler.execute(
                    WorkflowPhase.IMPLEMENT, context, dry_run=False,
                )

    @patch.object(ImplementPhaseHandler, "_run_development_phase")
    def test_partial_failure_does_not_raise(
        self, mock_run_dev, tmp_path,
    ):
        """When at least one task succeeds, do not raise."""
        gen_result = _make_gen_result(success=True, cost=0.05)

        chunk_ok = DevelopmentChunk(
            chunk_id="T1",
            description="ok",
            dependencies=[],
            file_targets=["src/a.py"],
            implementation_prompt="test",
            test_commands=[],
            metadata={
                "feature_id": "F1",
                "title": "OK task",
                "domain": "backend",
                "estimated_loc": 50,
                "prompt_constraints": [],
                "post_generation_validators": [],
                "_generation_result": gen_result,
            },
        )
        chunk_fail = DevelopmentChunk(
            chunk_id="T2",
            description="fail",
            dependencies=[],
            file_targets=["src/b.py"],
            implementation_prompt="test",
            test_commands=[],
            metadata={
                "feature_id": "F2",
                "title": "Failed task",
                "domain": "backend",
                "estimated_loc": 50,
                "prompt_constraints": [],
                "post_generation_validators": [],
                # No _generation_result
            },
        )

        state_ok = ChunkState(
            chunk_id="T1", status=ChunkStatus.PASSED, attempts=1,
        )
        state_fail = ChunkState(
            chunk_id="T2", status=ChunkStatus.FAILED, attempts=3,
            last_error="API error",
        )
        dev_result = DevelopmentResult(
            plan_id="test",
            success=False,
            chunk_states={"T1": state_ok, "T2": state_fail},
            execution_order=[["T1", "T2"]],
            total_duration_seconds=30.0,
            summary="1 passed, 1 failed",
        )
        mock_run_dev.return_value = dev_result

        handler = ImplementPhaseHandler()
        tasks = [
            _make_seed_task(task_id="T1"),
            _make_seed_task(task_id="T2"),
        ]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        with patch.object(
            ImplementPhaseHandler, "_tasks_to_chunks",
            return_value=([chunk_ok, chunk_fail], []),
        ):
            # Should NOT raise — T1 succeeded
            result = handler.execute(
                WorkflowPhase.IMPLEMENT, context, dry_run=False,
            )

        assert "T1" in context["generation_results"]
        assert context["generation_results"]["T1"].success is True

    @patch.object(ImplementPhaseHandler, "_run_development_phase")
    def test_error_message_includes_task_details(
        self, mock_run_dev, tmp_path,
    ):
        """Error message includes task IDs and error details."""
        chunk = DevelopmentChunk(
            chunk_id="PI-005",
            description="test",
            dependencies=[],
            file_targets=["src/seed_context.py"],
            implementation_prompt="test",
            test_commands=[],
            metadata={
                "feature_id": "F-003",
                "title": "SeedContext",
                "domain": "backend",
                "estimated_loc": 100,
                "prompt_constraints": [],
                "post_generation_validators": [],
            },
        )

        state = ChunkState(
            chunk_id="PI-005",
            status=ChunkStatus.FAILED,
            attempts=3,
            last_error="529 overloaded",
        )
        dev_result = DevelopmentResult(
            plan_id="test",
            success=False,
            chunk_states={"PI-005": state},
            execution_order=[["PI-005"]],
            total_duration_seconds=45.0,
            summary="0 passed, 1 failed",
        )
        mock_run_dev.return_value = dev_result

        handler = ImplementPhaseHandler()
        tasks = [_make_seed_task(task_id="PI-005")]
        context: dict[str, Any] = {
            "tasks": tasks,
            "project_root": str(tmp_path),
        }

        with patch.object(
            ImplementPhaseHandler, "_tasks_to_chunks",
            return_value=([chunk], []),
        ):
            with pytest.raises(RuntimeError, match="PI-005.*529 overloaded"):
                handler.execute(
                    WorkflowPhase.IMPLEMENT, context, dry_run=False,
                )
