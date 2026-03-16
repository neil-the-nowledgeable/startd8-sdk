"""Tests for SeedBuilder generation profile extraction — REQ-GPC-401."""

from startd8.seeds.builder import SeedBuilder


class TestSeedBuilderGenerationProfile:
    """REQ-GPC-401: Builder extracts profile from onboarding."""

    def test_sets_profile_from_onboarding(self):
        builder = SeedBuilder()
        builder.set_artifacts(onboarding={"generation_profile": "source"})
        seed = builder.build()
        assert seed.get("generation_profile") == "source"

    def test_default_none_without_onboarding(self):
        builder = SeedBuilder()
        builder.set_artifacts()
        seed = builder.build()
        assert "generation_profile" not in seed

    def test_default_none_when_onboarding_lacks_profile(self):
        builder = SeedBuilder()
        builder.set_artifacts(onboarding={"artifact_manifest_path": "/a/b"})
        seed = builder.build()
        # generation_profile not in onboarding → None → omitted from dict
        assert "generation_profile" not in seed

    def test_full_profile_serialized(self):
        builder = SeedBuilder()
        builder.set_artifacts(onboarding={"generation_profile": "full"})
        seed = builder.build()
        assert seed["generation_profile"] == "full"

    def test_omitted_example_artifacts_excluded(self):
        """Defense-in-depth: marker dicts in artifacts are not embedded."""
        builder = SeedBuilder()
        builder.set_artifacts(onboarding={
            "generation_profile": "source",
            "example_artifacts": {"_omitted": "profile=source"},
        })
        seed = builder.build()
        assert "_omitted" not in str(seed.get("artifacts", {}))

    def test_real_example_artifacts_included(self):
        builder = SeedBuilder()
        builder.set_artifacts(onboarding={
            "example_artifacts": {"dashboard": {"path": "/a/b"}},
        })
        seed = builder.build()
        assert seed["artifacts"]["example_artifacts"] == {"dashboard": {"path": "/a/b"}}
