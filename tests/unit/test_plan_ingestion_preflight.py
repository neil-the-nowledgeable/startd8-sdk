"""
Dedicated tests for plan ingestion preflight contract validation.

Covers:
- Source checksum verification against .contextcore.yaml
- Preflight report artifact (preflight-report.json)
- Graceful fallbacks when .contextcore.yaml is unavailable
"""

import json
from hashlib import sha256
from pathlib import Path

import pytest

from startd8.workflows.builtin.plan_ingestion_workflow import PlanIngestionWorkflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_onboarding(
    export_dir: Path,
    *,
    source_checksum: str | None = None,
    manifest_checksum: str | None = None,
    project_checksum: str | None = None,
) -> dict:
    """Create a valid onboarding-metadata.json with supporting files."""
    manifest_path = export_dir / "artifact-manifest.yaml"
    project_context_path = export_dir / "project-context.yaml"
    manifest_path.write_text("apiVersion: contextcore.io/v1\nkind: ArtifactManifest\n")
    project_context_path.write_text("apiVersion: contextcore.io/v1\nkind: ProjectContext\n")

    if manifest_checksum is None:
        manifest_checksum = sha256(manifest_path.read_bytes()).hexdigest()
    if project_checksum is None:
        project_checksum = sha256(project_context_path.read_bytes()).hexdigest()

    onboarding = {
        "artifact_manifest_path": str(manifest_path),
        "project_context_path": str(project_context_path),
        "artifact_manifest_checksum": manifest_checksum,
        "project_context_checksum": project_checksum,
        "source_checksum": source_checksum,
        "resolved_artifact_parameters": {"dashboard": {"x": {"resolved": True}}},
        "coverage": {"overallCoverage": 100, "gaps": []},
    }
    onboarding_path = export_dir / "onboarding-metadata.json"
    onboarding_path.write_text(json.dumps(onboarding))
    return onboarding


def _make_contextcore_yaml(path: Path, content: str = "project: test\n") -> str:
    """Write a .contextcore.yaml and return its SHA-256 checksum."""
    path.write_text(content)
    return sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Tests: Source checksum verification
# ---------------------------------------------------------------------------

class TestSourceChecksumVerification:
    """Test _preflight_export_contract source_checksum verification."""

    def setup_method(self):
        self.wf = PlanIngestionWorkflow()

    def test_preflight_verifies_source_checksum_match(self, tmp_path):
        """When .contextcore.yaml hash matches onboarding source_checksum, passes."""
        export_dir = tmp_path / "export"
        export_dir.mkdir()

        yaml_path = tmp_path / ".contextcore.yaml"
        checksum = _make_contextcore_yaml(yaml_path)
        _make_onboarding(export_dir, source_checksum=checksum)

        onboarding, evidence, warnings, errors = self.wf._preflight_export_contract(
            contextcore_export_dir=str(export_dir),
            context_files=None,
            output_dir=tmp_path,
            min_export_coverage=0,
            contextcore_yaml_path=yaml_path,
        )

        assert not errors, f"Expected no errors, got: {errors}"
        assert evidence["checksums"]["source_checksum_verified"] is True
        assert evidence["checksums"]["source_checksum_expected"] == checksum
        assert evidence["checksums"]["source_checksum_actual"] == checksum
        assert evidence["paths"]["contextcore_yaml"] == str(yaml_path)

    def test_preflight_rejects_stale_source_checksum(self, tmp_path):
        """When .contextcore.yaml hash differs from onboarding, returns error."""
        export_dir = tmp_path / "export"
        export_dir.mkdir()

        yaml_path = tmp_path / ".contextcore.yaml"
        _make_contextcore_yaml(yaml_path, content="project: test\n")
        _make_onboarding(export_dir, source_checksum="sha256:stale_checksum_value")

        onboarding, evidence, warnings, errors = self.wf._preflight_export_contract(
            contextcore_export_dir=str(export_dir),
            context_files=None,
            output_dir=tmp_path,
            min_export_coverage=0,
            contextcore_yaml_path=yaml_path,
        )

        assert any("source_checksum mismatch" in e for e in errors)
        assert evidence["checksums"]["source_checksum_verified"] is False

    def test_preflight_skips_verification_when_no_contextcore_yaml(self, tmp_path):
        """When .contextcore.yaml path is None, warn but don't error."""
        export_dir = tmp_path / "export"
        export_dir.mkdir()

        _make_onboarding(export_dir, source_checksum="sha256:some_checksum")

        onboarding, evidence, warnings, errors = self.wf._preflight_export_contract(
            contextcore_export_dir=str(export_dir),
            context_files=None,
            output_dir=tmp_path,
            min_export_coverage=0,
            contextcore_yaml_path=None,
        )

        # Should warn, not error — checksum present but can't verify.
        assert not any("source_checksum mismatch" in e for e in errors)
        assert any("not available for verification" in w for w in warnings)
        assert evidence["checksums"]["source_checksum_verified"] is None

    def test_preflight_warns_missing_source_checksum(self, tmp_path):
        """When onboarding lacks source_checksum, warn."""
        export_dir = tmp_path / "export"
        export_dir.mkdir()

        yaml_path = tmp_path / ".contextcore.yaml"
        _make_contextcore_yaml(yaml_path)
        _make_onboarding(export_dir, source_checksum=None)

        onboarding, evidence, warnings, errors = self.wf._preflight_export_contract(
            contextcore_export_dir=str(export_dir),
            context_files=None,
            output_dir=tmp_path,
            min_export_coverage=0,
            contextcore_yaml_path=yaml_path,
        )

        assert any("source_checksum missing" in w for w in warnings)
        assert evidence["checksums"]["source_checksum_verified"] is None

    def test_preflight_handles_nonexistent_contextcore_yaml(self, tmp_path):
        """When contextcore_yaml_path points to non-existent file, warn gracefully."""
        export_dir = tmp_path / "export"
        export_dir.mkdir()

        yaml_path = tmp_path / ".contextcore.yaml"  # Does not exist.
        _make_onboarding(export_dir, source_checksum="sha256:something")

        onboarding, evidence, warnings, errors = self.wf._preflight_export_contract(
            contextcore_export_dir=str(export_dir),
            context_files=None,
            output_dir=tmp_path,
            min_export_coverage=0,
            contextcore_yaml_path=yaml_path,
        )

        # Non-existent yaml → same as None: warn, not error.
        assert not any("source_checksum mismatch" in e for e in errors)
        assert any("not available for verification" in w for w in warnings)


