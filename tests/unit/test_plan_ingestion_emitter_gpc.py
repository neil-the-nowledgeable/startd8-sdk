"""Tests for seed artifact marker guards — REQ-GPC-402."""

from startd8.seeds.utils import is_omitted


class TestBuildSeedArtifactsMarkerGuard:
    """REQ-GPC-402: _build_seed_artifacts guards omitted markers."""

    def test_omitted_example_artifacts_excluded(self):
        """Marker dict in example_artifacts should not end up in seed artifacts."""
        # Simulate the guard logic from plan_ingestion_emitter.py
        onboarding_resolved = {
            "example_artifacts": {"_omitted": "profile=source"},
            "artifact_manifest_path": "/a/b",
        }
        artifacts_out: dict = {}

        ex = onboarding_resolved.get("example_artifacts")
        if ex and isinstance(ex, dict) and not is_omitted(ex):
            artifacts_out["example_artifacts"] = dict(ex)

        assert "example_artifacts" not in artifacts_out

    def test_real_example_artifacts_included(self):
        """Normal example_artifacts dict passes through."""
        onboarding_resolved = {
            "example_artifacts": {"dashboard": {"uid": "abc"}},
        }
        artifacts_out: dict = {}

        ex = onboarding_resolved.get("example_artifacts")
        if ex and isinstance(ex, dict) and not is_omitted(ex):
            artifacts_out["example_artifacts"] = dict(ex)

        assert artifacts_out["example_artifacts"] == {"dashboard": {"uid": "abc"}}

    def test_none_example_artifacts_excluded(self):
        """None example_artifacts should not produce an entry."""
        onboarding_resolved: dict = {}
        artifacts_out: dict = {}

        ex = onboarding_resolved.get("example_artifacts")
        if ex and isinstance(ex, dict) and not is_omitted(ex):
            artifacts_out["example_artifacts"] = dict(ex)

        assert "example_artifacts" not in artifacts_out
