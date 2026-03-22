"""Tests for security_prime.gate_models — Pydantic v2 gate verdict report models."""

from __future__ import annotations

import json

import pytest

from startd8.security_prime.gate_models import (
    GateFileEntry,
    GateFinding,
    GateVerdictReport,
    PostureResult,
    skipped_report,
)


class TestDefaultReport:
    """test_default_report — construct with just run_id + timestamp, verify defaults."""

    def test_default_report(self):
        report = GateVerdictReport(run_id="run-001", timestamp="2026-03-21T00:00:00Z")

        assert report.run_id == "run-001"
        assert report.timestamp == "2026-03-21T00:00:00Z"
        assert report.schema_version == "1.0.0"
        assert report.status == "completed"
        assert report.files_checked == 0
        assert report.files_skipped == 0
        assert report.files_total == 0
        assert report.aggregate_score == 1.0
        assert report.mean_score == 1.0
        assert report.gate_pass_rate == 1.0
        assert report.security_posture == "CLEAN"
        assert report.total_findings == 0
        assert report.findings_by_type == {}
        assert report.verdict_counts == {"pass": 0, "warn": 0, "fail": 0}
        assert report.databases_seen == []
        assert report.languages_seen == []
        assert report.total_timing_ms == 0.0
        assert report.posture.level == "clean"
        assert report.posture.reason == "No files checked"
        assert report.items == []
        # Optional sections default to None
        assert report.allowlist is None
        assert report.owasp_coverage is None
        assert report.score_distribution is None
        assert report.prompt_effectiveness is None
        assert report.threshold_sensitivity is None
        assert report.component_contributions is None


class TestFullReportRoundtrip:
    """test_full_report_roundtrip — construct with all fields, model_dump(), verify JSON-serializable."""

    def test_full_report_roundtrip(self):
        finding = GateFinding(
            check_type="injection",
            severity="error",
            message="SQL injection detected",
            line=42,
            pattern_hash="abc123",
        )
        file_entry = GateFileEntry(
            file_path="src/app.py",
            verdict="fail",
            score=0.0,
            findings_count=1,
            finding_types={"injection": 1},
            finding_severities=["error"],
            findings=[finding],
            database="postgresql",
            language="python",
            timing_ms=12.5,
            allowlisted=False,
            security_sensitive=True,
            prompt_security_features={"p0_injected": True},
        )
        posture = PostureResult(
            level="critical",
            reason="1 file(s) failed the Anzen gate",
            rules={"critical": "Any FAIL verdict"},
            interpretation="1 file(s) failed.",
        )
        report = GateVerdictReport(
            run_id="run-full",
            timestamp="2026-03-21T12:00:00Z",
            files_checked=1,
            files_skipped=0,
            files_total=1,
            aggregate_score=0.0,
            mean_score=0.0,
            gate_pass_rate=0.0,
            security_posture="CRITICAL",
            total_findings=1,
            findings_by_type={"injection": 1},
            verdict_counts={"pass": 0, "warn": 0, "fail": 1},
            databases_seen=["postgresql"],
            languages_seen=["python"],
            total_timing_ms=12.5,
            posture=posture,
            items=[file_entry],
            allowlist={"total_entries": 0},
            owasp_coverage={"coverage_percentage": 0.3},
            score_distribution={"min": 0.0, "max": 0.0},
            prompt_effectiveness={"p0": {"injected": True}},
            threshold_sensitivity=[{"threshold": 0.7, "fp_count": 0}],
            component_contributions=[{"file_path": "src/app.py", "score": 0.0}],
        )

        dumped = report.model_dump()
        # Verify JSON serializable
        json_str = json.dumps(dumped, default=str)
        parsed = json.loads(json_str)

        assert parsed["run_id"] == "run-full"
        assert parsed["items"][0]["file_path"] == "src/app.py"
        assert parsed["items"][0]["findings"][0]["check_type"] == "injection"
        assert parsed["posture"]["level"] == "critical"

        # Roundtrip: reconstruct from dumped dict
        reconstructed = GateVerdictReport(**dumped)
        assert reconstructed.run_id == report.run_id
        assert reconstructed.aggregate_score == report.aggregate_score
        assert len(reconstructed.items) == 1
        assert reconstructed.items[0].findings[0].check_type == "injection"


