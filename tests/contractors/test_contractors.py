"""
Tests for the Prime Contractor framework.

These tests verify the contractors module works correctly both
standalone and with ContextCore integration.
"""

import tempfile
from pathlib import Path

import pytest

from startd8.contractors import (
    CheckpointResult,
    CheckpointStatus,
    FeatureQueue,
    FeatureSpec,
    FeatureStatus,
    IntegrationCheckpoint,
    PrimeContractorWorkflow,
    get_registry,
)
from startd8.contractors.adapters import (
    HeuristicSizeEstimator,
    LoggingInstrumentor,
    SimpleMergeStrategy,
)
from startd8.contractors.protocols import (
    GenerationResult,
    MergeResult,
    MergeStatus,
    SizeEstimate,
)


class TestFeatureQueue:
    """Tests for FeatureQueue."""

    def test_add_feature(self, tmp_path):
        """Test adding a feature to the queue."""
        queue = FeatureQueue(state_file=tmp_path / "state.json", auto_save=False)
        spec = queue.add_feature("test-1", "Test Feature", description="A test")

        assert spec.id == "test-1"
        assert spec.name == "Test Feature"
        assert spec.status == FeatureStatus.PENDING

    def test_feature_dependencies(self, tmp_path):
        """Test feature dependency ordering."""
        queue = FeatureQueue(state_file=tmp_path / "state.json", auto_save=False)
        queue.add_feature("feat-1", "Feature 1")
        queue.add_feature("feat-2", "Feature 2", dependencies=["feat-1"])

        # First feature should be returned first
        next_feat = queue.get_next_feature()
        assert next_feat.id == "feat-1"

        # Complete first feature
        queue.complete_feature("feat-1")

        # Now second feature should be available
        next_feat = queue.get_next_feature()
        assert next_feat.id == "feat-2"

    def test_blocked_features(self, tmp_path):
        """Test that dependent features are blocked when parent fails."""
        queue = FeatureQueue(state_file=tmp_path / "state.json", auto_save=False)
        queue.add_feature("feat-1", "Feature 1")
        queue.add_feature("feat-2", "Feature 2", dependencies=["feat-1"])

        # Fail first feature
        queue.fail_feature("feat-1", "Test failure")

        # Second feature should be blocked
        feat2 = queue.features["feat-2"]
        assert feat2.status == FeatureStatus.BLOCKED

    def test_progress(self, tmp_path):
        """Test progress calculation."""
        queue = FeatureQueue(state_file=tmp_path / "state.json", auto_save=False)
        queue.add_feature("feat-1", "Feature 1")
        queue.add_feature("feat-2", "Feature 2")

        assert queue.get_progress() == 0.0

        queue.complete_feature("feat-1")
        assert queue.get_progress() == 50.0

        queue.complete_feature("feat-2")
        assert queue.get_progress() == 100.0

    def test_state_persistence(self, tmp_path):
        """Test queue state save/load."""
        state_file = tmp_path / "state.json"

        # Create and populate queue
        queue1 = FeatureQueue(state_file=state_file)
        queue1.add_feature("feat-1", "Feature 1")
        queue1.complete_feature("feat-1")
        queue1.save_state()

        # Load in new queue instance
        queue2 = FeatureQueue(state_file=state_file)
        assert "feat-1" in queue2.features
        assert queue2.features["feat-1"].status == FeatureStatus.COMPLETE


class TestLoggingInstrumentor:
    """Tests for LoggingInstrumentor."""

    def test_emit_span(self):
        """Test span emission."""
        instrumentor = LoggingInstrumentor(project_id="test")
        ctx = instrumentor.emit_span("test_span", {"key": "value"})

        assert ctx.trace_id
        assert ctx.span_id
        assert ctx.attributes == {"key": "value"}

    def test_emit_insight(self, caplog):
        """Test insight emission."""
        import logging

        with caplog.at_level(logging.INFO):
            instrumentor = LoggingInstrumentor(project_id="test")
            instrumentor.emit_insight(
                insight_type="test_insight",
                summary="Test summary",
                confidence=0.9,
            )

        assert "test_insight" in caplog.text
        assert "Test summary" in caplog.text


