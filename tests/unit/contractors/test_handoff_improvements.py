"""Tests for Gaps 1-5: Handoff improvement fields and extraction logic.

Covers:
- Gap 3: design_structural_delta extraction and consumption
- Gap 1: design_referenced_elements cross-validation
- Gap 2: manifest_file_checksums staleness detection
- Gap 4: design_mode_evidence and elevated weight in _classify_edit_mode
- Gap 5: manifest_truncation_tier recording and consumption
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.handoff import (
    HandoffData,
    load_design_handoff,
    write_design_handoff,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_validation():
    """Mock schema validation to avoid jsonschema dependency."""
    with patch("startd8.contractors.handoff._validate_handoff"):
        yield


@pytest.fixture
def handoff_kwargs():
    """Minimal kwargs for write_design_handoff."""
    return {
        "enriched_seed_path": "/abs/path/to/seed.json",
        "project_root": "/abs/path/to/project",
        "workflow_id": "test-wf-001",
        "completed_phases": ["design"],
        "design_results": {"T1": {"status": "designed"}},
        "scaffold": {},
    }


# ── Gap 3: design_structural_delta ─────────────────────────────────


class TestStructuralDelta:
    """Gap 3: Extraction and persistence of per-file element intent."""

    def test_extraction_basic(self):
        """_extract_structural_delta parses Files Touched with actions."""
        from startd8.contractors.context_seed_handlers import _extract_structural_delta

        doc = (
            "## Overview\nSome intro.\n"
            "### Files Touched\n"
            "- `src/auth.py` (modify)\n"
            "  - Add `OAuth2Handler` class\n"
            "  - Modify `login` to accept tokens\n"
            "- `src/config.py` (create)\n"
            "  - Add `AuthConfig` dataclass\n"
        )
        delta = _extract_structural_delta(doc)
        assert "src/auth.py" in delta
        assert "src/config.py" in delta
        assert len(delta["src/auth.py"]) == 2
        assert delta["src/auth.py"][0]["action"] == "add"
        assert delta["src/auth.py"][0]["element"] == "OAuth2Handler"
        assert delta["src/auth.py"][1]["action"] == "modify"
        assert delta["src/config.py"][0]["action"] == "add"

    def test_extraction_no_section(self):
        """Empty dict when no Files Touched section exists."""
        from startd8.contractors.context_seed_handlers import _extract_structural_delta

        doc = "## Overview\nJust text.\n## Architecture\nMore text.\n"
        assert _extract_structural_delta(doc) == {}

    def test_extraction_preserve_action(self):
        """Preserve action is correctly parsed."""
        from startd8.contractors.context_seed_handlers import _extract_structural_delta

        doc = (
            "### Files Touched\n"
            "- `src/core.py` (modify)\n"
            "  - Preserve `BaseClass` interface\n"
            "  - Add `new_method` to `BaseClass`\n"
        )
        delta = _extract_structural_delta(doc)
        assert delta["src/core.py"][0]["action"] == "preserve"
        assert delta["src/core.py"][0]["element"] == "BaseClass"
        assert delta["src/core.py"][1]["action"] == "add"

    def test_handoff_roundtrip(self, tmp_path, handoff_kwargs):
        """Structural delta persists through write/load cycle."""
        delta = {"T1": {"src/a.py": [{"element": "Foo", "action": "modify", "detail": "Change Foo"}]}}
        write_design_handoff(
            output_dir=str(tmp_path),
            design_structural_delta=delta,
            **handoff_kwargs,
        )
        loaded = load_design_handoff(tmp_path)
        assert loaded.design_structural_delta == delta

    def test_handoff_default_empty(self, tmp_path, handoff_kwargs):
        """Defaults to empty dict when not provided."""
        write_design_handoff(output_dir=str(tmp_path), **handoff_kwargs)
        loaded = load_design_handoff(tmp_path)
        assert loaded.design_structural_delta == {}


# ── Gap 1: design_referenced_elements ──────────────────────────────


class TestReferencedElements:
    """Gap 1: Cross-validation of element references against manifest."""

    def test_extraction_with_manifest(self):
        """References are cross-validated against manifest elements."""
        from startd8.contractors.context_seed_handlers import _extract_referenced_elements

        doc = (
            "Modify `AuthHandler` to use the new `validate_token` method.\n"
            "Preserve `BaseClass` interface.\n"
        )
        manifest_elements = {
            "src/auth.py": ["AuthHandler", "BaseClass", "login"],
        }
        refs = _extract_referenced_elements(doc, manifest_elements)
        assert "src/auth.py" in refs
        assert "AuthHandler" in refs["src/auth.py"]
        assert "BaseClass" in refs["src/auth.py"]
        # validate_token is NOT in manifest → should not appear
        assert "validate_token" not in refs.get("src/auth.py", [])

    def test_no_manifest_returns_empty(self):
        """Returns empty when no manifest is provided."""
        from startd8.contractors.context_seed_handlers import _extract_referenced_elements

        assert _extract_referenced_elements("some doc", None) == {}
        assert _extract_referenced_elements("some doc", {}) == {}

    def test_handoff_roundtrip(self, tmp_path, handoff_kwargs):
        """Referenced elements persist through write/load cycle."""
        refs = {"T1": {"src/a.py": ["ClassA", "func_b"]}}
        write_design_handoff(
            output_dir=str(tmp_path),
            design_referenced_elements=refs,
            **handoff_kwargs,
        )
        loaded = load_design_handoff(tmp_path)
        assert loaded.design_referenced_elements == refs


# ── Gap 2: manifest_file_checksums ─────────────────────────────────


class TestManifestFileChecksums:
    """Gap 2: Per-file checksums at design time for staleness detection."""

    def test_compute_checksums(self, tmp_path):
        """Checksums are computed for existing files."""
        from startd8.contractors.context_seed_handlers import _compute_manifest_file_checksums

        # Create a test file
        test_file = tmp_path / "src" / "module.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("class Foo:\n    pass\n")
        expected = hashlib.sha256(test_file.read_bytes()).hexdigest()

        result = _compute_manifest_file_checksums(
            ["src/module.py", "src/missing.py"],
            str(tmp_path),
        )
        assert result["src/module.py"] == expected
        assert "src/missing.py" not in result

    def test_empty_project_root(self):
        """Returns empty when project_root is empty."""
        from startd8.contractors.context_seed_handlers import _compute_manifest_file_checksums

        assert _compute_manifest_file_checksums(["a.py"], "") == {}

    def test_handoff_roundtrip(self, tmp_path, handoff_kwargs):
        """Checksums persist through write/load cycle."""
        checksums = {"src/a.py": "abc123", "src/b.py": "def456"}
        write_design_handoff(
            output_dir=str(tmp_path),
            manifest_file_checksums=checksums,
            **handoff_kwargs,
        )
        loaded = load_design_handoff(tmp_path)
        assert loaded.manifest_file_checksums == checksums


# ── Gap 4: design_mode_evidence ────────────────────────────────────


class TestDesignModeEvidence:
    """Gap 4: Extended design mode with reasoning and elevated weight."""

    def test_handoff_roundtrip(self, tmp_path, handoff_kwargs):
        """Evidence data persists through write/load cycle."""
        evidence = {
            "T1": {
                "mode": "update",
                "evidence": ["scaffold.existing_target_files", "design_doc_modify_annotation"],
                "reasoning": "2 signal(s): scaffold.existing_target_files, design_doc_modify_annotation",
            }
        }
        write_design_handoff(
            output_dir=str(tmp_path),
            design_mode_evidence=evidence,
            **handoff_kwargs,
        )
        loaded = load_design_handoff(tmp_path)
        assert loaded.design_mode_evidence == evidence

    def test_elevated_weight_with_evidence(self):
        """_classify_edit_mode elevates design_mode weight with >=2 evidence signals."""
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        task = MagicMock()
        task.task_id = "T1"
        task.target_files = ["src/new_file.py"]
        task.existing_content_hash = None
        task.file_scope = {}

        scaffold = {"existing_target_files": []}
        design_mode_summary = {"T1": "update"}

        # Without evidence: weight 1 (Tier 2)
        result_no_evidence = ImplementPhaseHandler._classify_edit_mode(
            task, scaffold, design_mode_summary,
        )

        # With strong evidence: weight elevated to 2 (Tier 1)
        evidence = {
            "T1": {
                "mode": "update",
                "evidence": ["scaffold.existing_target_files", "design_doc_modify_annotation"],
            }
        }
        result_with_evidence = ImplementPhaseHandler._classify_edit_mode(
            task, scaffold, design_mode_summary,
            design_mode_evidence=evidence,
        )

        # Both should classify as edit since design_mode="update"
        assert result_no_evidence.mode == "edit"
        assert result_with_evidence.mode == "edit"
        # But evidence version should have higher per-file edit weight
        no_ev_weight = result_no_evidence.per_file["src/new_file.py"].edit_weight
        with_ev_weight = result_with_evidence.per_file["src/new_file.py"].edit_weight
        assert with_ev_weight > no_ev_weight

    def test_no_elevation_with_single_signal(self):
        """Weight NOT elevated with only 1 evidence signal."""
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        task = MagicMock()
        task.task_id = "T1"
        task.target_files = ["src/new_file.py"]
        task.existing_content_hash = None
        task.file_scope = {}

        scaffold = {"existing_target_files": []}
        design_mode_summary = {"T1": "update"}

        # Single signal: no elevation
        evidence = {"T1": {"mode": "update", "evidence": ["design_doc_modify_annotation"]}}
        result = ImplementPhaseHandler._classify_edit_mode(
            task, scaffold, design_mode_summary,
            design_mode_evidence=evidence,
        )
        assert result.per_file["src/new_file.py"].edit_weight == 1


# ── Gap 5: manifest_truncation_tier ────────────────────────────────


class TestManifestTruncationTier:
    """Gap 5: Per-file truncation tier recording."""

    def test_handoff_roundtrip(self, tmp_path, handoff_kwargs):
        """Truncation tier data persists through write/load cycle."""
        tiers = {
            "src/a.py": "full",
            "src/b.py": "compact",
            "src/c.py": "unavailable",
        }
        write_design_handoff(
            output_dir=str(tmp_path),
            manifest_truncation_tier=tiers,
            **handoff_kwargs,
        )
        loaded = load_design_handoff(tmp_path)
        assert loaded.manifest_truncation_tier == tiers


# ── HandoffData field existence ────────────────────────────────────


class TestHandoffDataFields:
    """Verify all 5 new fields exist on HandoffData with correct defaults."""

    def test_structural_delta_default(self):
        h = HandoffData(
            enriched_seed_path="", project_root="", output_dir="", workflow_id="",
        )
        assert h.design_structural_delta == {}

    def test_referenced_elements_default(self):
        h = HandoffData(
            enriched_seed_path="", project_root="", output_dir="", workflow_id="",
        )
        assert h.design_referenced_elements == {}

    def test_manifest_checksums_default(self):
        h = HandoffData(
            enriched_seed_path="", project_root="", output_dir="", workflow_id="",
        )
        assert h.manifest_file_checksums == {}

    def test_mode_evidence_default(self):
        h = HandoffData(
            enriched_seed_path="", project_root="", output_dir="", workflow_id="",
        )
        assert h.design_mode_evidence == {}

    def test_truncation_tier_default(self):
        h = HandoffData(
            enriched_seed_path="", project_root="", output_dir="", workflow_id="",
        )
        assert h.manifest_truncation_tier == {}


# ── Backward compatibility ─────────────────────────────────────────


class TestBackwardCompatibility:
    """Loading a handoff without the new fields should still work."""

    def test_load_legacy_handoff(self, tmp_path):
        """Handoff missing new fields defaults gracefully."""
        legacy_data = {
            "enriched_seed_path": "/seed.json",
            "project_root": "/project",
            "output_dir": str(tmp_path),
            "workflow_id": "legacy-001",
            "schema_version": 1,
            "completed_phases": ["design"],
            "design_results": {},
            "scaffold": {},
            "design_mode_summary": {},
        }
        handoff_file = tmp_path / "design-handoff.json"
        handoff_file.write_text(json.dumps(legacy_data))

        loaded = load_design_handoff(handoff_file)
        assert loaded.design_structural_delta == {}
        assert loaded.design_referenced_elements == {}
        assert loaded.manifest_file_checksums == {}
        assert loaded.design_mode_evidence == {}
        assert loaded.manifest_truncation_tier == {}


# ── Development.py consumption ─────────────────────────────────────


class TestStructuralDeltaConsumption:
    """Verify _build_structural_delta renders chunk metadata correctly."""

    def test_renders_delta(self):
        """Structural delta renders as element-level guidance."""
        from startd8.contractors.artisan_phases.development import LeadContractorChunkExecutor

        chunk = MagicMock()
        chunk.metadata = {
            "_design_structural_delta": {
                "src/auth.py": [
                    {"element": "OAuth2Handler", "action": "add", "detail": "Add OAuth2Handler class"},
                    {"element": "login", "action": "modify", "detail": "Modify login to accept tokens"},
                ],
            },
        }

        result = LeadContractorChunkExecutor._build_structural_delta(chunk)
        assert len(result) > 0
        text = "\n".join(result)
        assert "Structural Intent" in text
        assert "`OAuth2Handler`" in text
        assert "`login`" in text
        assert "+" in text  # add prefix
        assert "~" in text  # modify prefix

    def test_empty_delta(self):
        """Returns empty list when no delta."""
        from startd8.contractors.artisan_phases.development import LeadContractorChunkExecutor

        chunk = MagicMock()
        chunk.metadata = {}
        assert LeadContractorChunkExecutor._build_structural_delta(chunk) == []

    def test_phantom_warnings_included(self):
        """Phantom element warnings are included when present."""
        from startd8.contractors.artisan_phases.development import LeadContractorChunkExecutor

        chunk = MagicMock()
        chunk.metadata = {
            "_design_structural_delta": {
                "src/a.py": [{"element": "Foo", "action": "modify", "detail": "x"}],
            },
            "_phantom_element_warnings": ["src/a.py:NonExistent"],
        }
        result = LeadContractorChunkExecutor._build_structural_delta(chunk)
        text = "\n".join(result)
        assert "WARNING" in text
        assert "NonExistent" in text

    def test_truncation_tier_note(self):
        """Truncation tier note included for non-full files."""
        from startd8.contractors.artisan_phases.development import LeadContractorChunkExecutor

        chunk = MagicMock()
        chunk.metadata = {
            "_design_structural_delta": {
                "src/a.py": [{"element": "X", "action": "add", "detail": "Add X"}],
            },
            "_manifest_truncation_tier": {
                "src/a.py": "compact",
                "src/b.py": "full",
            },
        }
        result = LeadContractorChunkExecutor._build_structural_delta(chunk)
        text = "\n".join(result)
        assert "truncated" in text.lower()
        assert "`src/a.py`" in text
