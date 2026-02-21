"""Unit tests for IntegrationEngine."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.checkpoint import CheckpointResult, CheckpointStatus
from startd8.contractors.integration_engine import IntegrationEngine, NullListener
from startd8.contractors.protocols import (
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
class FakeUnit:
    """Minimal IntegrationUnit for testing."""

    _id: str = "test-unit"
    _name: str = "Test Unit"
    _generated_files: List[str] = field(default_factory=list)
    _target_files: List[str] = field(default_factory=list)
    _context: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def generated_files(self) -> List[str]:
        return self._generated_files

    @property
    def target_files(self) -> List[str]:
        return self._target_files

    @property
    def context(self) -> Dict[str, Any]:
        return self._context


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


class RecordingListener:
    """Listener that records all calls for assertion."""

    def __init__(self):
        self.started: List[IntegrationUnit] = []
        self.files_integrated: List[tuple] = []
        self.checkpoint_results: List[tuple] = []
        self.failures: List[tuple] = []
        self.completed: List[tuple] = []

    def on_integration_started(self, unit):
        self.started.append(unit)

    def on_file_integrated(self, unit, source, target):
        self.files_integrated.append((unit, source, target))

    def on_checkpoint_result(self, unit, result):
        self.checkpoint_results.append((unit, result))

    def on_integration_failed(self, unit, error):
        self.failures.append((unit, error))

    def on_integration_completed(self, unit, files):
        self.completed.append((unit, files))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project_root(tmp_path):
    """Create a temp project root with a git repo."""
    root = tmp_path / "project"
    root.mkdir()
    return root


@pytest.fixture
def engine(project_root):
    """Create an IntegrationEngine with defaults."""
    return IntegrationEngine(
        project_root=project_root,
        merge_strategy=FakeMergeStrategy(),
        checkpoint=None,  # No checkpoints for basic tests
        dry_run=False,
        auto_commit=False,
    )


# ---------------------------------------------------------------------------
# TestSnapshotLifecycle
# ---------------------------------------------------------------------------

class TestSnapshotLifecycle:
    """Test snapshot/restore/cleanup with tmp_path."""

    def test_snapshot_existing_file(self, engine, project_root):
        target = project_root / "main.py"
        target.write_text("original content")

        engine._snapshot_target(target)

        snapshot = target.with_suffix(".py.pre_integration")
        assert snapshot.exists()
        assert snapshot.read_text() == "original content"
        assert str(target) in engine._pre_integration_snapshots

    def test_snapshot_absent_file_stores_none(self, engine, project_root):
        target = project_root / "new_file.py"

        engine._snapshot_target(target)

        assert str(target) in engine._pre_integration_snapshots
        assert engine._pre_integration_snapshots[str(target)] is None

    def test_snapshot_idempotent(self, engine, project_root):
        target = project_root / "main.py"
        target.write_text("v1")
        engine._snapshot_target(target)

        target.write_text("v2")
        engine._snapshot_target(target)  # should NOT re-snapshot

        snapshot = target.with_suffix(".py.pre_integration")
        assert snapshot.read_text() == "v1"  # original, not v2

    def test_restore_from_snapshot(self, engine, project_root):
        target = project_root / "main.py"
        target.write_text("original")
        engine._snapshot_target(target)

        target.write_text("modified")
        assert engine._restore_target(target) is True
        assert target.read_text() == "original"

    def test_restore_absent_file_deletes_created(self, engine, project_root):
        target = project_root / "new_file.py"
        engine._snapshot_target(target)  # records None

        target.write_text("should be deleted")
        assert engine._restore_target(target) is True
        assert not target.exists()

    def test_restore_no_snapshot_returns_false(self, engine, project_root):
        target = project_root / "unknown.py"
        assert engine._restore_target(target) is False

    def test_cleanup_removes_snapshot_files(self, engine, project_root):
        target = project_root / "main.py"
        target.write_text("content")
        engine._snapshot_target(target)

        snapshot = target.with_suffix(".py.pre_integration")
        assert snapshot.exists()

        removed = engine._cleanup_snapshots([target])
        assert removed == 1
        assert not snapshot.exists()

    def test_cleanup_all(self, engine, project_root):
        for name in ["a.py", "b.py"]:
            t = project_root / name
            t.write_text("x")
            engine._snapshot_target(t)

        removed = engine._cleanup_snapshots()
        assert removed == 2


# ---------------------------------------------------------------------------
# TestIntegrate
# ---------------------------------------------------------------------------

class TestIntegrate:
    """Test the integrate() pipeline end-to-end."""

    def test_success_path(self, engine, project_root):
        """Files are merged, result is success."""
        src = project_root / "staging" / "mod.py"
        src.parent.mkdir()
        src.write_text("print('hello')")

        tgt = project_root / "src" / "mod.py"

        unit = FakeUnit(
            _generated_files=[str(src)],
            _target_files=[str(tgt)],
        )

        result = engine.integrate(unit)

        assert result.success is True
        assert len(result.integrated_files) == 1
        assert tgt.exists()
        assert tgt.read_text() == "print('hello')"

    def test_no_files_integrated_returns_failure(self, engine, project_root):
        """When source files don't exist, integration fails."""
        unit = FakeUnit(
            _generated_files=[str(project_root / "nonexistent.py")],
            _target_files=[str(project_root / "target.py")],
        )

        result = engine.integrate(unit)

        assert result.success is False
        assert "No files were integrated" in result.errors[0]

    def test_dry_run_does_not_write(self, project_root):
        """Dry run logs but does not modify files."""
        engine = IntegrationEngine(
            project_root=project_root,
            merge_strategy=FakeMergeStrategy(),
            dry_run=True,
        )

        src = project_root / "staging" / "mod.py"
        src.parent.mkdir()
        src.write_text("print('hello')")

        tgt = project_root / "src" / "mod.py"

        unit = FakeUnit(
            _generated_files=[str(src)],
            _target_files=[str(tgt)],
        )

        result = engine.integrate(unit)

        assert result.success is True
        assert len(result.integrated_files) == 1
        # Target should NOT have been written (dry run)
        assert not tgt.exists()

    def test_listener_callbacks(self, engine, project_root):
        """Listener receives started, file_integrated, and completed."""
        src = project_root / "gen" / "a.py"
        src.parent.mkdir()
        src.write_text("x = 1")

        tgt = project_root / "src" / "a.py"

        unit = FakeUnit(
            _generated_files=[str(src)],
            _target_files=[str(tgt)],
        )

        listener = RecordingListener()
        engine.integrate(unit, listener=listener)

        assert len(listener.started) == 1
        assert len(listener.files_integrated) == 1
        assert len(listener.completed) == 1
        assert len(listener.failures) == 0

    def test_rollback_on_checkpoint_failure(self, project_root):
        """When checkpoints fail, files are rolled back."""
        mock_checkpoint = MagicMock()
        mock_checkpoint.pre_validate.return_value = CheckpointResult(
            status=CheckpointStatus.PASSED,
            name="Pre-validate",
            message="OK",
        )
        mock_checkpoint.run_all_checkpoints.return_value = [
            CheckpointResult(
                status=CheckpointStatus.FAILED,
                name="Syntax Check",
                message="Syntax error",
                errors=["invalid syntax line 5"],
            ),
        ]
        mock_checkpoint.summarize_results.return_value = False

        engine = IntegrationEngine(
            project_root=project_root,
            merge_strategy=FakeMergeStrategy(),
            checkpoint=mock_checkpoint,
        )

        # Pre-existing target
        tgt = project_root / "mod.py"
        tgt.write_text("original")

        src = project_root / "gen" / "mod.py"
        src.parent.mkdir()
        src.write_text("broken code")

        unit = FakeUnit(
            _generated_files=[str(src)],
            _target_files=[str(tgt)],
        )

        listener = RecordingListener()
        result = engine.integrate(unit, listener=listener)

        assert result.success is False
        assert result.rollback_performed is True
        assert len(listener.failures) == 1
        # Target should be restored to original
        assert tgt.read_text() == "original"

    @patch("startd8.contractors.integration_engine.subprocess")
    def test_auto_commit(self, mock_subprocess, project_root):
        """When auto_commit is True, git add/commit are called."""
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        engine = IntegrationEngine(
            project_root=project_root,
            merge_strategy=FakeMergeStrategy(),
            auto_commit=True,
        )

        src = project_root / "gen" / "a.py"
        src.parent.mkdir()
        src.write_text("x = 1")
        tgt = project_root / "src" / "a.py"

        unit = FakeUnit(
            _generated_files=[str(src)],
            _target_files=[str(tgt)],
        )

        result = engine.integrate(unit)

        assert result.success is True
        # git add + git commit = at least 2 subprocess.run calls
        assert mock_subprocess.run.call_count >= 2

    def test_retry_restores_snapshots(self, engine, project_root):
        """On attempt > 1, targets are restored from snapshots first."""
        tgt = project_root / "mod.py"
        tgt.write_text("original")

        src = project_root / "gen" / "mod.py"
        src.parent.mkdir()
        src.write_text("new code")

        unit = FakeUnit(
            _generated_files=[str(src)],
            _target_files=[str(tgt)],
        )

        # First attempt: creates snapshot
        engine.integrate(unit, attempt=1)
        assert tgt.read_text() == "new code"

        # Simulate modification
        tgt.write_text("modified in between")

        # Prepare a new source for retry
        src.write_text("retry code")

        # Second attempt: should restore from snapshot first
        result = engine.integrate(unit, attempt=2)

        assert result.success is True
        assert tgt.read_text() == "retry code"

    def test_advisory_checkpoint_downgrade(self, project_root):
        """Import Check and Lint Check FAILED are downgraded to WARNING."""
        mock_checkpoint = MagicMock()
        mock_checkpoint.pre_validate.return_value = CheckpointResult(
            status=CheckpointStatus.PASSED,
            name="Pre-validate",
            message="OK",
        )
        mock_checkpoint.run_all_checkpoints.return_value = [
            CheckpointResult(
                status=CheckpointStatus.PASSED,
                name="Syntax Check",
                message="OK",
            ),
            CheckpointResult(
                status=CheckpointStatus.FAILED,
                name="Import Check",
                message="Import failed",
                errors=["ModuleNotFoundError: foo"],
            ),
            CheckpointResult(
                status=CheckpointStatus.FAILED,
                name="Lint Check",
                message="Lint failed",
                errors=["F821 undefined name"],
            ),
        ]
        mock_checkpoint.summarize_results.return_value = True  # all pass after downgrade

        engine = IntegrationEngine(
            project_root=project_root,
            merge_strategy=FakeMergeStrategy(),
            checkpoint=mock_checkpoint,
        )

        src = project_root / "gen" / "mod.py"
        src.parent.mkdir()
        src.write_text("x = 1")
        tgt = project_root / "out" / "mod.py"

        unit = FakeUnit(
            _generated_files=[str(src)],
            _target_files=[str(tgt)],
        )

        result = engine.integrate(unit)
        assert result.success is True

        # Verify the checkpoint results were downgraded
        import_result = [
            r for r in mock_checkpoint.run_all_checkpoints.return_value
            if r.name == "Import Check"
        ][0]
        assert import_result.status == CheckpointStatus.WARNING


