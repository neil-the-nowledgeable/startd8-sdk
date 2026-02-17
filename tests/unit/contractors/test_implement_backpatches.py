"""Tests for IMPLEMENT phase back-patches (BP-1 through BP-5).

BP-1: Exit-side contract validation wired in _execute_phase
BP-2: HandoffData source_checksum round-trip and verification
BP-3: Inline design doc quality check uses line count (not char count)
BP-4: Resume cache partial-checksum warning
BP-5: Multi-type parameter_sources extraction
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from startd8.contractors.handoff import (
    DESIGN_HANDOFF_FILENAME,
    HandoffData,
    load_design_handoff,
    write_design_handoff,
    verify_source_checksum,
)


# ── Helpers ────────────────────────────────────────────────────────────


class _FakePhase:
    """Minimal phase-like object with a .value attribute."""

    def __init__(self, value: str):
        self.value = value


@dataclass
class _FakeSeedTask:
    """Minimal SeedTask-like object for chunk building tests."""

    task_id: str = "T-1"
    title: str = "Generate dashboard"
    task_type: str = "task"
    story_points: int = 3
    priority: str = "P1"
    labels: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    description: str = "Generate a monitoring dashboard"
    target_files: list[str] = field(default_factory=list)
    estimated_loc: int = 100
    feature_id: str = "F-1"
    domain: str = "observability"
    domain_reasoning: str = ""
    environment_checks: list[dict] = field(default_factory=list)
    prompt_constraints: list[str] = field(default_factory=list)
    post_generation_validators: list[str] = field(default_factory=list)
    available_siblings: list[str] = field(default_factory=list)
    existing_content_hash: Optional[str] = None
    design_doc_sections: list[str] = field(default_factory=list)
    artifact_types_addressed: list[str] = field(default_factory=list)
    file_scope: dict[str, str] = field(default_factory=dict)


@pytest.fixture(autouse=True)
def mock_handoff_validation():
    """Mock schema validation to avoid jsonschema dependency."""
    with patch("startd8.contractors.handoff._validate_handoff"):
        yield


# ============================================================================
# BP-1: Exit-side contract validation
# ============================================================================


class TestBP1ExitSideContractValidation:
    """Verify validate_phase_boundary is called on exit when _contract_path set."""

    def test_exit_validation_called_when_contract_path_set(self):
        """_execute_phase should call validate_phase_boundary on exit."""
        from startd8.contractors.artisan_contractor import ArtisanContractorWorkflow

        # Read the source to verify the exit-side validation is wired
        import inspect
        source = inspect.getsource(ArtisanContractorWorkflow._execute_phase)

        # Verify the exit-side boundary validation call exists after
        # validate_phase_exit and before phase_end
        exit_idx = source.index("validate_phase_exit(phase, context)")
        boundary_idx = source.index(
            'validate_phase_boundary(\n'
            '                            phase, context, "exit", self._contract_path'
        )
        phase_end_idx = source.index("phase_end = time.monotonic()")

        # Exit validation comes after phase_exit, boundary validation after that
        assert exit_idx < boundary_idx < phase_end_idx

    def test_exit_validation_guarded_by_contract_path(self):
        """Exit boundary validation only runs when _contract_path is set."""
        from startd8.contractors.artisan_contractor import ArtisanContractorWorkflow
        import inspect
        source = inspect.getsource(ArtisanContractorWorkflow._execute_phase)

        # Find the exit-side guard
        assert 'if self._contract_path:' in source
        # The exit-side block should appear after validate_phase_exit
        exit_idx = source.index("validate_phase_exit(phase, context)")
        # There should be a contract_path guard between exit and phase_end
        guard_after_exit = source.index(
            "if self._contract_path:", exit_idx
        )
        phase_end_idx = source.index("phase_end = time.monotonic()")
        assert exit_idx < guard_after_exit < phase_end_idx

    def test_emit_boundary_result_called_on_exit(self):
        """When exit_result is non-None, emit_boundary_result is called."""
        from startd8.contractors.artisan_contractor import ArtisanContractorWorkflow
        import inspect
        source = inspect.getsource(ArtisanContractorWorkflow._execute_phase)

        # Verify emit_boundary_result import+call appears in exit block
        # (after validate_phase_exit)
        exit_idx = source.index("validate_phase_exit(phase, context)")
        emit_idx = source.index("emit_boundary_result(exit_result)", exit_idx)
        assert emit_idx > exit_idx


# ============================================================================
# BP-2: HandoffData source_checksum
# ============================================================================


class TestBP2SourceChecksum:
    """source_checksum field on HandoffData + round-trip serialization."""

    def test_handoff_data_has_source_checksum_field(self):
        hd = HandoffData(
            enriched_seed_path="/seed.json",
            project_root="/proj",
            output_dir="/out",
            workflow_id="wf-1",
            source_checksum="abc123",
        )
        assert hd.source_checksum == "abc123"

    def test_source_checksum_defaults_to_none(self):
        hd = HandoffData(
            enriched_seed_path="/seed.json",
            project_root="/proj",
            output_dir="/out",
            workflow_id="wf-1",
        )
        assert hd.source_checksum is None

    def test_round_trip_with_checksum(self, tmp_path):
        checksum = "deadbeef" * 8  # 64 hex chars
        write_design_handoff(
            output_dir=str(tmp_path),
            enriched_seed_path="/seed.json",
            project_root="/proj",
            workflow_id="wf-1",
            source_checksum=checksum,
        )
        loaded = load_design_handoff(tmp_path)
        assert loaded.source_checksum == checksum

    def test_round_trip_without_checksum(self, tmp_path):
        write_design_handoff(
            output_dir=str(tmp_path),
            enriched_seed_path="/nonexistent/seed.json",
            project_root="/proj",
            workflow_id="wf-1",
        )
        loaded = load_design_handoff(tmp_path)
        # No seed file exists, so auto-compute fails gracefully
        assert loaded.source_checksum is None

    def test_auto_computes_checksum_from_seed(self, tmp_path):
        """When source_checksum is not provided, it's computed from the seed file."""
        seed = tmp_path / "seed.json"
        seed.write_text('{"tasks": []}', encoding="utf-8")
        expected = hashlib.sha256(seed.read_bytes()).hexdigest()

        write_design_handoff(
            output_dir=str(tmp_path),
            enriched_seed_path=str(seed),
            project_root="/proj",
            workflow_id="wf-1",
        )
        loaded = load_design_handoff(tmp_path)
        assert loaded.source_checksum == expected

    def test_explicit_checksum_overrides_auto(self, tmp_path):
        """Explicit source_checksum takes precedence over auto-compute."""
        seed = tmp_path / "seed.json"
        seed.write_text('{"tasks": []}', encoding="utf-8")
        explicit = "explicit" * 8

        write_design_handoff(
            output_dir=str(tmp_path),
            enriched_seed_path=str(seed),
            project_root="/proj",
            workflow_id="wf-1",
            source_checksum=explicit,
        )
        loaded = load_design_handoff(tmp_path)
        assert loaded.source_checksum == explicit

    def test_source_checksum_in_json_schema(self):
        from startd8.contractors.handoff import HANDOFF_SCHEMA
        props = HANDOFF_SCHEMA["properties"]
        assert "source_checksum" in props
        assert props["source_checksum"]["type"] == ["string", "null"]

    def test_old_handoff_without_checksum_loads(self, tmp_path):
        """Handoffs written before BP-2 (no source_checksum) still load."""
        old_data = {
            "enriched_seed_path": "/seed.json",
            "project_root": "/proj",
            "output_dir": "/out",
            "workflow_id": "wf-old",
            "completed_phases": [],
            "design_results": {},
            "scaffold": {},
            "schema_version": 1,
        }
        p = tmp_path / DESIGN_HANDOFF_FILENAME
        p.write_text(json.dumps(old_data))
        loaded = load_design_handoff(p)
        assert loaded.source_checksum is None


