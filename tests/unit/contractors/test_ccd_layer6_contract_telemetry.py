"""Tests for CCD Layer 6: Contract & Telemetry.

Covers:
- CCD-600: contract YAML amendments (schema_version, lane_assignments enrichment,
  design_results.*.lane_index optional field, shared_file_manifest, lane_conflicts)
- CCD-601/602: _CCD_DESIGN_SPAN_ATTRS canonical span attribute constant
- CCD-603: FinalizePhaseHandler._build_design_coherence_summary
- CCD checkpoint key inclusions (shared_file_manifest, lane_conflicts,
  _design_lane_count, lane_to_file_mapping, _design_lane_computation_skipped,
  design_mode_summary)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONTRACT_PATH = (
    Path(__file__).parents[3]
    / "src"
    / "startd8"
    / "contractors"
    / "contracts"
    / "artisan-pipeline.contract.yaml"
)


def _load_contract() -> dict[str, Any]:
    with open(_CONTRACT_PATH) as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# TestContractYAMLAmendment — CCD-600
# ---------------------------------------------------------------------------


class TestContractYAMLAmendment:
    """Tests for CCD-600 contract YAML changes."""

    @pytest.fixture
    def contract(self) -> dict[str, Any]:
        return _load_contract()

    # --- schema version ---

    def test_schema_version_bumped(self, contract: dict[str, Any]) -> None:
        """Schema version must be exactly 0.4.0 after CCD-600 bump."""
        assert contract["schema_version"] == "0.4.0"

    # --- design entry enrichments ---

    def test_design_entry_enrichment_has_lane_assignments(
        self, contract: dict[str, Any]
    ) -> None:
        """lane_assignments must appear in design phase entry enrichment list."""
        enrichments = contract["phases"]["design"]["entry"]["enrichment"]
        names = [e["name"] for e in enrichments]
        assert "lane_assignments" in names

    def test_design_entry_lane_assignments_is_advisory(
        self, contract: dict[str, Any]
    ) -> None:
        """lane_assignments enrichment must be advisory severity (DESIGN falls back gracefully)."""
        enrichments = contract["phases"]["design"]["entry"]["enrichment"]
        entry = next(e for e in enrichments if e["name"] == "lane_assignments")
        assert entry["severity"] == "advisory"

    def test_design_entry_enrichment_has_wave_assignments(
        self, contract: dict[str, Any]
    ) -> None:
        """wave_assignments must appear in design phase entry enrichment list."""
        enrichments = contract["phases"]["design"]["entry"]["enrichment"]
        names = [e["name"] for e in enrichments]
        assert "wave_assignments" in names

    # --- design exit optional fields ---

    def test_design_exit_optional_has_lane_index(
        self, contract: dict[str, Any]
    ) -> None:
        """design_results.*.lane_index must appear in design exit optional fields."""
        optional = contract["phases"]["design"]["exit"]["optional"]
        names = [e["name"] for e in optional]
        assert "design_results.*.lane_index" in names

    def test_design_exit_optional_has_shared_file_manifest(
        self, contract: dict[str, Any]
    ) -> None:
        """shared_file_manifest must appear in design exit optional fields."""
        optional = contract["phases"]["design"]["exit"]["optional"]
        names = [e["name"] for e in optional]
        assert "shared_file_manifest" in names

    def test_design_exit_optional_has_lane_conflicts(
        self, contract: dict[str, Any]
    ) -> None:
        """lane_conflicts must appear in design exit optional fields."""
        optional = contract["phases"]["design"]["exit"]["optional"]
        names = [e["name"] for e in optional]
        assert "lane_conflicts" in names

    def test_design_exit_optional_has_wave_index(
        self, contract: dict[str, Any]
    ) -> None:
        """design_results.*.wave_index must appear in design exit optional fields."""
        optional = contract["phases"]["design"]["exit"]["optional"]
        names = [e["name"] for e in optional]
        assert "design_results.*.wave_index" in names

    # --- guard: existing required fields must remain intact ---

    def test_existing_required_fields_unchanged(
        self, contract: dict[str, Any]
    ) -> None:
        """design_results must still be present as a required exit field."""
        required = contract["phases"]["design"]["exit"]["required"]
        names = [e["name"] for e in required]
        assert "design_results" in names

    def test_plan_exit_required_fields_intact(
        self, contract: dict[str, Any]
    ) -> None:
        """Core PLAN exit fields must survive any schema amendments."""
        required = contract["phases"]["plan"]["exit"]["required"]
        names = [e["name"] for e in required]
        for expected in ("tasks", "task_index", "plan_title", "plan_goals"):
            assert expected in names, f"Missing plan exit required field: {expected!r}"

    def test_implement_exit_required_fields_intact(
        self, contract: dict[str, Any]
    ) -> None:
        """Core IMPLEMENT exit fields must survive any schema amendments."""
        required = contract["phases"]["implement"]["exit"]["required"]
        names = [e["name"] for e in required]
        for expected in ("implementation", "generation_results", "truncation_flags"):
            assert expected in names, (
                f"Missing implement exit required field: {expected!r}"
            )

    # --- shared_file_manifest semantics ---

    def test_shared_file_manifest_description_mentions_task_ids(
        self, contract: dict[str, Any]
    ) -> None:
        """shared_file_manifest description should clarify it maps files to task IDs."""
        optional = contract["phases"]["design"]["exit"]["optional"]
        entry = next(e for e in optional if e["name"] == "shared_file_manifest")
        desc = entry.get("description", "")
        assert "task" in desc.lower()

    def test_lane_conflicts_description_mentions_compatibility(
        self, contract: dict[str, Any]
    ) -> None:
        """lane_conflicts description should reference compatibility checking."""
        optional = contract["phases"]["design"]["exit"]["optional"]
        entry = next(e for e in optional if e["name"] == "lane_conflicts")
        desc = entry.get("description", "")
        # Accept either "compatibility" or "conflict" as the key concept word.
        assert any(
            kw in desc.lower() for kw in ("compatib", "conflict", "check")
        ), f"Description does not describe lane conflict semantics: {desc!r}"


# ---------------------------------------------------------------------------
# TestDesignCoherenceSummary — CCD-603
# ---------------------------------------------------------------------------


class TestDesignCoherenceSummary:
    """Tests for CCD-603 FINALIZE coherence summary helper."""

    @staticmethod
    def _call(ctx: dict[str, Any]) -> dict[str, Any]:
        from startd8.contractors.context_seed_handlers import FinalizePhaseHandler

        return FinalizePhaseHandler._build_design_coherence_summary(ctx)

    # --- skip path ---

    def test_not_computed_when_lane_skipped(self) -> None:
        """Returns NOT_COMPUTED status when lane computation was skipped."""
        ctx: dict[str, Any] = {"_design_lane_computation_skipped": True}
        result = self._call(ctx)
        assert result["status"] == "NOT_COMPUTED"

    def test_not_computed_includes_reason(self) -> None:
        """NOT_COMPUTED result must include a human-readable reason field."""
        ctx: dict[str, Any] = {"_design_lane_computation_skipped": True}
        result = self._call(ctx)
        assert "reason" in result
        assert isinstance(result["reason"], str)
        assert result["reason"]  # non-empty

    def test_not_computed_ignores_other_keys(self) -> None:
        """Lane skipped flag short-circuits even if conflict data is present."""
        ctx: dict[str, Any] = {
            "_design_lane_computation_skipped": True,
            "lane_conflicts": [{"status": "COHERENT", "lane_index": 0}],
            "_design_lane_count": 5,
        }
        result = self._call(ctx)
        assert result["status"] == "NOT_COMPUTED"
        # Must not accidentally expose total_lanes from this path
        assert "total_lanes" not in result

    # --- empty / default state ---

    def test_empty_state_graceful_default(self) -> None:
        """Empty context must not raise; total_lanes defaults to 0."""
        ctx: dict[str, Any] = {}
        result = self._call(ctx)
        assert result["total_lanes"] == 0

    def test_empty_state_all_count_fields_zero(self) -> None:
        """All numeric count fields must default to 0 for an empty context."""
        ctx: dict[str, Any] = {}
        result = self._call(ctx)
        for field in (
            "total_lanes",
            "shared_file_lanes",
            "coherent_lanes",
            "warning_lanes",
            "conflicting_lanes",
            "shared_file_count",
        ):
            assert result[field] == 0, f"Expected 0 for {field!r}, got {result[field]}"

    def test_empty_state_lane_details_is_empty_list(self) -> None:
        """lane_details must be an empty list when there are no conflicts."""
        ctx: dict[str, Any] = {}
        result = self._call(ctx)
        assert result["lane_details"] == []

    # --- counts from real data ---

    def test_counts_correct(self) -> None:
        """coherent/warning/conflicting lane counts are derived from lane_conflicts."""
        ctx: dict[str, Any] = {
            "lane_conflicts": [
                {"status": "COHERENT", "lane_index": 0, "task_ids": ["T-1"]},
                {"status": "WARNING", "lane_index": 1, "task_ids": ["T-2"]},
                {"status": "CONFLICTING", "lane_index": 2, "task_ids": ["T-3"]},
            ],
            "lane_to_file_mapping": {1: ["src/a.py"]},
            "shared_file_manifest": {"src/a.py": ["T-2", "T-3"]},
            "_design_lane_count": 3,
        }
        result = self._call(ctx)
        assert result["coherent_lanes"] == 1
        assert result["warning_lanes"] == 1
        assert result["conflicting_lanes"] == 1
        assert result["total_lanes"] == 3

    def test_shared_file_count_uses_manifest_length(self) -> None:
        """shared_file_count reflects the number of unique files in shared_file_manifest."""
        ctx: dict[str, Any] = {
            "shared_file_manifest": {
                "src/a.py": ["T-1", "T-2"],
                "src/b.py": ["T-3"],
            },
            "_design_lane_count": 2,
        }
        result = self._call(ctx)
        assert result["shared_file_count"] == 2

    def test_shared_file_lanes_uses_lane_to_file_mapping(self) -> None:
        """shared_file_lanes counts lanes that have at least one shared file."""
        ctx: dict[str, Any] = {
            "lane_to_file_mapping": {0: ["src/a.py"], 2: ["src/b.py"]},
            "_design_lane_count": 3,
        }
        result = self._call(ctx)
        assert result["shared_file_lanes"] == 2

    def test_lane_details_populated_for_each_conflict(self) -> None:
        """lane_details list must have one entry per lane_conflicts item with a lane_index."""
        ctx: dict[str, Any] = {
            "lane_conflicts": [
                {"status": "WARNING", "lane_index": 0, "task_ids": ["T-1"]},
                {"status": "COHERENT", "lane_index": 1, "task_ids": ["T-2", "T-3"]},
            ],
            "lane_to_file_mapping": {0: ["src/x.py"]},
            "_design_lane_count": 2,
        }
        result = self._call(ctx)
        assert len(result["lane_details"]) == 2

    def test_lane_details_entry_structure(self) -> None:
        """Each lane_details entry must carry lane_index, task_ids, shared_files, status."""
        ctx: dict[str, Any] = {
            "lane_conflicts": [
                {"status": "WARNING", "lane_index": 0, "task_ids": ["T-1"]},
            ],
            "lane_to_file_mapping": {0: ["src/x.py"]},
            "_design_lane_count": 1,
        }
        result = self._call(ctx)
        detail = result["lane_details"][0]
        assert detail["lane_index"] == 0
        assert detail["task_ids"] == ["T-1"]
        assert detail["shared_files"] == ["src/x.py"]
        assert detail["status"] == "WARNING"

    def test_lane_details_skips_entries_without_lane_index(self) -> None:
        """Conflict entries missing lane_index are excluded from lane_details."""
        ctx: dict[str, Any] = {
            "lane_conflicts": [
                {"status": "COHERENT", "task_ids": ["T-1"]},  # no lane_index
                {"status": "COHERENT", "lane_index": 1, "task_ids": ["T-2"]},
            ],
            "_design_lane_count": 2,
        }
        result = self._call(ctx)
        # Only the entry with lane_index should appear
        assert len(result["lane_details"]) == 1
        assert result["lane_details"][0]["lane_index"] == 1

    def test_skipped_false_is_treated_as_normal_path(self) -> None:
        """Explicit False for _design_lane_computation_skipped is treated as normal."""
        ctx: dict[str, Any] = {
            "_design_lane_computation_skipped": False,
            "_design_lane_count": 1,
            "lane_conflicts": [{"status": "COHERENT", "lane_index": 0, "task_ids": []}],
        }
        result = self._call(ctx)
        assert result["total_lanes"] == 1
        assert "status" not in result  # normal path has no top-level status key

    def test_all_coherent_lanes(self) -> None:
        """All-COHERENT conflicts should produce 0 warning and conflicting counts."""
        ctx: dict[str, Any] = {
            "lane_conflicts": [
                {"status": "COHERENT", "lane_index": i, "task_ids": [f"T-{i}"]}
                for i in range(4)
            ],
            "_design_lane_count": 4,
        }
        result = self._call(ctx)
        assert result["coherent_lanes"] == 4
        assert result["warning_lanes"] == 0
        assert result["conflicting_lanes"] == 0


# ---------------------------------------------------------------------------
# TestCheckpointKeysInclusion — CCD checkpoint survival
# ---------------------------------------------------------------------------


class TestCheckpointKeysInclusion:
    """Tests for CCD checkpoint key additions."""

    @pytest.fixture(scope="class")
    def keys(self) -> frozenset[str]:
        from startd8.contractors.artisan_contractor import _CHECKPOINT_CONTEXT_KEYS

        return _CHECKPOINT_CONTEXT_KEYS

    def test_shared_file_manifest_in_keys(self, keys: frozenset[str]) -> None:
        """shared_file_manifest must survive checkpoint round-trips."""
        assert "shared_file_manifest" in keys

    def test_lane_conflicts_in_keys(self, keys: frozenset[str]) -> None:
        """lane_conflicts must survive checkpoint round-trips."""
        assert "lane_conflicts" in keys

    def test_design_lane_count_in_keys(self, keys: frozenset[str]) -> None:
        """_design_lane_count must survive checkpoint round-trips."""
        assert "_design_lane_count" in keys

    def test_lane_to_file_mapping_in_keys(self, keys: frozenset[str]) -> None:
        """lane_to_file_mapping must survive checkpoint round-trips."""
        assert "lane_to_file_mapping" in keys

    def test_design_lane_computation_skipped_in_keys(
        self, keys: frozenset[str]
    ) -> None:
        """_design_lane_computation_skipped flag must survive checkpoint round-trips."""
        assert "_design_lane_computation_skipped" in keys

    def test_design_mode_summary_in_keys(self, keys: frozenset[str]) -> None:
        """design_mode_summary must survive checkpoint round-trips (design→implement flow)."""
        assert "design_mode_summary" in keys

    def test_existing_keys_not_removed(self, keys: frozenset[str]) -> None:
        """Pre-CCD checkpoint keys must not have been accidentally dropped."""
        pre_ccd_keys = {
            "enriched_seed_path",
            "plan_title",
            "plan_goals",
            "domain_summary",
            "preflight_summary",
            "design_results",
            "truncation_flags",
            "_staging_dir",
        }
        missing = pre_ccd_keys - keys
        assert not missing, f"Pre-CCD keys removed from checkpoint: {missing}"

    def test_keys_is_frozenset(self) -> None:
        """_CHECKPOINT_CONTEXT_KEYS must be an immutable frozenset."""
        from startd8.contractors.artisan_contractor import _CHECKPOINT_CONTEXT_KEYS

        assert isinstance(_CHECKPOINT_CONTEXT_KEYS, frozenset)


# ---------------------------------------------------------------------------
# TestCCDDesignSpanAttrs — CCD-601/602
# ---------------------------------------------------------------------------


class TestCCDDesignSpanAttrs:
    """Tests for CCD-601/602 span attribute constant."""

    @pytest.fixture(scope="class")
    def attrs(self) -> frozenset[str]:
        from startd8.contractors.context_seed_handlers import _CCD_DESIGN_SPAN_ATTRS

        return _CCD_DESIGN_SPAN_ATTRS

    def test_all_expected_attrs_present(self, attrs: frozenset[str]) -> None:
        """All six canonical CCD span attributes must be present."""
        expected = {
            "task.lane_index",
            "task.lane_peer_count",
            "task.shared_file_count",
            "task.lane_prior_designs_count",
            "task.lane_prior_designs_truncated",
            "design.collision_severity",
        }
        assert attrs == expected

    def test_task_lane_index_present(self, attrs: frozenset[str]) -> None:
        """task.lane_index must be individually addressable by dashboard queries."""
        assert "task.lane_index" in attrs

    def test_task_lane_peer_count_present(self, attrs: frozenset[str]) -> None:
        """task.lane_peer_count must be present for cardinality-aware span annotation."""
        assert "task.lane_peer_count" in attrs

    def test_task_shared_file_count_present(self, attrs: frozenset[str]) -> None:
        """task.shared_file_count must be present for collision surface-area tracking."""
        assert "task.shared_file_count" in attrs

    def test_task_lane_prior_designs_count_present(self, attrs: frozenset[str]) -> None:
        """task.lane_prior_designs_count enables prior-context injection tracing."""
        assert "task.lane_prior_designs_count" in attrs

    def test_task_lane_prior_designs_truncated_present(
        self, attrs: frozenset[str]
    ) -> None:
        """task.lane_prior_designs_truncated flags prompt truncation events in traces."""
        assert "task.lane_prior_designs_truncated" in attrs

    def test_design_collision_severity_present(self, attrs: frozenset[str]) -> None:
        """design.collision_severity drives Gate 3b severity rollup dashboards."""
        assert "design.collision_severity" in attrs

    def test_is_frozenset(self, attrs: frozenset[str]) -> None:
        """_CCD_DESIGN_SPAN_ATTRS must be a frozenset to prevent accidental mutation."""
        from startd8.contractors.context_seed_handlers import _CCD_DESIGN_SPAN_ATTRS

        assert isinstance(_CCD_DESIGN_SPAN_ATTRS, frozenset)

    def test_no_unexpected_attrs(self, attrs: frozenset[str]) -> None:
        """No attributes beyond the six canonical ones should be present.

        Keeping the set tight prevents stale queries referencing retired attribute names.
        """
        expected = {
            "task.lane_index",
            "task.lane_peer_count",
            "task.shared_file_count",
            "task.lane_prior_designs_count",
            "task.lane_prior_designs_truncated",
            "design.collision_severity",
        }
        unexpected = attrs - expected
        assert not unexpected, f"Unexpected span attributes in constant: {unexpected}"

    def test_all_attrs_use_namespaced_keys(self, attrs: frozenset[str]) -> None:
        """All span attribute names must be dot-namespaced (OTel semantic convention)."""
        for attr in attrs:
            assert "." in attr, (
                f"Span attribute {attr!r} is not namespaced — must follow OTel "
                "semantic conventions (e.g. 'task.lane_index')"
            )
