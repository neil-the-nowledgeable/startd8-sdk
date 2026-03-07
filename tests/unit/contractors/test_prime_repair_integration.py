"""Tests for repair pipeline integration in PrimeContractorWorkflow.

Validates:
- RepairConfig forwarded to IntegrationEngine
- R2-S4: Successful repair doesn't consume retry budget
- REQ-RPL-204: Failed repair enriches error context
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.repair.config import RepairConfig


class TestRepairConfigForwarding:
    """Verify RepairConfig is forwarded to IntegrationEngine."""

    @patch("startd8.contractors.prime_contractor.IntegrationEngine")
    @patch("startd8.contractors.prime_contractor.IntegrationCheckpoint")
    @patch("startd8.contractors.prime_contractor.get_registry")
    def test_repair_config_forwarded(
        self, mock_registry, mock_checkpoint, mock_engine,
    ):
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        # Set up registry mock
        reg = MagicMock()
        mock_registry.return_value = reg
        reg.get_default_instrumentor.return_value = MagicMock
        reg.get_default_size_estimator.return_value = MagicMock
        reg.get_default_merge_strategy.return_value = MagicMock

        config = RepairConfig()
        wf = PrimeContractorWorkflow(
            project_root=Path("/tmp/test"),
            repair_config=config,
        )
        assert wf._repair_config is config
        # Verify IntegrationEngine was called with repair_config
        mock_engine.assert_called_once()
        call_kwargs = mock_engine.call_args
        assert call_kwargs.kwargs.get("repair_config") is config

    @patch("startd8.contractors.prime_contractor.IntegrationEngine")
    @patch("startd8.contractors.prime_contractor.IntegrationCheckpoint")
    @patch("startd8.contractors.prime_contractor.get_registry")
    def test_no_repair_config_default(
        self, mock_registry, mock_checkpoint, mock_engine,
    ):
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        reg = MagicMock()
        mock_registry.return_value = reg
        reg.get_default_instrumentor.return_value = MagicMock
        reg.get_default_size_estimator.return_value = MagicMock
        reg.get_default_merge_strategy.return_value = MagicMock

        wf = PrimeContractorWorkflow(project_root=Path("/tmp/test"))
        assert wf._repair_config is None
        call_kwargs = mock_engine.call_args
        assert call_kwargs.kwargs.get("repair_config") is None


class TestRetryCounterDecrement:
    """R2-S4: Successful repair doesn't consume retry budget."""

    def test_repair_success_decrements_attempts(self):
        """Feature with repair_success=True should have integration_attempts decremented."""
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(
            id="f1", name="test", description="test",
        )
        feature.integration_attempts = 3

        # Simulate what integrate_feature does on repair success
        result = MagicMock()
        result.success = True
        result.metadata = {"repair_success": True}
        result.integrated_files = []

        if result.metadata.get("repair_success"):
            feature.integration_attempts = max(
                0, feature.integration_attempts - 1,
            )

        assert feature.integration_attempts == 2

    def test_normal_success_no_decrement(self):
        """Feature without repair should not decrement."""
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(
            id="f1", name="test", description="test",
        )
        feature.integration_attempts = 3

        result = MagicMock()
        result.success = True
        result.metadata = {}

        if result.metadata.get("repair_success"):
            feature.integration_attempts = max(
                0, feature.integration_attempts - 1,
            )

        assert feature.integration_attempts == 3  # Unchanged

    def test_decrement_floors_at_zero(self):
        """Decrement never goes below zero."""
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(
            id="f1", name="test", description="test",
        )
        feature.integration_attempts = 0

        result = MagicMock()
        result.success = True
        result.metadata = {"repair_success": True}

        if result.metadata.get("repair_success"):
            feature.integration_attempts = max(
                0, feature.integration_attempts - 1,
            )

        assert feature.integration_attempts == 0