class TestHeuristicSizeEstimator:
    """Tests for HeuristicSizeEstimator."""

    def test_basic_estimation(self):
        """Test basic size estimation."""
        estimator = HeuristicSizeEstimator()
        estimate = estimator.estimate(
            task="Implement a simple function",
            inputs={},
        )

        assert isinstance(estimate, SizeEstimate)
        assert estimate.lines > 0
        assert estimate.tokens > 0
        assert estimate.complexity in ("low", "medium", "high")
        assert 0.0 <= estimate.confidence <= 1.0

    def test_pattern_matching(self):
        """Test that patterns affect estimation."""
        estimator = HeuristicSizeEstimator()

        # Simple task
        simple = estimator.estimate("fix a bug", {})

        # Complex task
        complex_task = estimator.estimate(
            "migrate the entire database schema",
            {"target_files": ["models.py", "schema.py", "migrations.py"]},
        )

        assert complex_task.lines > simple.lines


class TestSimpleMergeStrategy:
    """Tests for SimpleMergeStrategy."""

    def test_merge_new_file(self, tmp_path):
        """Test merging to a new file."""
        source = tmp_path / "source.py"
        target = tmp_path / "target.py"
        source.write_text("print('hello')")

        merger = SimpleMergeStrategy()
        assert merger.can_merge(source, target)

        result = merger.merge(source, target)
        assert result.status == MergeStatus.SUCCESS
        assert target.read_text() == "print('hello')"

    def test_merge_with_backup(self, tmp_path):
        """Test that backup is created for existing files."""
        source = tmp_path / "source.py"
        target = tmp_path / "target.py"
        source.write_text("print('new')")
        target.write_text("print('old')")

        merger = SimpleMergeStrategy()
        result = merger.merge(source, target, backup=True)

        assert result.status == MergeStatus.SUCCESS
        assert result.backup_path is not None
        assert result.backup_path.exists()
        assert result.backup_path.read_text() == "print('old')"
        assert target.read_text() == "print('new')"


class TestRegistry:
    """Tests for ContractorRegistry."""

    def test_discover(self):
        """Test registry discovery."""
        registry = get_registry()
        registry.discover()

        # Should have at least the built-in adapters
        assert "logging" in registry.list_instrumentors()
        assert "heuristic" in registry.list_size_estimators()
        assert "simple" in registry.list_merge_strategies()

    def test_default_instrumentor(self):
        """Test getting default instrumentor."""
        registry = get_registry()
        registry.discover()

        # Get the logging instrumentor specifically to avoid ContextCore deps
        instrumentor_cls = registry.get_instrumentor("logging")
        assert instrumentor_cls is not None

        # Should be instantiable
        instance = instrumentor_cls()
        assert hasattr(instance, "emit_span")


class TestIntegrationCheckpoint:
    """Tests for IntegrationCheckpoint."""

    def test_check_syntax_valid(self, tmp_path):
        """Test syntax check on valid Python."""
        checkpoint = IntegrationCheckpoint(project_root=tmp_path)
        valid_file = tmp_path / "valid.py"
        valid_file.write_text("def foo():\n    return 42\n")

        result = checkpoint.check_syntax([valid_file])
        assert result.status == CheckpointStatus.PASSED

    def test_check_syntax_invalid(self, tmp_path):
        """Test syntax check on invalid Python."""
        checkpoint = IntegrationCheckpoint(project_root=tmp_path)
        invalid_file = tmp_path / "invalid.py"
        invalid_file.write_text("def foo(\n")  # Invalid syntax

        result = checkpoint.check_syntax([invalid_file])
        assert result.status == CheckpointStatus.FAILED


class TestPrimeContractorWorkflow:
    """Tests for PrimeContractorWorkflow."""

    def test_dry_run(self, tmp_path):
        """Test dry run mode."""
        # Use LoggingInstrumentor to avoid ContextCore dependency
        workflow = PrimeContractorWorkflow(
            project_root=tmp_path,
            dry_run=True,
            instrumentor=LoggingInstrumentor(),
        )

        # Add a feature
        workflow.queue.add_feature(
            "test-feat",
            "Test Feature",
            description="A test feature",
            target_files=["test.py"],
        )

        # Run in dry run mode
        result = workflow.run()

        # Should complete without actually doing anything
        assert result["processed"] == 1

    def test_git_status_check(self, tmp_path):
        """Test git status checking (should work in non-git dirs)."""
        workflow = PrimeContractorWorkflow(
            project_root=tmp_path,
            instrumentor=LoggingInstrumentor(),
        )
        is_clean, dirty_files = workflow.check_git_status()

        # In a non-git directory, git command might fail
        # but the method should handle it gracefully
        assert isinstance(is_clean, bool)
        assert isinstance(dirty_files, list)
