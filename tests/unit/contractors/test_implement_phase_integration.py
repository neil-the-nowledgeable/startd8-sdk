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
    LLMChunkExecutor,
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

        handler = ImplementPhaseHandler()

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
        design_results = {
            "T1": {
                "status": "designed",
                "design_document": (
                    "├── __init__.py   ← THIS FILE\n"
                    "├── artifact_generators.py   ← shared, F-002+\n"
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