class TestSkippedReport:
    """test_skipped_report — verify skipped_report() produces status='skipped'."""

    def test_skipped_report_defaults(self):
        report = skipped_report()
        assert report.status == "skipped"
        assert report.run_id == "unknown"
        assert report.security_posture == "SKIPPED"
        assert report.posture.level == "skipped"
        assert report.posture.reason == "Security Prime was not active (query_prime not available)"
        assert report.timestamp  # non-empty

    def test_skipped_report_with_args(self):
        report = skipped_report(run_id="run-skip", timestamp="2026-01-01T00:00:00Z")
        assert report.run_id == "run-skip"
        assert report.timestamp == "2026-01-01T00:00:00Z"
        assert report.status == "skipped"


class TestFileEntryWithFindings:
    """test_file_entry_with_findings — GateFileEntry with GateFinding list."""

    def test_file_entry_with_findings(self):
        findings = [
            GateFinding(check_type="injection", severity="error", message="SQLi", line=10),
            GateFinding(check_type="credential_leakage", severity="warning", message="hardcoded key"),
        ]
        entry = GateFileEntry(
            file_path="src/db.py",
            verdict="fail",
            score=0.0,
            findings_count=2,
            findings=findings,
        )
        assert len(entry.findings) == 2
        assert entry.findings[0].check_type == "injection"
        assert entry.findings[0].line == 10
        assert entry.findings[1].severity == "warning"
        assert entry.findings[1].line is None  # default

    def test_file_entry_empty_findings(self):
        entry = GateFileEntry(file_path="src/clean.py", verdict="pass", score=1.0)
        assert entry.findings == []
        assert entry.findings_count == 0
        assert entry.finding_types == {}


class TestPostureResult:
    """test_posture_result — all three levels."""

    @pytest.mark.parametrize("level,reason", [
        ("clean", "All files passed"),
        ("degraded", "Warnings present"),
        ("critical", "1 file(s) failed"),
    ])
    def test_posture_levels(self, level, reason):
        posture = PostureResult(level=level, reason=reason)
        assert posture.level == level
        assert posture.reason == reason
        assert posture.rules == {}
        assert posture.interpretation == ""

    def test_posture_with_rules(self):
        posture = PostureResult(
            level="clean",
            reason="All passed",
            rules={"clean": "gate_pass_rate = 1.0"},
            interpretation="All gated files passed.",
        )
        assert posture.rules["clean"] == "gate_pass_rate = 1.0"
        assert posture.interpretation == "All gated files passed."


class TestSchemaVersion:
    """test_schema_version — verify default is '1.0.0'."""

    def test_schema_version_default(self):
        report = GateVerdictReport(run_id="r", timestamp="t")
        assert report.schema_version == "1.0.0"

    def test_schema_version_override(self):
        report = GateVerdictReport(run_id="r", timestamp="t", schema_version="2.0.0")
        assert report.schema_version == "2.0.0"


class TestModelDumpMatchesDictReport:
    """test_model_dump_matches_dict_report — build via build_gate_verdict_report(),
    then verify GateVerdictReport can be constructed from it."""

    def test_model_dump_matches_dict_report(self):
        from startd8.security_prime.gate_metrics import build_gate_verdict_report

        gate_results = [
            {
                "file_path": "src/handler.py",
                "verdict": "pass",
                "score": 1.0,
                "findings_count": 0,
                "finding_types": {},
                "timing_ms": 5.2,
                "database": "postgresql",
                "language": "python",
                "allowlisted": False,
            },
            {
                "file_path": "src/auth.py",
                "verdict": "warn",
                "score": 0.7,
                "findings_count": 1,
                "finding_types": {"lifecycle": 1},
                "timing_ms": 3.1,
                "database": "",
                "language": "python",
                "allowlisted": False,
            },
        ]
        dict_report = build_gate_verdict_report(gate_results, run_id="test-run")

        # The dict report should be loadable into the Pydantic model.
        # The dict has 'posture' as a dict — Pydantic coerces it to PostureResult.
        report = GateVerdictReport(**dict_report)

        assert report.run_id == "test-run"
        assert report.schema_version == "1.0.0"
        assert report.files_checked == 2
        assert report.files_total == 2
        assert report.verdict_counts["pass"] == 1
        assert report.verdict_counts["warn"] == 1
        assert len(report.items) == 2
        assert report.items[0].file_path == "src/handler.py"
        assert report.items[1].verdict == "warn"
        assert report.posture.level in ("clean", "degraded", "critical")
        assert report.security_posture == report.posture.level.upper()
        assert report.aggregate_score == dict_report["aggregate_score"]
        assert report.total_timing_ms == dict_report["total_timing_ms"]
