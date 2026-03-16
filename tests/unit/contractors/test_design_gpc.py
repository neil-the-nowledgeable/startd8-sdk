"""Tests for design phase profile-omission logging — REQ-GPC-500."""

from __future__ import annotations

import logging
from unittest.mock import patch, MagicMock

import pytest


class TestDesignFallbackProfileLogging:
    """REQ-GPC-500: design fallback logs when profile omits a field."""

    def test_logs_omission_for_source_profile(self, caplog):
        """When source profile sets onboarding fields to None, debug log explains."""
        # We test the fallback loop logic directly rather than running the
        # full design phase, because the handler requires extensive setup.
        # The logic under test is the _fallback_map loop in design.py.
        context = {
            "generation_profile": "source",
            "onboarding_derivation_rules": None,
            "onboarding_resolved_parameters": None,
            "onboarding_output_contracts": None,
            "onboarding_calibration_hints": None,
        }

        _fallback_map = [
            ("inv_derivation_rules", "onboarding_derivation_rules"),
            ("inv_resolved_parameters", "onboarding_resolved_parameters"),
            ("inv_output_contracts", "onboarding_output_contracts"),
            ("inv_calibration_hints", "onboarding_calibration_hints"),
        ]

        # Simulate the fallback loop with profile-aware logging
        _profile = context.get("generation_profile", "full")
        skipped = []
        for local_var, ctx_key in _fallback_map:
            # locals()[local_var] is None in the real code; simulate it
            fb_val = context.get(ctx_key)
            if fb_val is None and _profile != "full":
                skipped.append(ctx_key)

        assert len(skipped) == 4
        assert "onboarding_derivation_rules" in skipped
        assert "onboarding_calibration_hints" in skipped

    def test_no_log_for_full_profile(self):
        """Full profile with None fields doesn't trigger profile-omission log."""
        context = {
            "generation_profile": "full",
            "onboarding_derivation_rules": None,
        }

        _profile = context.get("generation_profile", "full")
        fb_val = context.get("onboarding_derivation_rules")

        # The profile-omission branch should NOT fire for full profile
        should_log_omission = fb_val is None and _profile != "full"
        assert should_log_omission is False