# ---------------------------------------------------------------------------
# TestDirtyProtection
# ---------------------------------------------------------------------------

class TestDirtyProtection:
    """Test dirty file protection."""

    @patch("startd8.contractors.integration_engine.subprocess")
    def test_dirty_target_blocks_merge(self, mock_subprocess, project_root):
        """Dirty target file blocks integration when allow_dirty=False."""
        # Make is_file_dirty return True
        mock_subprocess.run.return_value = MagicMock(
            stdout="M mod.py\n", returncode=0,
        )

        engine = IntegrationEngine(
            project_root=project_root,
            merge_strategy=FakeMergeStrategy(),
            allow_dirty=False,
        )

        tgt = project_root / "mod.py"
        tgt.write_text("dirty content")

        src = project_root / "gen" / "mod.py"
        src.parent.mkdir()
        src.write_text("new")

        unit = FakeUnit(
            _generated_files=[str(src)],
            _target_files=[str(tgt)],
        )

        result = engine.integrate(unit)
        assert result.success is False

    @patch("startd8.contractors.integration_engine.subprocess")
    def test_allow_dirty_overrides(self, mock_subprocess, project_root):
        """allow_dirty=True skips dirty check."""
        mock_subprocess.run.return_value = MagicMock(
            stdout="M mod.py\n", returncode=0,
        )

        engine = IntegrationEngine(
            project_root=project_root,
            merge_strategy=FakeMergeStrategy(),
            allow_dirty=True,
        )

        tgt = project_root / "mod.py"
        tgt.write_text("dirty content")

        src = project_root / "gen" / "mod.py"
        src.parent.mkdir()
        src.write_text("new")

        unit = FakeUnit(
            _generated_files=[str(src)],
            _target_files=[str(tgt)],
        )

        result = engine.integrate(unit)
        assert result.success is True


