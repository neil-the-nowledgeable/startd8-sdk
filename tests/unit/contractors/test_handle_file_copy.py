"""Tests for PrimeContractorWorkflow._handle_file_copy output path routing.

Verifies that file-copy tasks write to output_dir (consistent with normal
generation paths), not project_root.
"""

import pytest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, PropertyMock

from startd8.contractors.queue import FeatureSpec, FeatureStatus


@dataclass
class _FakeFeatureQueue:
    """Minimal queue stub for _handle_file_copy tests."""

    features: Dict[str, FeatureSpec] = field(default_factory=dict)

    def get_feature(self, feature_id: str) -> Optional[FeatureSpec]:
        return self.features.get(feature_id)


class TestHandleFileCopyOutputDir:
    """_handle_file_copy must write to output_dir, not project_root."""

    def _make_contractor(self, project_root: Path, output_dir: Path):
        """Build a minimal mock PrimeContractorWorkflow for _handle_file_copy."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        mock = MagicMock(spec=PrimeContractorWorkflow)
        mock.project_root = project_root
        mock.queue = _FakeFeatureQueue()
        mock._FILE_COPY_READ_TIMEOUT_S = 5

        # Wire _resolve_output_dir to return the test output_dir
        mock._resolve_output_dir = MagicMock(return_value=output_dir)

        # Bind the real method to the mock instance
        mock._handle_file_copy = PrimeContractorWorkflow._handle_file_copy.__get__(
            mock, PrimeContractorWorkflow,
        )
        return mock

    def test_copy_writes_to_output_dir(self, tmp_path):
        """File copy target lands in output_dir, not project_root."""
        project_root = tmp_path / "project"
        output_dir = tmp_path / "output" / "generated"
        project_root.mkdir(parents=True)
        output_dir.mkdir(parents=True)

        # Create predecessor's output in output_dir
        predecessor_file = output_dir / "src" / "svc" / "logger.py"
        predecessor_file.parent.mkdir(parents=True)
        predecessor_file.write_text("# logger module\n", encoding="utf-8")

        # Set up queue with completed predecessor
        predecessor = FeatureSpec(
            id="PI-001",
            name="Logger",
            status=FeatureStatus.COMPLETE,
            target_files=["src/svc/logger.py"],
            generated_files=[str(predecessor_file)],
        )

        feature = FeatureSpec(
            id="PI-002",
            name="Logger Copy",
            target_files=["src/other_svc/logger.py"],
            copy_source_task_id="PI-001",
            copy_source_file="src/svc/logger.py",
        )

        contractor = self._make_contractor(project_root, output_dir)
        contractor.queue.features["PI-001"] = predecessor

        result = contractor._handle_file_copy(feature)

        assert result is not None
        assert result.success is True
        assert result.cost_usd == 0.0

        # Target must be under output_dir, NOT project_root
        target = Path(result.generated_files[0])
        assert target.is_relative_to(output_dir), (
            f"Expected target under {output_dir}, got {target}"
        )
        assert not target.is_relative_to(project_root) or output_dir.is_relative_to(
            project_root
        ), f"Target should not be under project_root: {target}"

        # File must exist and match source content
        assert target.exists()
        assert target.read_text() == "# logger module\n"

    def test_copy_source_falls_back_to_project_root(self, tmp_path):
        """When source file is not in output_dir, falls back to project_root."""
        project_root = tmp_path / "project"
        output_dir = tmp_path / "output" / "generated"
        project_root.mkdir(parents=True)
        output_dir.mkdir(parents=True)

        # Source file only exists at project_root (not in output_dir)
        source_file = project_root / "src" / "svc" / "logger.py"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("# from project root\n", encoding="utf-8")

        predecessor = FeatureSpec(
            id="PI-001",
            name="Logger",
            status=FeatureStatus.COMPLETE,
            target_files=["src/svc/logger.py"],
            generated_files=[str(source_file)],
        )

        feature = FeatureSpec(
            id="PI-002",
            name="Logger Copy",
            target_files=["src/other_svc/logger.py"],
            copy_source_task_id="PI-001",
            copy_source_file="src/svc/logger.py",
        )

        contractor = self._make_contractor(project_root, output_dir)
        contractor.queue.features["PI-001"] = predecessor

        result = contractor._handle_file_copy(feature)

        assert result is not None
        assert result.success is True

        # Target still goes to output_dir
        target = Path(result.generated_files[0])
        assert target.is_relative_to(output_dir)
        assert target.read_text() == "# from project root\n"

    def test_copy_prefers_output_dir_source(self, tmp_path):
        """When source exists in both output_dir and project_root, prefers output_dir."""
        project_root = tmp_path / "project"
        output_dir = tmp_path / "output" / "generated"
        project_root.mkdir(parents=True)
        output_dir.mkdir(parents=True)

        # Source in both locations with different content
        (project_root / "src" / "svc").mkdir(parents=True)
        (project_root / "src" / "svc" / "logger.py").write_text("# stale\n")

        (output_dir / "src" / "svc").mkdir(parents=True)
        (output_dir / "src" / "svc" / "logger.py").write_text("# fresh\n")

        predecessor = FeatureSpec(
            id="PI-001",
            name="Logger",
            status=FeatureStatus.COMPLETE,
            target_files=["src/svc/logger.py"],
            generated_files=[str(output_dir / "src" / "svc" / "logger.py")],
        )

        feature = FeatureSpec(
            id="PI-002",
            name="Logger Copy",
            target_files=["src/other_svc/logger.py"],
            copy_source_task_id="PI-001",
            copy_source_file="src/svc/logger.py",
        )

        contractor = self._make_contractor(project_root, output_dir)
        contractor.queue.features["PI-001"] = predecessor

        result = contractor._handle_file_copy(feature)

        target = Path(result.generated_files[0])
        assert target.read_text() == "# fresh\n", (
            "Should prefer output_dir source over project_root"
        )

    def test_copy_metadata_includes_strategy(self, tmp_path):
        """Result metadata records file_copy strategy and SHA-256."""
        project_root = tmp_path / "project"
        output_dir = tmp_path / "output" / "generated"
        project_root.mkdir(parents=True)
        output_dir.mkdir(parents=True)

        source = output_dir / "src" / "svc" / "mod.py"
        source.parent.mkdir(parents=True)
        source.write_text("x = 1\n")

        predecessor = FeatureSpec(
            id="PI-001", name="Mod", status=FeatureStatus.COMPLETE,
            target_files=["src/svc/mod.py"],
            generated_files=[str(source)],
        )
        feature = FeatureSpec(
            id="PI-002", name="Mod Copy",
            target_files=["src/svc2/mod.py"],
            copy_source_task_id="PI-001",
            copy_source_file="src/svc/mod.py",
        )

        contractor = self._make_contractor(project_root, output_dir)
        contractor.queue.features["PI-001"] = predecessor

        result = contractor._handle_file_copy(feature)

        assert result.metadata["strategy"] == "file_copy"
        assert result.metadata["copy_source_task_id"] == "PI-001"
        assert "sha256" in result.metadata
        assert len(result.metadata["sha256"]) == 64  # hex digest
