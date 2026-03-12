"""
Generation Manifest Tests — Run Provenance (pipeline mode only)

Covers:
1. Manifest writing (pipeline mode only, 0o600 permissions, I/O error handling)
2. Manifest schema (v1.1.0, no source_checksum — staleness removed per R2)
3. Effective config and feature entries

R2: Staleness detection (TestStalenessDetection, TestSourceChecksum,
TestManifestRoundTrip) removed — subsumed by content-addressable
generation cache (AC-R3).
"""

import json
import os
import stat
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from startd8.contractors.prime_contractor import (
    ExecutionMode,
    PrimeContractorWorkflow,
)
from startd8.contractors.queue import FeatureSpec


# ============================================================================
# Helpers: Minimal workflow construction
# ============================================================================


def _make_workflow(
    *,
    project_root: Path,
    execution_mode: str = "pipeline",
) -> PrimeContractorWorkflow:
    """Create a minimal PrimeContractorWorkflow for testing manifest methods."""
    wf = object.__new__(PrimeContractorWorkflow)
    wf.project_root = project_root
    wf.dry_run = False
    wf.max_retries = 3
    wf.check_truncation = True
    wf.force_regenerate = False
    wf.total_cost_usd = 0.0
    wf.total_input_tokens = 0
    wf.total_output_tokens = 0
    wf.integration_history = []

    # SeedContext mock
    seed = MagicMock()
    seed.execution_mode = execution_mode
    wf._seed_context = seed

    # Strategy mock
    strategy = MagicMock()
    strategy.mode = execution_mode
    wf._context_strategy = strategy

    return wf


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
        assert manifest["schema_version"] == "1.1.0"
        assert manifest["execution_mode"] == "pipeline"
        assert "source_checksum" not in manifest  # R2: removed
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

    def test_manifest_cost_aggregates(self, tmp_path):
        """Manifest includes total cost and token counts."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        wf.total_cost_usd = 1.23
        wf.total_input_tokens = 5000
        wf.total_output_tokens = 3000
        wf._write_generation_manifest({})

        path = tmp_path / ".startd8" / "generation-manifest.json"
        manifest = json.loads(path.read_text())
        assert manifest["total_cost_usd"] == 1.23
        assert manifest["total_input_tokens"] == 5000
        assert manifest["total_output_tokens"] == 3000