# ---------------------------------------------------------------------------
# TestBoundaryValidation
# ---------------------------------------------------------------------------

class TestBoundaryValidation:
    """Test _validate_boundary advisory logging."""

    def test_missing_generated_files_logs_warning(self, engine, caplog):
        """Warning logged when unit has empty generated_files."""
        unit = FakeUnit(_generated_files=[], _target_files=["t.py"])

        import logging
        with caplog.at_level(logging.WARNING):
            engine._validate_boundary(unit)

        assert any("no generated_files" in r.message for r in caplog.records)

    def test_missing_target_files_logs_warning(self, engine, caplog):
        """Warning logged when unit has empty target_files."""
        unit = FakeUnit(_generated_files=["g.py"], _target_files=[])

        import logging
        with caplog.at_level(logging.WARNING):
            engine._validate_boundary(unit)

        assert any("no target_files" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# TestNullListener
# ---------------------------------------------------------------------------

class TestNullListener:
    """Ensure NullListener doesn't raise."""

    def test_all_methods_are_noop(self):
        listener = NullListener()
        unit = FakeUnit()
        listener.on_integration_started(unit)
        listener.on_file_integrated(unit, Path("a"), Path("b"))
        listener.on_checkpoint_result(unit, None)
        listener.on_integration_failed(unit, "err")
        listener.on_integration_completed(unit, [])


# ---------------------------------------------------------------------------
# TestProtocolCompliance
# ---------------------------------------------------------------------------

class TestProtocolCompliance:
    """Verify FakeUnit satisfies IntegrationUnit at runtime."""

    def test_fake_unit_is_integration_unit(self):
        unit = FakeUnit()
        assert isinstance(unit, IntegrationUnit)

    def test_recording_listener_is_integration_listener(self):
        listener = RecordingListener()
        assert isinstance(listener, IntegrationListener)

    def test_null_listener_is_integration_listener(self):
        listener = NullListener()
        assert isinstance(listener, IntegrationListener)