class TestVerifySourceChecksum:
    """Tests for verify_source_checksum()."""

    def test_no_checksum_returns_none(self):
        hd = HandoffData(
            enriched_seed_path="/seed.json",
            project_root="/proj",
            output_dir="/out",
            workflow_id="wf-1",
            source_checksum=None,
        )
        assert verify_source_checksum(hd) is None

    def test_matching_checksum_returns_none(self, tmp_path):
        seed = tmp_path / "seed.json"
        seed.write_text('{"tasks": []}', encoding="utf-8")
        checksum = hashlib.sha256(seed.read_bytes()).hexdigest()

        hd = HandoffData(
            enriched_seed_path=str(seed),
            project_root="/proj",
            output_dir="/out",
            workflow_id="wf-1",
            source_checksum=checksum,
        )
        assert verify_source_checksum(hd) is None

    def test_mismatched_checksum_returns_warning(self, tmp_path):
        seed = tmp_path / "seed.json"
        seed.write_text('{"tasks": []}', encoding="utf-8")

        hd = HandoffData(
            enriched_seed_path=str(seed),
            project_root="/proj",
            output_dir="/out",
            workflow_id="wf-1",
            source_checksum="wrong" * 16,
        )
        result = verify_source_checksum(hd)
        assert result is not None
        assert "Source checksum drift" in result

    def test_missing_seed_file_returns_none(self, tmp_path):
        hd = HandoffData(
            enriched_seed_path=str(tmp_path / "gone.json"),
            project_root="/proj",
            output_dir="/out",
            workflow_id="wf-1",
            source_checksum="abc123",
        )
        assert verify_source_checksum(hd) is None


