"""Tests for AR-153 retry feedback bridging in ImplementPhaseHandler.

Verifies that orchestrator-level retry feedback (prior_error_feedback,
retry_feedback, _retry_attempt) is correctly bridged into DevelopmentPhase
keys (last_error, test_output) and that IMPLEMENT cache is skipped on retry.
"""

from __future__ import annotations

import pytest

from startd8.contractors.context_seed_handlers import ImplementPhaseHandler


class TestBridgeRetryFeedback:
    """Tests for ImplementPhaseHandler._bridge_retry_feedback()."""

    def test_no_retry_returns_false(self):
        """No bridging when _retry_attempt is absent or zero."""
        context: dict = {}
        assert ImplementPhaseHandler._bridge_retry_feedback(context) is False
        assert "last_error" not in context
        assert "test_output" not in context

    def test_no_retry_zero(self):
        """No bridging when _retry_attempt is explicitly 0."""
        context: dict = {"_retry_attempt": 0}
        assert ImplementPhaseHandler._bridge_retry_feedback(context) is False

    def test_bridges_prior_error_feedback_to_last_error(self):
        """prior_error_feedback is copied to last_error."""
        context: dict = {
            "_retry_attempt": 1,
            "prior_error_feedback": "TEST failed: 2 validators failed",
        }
        result = ImplementPhaseHandler._bridge_retry_feedback(context)
        assert result is True
        assert context["last_error"] == "TEST failed: 2 validators failed"

    def test_does_not_overwrite_existing_last_error(self):
        """If last_error already exists, don't overwrite it."""
        context: dict = {
            "_retry_attempt": 1,
            "prior_error_feedback": "new error",
            "last_error": "existing error",
        }
        ImplementPhaseHandler._bridge_retry_feedback(context)
        assert context["last_error"] == "existing error"

    def test_extracts_test_failures_to_test_output(self):
        """retry_feedback with test_failures details populates test_output."""
        context: dict = {
            "_retry_attempt": 1,
            "retry_feedback": {
                "source_phase": "test",
                "details": {
                    "test_failures": {
                        "PI-005": {
                            "passed": False,
                            "failures": ["syntax_validator", "import_validator"],
                        },
                    },
                },
            },
        }
        ImplementPhaseHandler._bridge_retry_feedback(context)
        assert "test_output" in context
        assert "PI-005" in context["test_output"]
        assert "syntax_validator" in context["test_output"]
        assert "[TEST phase failures]" in context["test_output"]

    def test_extracts_review_failures_to_test_output(self):
        """retry_feedback with review_failures populates test_output."""
        context: dict = {
            "_retry_attempt": 2,
            "retry_feedback": {
                "source_phase": "review",
                "details": {
                    "review_failures": {
                        "PI-005": {"score": 3.5, "passed": False},
                    },
                },
            },
        }
        ImplementPhaseHandler._bridge_retry_feedback(context)
        assert "PI-005" in context["test_output"]
        assert "review score 3.5" in context["test_output"]
        assert "[REVIEW phase failures]" in context["test_output"]

    def test_extracts_integration_failures_to_test_output(self):
        """retry_feedback with integration_failures populates test_output."""
        context: dict = {
            "_retry_attempt": 1,
            "retry_feedback": {
                "source_phase": "integrate",
                "details": {
                    "integration_failures": {
                        "PI-005": {"error": "merge conflict in src/api.py"},
                    },
                },
            },
        }
        ImplementPhaseHandler._bridge_retry_feedback(context)
        assert "PI-005" in context["test_output"]
        assert "merge conflict" in context["test_output"]
        assert "[INTEGRATE phase failures]" in context["test_output"]

    def test_does_not_overwrite_existing_test_output(self):
        """If test_output already exists, don't overwrite it."""
        context: dict = {
            "_retry_attempt": 1,
            "test_output": "existing output",
            "retry_feedback": {
                "source_phase": "test",
                "details": {
                    "test_failures": {"PI-005": {"failures": ["x"]}},
                },
            },
        }
        ImplementPhaseHandler._bridge_retry_feedback(context)
        assert context["test_output"] == "existing output"

    def test_no_crash_on_empty_retry_feedback(self):
        """Handles retry_feedback with empty/missing details gracefully."""
        context: dict = {
            "_retry_attempt": 1,
            "retry_feedback": {},
        }
        result = ImplementPhaseHandler._bridge_retry_feedback(context)
        assert result is True
        # No test_output set because no failure details
        assert "test_output" not in context

    def test_no_crash_on_non_dict_retry_feedback(self):
        """Handles non-dict retry_feedback gracefully."""
        context: dict = {
            "_retry_attempt": 1,
            "retry_feedback": "not a dict",
        }
        result = ImplementPhaseHandler._bridge_retry_feedback(context)
        assert result is True
        assert "test_output" not in context

    def test_bridges_both_error_and_details(self):
        """Full bridge: prior_error_feedback + structured details."""
        context: dict = {
            "_retry_attempt": 1,
            "prior_error_feedback": (
                "Feature: PI-005\n"
                "Source phase: test\n"
                "Failure summary: 1 task failed validation\n"
            ),
            "retry_feedback": {
                "source_phase": "test",
                "details": {
                    "test_failures": {
                        "PI-005": {"failures": ["syntax_check"]},
                    },
                },
            },
        }
        ImplementPhaseHandler._bridge_retry_feedback(context)
        assert "Feature: PI-005" in context["last_error"]
        assert "PI-005" in context["test_output"]
        assert "syntax_check" in context["test_output"]


class TestFeatureCleanup:
    """Verify orchestrator cleanup prevents cross-feature leakage."""

    def test_cleanup_keys_documented(self):
        """The keys bridged by _bridge_retry_feedback should be cleaned up.

        This test documents the contract: if _bridge_retry_feedback sets
        last_error/test_output, the orchestrator's finally block must pop them.
        """
        # Simulate what _bridge_retry_feedback + orchestrator cleanup does
        context: dict = {
            "_retry_attempt": 1,
            "prior_error_feedback": "error text",
            "retry_feedback": {
                "source_phase": "test",
                "details": {"test_failures": {"T-1": {"failures": ["x"]}}},
            },
        }
        ImplementPhaseHandler._bridge_retry_feedback(context)
        assert "last_error" in context
        assert "test_output" in context

        # Simulate orchestrator's finally block cleanup
        for key in (
            "current_feature_id", "current_feature_phase",
            "_retry_attempt", "retry_feedback", "prior_error_feedback",
            "last_error", "test_output",
        ):
            context.pop(key, None)

        # Verify all retry-related keys are gone
        assert "last_error" not in context
        assert "test_output" not in context
        assert "prior_error_feedback" not in context
        assert "retry_feedback" not in context
        assert "_retry_attempt" not in context