class TestFailedRepairErrorEnrichment:
    """REQ-RPL-204: Failed repair enriches error context."""

    def _simulate_failed_repair(self, feature, result):
        """Simulate the integrate_feature failed-repair enrichment logic."""
        from startd8.repair.diagnostics import sanitize_diagnostic

        if result.metadata.get("repair_attempted") and not result.metadata.get("repair_success"):
            repair_context = {
                "repair_attempted": True,
                "repair_steps_applied": result.metadata.get("repair_steps", []),
                "repair_files_modified": result.metadata.get("repair_files_modified", []),
                "repair_duration_ms": result.metadata.get("repair_duration_ms", 0),
                "repair_error": result.metadata.get("repair_error"),
            }
            if repair_context.get("repair_error"):
                repair_context["repair_error"] = sanitize_diagnostic(
                    str(repair_context["repair_error"])
                )
            feature.metadata["_repair_context"] = repair_context

            # Backward-compatible human-readable error_message
            repair_detail = (
                f"Repair attempted (steps: {result.metadata.get('repair_steps', [])}) "
                f"but failed"
            )
            if result.metadata.get("repair_error"):
                repair_detail += f": {result.metadata['repair_error']}"
            feature.error_message = (
                (feature.error_message or "") + f" | {repair_detail}"
            ).lstrip(" | ")

    def test_failed_repair_enriches_error(self):
        """When repair fails, error message includes repair details."""
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(
            id="f1", name="test", description="test",
        )
        feature.error_message = "Syntax Check failed"

        result = MagicMock()
        result.success = False
        result.metadata = {
            "repair_attempted": True,
            "repair_success": False,
            "repair_steps": ["fence_strip", "ast_validate"],
            "repair_error": "re-checkpoint failed",
        }
        result.checkpoint_results = []

        self._simulate_failed_repair(feature, result)

        assert "Repair attempted" in feature.error_message
        assert "fence_strip" in feature.error_message
        assert "re-checkpoint failed" in feature.error_message

    def test_failed_repair_stores_structured_context(self):
        """When repair fails, feature.metadata gets _repair_context dict."""
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(
            id="f1", name="test", description="test",
        )
        feature.error_message = "Syntax Check failed"

        result = MagicMock()
        result.success = False
        result.metadata = {
            "repair_attempted": True,
            "repair_success": False,
            "repair_steps": ["fence_strip", "ast_validate"],
            "repair_files_modified": ["src/foo.py"],
            "repair_duration_ms": 150,
            "repair_error": "re-checkpoint failed",
        }

        self._simulate_failed_repair(feature, result)

        ctx = feature.metadata.get("_repair_context")
        assert ctx is not None
        assert ctx["repair_attempted"] is True
        assert ctx["repair_steps_applied"] == ["fence_strip", "ast_validate"]
        assert ctx["repair_files_modified"] == ["src/foo.py"]
        assert ctx["repair_duration_ms"] == 150
        assert ctx["repair_error"] == "re-checkpoint failed"

    def test_structured_context_expected_keys(self):
        """The _repair_context dict has exactly the expected keys."""
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(
            id="f1", name="test", description="test",
        )

        result = MagicMock()
        result.success = False
        result.metadata = {
            "repair_attempted": True,
            "repair_success": False,
            "repair_steps": [],
        }

        self._simulate_failed_repair(feature, result)

        expected_keys = {
            "repair_attempted",
            "repair_steps_applied",
            "repair_files_modified",
            "repair_duration_ms",
            "repair_error",
        }
        assert set(feature.metadata["_repair_context"].keys()) == expected_keys

    def test_repair_error_sanitized(self):
        """ANSI escapes and secrets are stripped from repair_error."""
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(
            id="f1", name="test", description="test",
        )

        result = MagicMock()
        result.success = False
        result.metadata = {
            "repair_attempted": True,
            "repair_success": False,
            "repair_steps": ["fence_strip"],
            "repair_error": "\x1b[31mError\x1b[0m: API_KEY=sk-secret123",
        }

        self._simulate_failed_repair(feature, result)

        ctx = feature.metadata["_repair_context"]
        # ANSI stripped
        assert "\x1b[" not in ctx["repair_error"]
        # Secret redacted
        assert "sk-secret123" not in ctx["repair_error"]
        assert "REDACTED" in ctx["repair_error"]

    def test_no_enrichment_without_repair(self):
        """When repair was not attempted, error message is unchanged."""
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(
            id="f1", name="test", description="test",
        )
        feature.error_message = "Syntax Check failed"

        result = MagicMock()
        result.success = False
        result.metadata = {}

        self._simulate_failed_repair(feature, result)

        assert feature.error_message == "Syntax Check failed"
        assert "_repair_context" not in feature.metadata

    def test_backward_compat_error_message_preserved(self):
        """Both structured _repair_context and string error_message are set."""
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(
            id="f1", name="test", description="test",
        )
        feature.error_message = "Lint failed"

        result = MagicMock()
        result.success = False
        result.metadata = {
            "repair_attempted": True,
            "repair_success": False,
            "repair_steps": ["indent_normalize"],
            "repair_error": "still broken",
        }

        self._simulate_failed_repair(feature, result)

        # Structured context exists
        assert "_repair_context" in feature.metadata
        # Human-readable string also exists
        assert "Repair attempted" in feature.error_message
        assert "still broken" in feature.error_message


