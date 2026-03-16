"""Tests for ContextSeed.generation_profile — REQ-GPC-400."""

from startd8.seeds.models import ContextSeed


class TestContextSeedGenerationProfile:
    """REQ-GPC-400: ContextSeed carries generation_profile."""

    def test_top_level_field_in_to_dict(self):
        seed = ContextSeed(generation_profile="source")
        d = seed.to_dict()
        assert d["generation_profile"] == "source"

    def test_default_is_none(self):
        seed = ContextSeed()
        assert seed.generation_profile is None

    def test_none_omitted_from_to_dict(self):
        seed = ContextSeed()
        d = seed.to_dict()
        assert "generation_profile" not in d

    def test_all_profile_values(self):
        for profile in ("source", "monitoring", "operator", "sponsor",
                        "practitioner", "observability", "full"):
            seed = ContextSeed(generation_profile=profile)
            assert seed.to_dict()["generation_profile"] == profile
