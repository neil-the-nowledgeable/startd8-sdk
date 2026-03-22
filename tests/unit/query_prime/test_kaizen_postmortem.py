"""Tests for Query Prime Kaizen integration — Phases 0 + 3.

Phase 0: CAUSE_TO_SUGGESTION entries in prime_postmortem.py.
Phase 3: query_security key in kaizen-metrics.json via security_prime/kaizen.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.contractors.prime_postmortem import (
    CAUSE_TO_SUGGESTION,
    _SEMANTIC_CATEGORY_TO_SUGGESTION,
)
from startd8.security_prime.kaizen import update_query_security_metrics


# ---------------------------------------------------------------------------
# Phase 0: CAUSE_TO_SUGGESTION entries
# ---------------------------------------------------------------------------


class TestQueryPrimeSuggestionEntries:
    """Verify all Query Prime entries exist in CAUSE_TO_SUGGESTION."""

    EXPECTED_KEYS = [
        "query_injection_interpolation",
        "query_injection_concatenation",
        "query_credential_logged",
        "query_credential_exposed",
        "query_lifecycle_per_request",
        "query_lifecycle_no_dispose",
        "query_t3_insufficient",
        "sql_injection_detected",  # Pre-existing
    ]

    @pytest.mark.parametrize("key", EXPECTED_KEYS)
    def test_entry_exists(self, key: str):
        assert key in CAUSE_TO_SUGGESTION

    @pytest.mark.parametrize("key", EXPECTED_KEYS)
    def test_entry_has_phase(self, key: str):
        assert "phase" in CAUSE_TO_SUGGESTION[key]
        assert CAUSE_TO_SUGGESTION[key]["phase"] in ("spec", "draft")

    @pytest.mark.parametrize("key", EXPECTED_KEYS)
    def test_entry_has_hint(self, key: str):
        assert "hint" in CAUSE_TO_SUGGESTION[key]
        assert len(CAUSE_TO_SUGGESTION[key]["hint"]) > 10

    def test_injection_entries_have_confidence(self):
        for key in ["query_injection_interpolation", "query_injection_concatenation"]:
            assert CAUSE_TO_SUGGESTION[key].get("confidence", 0) >= 0.9

    def test_credential_entries_have_confidence(self):
        for key in ["query_credential_logged", "query_credential_exposed"]:
            assert CAUSE_TO_SUGGESTION[key].get("confidence", 0) >= 0.8

    def test_lifecycle_entries_have_confidence(self):
        for key in ["query_lifecycle_per_request", "query_lifecycle_no_dispose"]:
            assert CAUSE_TO_SUGGESTION[key].get("confidence", 0) >= 0.7

    def test_t3_insufficient_targets_spec_phase(self):
        assert CAUSE_TO_SUGGESTION["query_t3_insufficient"]["phase"] == "spec"


class TestSemanticCategoryMapping:
    """Verify _SEMANTIC_CATEGORY_TO_SUGGESTION mappings."""

    def test_injection_mapped(self):
        assert "query_security_injection" in _SEMANTIC_CATEGORY_TO_SUGGESTION

    def test_credential_mapped(self):
        assert "query_security_credential_leakage" in _SEMANTIC_CATEGORY_TO_SUGGESTION

    def test_lifecycle_mapped(self):
        assert "query_security_lifecycle" in _SEMANTIC_CATEGORY_TO_SUGGESTION

    def test_all_targets_exist_in_cause_to_suggestion(self):
        for category, target in _SEMANTIC_CATEGORY_TO_SUGGESTION.items():
            assert target in CAUSE_TO_SUGGESTION, (
                f"Category {category} maps to {target} which is missing"
            )


# ---------------------------------------------------------------------------
# Phase 3: query_security metrics in kaizen-metrics.json
# ---------------------------------------------------------------------------


class TestUpdateQuerySecurityMetrics:
    """Tests for update_query_security_metrics."""

    def test_writes_query_security_key(self, tmp_path: Path):
        report = {
            "mean_score": 0.85,
            "pass_rate": 0.90,
            "total_work_items": 10,
            "total_cost_usd": 0.05,
            "injection_total": 1,
            "credential_total": 0,
            "lifecycle_total": 2,
            "by_database": {"postgresql": {"count": 10, "mean_score": 0.85}},
            "by_tier": {"simple": {"count": 8, "mean_score": 0.9}},
        }
        update_query_security_metrics(str(tmp_path), report)

        metrics = json.loads((tmp_path / "kaizen-metrics.json").read_text())
        assert "query_security" in metrics
        assert metrics["query_security"]["mean_score"] == 0.85
        assert metrics["query_security"]["injection_total"] == 1

    def test_preserves_existing_security_key(self, tmp_path: Path):
        # Write existing security key
        existing = {"security": {"injection_blocked": 5, "aggregate_score": 0.7}}
        (tmp_path / "kaizen-metrics.json").write_text(json.dumps(existing))

        report = {"mean_score": 0.9, "pass_rate": 1.0}
        update_query_security_metrics(str(tmp_path), report)

        metrics = json.loads((tmp_path / "kaizen-metrics.json").read_text())
        assert "security" in metrics
        assert metrics["security"]["injection_blocked"] == 5
        assert "query_security" in metrics

    def test_preserves_other_keys(self, tmp_path: Path):
        existing = {"success_rate": 0.95, "cost": 1.23}
        (tmp_path / "kaizen-metrics.json").write_text(json.dumps(existing))

        update_query_security_metrics(str(tmp_path), {"mean_score": 0.8})

        metrics = json.loads((tmp_path / "kaizen-metrics.json").read_text())
        assert metrics["success_rate"] == 0.95
        assert metrics["cost"] == 1.23
        assert "query_security" in metrics

    def test_creates_file_if_missing(self, tmp_path: Path):
        update_query_security_metrics(str(tmp_path), {"mean_score": 0.5})
        assert (tmp_path / "kaizen-metrics.json").is_file()

    def test_handles_corrupt_existing_file(self, tmp_path: Path):
        (tmp_path / "kaizen-metrics.json").write_text("not json")
        update_query_security_metrics(str(tmp_path), {"mean_score": 0.5})
        metrics = json.loads((tmp_path / "kaizen-metrics.json").read_text())
        assert "query_security" in metrics
