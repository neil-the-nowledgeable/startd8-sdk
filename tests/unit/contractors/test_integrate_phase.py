"""Unit tests for the INTEGRATE phase: IntegratePhaseHandler, SeedTaskUnit, context propagation."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.artisan_contractor import WorkflowPhase
from startd8.contractors.protocols import (
    GenerationResult,
    IntegrationListener,
    IntegrationResult,
    IntegrationUnit,
    MergeResult,
    MergeStatus,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class FakeSeedTask:
    """Minimal SeedTask for testing (matches context_seed_handlers.SeedTask fields)."""

    task_id: str = "task-001"
    title: str = "Implement widget"
    task_type: str = "implementation"
    story_points: int = 3
    priority: str = "high"
    labels: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    description: str = "Build the widget module"
    target_files: List[str] = field(default_factory=list)
    estimated_loc: int = 100
    feature_id: str = "feat-001"
    domain: str = "python_library"
    domain_reasoning: str = "test"
    environment_checks: List[Dict[str, Any]] = field(default_factory=list)
    prompt_constraints: List[str] = field(default_factory=list)
    post_generation_validators: List[str] = field(default_factory=list)
    available_siblings: List[str] = field(default_factory=list)
    existing_content_hash: Optional[str] = None
    design_doc_sections: List[str] = field(default_factory=list)
    artifact_types_addressed: List[str] = field(default_factory=list)
    file_scope: Dict[str, str] = field(default_factory=dict)
    deps_source: Optional[str] = None
    deps_confidence: float = 1.0
    requirements_text: str = ""
    api_signatures: List[str] = field(default_factory=list)
    protocol: str = ""
    runtime_dependencies: List[str] = field(default_factory=list)
    negative_scope: List[str] = field(default_factory=list)
    wave_index: Optional[int] = None


class FakeMergeStrategy:
    """Simple merge strategy that copies source to target."""

    def can_merge(self, source: Path, target: Path) -> bool:
        return True

    def merge(self, source: Path, target: Path, backup: bool = True) -> MergeResult:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return MergeResult(status=MergeStatus.SUCCESS)


class FailingMergeStrategy:
    """Merge strategy that always returns ERROR."""

    def can_merge(self, source: Path, target: Path) -> bool:
        return True

    def merge(self, source: Path, target: Path, backup: bool = True) -> MergeResult:
        return MergeResult(status=MergeStatus.ERROR, error="Merge failed on purpose")


# ---------------------------------------------------------------------------
# TestSeedTaskUnit
# ---------------------------------------------------------------------------


class TestSeedTaskUnit:
    """Verify SeedTaskUnit satisfies IntegrationUnit and forwards fields."""

    def test_protocol_compliance(self):
        """SeedTaskUnit satisfies IntegrationUnit at runtime."""
        from startd8.contractors.context_seed_handlers import SeedTaskUnit

        task = FakeSeedTask(
            task_id="t-1",
            title="Test Task",
            target_files=["src/mod.py"],
        )
        gr = GenerationResult(
            success=True,
            generated_files=[Path("/tmp/staging/mod.py")],
            model="mock:mock",
            cost_usd=0.01,
            iterations=2,
            input_tokens=100,
            output_tokens=200,
        )

        unit = SeedTaskUnit(task, gr)
        assert isinstance(unit, IntegrationUnit)

    def test_id_returns_task_id(self):
        from startd8.contractors.context_seed_handlers import SeedTaskUnit

        task = FakeSeedTask(task_id="task-42")
        gr = GenerationResult(success=True)

        unit = SeedTaskUnit(task, gr)
        assert unit.id == "task-42"

    def test_name_returns_title(self):
        from startd8.contractors.context_seed_handlers import SeedTaskUnit

        task = FakeSeedTask(title="My Cool Task")
        gr = GenerationResult(success=True)

        unit = SeedTaskUnit(task, gr)
        assert unit.name == "My Cool Task"

    def test_generated_files_returns_strings(self):
        from startd8.contractors.context_seed_handlers import SeedTaskUnit

        task = FakeSeedTask()
        gr = GenerationResult(
            success=True,
            generated_files=[Path("/tmp/a.py"), Path("/tmp/b.py")],
        )

        unit = SeedTaskUnit(task, gr)
        assert unit.generated_files == ["/tmp/a.py", "/tmp/b.py"]

    def test_target_files_returns_task_targets(self):
        from startd8.contractors.context_seed_handlers import SeedTaskUnit

        task = FakeSeedTask(target_files=["src/widget.py", "tests/test_widget.py"])
        gr = GenerationResult(success=True)

        unit = SeedTaskUnit(task, gr)
        assert unit.target_files == ["src/widget.py", "tests/test_widget.py"]

    def test_context_forwards_all_task_fields(self):
        """Context dict contains all SeedTask fields via asdict."""
        from startd8.contractors.context_seed_handlers import SeedTaskUnit

        task = FakeSeedTask(
            task_id="t-1",
            title="Widget",
            domain="python_library",
            estimated_loc=200,
        )
        gr = GenerationResult(
            success=True,
            model="anthropic:haiku",
            cost_usd=0.05,
            iterations=3,
            input_tokens=500,
            output_tokens=1000,
        )

        unit = SeedTaskUnit(task, gr)
        ctx = unit.context

        # Task fields
        assert ctx["task_id"] == "t-1"
        assert ctx["title"] == "Widget"
        assert ctx["domain"] == "python_library"
        assert ctx["estimated_loc"] == 200

        # Generation metadata
        assert "_generation" in ctx
        gen = ctx["_generation"]
        assert gen["model"] == "anthropic:haiku"
        assert gen["cost_usd"] == 0.05
        assert gen["iterations"] == 3
        assert gen["input_tokens"] == 500
        assert gen["output_tokens"] == 1000


# ---------------------------------------------------------------------------
# TestArtisanIntegrationListener
# ---------------------------------------------------------------------------


class TestArtisanIntegrationListener:
    """Verify ArtisanIntegrationListener logs without errors."""

    def test_all_methods_callable(self):
        from startd8.contractors.context_seed_handlers import ArtisanIntegrationListener

        listener = ArtisanIntegrationListener("task-001")

        # Create a minimal unit-like object
        unit = MagicMock()
        unit.name = "Test Task"

        # All methods should run without raising
        listener.on_integration_started(unit)
        listener.on_file_integrated(unit, Path("source.py"), Path("target.py"))
        listener.on_checkpoint_result(unit, None)
        listener.on_integration_failed(unit, "some error")
        listener.on_integration_completed(unit, [Path("a.py")])

    def test_satisfies_integration_listener_protocol(self):
        from startd8.contractors.context_seed_handlers import ArtisanIntegrationListener

        listener = ArtisanIntegrationListener("task-001")
        assert isinstance(listener, IntegrationListener)


# ---------------------------------------------------------------------------
# TestIntegratePhaseHandler
# ---------------------------------------------------------------------------


class TestIntegratePhaseHandler:
    """Test IntegratePhaseHandler.execute() with mocked engine."""

    @pytest.fixture
    def project_root(self, tmp_path):
        root = tmp_path / "project"
        root.mkdir()
        (root / "src").mkdir()
        return root

    @pytest.fixture
    def staging_dir(self, project_root):
        sd = project_root / ".startd8" / "staging"
        sd.mkdir(parents=True)
        return sd

    def _make_handler(self):
        from startd8.contractors.context_seed_handlers import (
            HandlerConfig,
            IntegratePhaseHandler,
        )
        config = HandlerConfig()
        return IntegratePhaseHandler(config=config)

    @patch("startd8.contractors.integration_engine.IntegrationEngine")
    @patch("startd8.contractors.registry.get_registry")
    @patch("startd8.contractors.context_seed.phases.integrate._ensure_context_loaded")
    def test_success_path(
        self,
        mock_ensure_ctx,
        mock_get_registry,
        mock_engine_cls,
        project_root,
        staging_dir,
    ):
        """Successful integration: engine returns success for all tasks."""
        task = FakeSeedTask(
            task_id="task-001",
            title="Widget",
            target_files=[str(project_root / "src" / "widget.py")],
        )
        mock_ensure_ctx.return_value = [task]

        mock_registry = MagicMock()
        mock_registry.get_default_merge_strategy.return_value = FakeMergeStrategy
        mock_get_registry.return_value = mock_registry

        mock_engine = MagicMock()
        mock_engine.integrate.return_value = IntegrationResult(
            success=True,
            integrated_files=[project_root / "src" / "widget.py"],
        )
        mock_engine_cls.return_value = mock_engine

        gr = GenerationResult(
            success=True,
            generated_files=[staging_dir / "widget.py"],
        )

        context = {
            "project_root": str(project_root),
            "_staging_dir": str(staging_dir),
            "tasks": [task],
            "generation_results": {"task-001": gr},
        }

        handler = self._make_handler()
        result = handler.execute(WorkflowPhase.INTEGRATE, context)

        assert result["cost"] == 0.0
        assert result["metadata"]["passed"] == 1
        assert result["metadata"]["total"] == 1
        assert context["integration_results"]["task-001"]["success"] is True

    @patch("startd8.contractors.integration_engine.IntegrationEngine")
    @patch("startd8.contractors.registry.get_registry")
    @patch("startd8.contractors.context_seed.phases.integrate._ensure_context_loaded")
    def test_partial_failure(
        self,
        mock_ensure_ctx,
        mock_get_registry,
        mock_engine_cls,
        project_root,
        staging_dir,
    ):
        """Some tasks succeed, some fail — results captured per-task."""
        task_a = FakeSeedTask(
            task_id="task-a",
            title="Task A",
            target_files=[str(project_root / "src" / "a.py")],
        )
        task_b = FakeSeedTask(
            task_id="task-b",
            title="Task B",
            target_files=[str(project_root / "src" / "b.py")],
        )
        mock_ensure_ctx.return_value = [task_a, task_b]

        mock_registry = MagicMock()
        mock_registry.get_default_merge_strategy.return_value = FakeMergeStrategy
        mock_get_registry.return_value = mock_registry

        mock_engine = MagicMock()

        def side_effect(unit, listener=None):
            if unit.id == "task-a":
                return IntegrationResult(
                    success=True,
                    integrated_files=[project_root / "src" / "a.py"],
                )
            return IntegrationResult(
                success=False,
                errors=["Syntax error in b.py"],
                rollback_performed=True,
            )

        mock_engine.integrate.side_effect = side_effect
        mock_engine_cls.return_value = mock_engine

        context = {
            "project_root": str(project_root),
            "_staging_dir": str(staging_dir),
            "tasks": [task_a, task_b],
            "generation_results": {
                "task-a": GenerationResult(
                    success=True,
                    generated_files=[staging_dir / "a.py"],
                ),
                "task-b": GenerationResult(
                    success=True,
                    generated_files=[staging_dir / "b.py"],
                ),
            },
        }

        handler = self._make_handler()
        result = handler.execute(WorkflowPhase.INTEGRATE, context)

        assert result["metadata"]["passed"] == 1
        assert result["metadata"]["total"] == 2
        assert context["integration_results"]["task-a"]["success"] is True
        assert context["integration_results"]["task-b"]["success"] is False
        assert context["integration_results"]["task-b"]["rollback_performed"] is True

    @patch("startd8.contractors.integration_engine.IntegrationEngine")
    @patch("startd8.contractors.registry.get_registry")
    @patch("startd8.contractors.context_seed.phases.integrate._ensure_context_loaded")
    def test_all_fail(
        self,
        mock_ensure_ctx,
        mock_get_registry,
        mock_engine_cls,
        project_root,
        staging_dir,
    ):
        """All tasks fail — still writes results to context."""
        task = FakeSeedTask(task_id="task-001")
        mock_ensure_ctx.return_value = [task]

        mock_registry = MagicMock()
        mock_registry.get_default_merge_strategy.return_value = FakeMergeStrategy
        mock_get_registry.return_value = mock_registry

        mock_engine = MagicMock()
        mock_engine.integrate.return_value = IntegrationResult(
            success=False,
            errors=["No files integrated"],
        )
        mock_engine_cls.return_value = mock_engine

        context = {
            "project_root": str(project_root),
            "_staging_dir": str(staging_dir),
            "tasks": [task],
            "generation_results": {
                "task-001": GenerationResult(success=True),
            },
        }

        handler = self._make_handler()
        result = handler.execute(WorkflowPhase.INTEGRATE, context)

        assert result["metadata"]["passed"] == 0
        assert result["metadata"]["total"] == 1
        assert context["integration_results"]["task-001"]["success"] is False

    @patch("startd8.contractors.integration_engine.IntegrationEngine")
    @patch("startd8.contractors.registry.get_registry")
    @patch("startd8.contractors.context_seed.phases.integrate._ensure_context_loaded")
    def test_dry_run(
        self,
        mock_ensure_ctx,
        mock_get_registry,
        mock_engine_cls,
        project_root,
        staging_dir,
    ):
        """Dry run passes dry_run=True to engine, staging dir not cleaned."""
        task = FakeSeedTask(task_id="task-001")
        mock_ensure_ctx.return_value = [task]

        mock_registry = MagicMock()
        mock_registry.get_default_merge_strategy.return_value = FakeMergeStrategy
        mock_get_registry.return_value = mock_registry

        mock_engine = MagicMock()
        mock_engine.integrate.return_value = IntegrationResult(
            success=True,
            integrated_files=[project_root / "src" / "mod.py"],
        )
        mock_engine_cls.return_value = mock_engine

        # Put a file in staging to verify it's not cleaned
        (staging_dir / "marker.txt").write_text("keep me")

        context = {
            "project_root": str(project_root),
            "_staging_dir": str(staging_dir),
            "tasks": [task],
            "generation_results": {
                "task-001": GenerationResult(success=True),
            },
        }

        handler = self._make_handler()
        result = handler.execute(WorkflowPhase.INTEGRATE, context, dry_run=True)

        # Engine was constructed with dry_run=True
        _, kwargs = mock_engine_cls.call_args
        assert kwargs.get("dry_run") is True

        # Staging dir should still exist (not cleaned in dry run)
        assert staging_dir.exists()
        assert (staging_dir / "marker.txt").exists()

    @patch("startd8.contractors.integration_engine.IntegrationEngine")
    @patch("startd8.contractors.registry.get_registry")
    @patch("startd8.contractors.context_seed.phases.integrate._ensure_context_loaded")
    def test_skips_failed_generation_results(
        self,
        mock_ensure_ctx,
        mock_get_registry,
        mock_engine_cls,
        project_root,
        staging_dir,
    ):
        """Tasks with failed generation_results are skipped."""
        task = FakeSeedTask(task_id="task-001")
        mock_ensure_ctx.return_value = [task]

        mock_registry = MagicMock()
        mock_registry.get_default_merge_strategy.return_value = FakeMergeStrategy
        mock_get_registry.return_value = mock_registry

        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        context = {
            "project_root": str(project_root),
            "_staging_dir": str(staging_dir),
            "tasks": [task],
            "generation_results": {
                "task-001": GenerationResult(success=False, error="Generation failed"),
            },
        }

        handler = self._make_handler()
        result = handler.execute(WorkflowPhase.INTEGRATE, context)

        # Engine should not have been called at all
        mock_engine.integrate.assert_not_called()
        assert result["metadata"]["total"] == 1

    @patch("startd8.contractors.integration_engine.IntegrationEngine")
    @patch("startd8.contractors.registry.get_registry")
    @patch("startd8.contractors.context_seed.phases.integrate._ensure_context_loaded")
    def test_skips_unknown_task_ids(
        self,
        mock_ensure_ctx,
        mock_get_registry,
        mock_engine_cls,
        project_root,
        staging_dir,
    ):
        """generation_results with no matching task in task_map are skipped."""
        task = FakeSeedTask(task_id="task-001")
        mock_ensure_ctx.return_value = [task]

        mock_registry = MagicMock()
        mock_registry.get_default_merge_strategy.return_value = FakeMergeStrategy
        mock_get_registry.return_value = mock_registry

        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        context = {
            "project_root": str(project_root),
            "_staging_dir": str(staging_dir),
            "tasks": [task],
            "generation_results": {
                "unknown-task": GenerationResult(success=True),
            },
        }

        handler = self._make_handler()
        result = handler.execute(WorkflowPhase.INTEGRATE, context)

        mock_engine.integrate.assert_not_called()
        assert result["metadata"]["total"] == 0


# ---------------------------------------------------------------------------
# TestContextPropagation
# ---------------------------------------------------------------------------


class TestContextPropagation:
    """Verify context dict is correctly updated by IntegratePhaseHandler."""

    @pytest.fixture
    def project_root(self, tmp_path):
        root = tmp_path / "project"
        root.mkdir()
        return root

    @pytest.fixture
    def staging_dir(self, project_root):
        sd = project_root / ".startd8" / "staging"
        sd.mkdir(parents=True)
        return sd

    @patch("startd8.contractors.integration_engine.IntegrationEngine")
    @patch("startd8.contractors.registry.get_registry")
    @patch("startd8.contractors.context_seed.phases.integrate._ensure_context_loaded")
    def test_generation_results_paths_updated(
        self,
        mock_ensure_ctx,
        mock_get_registry,
        mock_engine_cls,
        project_root,
        staging_dir,
    ):
        """On success, generation_results.generated_files are updated to project paths."""
        from startd8.contractors.context_seed_handlers import IntegratePhaseHandler, HandlerConfig

        task = FakeSeedTask(
            task_id="task-001",
            target_files=[str(project_root / "src" / "widget.py")],
        )
        mock_ensure_ctx.return_value = [task]

        mock_registry = MagicMock()
        mock_registry.get_default_merge_strategy.return_value = FakeMergeStrategy
        mock_get_registry.return_value = mock_registry

        integrated_path = project_root / "src" / "widget.py"
        mock_engine = MagicMock()
        mock_engine.integrate.return_value = IntegrationResult(
            success=True,
            integrated_files=[integrated_path],
        )
        mock_engine_cls.return_value = mock_engine

        gr = GenerationResult(
            success=True,
            generated_files=[staging_dir / "widget.py"],
        )

        context = {
            "project_root": str(project_root),
            "_staging_dir": str(staging_dir),
            "tasks": [task],
            "generation_results": {"task-001": gr},
        }

        handler = IntegratePhaseHandler(config=HandlerConfig())
        handler.execute(WorkflowPhase.INTEGRATE, context)

        # generation_results paths should now point to project_root
        assert gr.generated_files == [Path(str(integrated_path))]

    @patch("startd8.contractors.integration_engine.IntegrationEngine")
    @patch("startd8.contractors.registry.get_registry")
    @patch("startd8.contractors.context_seed.phases.integrate._ensure_context_loaded")
    def test_integration_results_written_to_context(
        self,
        mock_ensure_ctx,
        mock_get_registry,
        mock_engine_cls,
        project_root,
        staging_dir,
    ):
        """integration_results key is added to context dict."""
        from startd8.contractors.context_seed_handlers import IntegratePhaseHandler, HandlerConfig

        task = FakeSeedTask(task_id="task-001")
        mock_ensure_ctx.return_value = [task]

        mock_registry = MagicMock()
        mock_registry.get_default_merge_strategy.return_value = FakeMergeStrategy
        mock_get_registry.return_value = mock_registry

        mock_engine = MagicMock()
        mock_engine.integrate.return_value = IntegrationResult(
            success=True,
            integrated_files=[project_root / "src" / "mod.py"],
        )
        mock_engine_cls.return_value = mock_engine

        context = {
            "project_root": str(project_root),
            "_staging_dir": str(staging_dir),
            "tasks": [task],
            "generation_results": {
                "task-001": GenerationResult(success=True),
            },
        }

        handler = IntegratePhaseHandler(config=HandlerConfig())
        handler.execute(WorkflowPhase.INTEGRATE, context)

        assert "integration_results" in context
        assert "task-001" in context["integration_results"]
        ir = context["integration_results"]["task-001"]
        assert ir["success"] is True
        assert isinstance(ir["integrated_files"], list)

    @patch("startd8.contractors.integration_engine.IntegrationEngine")
    @patch("startd8.contractors.registry.get_registry")
    @patch("startd8.contractors.context_seed.phases.integrate._ensure_context_loaded")
    def test_failed_task_paths_not_updated(
        self,
        mock_ensure_ctx,
        mock_get_registry,
        mock_engine_cls,
        project_root,
        staging_dir,
    ):
        """On failure, generation_results.generated_files retain staging paths."""
        from startd8.contractors.context_seed_handlers import IntegratePhaseHandler, HandlerConfig

        task = FakeSeedTask(task_id="task-001")
        mock_ensure_ctx.return_value = [task]

        mock_registry = MagicMock()
        mock_registry.get_default_merge_strategy.return_value = FakeMergeStrategy
        mock_get_registry.return_value = mock_registry

        mock_engine = MagicMock()
        mock_engine.integrate.return_value = IntegrationResult(
            success=False,
            errors=["Checkpoint failed"],
            rollback_performed=True,
        )
        mock_engine_cls.return_value = mock_engine

        original_staging_file = staging_dir / "mod.py"
        gr = GenerationResult(
            success=True,
            generated_files=[original_staging_file],
        )

        context = {
            "project_root": str(project_root),
            "_staging_dir": str(staging_dir),
            "tasks": [task],
            "generation_results": {"task-001": gr},
        }

        handler = IntegratePhaseHandler(config=HandlerConfig())
        handler.execute(WorkflowPhase.INTEGRATE, context)

        # Failed merges now clear generated_files
        assert gr.generated_files == []


# ---------------------------------------------------------------------------
# TestResumeCompat
# ---------------------------------------------------------------------------


class TestResumeCompat:
    """Simulate checkpoint resume after IMPLEMENT — verify INTEGRATE runs correctly."""

    @pytest.fixture
    def project_root(self, tmp_path):
        root = tmp_path / "project"
        root.mkdir()
        return root

    @pytest.fixture
    def staging_dir(self, project_root):
        sd = project_root / ".startd8" / "staging"
        sd.mkdir(parents=True)
        return sd

    @patch("startd8.contractors.integration_engine.IntegrationEngine")
    @patch("startd8.contractors.registry.get_registry")
    @patch("startd8.contractors.context_seed.phases.integrate._ensure_context_loaded")
    def test_resume_after_implement(
        self,
        mock_ensure_ctx,
        mock_get_registry,
        mock_engine_cls,
        project_root,
        staging_dir,
    ):
        """After checkpoint resume, INTEGRATE processes staging files normally."""
        from startd8.contractors.context_seed_handlers import IntegratePhaseHandler, HandlerConfig

        task = FakeSeedTask(
            task_id="task-001",
            target_files=[str(project_root / "src" / "widget.py")],
        )
        mock_ensure_ctx.return_value = [task]

        mock_registry = MagicMock()
        mock_registry.get_default_merge_strategy.return_value = FakeMergeStrategy
        mock_get_registry.return_value = mock_registry

        mock_engine = MagicMock()
        mock_engine.integrate.return_value = IntegrationResult(
            success=True,
            integrated_files=[project_root / "src" / "widget.py"],
        )
        mock_engine_cls.return_value = mock_engine

        # Simulate resumed context: tasks loaded from seed, staging paths in generation_results
        staged_file = staging_dir / "widget.py"
        staged_file.write_text("# generated code")

        context = {
            "project_root": str(project_root),
            "_staging_dir": str(staging_dir),
            "enriched_seed_path": "/path/to/seed.json",
            "tasks": [task],
            "generation_results": {
                "task-001": GenerationResult(
                    success=True,
                    generated_files=[staged_file],
                    model="mock:mock",
                ),
            },
        }

        handler = IntegratePhaseHandler(config=HandlerConfig())
        result = handler.execute(WorkflowPhase.INTEGRATE, context)

        assert result["metadata"]["passed"] == 1
        assert context["integration_results"]["task-001"]["success"] is True

    @patch("startd8.contractors.integration_engine.IntegrationEngine")
    @patch("startd8.contractors.registry.get_registry")
    @patch("startd8.contractors.context_seed.phases.integrate._ensure_context_loaded")
    def test_empty_generation_results_produces_empty_output(
        self,
        mock_ensure_ctx,
        mock_get_registry,
        mock_engine_cls,
        project_root,
        staging_dir,
    ):
        """When generation_results is empty, INTEGRATE completes with 0 tasks."""
        from startd8.contractors.context_seed_handlers import IntegratePhaseHandler, HandlerConfig

        mock_ensure_ctx.return_value = []

        mock_registry = MagicMock()
        mock_registry.get_default_merge_strategy.return_value = FakeMergeStrategy
        mock_get_registry.return_value = mock_registry

        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine

        context = {
            "project_root": str(project_root),
            "_staging_dir": str(staging_dir),
            "tasks": [],
            "generation_results": {},
        }

        handler = IntegratePhaseHandler(config=HandlerConfig())
        result = handler.execute(WorkflowPhase.INTEGRATE, context)

        assert result["metadata"]["passed"] == 0
        assert result["metadata"]["total"] == 0
        assert context["integration_results"] == {}
        mock_engine.integrate.assert_not_called()
