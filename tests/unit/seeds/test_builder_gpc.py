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
