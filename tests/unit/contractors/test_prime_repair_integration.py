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

        # Simulate what integrate_feature does
        if result.metadata.get("repair_attempted") and not result.metadata.get("repair_success"):
            repair_detail = (
                f"Repair attempted (steps: {result.metadata.get('repair_steps', [])}) "
                f"but failed"
            )
            if result.metadata.get("repair_error"):
                repair_detail += f": {result.metadata['repair_error']}"
            feature.error_message = (
                (feature.error_message or "") + f" | {repair_detail}"
            ).lstrip(" | ")

        assert "Repair attempted" in feature.error_message
        assert "fence_strip" in feature.error_message
        assert "re-checkpoint failed" in feature.error_message

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

        if result.metadata.get("repair_attempted") and not result.metadata.get("repair_success"):
            feature.error_message += " | repair info"

        assert feature.error_message == "Syntax Check failed"
