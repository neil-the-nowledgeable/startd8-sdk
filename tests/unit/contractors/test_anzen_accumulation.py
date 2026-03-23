"""Tests for REQ-QPA-500: cross-feature Anzen gate metric accumulation.

Verifies that finalize_anzen_metrics() aggregates entries from multiple
features rather than overwriting with the last feature's results.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from startd8.contractors.integration_engine import IntegrationEngine


def _make_engine(tmp_path: Path) -> IntegrationEngine:
    """Create a minimal IntegrationEngine with a temp project root."""
    merge = MagicMock()
    return IntegrationEngine(
        project_root=tmp_path,
        merge_strategy=merge,
    )


def _make_entry(
    file_path: str,
    database: str,
    score: float = 1.0,
    injection: int = 0,
    credential: int = 0,
    lifecycle: int = 0,
    verdict: str = "pass",
) -> dict:
    """Build a minimal enriched_entry dict matching Anzen gate output."""
    return {
        "file_path": file_path,
        "database": database,
        "score": score,
        "verdict": verdict,
        "finding_types": {
            "injection": injection,
            "credential_leakage": credential,
            "lifecycle": lifecycle,
        },
        "findings": [],
    }


@pytest.mark.unit
class TestAnzenAccumulation:
    """REQ-QPA-500: Cross-feature metric accumulation."""

    def test_accumulate_across_features(self, tmp_path: Path):
        """3 features (DB, no-DB, DB) → final metrics include both DB features."""
        engine = _make_engine(tmp_path)

        # Feature 1: AlloyDB store — 2 injection findings
        engine._anzen_gate_entries.extend([
            _make_entry("AlloyDBCartStore.cs", "postgresql", score=0.6, injection=2),
        ])
        # Feature 2: CartService.cs — no DB surface → no entries added
        # (nothing appended to _anzen_gate_entries)

        # Feature 3: SpannerCartStore.cs — 1 credential finding
        engine._anzen_gate_entries.extend([
            _make_entry("SpannerCartStore.cs", "spanner", score=0.9, credential=1),
        ])

        report = engine.finalize_anzen_metrics(str(tmp_path), "run-test")

        assert report["total_work_items"] == 2
        assert report["injection_total"] == 2
        assert report["credential_total"] == 1
        assert "postgresql" in report["by_database"]
        assert "spanner" in report["by_database"]
        assert report["status"] == "fail"  # has injections

        # Verify file was written
        qp_path = tmp_path / "query-security-metrics.json"
        assert qp_path.exists()
        written = json.loads(qp_path.read_text())
        assert written["total_work_items"] == 2
        assert written["run_id"] == "run-test"

    def test_empty_run_writes_sentinel(self, tmp_path: Path):
        """3 non-DB features → writes no_queries_detected once."""
        engine = _make_engine(tmp_path)
        # No entries added (all features had no DB surface)

        report = engine.finalize_anzen_metrics(str(tmp_path), "run-empty")

        assert report["status"] == "no_queries_detected"
        assert report["total_work_items"] == 0
        assert report["by_database"] == {}

        qp_path = tmp_path / "query-security-metrics.json"
        assert qp_path.exists()
        written = json.loads(qp_path.read_text())
        assert written["status"] == "no_queries_detected"

    def test_aggregates_by_database(self, tmp_path: Path):
        """Features with different databases → by_database has all entries."""
        engine = _make_engine(tmp_path)
        engine._anzen_gate_entries.extend([
            _make_entry("Redis.cs", "redis", score=1.0),
            _make_entry("Spanner.cs", "spanner", score=0.8, credential=1),
            _make_entry("Alloy1.cs", "postgresql", score=0.5, injection=1),
            _make_entry("Alloy2.cs", "postgresql", score=0.7, injection=1),
        ])

        report = engine.finalize_anzen_metrics(str(tmp_path), "run-multi")

        assert len(report["by_database"]) == 3
        assert report["by_database"]["postgresql"]["count"] == 2
        assert report["by_database"]["redis"]["count"] == 1
        assert report["by_database"]["spanner"]["count"] == 1
        assert report["total_work_items"] == 4
        assert report["injection_total"] == 2
        assert report["credential_total"] == 1

    def test_mean_score_computed_correctly(self, tmp_path: Path):
        """Verify mean_score is the average of all entry scores."""
        engine = _make_engine(tmp_path)
        engine._anzen_gate_entries.extend([
            _make_entry("A.cs", "postgresql", score=0.8),
            _make_entry("B.cs", "postgresql", score=0.6),
        ])

        report = engine.finalize_anzen_metrics(str(tmp_path), "run-score")

        assert report["mean_score"] == 0.7
        assert report["pass_rate"] == 0.5  # 1 of 2 >= 0.8

    def test_parameterization_rate(self, tmp_path: Path):
        """Parameterization rate = 1 - injection_total/work_items."""
        engine = _make_engine(tmp_path)
        engine._anzen_gate_entries.extend([
            _make_entry("A.cs", "postgresql", injection=1),
            _make_entry("B.cs", "postgresql", injection=0),
            _make_entry("C.cs", "spanner", injection=0),
            _make_entry("D.cs", "redis", injection=1),
        ])

        report = engine.finalize_anzen_metrics(str(tmp_path), "run-param")

        assert report["parameterization_rate"] == 0.5  # 2 of 4 clean

    def test_no_overwrite_on_subsequent_finalize(self, tmp_path: Path):
        """Calling finalize twice doesn't corrupt — entries are already consumed."""
        engine = _make_engine(tmp_path)
        engine._anzen_gate_entries.extend([
            _make_entry("A.cs", "postgresql", injection=1),
        ])

        r1 = engine.finalize_anzen_metrics(str(tmp_path), "run-1")
        r2 = engine.finalize_anzen_metrics(str(tmp_path), "run-2")

        # Both calls see the same accumulated entries
        assert r1["total_work_items"] == 1
        assert r2["total_work_items"] == 1