# ---------------------------------------------------------------------------
# Tests: Preflight report artifact
# ---------------------------------------------------------------------------

class TestPreflightReport:
    """Test _write_preflight_report produces correct JSON artifact."""

    def test_preflight_report_written_on_pass(self, tmp_path):
        """On successful preflight, writes passed=true report."""
        evidence = {
            "checksums": {"source_checksum_verified": True},
            "paths": {"onboarding_metadata": "/some/path"},
            "coverage": {"overallCoverage": 100},
        }
        path = PlanIngestionWorkflow._write_preflight_report(
            tmp_path, passed=True, evidence=evidence, warnings=[], errors=[],
        )

        assert path.exists()
        assert path.name == "preflight-report.json"
        report = json.loads(path.read_text())
        assert report["passed"] is True
        assert report["source_checksum_verified"] is True
        assert report["evidence"] == evidence
        assert report["warnings"] == []
        assert report["errors"] == []
        assert "generated_at" in report

    def test_preflight_report_written_on_fail(self, tmp_path):
        """On failed preflight, writes passed=false report with errors."""
        errors = [
            "Preflight: source_checksum mismatch",
            "Preflight: coverage too low",
        ]
        evidence = {
            "checksums": {"source_checksum_verified": False},
            "paths": {},
            "coverage": {},
        }
        path = PlanIngestionWorkflow._write_preflight_report(
            tmp_path, passed=False, evidence=evidence, warnings=[], errors=errors,
        )

        assert path.exists()
        report = json.loads(path.read_text())
        assert report["passed"] is False
        assert report["source_checksum_verified"] is False
        assert len(report["errors"]) == 2

    def test_preflight_report_includes_warnings(self, tmp_path):
        """Warnings are captured in the report even when passing."""
        warnings = ["Preflight: source_checksum missing in onboarding metadata"]
        path = PlanIngestionWorkflow._write_preflight_report(
            tmp_path, passed=True,
            evidence={"checksums": {"source_checksum_verified": None}, "paths": {}, "coverage": {}},
            warnings=warnings, errors=[],
        )

        report = json.loads(path.read_text())
        assert report["passed"] is True
        assert report["source_checksum_verified"] is None
        assert len(report["warnings"]) == 1

    def test_preflight_report_creates_output_dir(self, tmp_path):
        """Report creates output directory if it doesn't exist."""
        nested = tmp_path / "deep" / "nested" / "dir"
        path = PlanIngestionWorkflow._write_preflight_report(
            nested, passed=True,
            evidence={"checksums": {}, "paths": {}, "coverage": {}},
            warnings=[], errors=[],
        )
        assert path.exists()
        assert nested.exists()
