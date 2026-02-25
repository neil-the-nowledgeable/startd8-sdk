"""
Phase 4 Tests — Generation Manifest, Staleness Detection, Validation Hookpoint

Covers:
1. Source checksum computation (deterministic, canonical)
2. Manifest writing (pipeline mode only, 0o600 permissions, I/O error handling)
3. Staleness detection (checksum match reuses, mismatch regenerates, no manifest regenerates)
4. Force-regenerate bypasses staleness
5. Standalone mode always regenerates (no staleness check)

All tests use a minimal mock PrimeContractorWorkflow to avoid full workflow setup.
"""

import json
import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.prime_contractor import (
    ExecutionMode,
    ModeConfig,
    PrimeContractorWorkflow,
)
from startd8.contractors.queue import FeatureSpec, FeatureStatus


# ============================================================================
# Helpers: Minimal workflow construction
# ============================================================================


def _make_workflow(
    *,
    project_root: Path,
    execution_mode: str = "pipeline",
    force_regenerate: bool = False,
) -> PrimeContractorWorkflow:
    """Create a minimal PrimeContractorWorkflow for testing Phase 4 methods.

    Avoids full __init__ by directly setting required attributes.
    """
    wf = object.__new__(PrimeContractorWorkflow)
    wf.project_root = project_root
    wf.dry_run = False
    wf.max_retries = 3
    wf.check_truncation = True
    wf.force_regenerate = force_regenerate
    wf.total_cost_usd = 0.0
    wf.total_input_tokens = 0
    wf.total_output_tokens = 0
    wf.integration_history = []

    # SeedContext mock
    seed = MagicMock()
    seed.execution_mode = execution_mode
    seed.to_dict.return_value = {
        "onboarding_metadata": {"project": "test"},
        "architectural_context": None,
        "design_calibration": None,
        "execution_mode": execution_mode,
    }
    wf._seed_context = seed

    # Strategy mock
    strategy = MagicMock()
    strategy.mode = execution_mode
    wf._context_strategy = strategy

    return wf


def _make_feature(feature_id: str = "F-001", name: str = "test-feature") -> FeatureSpec:
    """Create a minimal FeatureSpec for testing."""
    return FeatureSpec(
        id=feature_id,
        name=name,
        description="Test feature",
        target_files=["src/test.py"],
    )


# ============================================================================
# TestSourceChecksum
# ============================================================================


class TestSourceChecksum:
    """Validate source checksum computation."""

    def test_checksum_is_deterministic(self, tmp_path):
        """Same seed produces same checksum."""
        wf = _make_workflow(project_root=tmp_path)
        c1 = wf._compute_source_checksum()
        c2 = wf._compute_source_checksum()
        assert c1 == c2
        assert len(c1) == 64  # SHA-256 hex length

    def test_different_seeds_produce_different_checksums(self, tmp_path):
        """Different seed data produces different checksums."""
        wf1 = _make_workflow(project_root=tmp_path)
        wf2 = _make_workflow(project_root=tmp_path)
        wf2._seed_context.to_dict.return_value = {
            "onboarding_metadata": {"project": "different"},
        }
        assert wf1._compute_source_checksum() != wf2._compute_source_checksum()

    def test_checksum_canonical_ordering(self, tmp_path):
        """Checksum uses sorted keys for canonical representation."""
        wf1 = _make_workflow(project_root=tmp_path)
        wf1._seed_context.to_dict.return_value = {"b": 2, "a": 1}
        wf2 = _make_workflow(project_root=tmp_path)
        wf2._seed_context.to_dict.return_value = {"a": 1, "b": 2}
        assert wf1._compute_source_checksum() == wf2._compute_source_checksum()

    def test_checksum_none_seed(self, tmp_path):
        """None seed context produces empty-dict checksum."""
        wf = _make_workflow(project_root=tmp_path)
        wf._seed_context = None
        checksum = wf._compute_source_checksum()
        assert len(checksum) == 64  # Still valid SHA-256


# ============================================================================
# TestManifestWriting
# ============================================================================


class TestManifestWriting:
    """Validate generation manifest writing."""

    def test_manifest_written_in_pipeline_mode(self, tmp_path):
        """Pipeline mode writes manifest file."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        wf.integration_history = [
            {"feature_id": "F-001", "feature_name": "auth", "success": True,
             "cost_usd": 0.05, "model": "claude-sonnet"},
        ]
        wf._write_generation_manifest({})

        path = tmp_path / ".startd8" / "generation-manifest.json"
        assert path.exists()

        manifest = json.loads(path.read_text())
        assert manifest["schema_version"] == "1.0.0"
        assert manifest["execution_mode"] == "pipeline"
        assert "source_checksum" in manifest
        assert "F-001" in manifest["features"]
        assert manifest["features"]["F-001"]["model"] == "claude-sonnet"

    def test_manifest_not_written_in_standalone_mode(self, tmp_path):
        """Standalone mode does not write manifest."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="standalone")
        wf._write_generation_manifest({})

        path = tmp_path / ".startd8" / "generation-manifest.json"
        assert not path.exists()

    def test_manifest_permissions(self, tmp_path):
        """Manifest written with 0o600 permissions (owner read/write only)."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        wf._write_generation_manifest({})

        path = tmp_path / ".startd8" / "generation-manifest.json"
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600

    def test_manifest_io_error_does_not_fail(self, tmp_path):
        """I/O errors during manifest write are logged, not raised."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")

        # Make .startd8 a file (not directory) to cause mkdir to fail
        startd8_path = tmp_path / ".startd8"
        startd8_path.write_text("blocker")

        # Should not raise
        wf._write_generation_manifest({})

    def test_manifest_effective_config(self, tmp_path):
        """Manifest includes effective_config with workflow settings."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        wf._write_generation_manifest({})

        path = tmp_path / ".startd8" / "generation-manifest.json"
        manifest = json.loads(path.read_text())
        config = manifest["effective_config"]
        assert config["mode"] == "pipeline"
        assert config["strategy"] == "pipeline"
        assert "dry_run" in config
        assert "max_retries" in config

    def test_manifest_includes_generated_at(self, tmp_path):
        """Manifest includes generated_at timestamp."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        wf._write_generation_manifest({})

        path = tmp_path / ".startd8" / "generation-manifest.json"
        manifest = json.loads(path.read_text())
        assert "generated_at" in manifest
        assert "T" in manifest["generated_at"]  # ISO format


