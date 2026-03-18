"""Tests for exemplar extraction from run directories (REQ-PEP-000)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.exemplars.extractor import extract_exemplars_from_run
from startd8.exemplars.registry import ExemplarRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_run_dir(tmp_path: Path, run_id: str = "run-001") -> Path:
    """Create a mock run directory with postmortem and seed."""
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)

    # Write postmortem
    postmortem = {
        "report_id": "pm-001",
        "timestamp": "2026-03-18T12:00:00Z",
        "features": [
            {
                "feature_id": "PI-001",
                "name": "AdService",
                "status": "completed",
                "success": True,
                "requirement_score": 1.0,
                "disk_quality_score": 1.0,
                "assembly_delta": 0.0,
                "semantic_error_count": 0,
                "verdict": "PASS",
                "cost_usd": 0.15,
                "target_files": ["src/main/java/AdService.java"],
                "generated_files": ["generated/src/main/java/AdService.java"],
            },
            {
                "feature_id": "PI-002",
                "name": "FailedFeature",
                "status": "failed",
                "success": False,
                "requirement_score": 0.5,
                "disk_quality_score": 0.3,
                "verdict": "FAIL",
                "cost_usd": 0.20,
                "target_files": ["src/main/java/Client.java"],
                "generated_files": [],
            },
        ],
    }
    (run_dir / "prime-postmortem-report.json").write_text(
        json.dumps(postmortem), encoding="utf-8",
    )

    # Write seed
    seed = {
        "tasks": [
            {
                "task_id": "PI-001",
                "feature_id": "PI-001",
                "language": "java",
                "protocol": "grpc",
                "config": {
                    "context": {
                        "service_metadata": {"transport_protocol": "grpc"},
                    },
                    "forward_manifest": {"elements": ["AdService"]},
                },
            },
        ],
    }
    (run_dir / "prime-context-seed.json").write_text(
        json.dumps(seed), encoding="utf-8",
    )

    # Create a mock generated file
    gen_dir = run_dir / "generated" / "src" / "main" / "java"
    gen_dir.mkdir(parents=True)
    (gen_dir / "AdService.java").write_text(
        "package hipstershop;\n\npublic class AdService {\n  // code\n}\n",
        encoding="utf-8",
    )

    return run_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractExemplarsFromRun:
    """REQ-PEP-000: Extract from successful runs."""

    def test_extracts_passing_features(self, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        entries = extract_exemplars_from_run(run_dir)
        assert len(entries) == 1
        assert entries[0].source_feature_id == "PI-001"

    def test_skips_failing_features(self, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        entries = extract_exemplars_from_run(run_dir)
        feature_ids = {e.source_feature_id for e in entries}
        assert "PI-002" not in feature_ids

    def test_sets_maturity_to_validated(self, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        entries = extract_exemplars_from_run(run_dir)
        assert entries[0].maturity == 1

    def test_fingerprint_computed(self, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        entries = extract_exemplars_from_run(run_dir)
        fp = entries[0].fingerprint
        assert fp.language == "java"
        assert fp.transport == "grpc"
        assert fp.file_type == "source"

    def test_scores_captured(self, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        entries = extract_exemplars_from_run(run_dir)
        assert entries[0].scores.requirement_score == 1.0
        assert entries[0].scores.cost_usd == 0.15

    def test_code_summary_populated(self, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        entries = extract_exemplars_from_run(run_dir)
        assert "AdService" in entries[0].code_summary

    def test_adds_to_registry(self, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        reg = ExemplarRegistry(project_id="test")
        extract_exemplars_from_run(run_dir, registry=reg)
        assert len(reg) == 1

    def test_returns_empty_for_missing_postmortem(self, tmp_path):
        empty_dir = tmp_path / "run-empty"
        empty_dir.mkdir()
        entries = extract_exemplars_from_run(empty_dir)
        assert entries == []

    def test_returns_empty_for_no_passing_features(self, tmp_path):
        run_dir = tmp_path / "run-fail"
        run_dir.mkdir()
        postmortem = {
            "features": [
                {
                    "feature_id": "F-1",
                    "requirement_score": 0.5,
                    "verdict": "FAIL",
                    "target_files": ["f.py"],
                },
            ],
        }
        (run_dir / "prime-postmortem-report.json").write_text(
            json.dumps(postmortem), encoding="utf-8",
        )
        entries = extract_exemplars_from_run(run_dir)
        assert entries == []

    def test_custom_min_score(self, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        # Lower threshold to include 0.5-scoring features
        entries = extract_exemplars_from_run(
            run_dir, min_requirement_score=0.4,
        )
        # PI-002 has req_score=0.5 but verdict=FAIL, so still excluded
        assert len(entries) == 1

    def test_exemplar_id_format(self, tmp_path):
        run_dir = _make_run_dir(tmp_path)
        entries = extract_exemplars_from_run(run_dir)
        assert entries[0].id.startswith("ex-")
        assert "run-001" in entries[0].id


class TestExtractorMultipleRuns:
    """Multiple runs → maturity promotion."""

    def test_two_runs_promote_to_confirmed(self, tmp_path):
        reg = ExemplarRegistry()

        run1 = _make_run_dir(tmp_path, "run-001")
        extract_exemplars_from_run(run1, registry=reg)

        run2 = _make_run_dir(tmp_path, "run-002")
        extract_exemplars_from_run(run2, registry=reg)

        promotions = reg.promote_maturity()
        assert len(promotions) == 2
        assert all(p["new_level"] == 2 for p in promotions)
