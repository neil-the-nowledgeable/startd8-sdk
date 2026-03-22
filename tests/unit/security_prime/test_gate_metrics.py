"""Tests for security_prime.gate_metrics — Phases 1, 2, 4, 6."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock

import pytest

from startd8.security_prime.gate_metrics import (
    build_gate_verdict_report,
    build_owasp_section,
    compute_component_contributions,
    compute_hint_escalation_effectiveness,
    compute_prompt_effectiveness,
    compute_score_distribution,
    compute_threshold_sensitivity,
    determine_posture,
    write_gate_metrics_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    verdict: str = "pass",
    score: float = 1.0,
    findings_count: int = 0,
    finding_types: Dict[str, int] | None = None,
    finding_severities: List[str] | None = None,
    database: str = "postgresql",
    language: str = "python",
    timing_ms: float = 5.0,
    allowlisted: bool = False,
    file_path: str = "src/store.py",
) -> Dict[str, Any]:
    return {
        "file_path": file_path,
        "verdict": verdict,
        "score": score,
        "findings_count": findings_count,
        "finding_types": finding_types or {},
        "finding_severities": finding_severities or [],
        "database": database,
        "language": language,
        "timing_ms": timing_ms,
        "allowlisted": allowlisted,
    }


# ===========================================================================
# L1: Gate verdict report
# ===========================================================================


class TestBuildGateVerdictReport:
    def test_empty_results(self):
        report = build_gate_verdict_report([], "run-001")
        assert report["schema_version"] == "1.0.0"
        assert report["files_checked"] == 0
        assert report["files_total"] == 0
        assert report["aggregate_score"] == 1.0
        assert report["gate_pass_rate"] == 1.0
        assert report["posture"]["level"] == "clean"
        assert report["security_posture"] == "CLEAN"

    def test_all_pass(self):
        entries = [_make_entry(), _make_entry(file_path="src/db.py")]
        report = build_gate_verdict_report(entries, "run-002")
        assert report["files_checked"] == 2
        assert report["files_total"] == 2
        assert report["aggregate_score"] == 1.0
        assert report["gate_pass_rate"] == 1.0
        assert report["verdict_counts"]["pass"] == 2

    def test_mixed_verdicts(self):
        entries = [
            _make_entry(verdict="pass", score=1.0),
            _make_entry(verdict="fail", score=0.0, findings_count=2,
                        finding_types={"injection": 2}),
            _make_entry(verdict="warn", score=0.7, findings_count=1,
                        finding_types={"lifecycle": 1}),
        ]
        report = build_gate_verdict_report(entries, "run-003")
        assert report["verdict_counts"] == {"pass": 1, "warn": 1, "fail": 1}
        assert report["aggregate_score"] == 0.0
        assert report["total_findings"] == 3
        assert report["findings_by_type"]["injection"] == 2
        assert report["posture"]["level"] == "critical"

    def test_timing_aggregated(self):
        entries = [
            _make_entry(timing_ms=10.0),
            _make_entry(timing_ms=20.0, file_path="src/b.py"),
        ]
        report = build_gate_verdict_report(entries, "run-004")
        assert report["total_timing_ms"] == 30.0

    def test_databases_and_languages_seen(self):
        entries = [
            _make_entry(database="postgresql", language="python"),
            _make_entry(database="spanner", language="csharp",
                        file_path="src/b.cs"),
        ]
        report = build_gate_verdict_report(entries, "run-005")
        assert "postgresql" in report["databases_seen"]
        assert "spanner" in report["databases_seen"]
        assert "python" in report["languages_seen"]

    def test_optional_sections(self):
        report = build_gate_verdict_report(
            [_make_entry()], "run-006",
            allowlist_metrics={"total": 1},
            owasp_data={"coverage": 0.4},
            score_distribution={"mean": 1.0},
            prompt_effectiveness={"p0": {}},
        )
        assert "allowlist" in report
        assert "owasp_coverage" in report
        assert "score_distribution" in report
        assert "prompt_effectiveness" in report

    def test_per_file_items(self):
        entries = [_make_entry(score=0.85)]
        report = build_gate_verdict_report(entries, "run-007")
        assert len(report["items"]) == 1
        assert report["items"][0]["score"] == 0.85


class TestDeterminePosture:
    def test_clean(self):
        p = determine_posture({"pass": 5, "warn": 0, "fail": 0}, 1.0)
        assert p["level"] == "clean"
        assert "rules" in p
        assert "interpretation" in p
        assert "All gated files passed" in p["interpretation"]

    def test_degraded_from_warn(self):
        p = determine_posture({"pass": 4, "warn": 1, "fail": 0}, 0.8, total_files=5)
        assert p["level"] == "degraded"
        assert "rules" in p
        assert "1 file(s) have warnings" in p["interpretation"]
        assert "4 of 5" in p["interpretation"]

    def test_critical_from_fail(self):
        p = determine_posture({"pass": 3, "warn": 0, "fail": 2}, 0.6, total_files=5)
        assert p["level"] == "critical"
        assert "2 file(s) failed" in p["interpretation"]
        assert "3 of 5" in p["interpretation"]

    def test_posture_rules_always_present(self):
        for verdicts, rate in [
            ({"pass": 5, "warn": 0, "fail": 0}, 1.0),
            ({"pass": 4, "warn": 1, "fail": 0}, 0.8),
            ({"pass": 3, "warn": 0, "fail": 2}, 0.6),
        ]:
            p = determine_posture(verdicts, rate)
            assert "clean" in p["rules"]
            assert "degraded" in p["rules"]
            assert "critical" in p["rules"]


class TestWriteGateMetricsReport:
    def test_writes_json_file(self, tmp_path):
        report = {"run_id": "test", "items": []}
        write_gate_metrics_report(report, str(tmp_path))
        path = tmp_path / "security-gate-metrics.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["run_id"] == "test"

    def test_handles_oserror(self, tmp_path):
        """Advisory write should not raise on permission errors."""
        report = {"run_id": "test"}
        # Write to non-existent nested path — should create dirs
        nested = tmp_path / "a" / "b"
        write_gate_metrics_report(report, str(nested))
        assert (nested / "security-gate-metrics.json").exists()


# ===========================================================================
# L6: OWASP coverage
# ===========================================================================


class TestBuildOwaspSection:
    def test_no_checks_ran(self):
        result = build_owasp_section()
        assert result["coverage_percentage"] == 0.0
        assert result["categories_total"] == 10

    def test_partial_coverage(self):
        result = build_owasp_section(
            checks_that_ran={"injection", "credential_leakage", "lifecycle"},
            findings_by_check={"injection": 2},
        )
        # A03 (injection) + A02 (credential) + A05 (lifecycle) + A09 (credential) = 4 covered
        assert result["categories_covered"] == 4
        assert result["coverage_percentage"] == pytest.approx(0.4)

    def test_gaps_sorted_by_impact(self):
        result = build_owasp_section(checks_that_ran=set())
        gaps = result["gaps"]
        # High impact gaps should come first
        impacts = [g["impact"] for g in gaps]
        order = {"high": 0, "medium": 1, "low": 2}
        for i in range(len(impacts) - 1):
            assert order[impacts[i]] <= order[impacts[i + 1]]

    def test_full_coverage(self):
        # All implemented checks run
        all_checks = {"injection", "credential_leakage", "lifecycle"}
        result = build_owasp_section(checks_that_ran=all_checks)
        assert result["categories_covered"] == 4  # Only 4/10 have checks implemented

    def test_findings_by_check(self):
        result = build_owasp_section(
            checks_that_ran={"injection"},
            findings_by_check={"injection": 5},
        )
        a03 = next(c for c in result["categories"] if c["category"] == "A03:2021")
        assert a03["findings"] == 5


# ===========================================================================
# L2: Score distribution
# ===========================================================================


class TestComputeScoreDistribution:
    def test_empty(self):
        d = compute_score_distribution([])
        assert d["count"] == 0
        assert d["mean"] is None

    def test_single_score(self):
        d = compute_score_distribution([0.85])
        assert d["count"] == 1
        assert d["mean"] == 0.85
        assert d["std_dev"] == 0.0

    def test_bimodal(self):
        scores = [0.0, 0.0, 1.0, 1.0]
        d = compute_score_distribution(scores)
        assert d["min"] == 0.0
        assert d["max"] == 1.0
        assert d["mean"] == 0.5
        assert d["count"] == 4

    def test_threshold_counts(self):
        scores = [0.4, 0.6, 0.8, 0.95]
        d = compute_score_distribution(scores)
        assert d["threshold_counts"]["0.5"]["above"] == 3
        assert d["threshold_counts"]["0.5"]["below"] == 1
        assert d["threshold_counts"]["0.9"]["above"] == 1

    def test_shape_bimodal(self):
        scores = [0.0, 0.0, 1.0, 1.0]
        d = compute_score_distribution(scores)
        assert d["shape"] == "bimodal"

    def test_shape_clustered_high(self):
        scores = [0.90, 0.95, 1.0, 0.92]
        d = compute_score_distribution(scores)
        assert d["shape"] == "clustered_high"

    def test_shape_clustered_low(self):
        scores = [0.1, 0.2, 0.3, 0.4]
        d = compute_score_distribution(scores)
        assert d["shape"] == "clustered_low"

    def test_shape_insufficient_data(self):
        d = compute_score_distribution([0.5])
        assert d["shape"] == "insufficient_data"


class TestComputeThresholdSensitivity:
    def test_no_findings(self):
        entries = [_make_entry(score=0.9), _make_entry(score=1.0, file_path="b.py")]
        result = compute_threshold_sensitivity(entries, thresholds=[0.8])
        assert result[0]["fp_count"] == 0
        assert result[0]["fn_count"] == 0

    def test_false_positive(self):
        # Score < threshold but no hard findings
        entries = [
            _make_entry(score=0.6, finding_types={"lifecycle": 1}),
        ]
        result = compute_threshold_sensitivity(entries, thresholds=[0.7])
        assert result[0]["fp_count"] == 1

    def test_false_negative(self):
        # Score >= threshold but has injection
        entries = [
            _make_entry(score=0.9, finding_types={"injection": 1}),
        ]
        result = compute_threshold_sensitivity(entries, thresholds=[0.8])
        assert result[0]["fn_count"] == 1

    def test_default_thresholds(self):
        result = compute_threshold_sensitivity([_make_entry()])
        assert len(result) == 5  # [0.50, 0.60, 0.70, 0.80, 0.90]

    def test_files_passing_failing(self):
        entries = [
            _make_entry(score=0.9),
            _make_entry(score=0.5, file_path="b.py"),
        ]
        result = compute_threshold_sensitivity(entries, thresholds=[0.7])
        assert result[0]["files_passing"] == 1
        assert result[0]["files_failing"] == 1


class TestComputeComponentContributions:
    def test_no_failed_files(self):
        entries = [_make_entry(score=1.0)]
        result = compute_component_contributions(entries)
        assert result == []

    def test_failed_with_severities(self):
        entries = [
            _make_entry(
                score=0.5,
                finding_severities=["error", "warning"],
            ),
        ]
        result = compute_component_contributions(entries)
        assert len(result) == 1
        assert result[0]["file_path"] == "src/store.py"
        assert len(result[0]["breakdown"]) == 2

    def test_failed_without_severities(self):
        entries = [_make_entry(score=0.0)]
        result = compute_component_contributions(entries)
        assert len(result) == 1
        assert result[0]["breakdown"] == []
        assert result[0]["short_circuit_applied"] is False

    def test_short_circuit_on_injection(self):
        entries = [
            _make_entry(
                score=0.0,
                finding_types={"injection": 1},
                finding_severities=["error"],
            ),
        ]
        result = compute_component_contributions(entries)
        assert len(result) == 1
        assert result[0]["short_circuit_applied"] is True
        assert "injection" in result[0]["short_circuit_reason"]


# ===========================================================================
# L5: Prompt effectiveness
# ===========================================================================


class TestComputePromptEffectiveness:
    def test_baseline_no_injection(self):
        entries = [_make_entry()]
        result = compute_prompt_effectiveness(entries)
        assert result["p0"]["correlation"] == "baseline"
        # 0 security_sensitive_tasks < 5 → insufficient_data
        assert result["p1"]["value_signal"] == "insufficient_data"

    def test_p1_neutral(self):
        entries = [_make_entry() for _ in range(5)]
        result = compute_prompt_effectiveness(
            entries, security_sensitive_tasks=5, p1_databases=[],
        )
        assert result["p1"]["value_signal"] == "neutral"

    def test_p0_positive(self):
        entries = [_make_entry(), _make_entry(file_path="b.py")]
        result = compute_prompt_effectiveness(entries, p0_injected=True)
        assert result["p0"]["correlation"] == "positive"

    def test_p0_weak(self):
        entries = [
            _make_entry(
                verdict="fail", finding_types={"injection": 1},
            ),
        ]
        result = compute_prompt_effectiveness(entries, p0_injected=True)
        assert result["p0"]["correlation"] == "weak"

    def test_p1_insufficient_data(self):
        entries = [_make_entry()]
        result = compute_prompt_effectiveness(
            entries, security_sensitive_tasks=3, p1_databases=["postgresql"],
        )
        assert result["p1"]["value_signal"] == "insufficient_data"

    def test_p1_positive(self):
        entries = [_make_entry() for _ in range(5)]
        result = compute_prompt_effectiveness(
            entries, security_sensitive_tasks=5, p1_databases=["postgresql"],
        )
        assert result["p1"]["value_signal"] == "positive"

    def test_p1_negative(self):
        entries = [
            _make_entry(finding_types={"injection": 1}),
        ] * 5
        result = compute_prompt_effectiveness(
            entries, security_sensitive_tasks=5, p1_databases=["postgresql"],
        )
        assert result["p1"]["value_signal"] == "negative"


class TestComputeHintEscalationEffectiveness:
    def test_clean_run_no_history(self, tmp_path):
        result = compute_hint_escalation_effectiveness(
            str(tmp_path), current_injection_found=False,
        )
        assert result["effectiveness"] == "positive"
        assert result["escalation_level"] == "guidance"
        assert result["current_consecutive_runs"] == 0

    def test_first_injection(self, tmp_path):
        result = compute_hint_escalation_effectiveness(
            str(tmp_path), current_injection_found=True,
        )
        assert result["current_consecutive_runs"] == 1
        assert result["escalation_level"] == "guidance"
        assert result["effectiveness"] == "neutral"

    def test_resolved_after_escalation(self, tmp_path):
        # Simulate prior consecutive runs
        metrics = {"security": {"consecutive_injection_runs": 2}}
        (tmp_path / "kaizen-metrics.json").write_text(json.dumps(metrics))
        result = compute_hint_escalation_effectiveness(
            str(tmp_path), current_injection_found=False,
        )
        assert result["prior_consecutive_runs"] == 2
        assert result["effectiveness"] == "positive"

    def test_persists_at_critical(self, tmp_path):
        metrics = {"security": {"consecutive_injection_runs": 3}}
        (tmp_path / "kaizen-metrics.json").write_text(json.dumps(metrics))
        result = compute_hint_escalation_effectiveness(
            str(tmp_path), current_injection_found=True,
        )
        assert result["current_consecutive_runs"] == 4
        assert result["escalation_level"] == "critical"
        assert result["effectiveness"] == "negative"
        assert "interpretation" in result
        assert "persists" in result["interpretation"].lower()

    def test_interpretation_clean(self, tmp_path):
        result = compute_hint_escalation_effectiveness(
            str(tmp_path), current_injection_found=False,
        )
        assert "clean run" in result["interpretation"].lower()

    def test_interpretation_resolved(self, tmp_path):
        metrics = {"security": {"consecutive_injection_runs": 2}}
        (tmp_path / "kaizen-metrics.json").write_text(json.dumps(metrics))
        result = compute_hint_escalation_effectiveness(
            str(tmp_path), current_injection_found=False,
        )
        assert "resolved" in result["interpretation"].lower()
