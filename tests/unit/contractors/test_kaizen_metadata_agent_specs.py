"""Tests for Kaizen metadata.json agent spec resolution (L3 fix).

Verifies that _update_kaizen_metadata_agent_specs patches metadata.json
with resolved agent specs after generation completes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.prime_contractor import PrimeContractorWorkflow
from startd8.contractors.queue import FeatureSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feature(**overrides: Any) -> FeatureSpec:
    defaults = {
        "id": "KZ-001",
        "name": "Test feature",
        "description": "A feature for testing kaizen metadata.",
        "target_files": ["src/test.py"],
        "dependencies": [],
    }
    defaults.update(overrides)
    return FeatureSpec(**defaults)


def _make_workflow(tmp_path: Path) -> PrimeContractorWorkflow:
    """Build a minimal PrimeContractorWorkflow with kaizen enabled."""
    with patch.object(PrimeContractorWorkflow, "__init__", lambda self, **kw: None):
        wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)

    wf.project_root = tmp_path
    from startd8.contractors.prime_contractor import KaizenConfig
    wf._kaizen = KaizenConfig(enabled=True, prompt_dir=tmp_path / "kaizen-prompts")
    wf._kaizen.prompt_dir.mkdir(parents=True, exist_ok=True)
    wf.code_generator = MagicMock()
    wf.code_generator.lead_agent = None
    wf.code_generator.drafter_agent = None
    return wf


def _write_initial_metadata(
    kaizen_dir: Path,
    feature: FeatureSpec,
    run_id: str = "standalone",
    lead: str = "unknown",
    drafter: str = "unknown",
) -> Path:
    """Create a metadata.json with initial (possibly unknown) agent specs."""
    safe_fid = feature.id.replace("/", "_")
    meta_dir = kaizen_dir / run_id / safe_fid
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta_path = meta_dir / "metadata.json"
    metadata = {
        "feature_id": feature.id,
        "feature_name": feature.name,
        "target_files": feature.target_files or [],
        "lead_agent_spec": lead,
        "drafter_agent_spec": drafter,
        "timestamp": "2026-03-09T00:00:00+00:00",
    }
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return meta_path


def _make_result(lead_spec: str | None = None, drafter_spec: str | None = None) -> MagicMock:
    """Create a mock GenerationResult with metadata containing agent specs."""
    result = MagicMock()
    result.metadata = {}
    if lead_spec is not None:
        result.metadata["lead_agent_spec"] = lead_spec
    if drafter_spec is not None:
        result.metadata["drafter_agent_spec"] = drafter_spec
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUpdateKaizenMetadataAgentSpecs:
    """Tests for _update_kaizen_metadata_agent_specs."""

    def test_updates_unknown_specs_with_resolved_values(self, tmp_path: Path) -> None:
        """When metadata has 'unknown' specs, they should be patched with resolved values."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        meta_path = _write_initial_metadata(wf._kaizen.prompt_dir, feature)
        result = _make_result(
            lead_spec="anthropic:claude-sonnet-4-20250514",
            drafter_spec="anthropic:claude-haiku-4-5-20251001",
        )

        wf._update_kaizen_metadata_agent_specs(feature, result)

        updated = json.loads(meta_path.read_text(encoding="utf-8"))
        assert updated["lead_agent_spec"] == "anthropic:claude-sonnet-4-20250514"
        assert updated["drafter_agent_spec"] == "anthropic:claude-haiku-4-5-20251001"

    def test_updates_none_specs_with_resolved_values(self, tmp_path: Path) -> None:
        """When metadata has None specs, they should be patched with resolved values."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        meta_path = _write_initial_metadata(
            wf._kaizen.prompt_dir, feature, lead=None, drafter=None,
        )
        result = _make_result(
            lead_spec="openai:gpt-4-turbo",
            drafter_spec="openai:gpt-4o-mini",
        )

        wf._update_kaizen_metadata_agent_specs(feature, result)

        updated = json.loads(meta_path.read_text(encoding="utf-8"))
        assert updated["lead_agent_spec"] == "openai:gpt-4-turbo"
        assert updated["drafter_agent_spec"] == "openai:gpt-4o-mini"

    def test_does_not_overwrite_already_resolved_specs(self, tmp_path: Path) -> None:
        """When metadata already has real specs, they should not be overwritten."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        meta_path = _write_initial_metadata(
            wf._kaizen.prompt_dir,
            feature,
            lead="anthropic:claude-opus-4-20250514",
            drafter="gemini:gemini-2.5-flash",
        )
        result = _make_result(
            lead_spec="anthropic:claude-sonnet-4-20250514",
            drafter_spec="anthropic:claude-haiku-4-5-20251001",
        )

        wf._update_kaizen_metadata_agent_specs(feature, result)

        updated = json.loads(meta_path.read_text(encoding="utf-8"))
        # Original values preserved — not overwritten
        assert updated["lead_agent_spec"] == "anthropic:claude-opus-4-20250514"
        assert updated["drafter_agent_spec"] == "gemini:gemini-2.5-flash"

    def test_noop_when_result_is_none(self, tmp_path: Path) -> None:
        """When result is None, metadata should not be modified."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        meta_path = _write_initial_metadata(wf._kaizen.prompt_dir, feature)
        original = meta_path.read_text(encoding="utf-8")

        wf._update_kaizen_metadata_agent_specs(feature, None)

        assert meta_path.read_text(encoding="utf-8") == original

    def test_noop_when_result_has_no_metadata(self, tmp_path: Path) -> None:
        """When result has no metadata dict, should be a no-op."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        meta_path = _write_initial_metadata(wf._kaizen.prompt_dir, feature)
        original = meta_path.read_text(encoding="utf-8")

        result = MagicMock()
        result.metadata = None

        wf._update_kaizen_metadata_agent_specs(feature, result)

        assert meta_path.read_text(encoding="utf-8") == original

    def test_noop_when_kaizen_disabled(self, tmp_path: Path) -> None:
        """When kaizen is disabled, should be a no-op."""
        wf = _make_workflow(tmp_path)
        wf._kaizen.enabled = False
        feature = _make_feature()
        meta_path = _write_initial_metadata(wf._kaizen.prompt_dir, feature)
        original = meta_path.read_text(encoding="utf-8")
        result = _make_result(lead_spec="anthropic:claude-sonnet-4-20250514")

        wf._update_kaizen_metadata_agent_specs(feature, result)

        assert meta_path.read_text(encoding="utf-8") == original

    def test_noop_when_metadata_file_missing(self, tmp_path: Path) -> None:
        """When metadata.json doesn't exist yet, should silently return."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        result = _make_result(lead_spec="anthropic:claude-sonnet-4-20250514")

        # No metadata.json created — should not raise
        wf._update_kaizen_metadata_agent_specs(feature, result)

    def test_partial_update_lead_only(self, tmp_path: Path) -> None:
        """When only lead_agent_spec is in result metadata, only lead is updated."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        meta_path = _write_initial_metadata(wf._kaizen.prompt_dir, feature)
        result = _make_result(lead_spec="anthropic:claude-sonnet-4-20250514")

        wf._update_kaizen_metadata_agent_specs(feature, result)

        updated = json.loads(meta_path.read_text(encoding="utf-8"))
        assert updated["lead_agent_spec"] == "anthropic:claude-sonnet-4-20250514"
        assert updated["drafter_agent_spec"] == "unknown"  # unchanged

    def test_partial_update_drafter_only(self, tmp_path: Path) -> None:
        """When only drafter_agent_spec is in result metadata, only drafter is updated."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        meta_path = _write_initial_metadata(wf._kaizen.prompt_dir, feature)
        result = _make_result(drafter_spec="openai:gpt-4o-mini")

        wf._update_kaizen_metadata_agent_specs(feature, result)

        updated = json.loads(meta_path.read_text(encoding="utf-8"))
        assert updated["lead_agent_spec"] == "unknown"  # unchanged
        assert updated["drafter_agent_spec"] == "openai:gpt-4o-mini"

    def test_idempotent_on_repeat_call(self, tmp_path: Path) -> None:
        """Calling the method twice with the same result should produce the same output."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        meta_path = _write_initial_metadata(wf._kaizen.prompt_dir, feature)
        result = _make_result(
            lead_spec="anthropic:claude-sonnet-4-20250514",
            drafter_spec="anthropic:claude-haiku-4-5-20251001",
        )

        wf._update_kaizen_metadata_agent_specs(feature, result)
        first_content = meta_path.read_text(encoding="utf-8")

        wf._update_kaizen_metadata_agent_specs(feature, result)
        second_content = meta_path.read_text(encoding="utf-8")

        assert first_content == second_content

    @patch.dict("os.environ", {"KAIZEN_RUN_ID": "run-017"})
    def test_respects_kaizen_run_id_env(self, tmp_path: Path) -> None:
        """When KAIZEN_RUN_ID is set, metadata is located under that run_id subdir."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        meta_path = _write_initial_metadata(
            wf._kaizen.prompt_dir, feature, run_id="run-017",
        )
        result = _make_result(
            lead_spec="anthropic:claude-sonnet-4-20250514",
            drafter_spec="anthropic:claude-haiku-4-5-20251001",
        )

        wf._update_kaizen_metadata_agent_specs(feature, result)

        updated = json.loads(meta_path.read_text(encoding="utf-8"))
        assert updated["lead_agent_spec"] == "anthropic:claude-sonnet-4-20250514"
        assert updated["drafter_agent_spec"] == "anthropic:claude-haiku-4-5-20251001"

    def test_non_fatal_on_corrupt_json(self, tmp_path: Path) -> None:
        """If metadata.json is corrupt, the update should log a warning and not raise."""
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        safe_fid = feature.id.replace("/", "_")
        meta_dir = wf._kaizen.prompt_dir / "standalone" / safe_fid
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_path = meta_dir / "metadata.json"
        meta_path.write_text("{corrupt json", encoding="utf-8")

        result = _make_result(lead_spec="anthropic:claude-sonnet-4-20250514")

        # Should not raise
        wf._update_kaizen_metadata_agent_specs(feature, result)