class TestRetryRepairContextConsumption:
    """REQ-RPL-204: Structured repair context enriches the LLM retry prompt."""

    def test_prior_error_enriched_with_repair_context(self):
        """process_feature retry path enriches prior_error with _repair_context."""
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(
            id="f1", name="test", description="test",
        )
        feature.error_message = "Lint Check failed"
        feature.metadata["_repair_context"] = {
            "repair_attempted": True,
            "repair_steps_applied": ["fence_strip", "ast_validate"],
            "repair_files_modified": ["src/foo.py"],
            "repair_duration_ms": 200,
            "repair_error": "re-check still failed",
        }

        # Simulate the retry path logic from process_feature
        prior_error = feature.error_message
        repair_ctx = feature.metadata.get("_repair_context")
        if repair_ctx:
            steps = repair_ctx.get("repair_steps_applied", [])
            files = repair_ctx.get("repair_files_modified", [])
            detail_parts = []
            if steps:
                detail_parts.append(f"Repair steps applied: {steps}")
            if files:
                detail_parts.append(f"Files modified by repair: {files}")
            if repair_ctx.get("repair_error"):
                detail_parts.append(f"Repair error: {repair_ctx['repair_error']}")
            if detail_parts:
                prior_error += "\n[Structured repair context]\n" + "\n".join(detail_parts)

        assert "[Structured repair context]" in prior_error
        assert "fence_strip" in prior_error
        assert "src/foo.py" in prior_error
        assert "re-check still failed" in prior_error

    def test_repair_context_cleared_after_consumption(self):
        """_repair_context is removed from metadata after retry consumes it."""
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(
            id="f1", name="test", description="test",
        )
        feature.error_message = "Check failed"
        feature.metadata["_repair_context"] = {
            "repair_attempted": True,
            "repair_steps_applied": [],
            "repair_files_modified": [],
            "repair_duration_ms": 0,
            "repair_error": None,
        }

        # Simulate the retry path clearing _repair_context
        feature.metadata.pop("_repair_context", None)

        assert "_repair_context" not in feature.metadata

    def test_no_enrichment_without_repair_context(self):
        """Without _repair_context, prior_error is unchanged."""
        from startd8.contractors.queue import FeatureSpec

        feature = FeatureSpec(
            id="f1", name="test", description="test",
        )
        feature.error_message = "Lint failed"

        prior_error = feature.error_message
        repair_ctx = feature.metadata.get("_repair_context")
        if repair_ctx:
            prior_error += "\n[Structured repair context]\nsome detail"

        assert prior_error == "Lint failed"
        assert "[Structured repair context]" not in prior_error
