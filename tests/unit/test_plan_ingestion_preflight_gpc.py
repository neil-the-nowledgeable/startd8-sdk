"""Tests for profile-aware preflight — REQ-GPC-300/301."""

import json
from hashlib import sha256
from pathlib import Path

import pytest

from startd8.workflows.builtin.plan_ingestion_workflow import PlanIngestionWorkflow


def _make_onboarding(
    export_dir: Path,
    *,
    generation_profile: str = "full",
    include_resolvability: bool = True,
) -> dict:
    """Create onboarding-metadata.json with optional resolvability."""
    manifest_path = export_dir / "artifact-manifest.yaml"
    project_context_path = export_dir / "project-context.yaml"
    manifest_path.write_text("apiVersion: contextcore.io/v1\nkind: ArtifactManifest\n")
    project_context_path.write_text("apiVersion: contextcore.io/v1\nkind: ProjectContext\n")

    manifest_checksum = sha256(manifest_path.read_bytes()).hexdigest()
    project_checksum = sha256(project_context_path.read_bytes()).hexdigest()

    onboarding: dict = {
        "generation_profile": generation_profile,
        "artifact_manifest_path": str(manifest_path),
        "project_context_path": str(project_context_path),
        "artifact_manifest_checksum": manifest_checksum,
        "project_context_checksum": project_checksum,
        "coverage": {"overallCoverage": 100, "gaps": []},
    }
    if include_resolvability:
        onboarding["resolved_artifact_parameters"] = {"dashboard": {"x": {"resolved": True}}}

    onboarding_path = export_dir / "onboarding-metadata.json"
    onboarding_path.write_text(json.dumps(onboarding))
    return onboarding


class TestPreflightProfileAwareness:
    """REQ-GPC-300: profile-aware preflight validation."""

    def setup_method(self):
        self.wf = PlanIngestionWorkflow()

    def test_source_profile_passes_without_resolvability(self, tmp_path):
        """Source profile skips parameter resolvability check."""
        export_dir = tmp_path / "export"
        export_dir.mkdir()
        _make_onboarding(
            export_dir,
            generation_profile="source",
            include_resolvability=False,
        )

        onboarding, evidence, warnings, errors = self.wf._preflight_export_contract(
            contextcore_export_dir=str(export_dir),
            context_files=None,
            output_dir=tmp_path,
            min_export_coverage=0,
        )
        # No error about missing resolvability
        resolvability_errors = [
            e for e in errors if "parameter resolvability" in e
        ]
        assert resolvability_errors == []

    def test_full_profile_fails_without_resolvability(self, tmp_path):
        """Full profile still enforces parameter resolvability."""
        export_dir = tmp_path / "export"
        export_dir.mkdir()
        _make_onboarding(
            export_dir,
            generation_profile="full",
            include_resolvability=False,
        )

        onboarding, evidence, warnings, errors = self.wf._preflight_export_contract(
            contextcore_export_dir=str(export_dir),
            context_files=None,
            output_dir=tmp_path,
            min_export_coverage=0,
        )
        resolvability_errors = [
            e for e in errors if "parameter resolvability" in e
        ]
        assert len(resolvability_errors) == 1

    def test_sponsor_profile_passes_without_resolvability(self, tmp_path):
        """Sponsor profile skips parameter resolvability check."""
        export_dir = tmp_path / "export"
        export_dir.mkdir()
        _make_onboarding(
            export_dir,
            generation_profile="sponsor",
            include_resolvability=False,
        )

        onboarding, evidence, warnings, errors = self.wf._preflight_export_contract(
            contextcore_export_dir=str(export_dir),
            context_files=None,
            output_dir=tmp_path,
            min_export_coverage=0,
        )
        resolvability_errors = [
            e for e in errors if "parameter resolvability" in e
        ]
        assert resolvability_errors == []

    def test_observability_profile_enforces_resolvability(self, tmp_path):
        """Observability profile still requires parameter resolvability."""
        export_dir = tmp_path / "export"
        export_dir.mkdir()
        _make_onboarding(
            export_dir,
            generation_profile="observability",
            include_resolvability=False,
        )

        onboarding, evidence, warnings, errors = self.wf._preflight_export_contract(
            contextcore_export_dir=str(export_dir),
            context_files=None,
            output_dir=tmp_path,
            min_export_coverage=0,
        )
        resolvability_errors = [
            e for e in errors if "parameter resolvability" in e
        ]
        assert len(resolvability_errors) == 1

    def test_default_profile_is_full(self, tmp_path):
        """Missing generation_profile defaults to full behavior."""
        export_dir = tmp_path / "export"
        export_dir.mkdir()

        # Manually create onboarding without generation_profile
        manifest_path = export_dir / "artifact-manifest.yaml"
        project_context_path = export_dir / "project-context.yaml"
        manifest_path.write_text("apiVersion: v1\n")
        project_context_path.write_text("apiVersion: v1\n")

        onboarding = {
            "artifact_manifest_path": str(manifest_path),
            "project_context_path": str(project_context_path),
            "artifact_manifest_checksum": sha256(manifest_path.read_bytes()).hexdigest(),
            "project_context_checksum": sha256(project_context_path.read_bytes()).hexdigest(),
            "coverage": {"overallCoverage": 100, "gaps": []},
            # No generation_profile, no resolvability
        }
        (export_dir / "onboarding-metadata.json").write_text(json.dumps(onboarding))

        _, _, _, errors = self.wf._preflight_export_contract(
            contextcore_export_dir=str(export_dir),
            context_files=None,
            output_dir=tmp_path,
            min_export_coverage=0,
        )
        resolvability_errors = [
            e for e in errors if "parameter resolvability" in e
        ]
        assert len(resolvability_errors) == 1  # full profile enforces it
