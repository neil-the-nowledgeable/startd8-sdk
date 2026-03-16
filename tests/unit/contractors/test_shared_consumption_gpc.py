"""Tests for consumption tracking profile recording — REQ-GPC-700."""

from __future__ import annotations

from startd8.contractors.context_seed.shared import _track_onboarding_consumption


class TestConsumptionAuditProfile:
    """REQ-GPC-700: consumption audit includes generation_profile."""

    def test_audit_includes_profile(self):
        context: dict = {"generation_profile": "source"}
        _track_onboarding_consumption(context, "derivation_rules", "DESIGN")

        audit = context["_onboarding_consumption"]
        assert audit["_generation_profile"] == "source"
        assert "DESIGN" in audit["derivation_rules"]

    def test_audit_defaults_to_full(self):
        context: dict = {}
        _track_onboarding_consumption(context, "calibration_hints", "DESIGN")

        audit = context["_onboarding_consumption"]
        assert audit["_generation_profile"] == "full"

    def test_profile_set_once(self):
        """Profile is only set on first call, not overwritten."""
        context: dict = {"generation_profile": "operator"}
        _track_onboarding_consumption(context, "field_a", "DESIGN")

        # Change profile in context (shouldn't affect audit)
        context["generation_profile"] = "source"
        _track_onboarding_consumption(context, "field_b", "IMPLEMENT")

        audit = context["_onboarding_consumption"]
        assert audit["_generation_profile"] == "operator"

    def test_multiple_phases_tracked(self):
        context: dict = {"generation_profile": "full"}
        _track_onboarding_consumption(context, "derivation_rules", "DESIGN")
        _track_onboarding_consumption(context, "derivation_rules", "IMPLEMENT")

        audit = context["_onboarding_consumption"]
        assert audit["derivation_rules"] == ["DESIGN", "IMPLEMENT"]