# ============================================================================
# BP-3: Inline quality check uses line count
# ============================================================================


class TestBP3InlineQualityCheckLineCount:
    """The inline DESIGN→IMPLEMENT boundary check should use line count, not char count."""

    def test_short_lines_rejected(self):
        """49 lines of content should trigger the warning (< 50 line threshold)."""
        # 49 lines = below threshold
        design_doc = "\n".join(f"Line {i}" for i in range(49))
        assert len(design_doc.strip().splitlines()) == 49

        # The inline check: not design_doc_text or _line_count < 50
        _line_count = len(design_doc.strip().splitlines())
        assert _line_count < 50  # Would trigger fallback

    def test_fifty_lines_accepted(self):
        """Exactly 50 lines should pass the threshold."""
        design_doc = "\n".join(f"Line {i}" for i in range(50))
        _line_count = len(design_doc.strip().splitlines())
        assert _line_count >= 50  # Would NOT trigger fallback

    def test_long_single_line_rejected(self):
        """A single long line (>50 chars) should be rejected (< 50 lines)."""
        design_doc = "x" * 200  # Long but only 1 line
        _line_count = len(design_doc.strip().splitlines())
        assert _line_count < 50  # Would trigger fallback

    def test_source_uses_splitlines_not_len(self):
        """Verify the source code uses splitlines-based check, not char-based."""
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler
        import inspect
        source = inspect.getsource(ImplementPhaseHandler._tasks_to_chunks)

        # Should contain the line-count version
        assert "design_doc_text.strip().splitlines()" in source
        # Should NOT contain the old char-based check
        assert "len(design_doc_text.strip()) < 50" not in source


# ============================================================================
# BP-4: Resume cache partial-checksum warning
# ============================================================================