# ============================================================================
# TestStalenessDetection
# ============================================================================


class TestStalenessDetection:
    """Validate staleness detection logic."""

    def _write_manifest(self, tmp_path, checksum, features=None):
        """Helper: write a manifest file with given checksum."""
        manifest = {
            "schema_version": "1.0.0",
            "source_checksum": checksum,
            "features": features or {},
        }
        manifest_dir = tmp_path / ".startd8"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "generation-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8",
        )

    def test_no_manifest_regenerates(self, tmp_path):
        """No manifest file → regenerate."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        feature = _make_feature()
        assert wf._check_staleness(feature) is True

    def test_matching_checksum_reuses(self, tmp_path):
        """Matching checksum → reuse (no regeneration)."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        checksum = wf._compute_source_checksum()
        self._write_manifest(tmp_path, checksum, features={"F-001": {"name": "test"}})

        feature = _make_feature()
        assert wf._check_staleness(feature) is False

    def test_mismatched_checksum_regenerates(self, tmp_path):
        """Different checksum → regenerate."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        self._write_manifest(tmp_path, "old_checksum_000", features={"F-001": {}})

        feature = _make_feature()
        assert wf._check_staleness(feature) is True

    def test_force_regenerate_bypasses(self, tmp_path):
        """force_regenerate=True → always regenerate."""
        wf = _make_workflow(
            project_root=tmp_path, execution_mode="pipeline", force_regenerate=True,
        )
        checksum = wf._compute_source_checksum()
        self._write_manifest(tmp_path, checksum, features={"F-001": {}})

        feature = _make_feature()
        assert wf._check_staleness(feature) is True

    def test_standalone_always_regenerates(self, tmp_path):
        """Standalone mode always regenerates regardless of manifest."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="standalone")
        feature = _make_feature()
        assert wf._check_staleness(feature) is True

    def test_corrupt_manifest_handled(self, tmp_path):
        """Corrupt/unparsable manifest → regenerate gracefully."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        manifest_dir = tmp_path / ".startd8"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "generation-manifest.json").write_text("not json {{{")

        feature = _make_feature()
        assert wf._check_staleness(feature) is True

    def test_missing_checksum_in_manifest_regenerates(self, tmp_path):
        """Manifest without source_checksum → regenerate."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        manifest_dir = tmp_path / ".startd8"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "generation-manifest.json").write_text(
            json.dumps({"schema_version": "1.0.0", "features": {}})
        )

        feature = _make_feature()
        assert wf._check_staleness(feature) is True

    def test_feature_not_in_manifest_regenerates(self, tmp_path):
        """Feature ID not in manifest's features dict → regenerate."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        checksum = wf._compute_source_checksum()
        self._write_manifest(tmp_path, checksum, features={"F-999": {}})

        feature = _make_feature()  # F-001, not in manifest
        assert wf._check_staleness(feature) is True

    def test_different_workflow_id_same_checksum_reuses(self, tmp_path):
        """Different workflow_id with same checksum → reuse (ID is for provenance only)."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        checksum = wf._compute_source_checksum()
        self._write_manifest(tmp_path, checksum, features={"F-001": {}})

        # Verify reuse even though there's no workflow_id match
        feature = _make_feature()
        assert wf._check_staleness(feature) is False


# ============================================================================
# TestManifestRoundTrip
# ============================================================================


class TestManifestRoundTrip:
    """Validate write → read → staleness check round-trip."""

    def test_write_then_check_staleness(self, tmp_path):
        """Written manifest enables staleness reuse."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        wf.integration_history = [
            {"feature_id": "F-001", "feature_name": "auth", "success": True,
             "cost_usd": 0.05, "model": "claude-sonnet"},
        ]
        wf._write_generation_manifest({})

        # Same workflow reads manifest and detects freshness
        feature = _make_feature()
        assert wf._check_staleness(feature) is False

    def test_read_after_seed_change(self, tmp_path):
        """Manifest becomes stale after seed change."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        wf.integration_history = [
            {"feature_id": "F-001", "feature_name": "auth", "success": True,
             "cost_usd": 0.05, "model": "claude-sonnet"},
        ]
        wf._write_generation_manifest({})

        # Change seed data
        wf._seed_context.to_dict.return_value = {"changed": True}

        feature = _make_feature()
        assert wf._check_staleness(feature) is True
