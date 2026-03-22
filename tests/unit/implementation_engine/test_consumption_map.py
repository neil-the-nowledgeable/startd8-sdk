"""Tests for seed field consumption map (REQ-SU-201)."""

import json

from startd8.implementation_engine.consumption_map import (
    SEED_FIELD_CONSUMPTION_MAP,
    compute_seed_consumption_report,
)


class TestConsumptionMap:
    """Consumption map constant tests."""

    def test_map_contains_critical_fields(self):
        for field in ("target_files", "task_description", "depends_on"):
            assert field in SEED_FIELD_CONSUMPTION_MAP
            assert SEED_FIELD_CONSUMPTION_MAP[field]["impact"] == "critical"

    def test_map_has_minimum_field_count(self):
        assert len(SEED_FIELD_CONSUMPTION_MAP) >= 28

    def test_all_entries_have_required_keys(self):
        for name, meta in SEED_FIELD_CONSUMPTION_MAP.items():
            assert "consumer" in meta, f"{name} missing consumer"
            assert "impact" in meta, f"{name} missing impact"
            assert "notes" in meta, f"{name} missing notes"
            assert meta["impact"] in ("critical", "high", "medium", "low"), (
                f"{name} has invalid impact: {meta['impact']}"
            )


class TestComputeReport:
    """compute_seed_consumption_report tests."""

    def test_full_coverage(self):
        all_fields = set(SEED_FIELD_CONSUMPTION_MAP)
        report = compute_seed_consumption_report(all_fields)
        assert report["coverage_pct"] == 100.0
        assert report["missing_high_impact_fields"] == []
        assert report["unused_fields"] == []

    def test_missing_critical_fields(self):
        report = compute_seed_consumption_report(set())
        assert "target_files" in report["missing_high_impact_fields"]
        assert "task_description" in report["missing_high_impact_fields"]
        assert "depends_on" in report["missing_high_impact_fields"]

    def test_extra_fields_reported_as_unused(self):
        report = compute_seed_consumption_report({"unknown_field_xyz"})
        assert "unknown_field_xyz" in report["unused_fields"]

    def test_empty_seed(self):
        report = compute_seed_consumption_report(set())
        assert report["coverage_pct"] == 0.0
        assert report["present_count"] == 0

    def test_report_is_json_serializable(self):
        report = compute_seed_consumption_report({"target_files", "task_description"})
        json.dumps(report)  # should not raise