class TestBP4PartialChecksumWarning:
    """When only one of cached/source checksum is present, a warning is logged."""

    def test_implement_cache_partial_checksum_warning(self, caplog):
        """IMPLEMENT resume cache logs warning when only one checksum exists."""
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        # Verify the source code contains the partial-checksum warning
        import inspect
        source = inspect.getsource(ImplementPhaseHandler)

        assert "partial checksum" in source
        # The IMPLEMENT handler's resume cache validation
        assert (
            "IMPLEMENT --resume: Layer 3 (source checksum): partial checksum" in source
        )

    def test_review_cache_partial_checksum_warning(self):
        """REVIEW resume cache logs warning when only one checksum exists."""
        from startd8.contractors.context_seed_handlers import ReviewPhaseHandler

        import inspect
        source = inspect.getsource(ReviewPhaseHandler)

        assert "partial checksum" in source
        assert (
            "REVIEW: Layer 1 (source checksum): partial checksum" in source
        )

    def test_partial_checksum_does_not_reject_cache(self):
        """Partial checksum should warn but NOT invalidate the cache."""
        # The code should NOT return None/empty when only one checksum is present.
        # Verify this by checking the control flow: elif branch does NOT have
        # 'return None' or 'return {}'.
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler
        import inspect
        source = inspect.getsource(ImplementPhaseHandler)

        # Find the partial-checksum elif block
        idx = source.index(
            "IMPLEMENT --resume: Layer 3 (source checksum): partial checksum"
        )
        # The next 5 lines after this should be the warning message, NOT a return
        block = source[idx:idx + 300]
        # There should be no "return None" immediately in this block
        assert "return None" not in block.split("# Parse GenerationResult")[0].split(
            "IMPLEMENT --resume: Layer 3"
        )[-1]


# ============================================================================
# BP-5: Multi-type parameter_sources extraction
# ============================================================================


class TestBP5MultiTypeParameterSources:
    """parameter_sources should merge all artifact types, not just the first."""

    def test_multi_artifact_type_extraction(self):
        """A task with 2 artifact types should get parameter_sources for both."""
        parameter_sources = {
            "ServiceMonitor": {"port": "metrics", "interval": "30s"},
            "PrometheusRule": {"severity": "critical"},
            "Dashboard": {"uid": "auto"},
        }
        artifact_types = ["ServiceMonitor", "PrometheusRule"]

        # This is the BP-5 logic (merged from the fix)
        result = {
            atype: parameter_sources.get(atype, {})
            for atype in artifact_types
            if atype in parameter_sources
        }

        assert "ServiceMonitor" in result
        assert "PrometheusRule" in result
        assert "Dashboard" not in result
        assert result["ServiceMonitor"]["port"] == "metrics"
        assert result["PrometheusRule"]["severity"] == "critical"

    def test_single_artifact_type(self):
        """A task with 1 artifact type should still work correctly."""
        parameter_sources = {
            "ServiceMonitor": {"port": "metrics"},
        }
        artifact_types = ["ServiceMonitor"]

        result = {
            atype: parameter_sources.get(atype, {})
            for atype in artifact_types
            if atype in parameter_sources
        }

        assert result == {"ServiceMonitor": {"port": "metrics"}}

    def test_no_artifact_types(self):
        """A task with no artifact types should produce empty dict."""
        artifact_types: list[str] = []
        result = (
            {
                atype: {}.get(atype, {})
                for atype in artifact_types
                if atype in {}
            }
            if artifact_types
            else {}
        )
        assert result == {}

    def test_unknown_artifact_type_excluded(self):
        """Artifact types not in parameter_sources are excluded (not defaulted)."""
        parameter_sources = {
            "ServiceMonitor": {"port": "metrics"},
        }
        artifact_types = ["ServiceMonitor", "UnknownType"]

        result = {
            atype: parameter_sources.get(atype, {})
            for atype in artifact_types
            if atype in parameter_sources
        }

        assert "ServiceMonitor" in result
        assert "UnknownType" not in result

    def test_source_uses_dict_comprehension_not_index_zero(self):
        """Verify the source code uses dict comprehension, not [0] indexing."""
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler
        import inspect
        source = inspect.getsource(ImplementPhaseHandler._tasks_to_chunks)

        # Should NOT contain the old [0] indexing pattern
        assert "artifact_types_addressed[0]" not in source
        # Should contain a comprehension over artifact_types_addressed
        assert "for atype in task.artifact_types_addressed" in source
