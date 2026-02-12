"""Tests for startd8.contractors.handoff — design handoff persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.contractors.handoff import (
    DESIGN_HANDOFF_FILENAME,
    HANDOFF_SCHEMA,
    SCHEMA_VERSION,
    HandoffData,
    load_design_handoff,
    write_design_handoff,
)
from startd8.workflows.builtin.schema_versions import ARTISAN_SCHEMA_VERSION


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def handoff_kwargs():
    """Minimal kwargs for write_design_handoff."""
    return {
        "enriched_seed_path": "/abs/path/to/seed.json",
        "project_root": "/abs/path/to/project",
        "workflow_id": "test-wf-001",
        "completed_phases": ["plan", "scaffold", "design"],
        "design_results": {"T1": {"status": "agreed", "cost": 0.05}},
        "scaffold": {"directories_created": ["/abs/path/to/project/src"]},
    }


# ── write_design_handoff ─────────────────────────────────────────────


class TestWriteDesignHandoff:
    def test_creates_file(self, tmp_path, handoff_kwargs):
        result = write_design_handoff(output_dir=str(tmp_path), **handoff_kwargs)
        assert result.exists()
        assert result.name == DESIGN_HANDOFF_FILENAME

    def test_includes_all_fields(self, tmp_path, handoff_kwargs):
        write_design_handoff(output_dir=str(tmp_path), **handoff_kwargs)
        data = json.loads((tmp_path / DESIGN_HANDOFF_FILENAME).read_text())
        assert data["enriched_seed_path"] == handoff_kwargs["enriched_seed_path"]
        assert data["project_root"] == handoff_kwargs["project_root"]
        assert data["workflow_id"] == handoff_kwargs["workflow_id"]
        assert data["completed_phases"] == handoff_kwargs["completed_phases"]
        assert data["design_results"] == handoff_kwargs["design_results"]
        assert data["scaffold"] == handoff_kwargs["scaffold"]
        assert data["schema_version"] == SCHEMA_VERSION
        assert data["schema_version_str"] == ARTISAN_SCHEMA_VERSION
        assert data["created_at"]  # non-empty timestamp

    def test_creates_parent_dirs(self, tmp_path, handoff_kwargs):
        nested = tmp_path / "a" / "b" / "c"
        result = write_design_handoff(output_dir=str(nested), **handoff_kwargs)
        assert result.exists()
        assert result.parent == nested

    def test_defaults_for_optional_fields(self, tmp_path):
        result = write_design_handoff(
            output_dir=str(tmp_path),
            enriched_seed_path="/seed.json",
            project_root="/project",
            workflow_id="wf-minimal",
        )
        data = json.loads(result.read_text())
        assert data["design_results"] == {}
        assert data["scaffold"] == {}
        assert data["completed_phases"] == []
        assert data["context_files"] == []
        assert data["coverage_gaps"] == []

    def test_context_files_round_trip(self, tmp_path, handoff_kwargs):
        ctx_files = [
            {"path": "src/foo.py", "checksum": "abc123"},
            {"path": "docs/plan.md", "checksum": None},
        ]
        write_design_handoff(
            output_dir=str(tmp_path),
            context_files=ctx_files,
            **handoff_kwargs,
        )
        handoff = load_design_handoff(tmp_path)
        assert handoff.context_files == ctx_files

    def test_coverage_gaps_round_trip(self, tmp_path, handoff_kwargs):
        coverage_gaps = ["ServiceMonitor", "PrometheusRule"]
        write_design_handoff(
            output_dir=str(tmp_path),
            coverage_gaps=coverage_gaps,
            **handoff_kwargs,
        )
        handoff = load_design_handoff(tmp_path)
        assert handoff.coverage_gaps == coverage_gaps


# ── load_design_handoff ──────────────────────────────────────────────


class TestLoadDesignHandoff:
    def test_load_from_file(self, tmp_path, handoff_kwargs):
        write_design_handoff(output_dir=str(tmp_path), **handoff_kwargs)
        file_path = tmp_path / DESIGN_HANDOFF_FILENAME
        handoff = load_design_handoff(file_path)
        assert handoff.enriched_seed_path == handoff_kwargs["enriched_seed_path"]
        assert handoff.workflow_id == handoff_kwargs["workflow_id"]

    def test_load_from_directory(self, tmp_path, handoff_kwargs):
        write_design_handoff(output_dir=str(tmp_path), **handoff_kwargs)
        handoff = load_design_handoff(tmp_path)
        assert handoff.project_root == handoff_kwargs["project_root"]
        assert handoff.design_results == handoff_kwargs["design_results"]

    def test_round_trip_preserves_data(self, tmp_path, handoff_kwargs):
        write_design_handoff(output_dir=str(tmp_path), **handoff_kwargs)
        handoff = load_design_handoff(tmp_path)
        assert handoff.enriched_seed_path == handoff_kwargs["enriched_seed_path"]
        assert handoff.project_root == handoff_kwargs["project_root"]
        assert handoff.workflow_id == handoff_kwargs["workflow_id"]
        assert handoff.completed_phases == handoff_kwargs["completed_phases"]
        assert handoff.design_results == handoff_kwargs["design_results"]
        assert handoff.scaffold == handoff_kwargs["scaffold"]
        assert handoff.schema_version == SCHEMA_VERSION
        assert handoff.schema_version_str == ARTISAN_SCHEMA_VERSION

    def test_load_accepts_string_path(self, tmp_path, handoff_kwargs):
        write_design_handoff(output_dir=str(tmp_path), **handoff_kwargs)
        handoff = load_design_handoff(str(tmp_path))
        assert isinstance(handoff, HandoffData)


# ── Error cases ──────────────────────────────────────────────────────


class TestLoadErrors:
    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Handoff file not found"):
            load_design_handoff(tmp_path / "nonexistent.json")

    def test_dir_without_handoff(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Handoff file not found"):
            load_design_handoff(tmp_path)

    def test_missing_required_keys(self, tmp_path):
        bad_file = tmp_path / DESIGN_HANDOFF_FILENAME
        bad_file.write_text(json.dumps({"schema_version": 1}))
        with pytest.raises(ValueError, match="missing required keys"):
            load_design_handoff(bad_file)

    def test_future_schema_version(self, tmp_path):
        future_file = tmp_path / DESIGN_HANDOFF_FILENAME
        future_file.write_text(json.dumps({
            "schema_version": 999,
            "enriched_seed_path": "/s",
            "project_root": "/p",
            "output_dir": "/o",
            "workflow_id": "wf",
        }))
        with pytest.raises(ValueError, match="newer than supported"):
            load_design_handoff(future_file)

    def test_missing_schema_version(self, tmp_path):
        bad_file = tmp_path / DESIGN_HANDOFF_FILENAME
        bad_file.write_text(json.dumps({
            "enriched_seed_path": "/s",
            "project_root": "/p",
            "output_dir": "/o",
            "workflow_id": "wf",
        }))
        with pytest.raises(ValueError, match="missing 'schema_version'"):
            load_design_handoff(bad_file)


# ── Schema validation (Item 13) ──────────────────────────────────────────


class TestHandoffSchema:
    def test_schema_validates_handoff_dict(self):
        """HANDOFF_SCHEMA validates a minimal valid handoff."""
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")
        valid = {
            "enriched_seed_path": "/path/to/seed.json",
            "project_root": "/project",
            "output_dir": "/out",
            "workflow_id": "wf-1",
            "completed_phases": [],
            "design_results": {},
            "scaffold": {},
            "artifact_manifest_path": None,
            "project_context_path": None,
            "context_files": [],
            "example_artifacts": {},
            "coverage_gaps": [],
            "created_at": "2026-02-12T00:00:00Z",
            "schema_version": 1,
        }
        jsonschema.validate(valid, HANDOFF_SCHEMA)
