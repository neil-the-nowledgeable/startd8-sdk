"""Tests for runtime cloud-cost lookup in MicroPrime metrics.

Verifies that ``_get_cloud_costs`` resolves pricing from PricingService
and falls back gracefully when the service or model catalog is unavailable.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from startd8.micro_prime.metrics import (
    _FALLBACK_CLOUD_INPUT,
    _FALLBACK_CLOUD_OUTPUT,
    _LOCAL_COST_PER_M_INPUT,
    _LOCAL_COST_PER_M_OUTPUT,
    _get_cloud_costs,
    generate_cost_report,
)
from startd8.micro_prime.models import (
    ElementResult,
    FileResult,
    MicroPrimeConfig,
    SeedResult,
    TierClassification,
)


# ---------------------------------------------------------------------------
# _get_cloud_costs tests
# ---------------------------------------------------------------------------


class TestGetCloudCostsDefault:
    """Default (no model_spec) resolution via model catalog + PricingService."""

    def test_default_returns_haiku_fallback_values(self):
        """With no model_spec, should return Haiku pricing from PricingService."""
        input_cost, output_cost = _get_cloud_costs()
        # Should return *some* pricing (either from PricingService or fallback)
        assert isinstance(input_cost, float)
        assert isinstance(output_cost, float)
        assert input_cost >= 0
        assert output_cost >= 0

    def test_fallback_constants_match_expected(self):
        """Haiku fallback constants are $0.80/$4.00."""
        assert _FALLBACK_CLOUD_INPUT == 0.80
        assert _FALLBACK_CLOUD_OUTPUT == 4.00


class TestGetCloudCostsCustomModel:
    """Custom model_spec returns pricing from PricingService."""

    def test_custom_model_returns_pricing_service_costs(self):
        """A known model spec should return its PricingService costs."""
        mock_pricing_obj = MagicMock()
        mock_pricing_obj.input_cost_per_million = 3.0
        mock_pricing_obj.output_cost_per_million = 15.0

        mock_service = MagicMock()
        mock_service.get_pricing.return_value = mock_pricing_obj

        mock_cls = MagicMock(return_value=mock_service)

        with patch("startd8.costs.pricing.PricingService", mock_cls):
            input_cost, output_cost = _get_cloud_costs("anthropic:claude-sonnet-4-6")

        mock_service.get_pricing.assert_called_once_with("claude-sonnet-4-6")
        assert input_cost == 3.0
        assert output_cost == 15.0

    def test_model_spec_without_provider_prefix(self):
        """A bare model name (no colon) is passed to get_pricing directly."""
        mock_pricing_obj = MagicMock()
        mock_pricing_obj.input_cost_per_million = 2.5
        mock_pricing_obj.output_cost_per_million = 10.0

        mock_service = MagicMock()
        mock_service.get_pricing.return_value = mock_pricing_obj

        mock_cls = MagicMock(return_value=mock_service)

        with patch("startd8.costs.pricing.PricingService", mock_cls):
            input_cost, output_cost = _get_cloud_costs("gpt-4o")

        mock_service.get_pricing.assert_called_once_with("gpt-4o")
        assert input_cost == 2.5
        assert output_cost == 10.0


class TestGetCloudCostsFallback:
    """Graceful fallback when PricingService is unavailable."""

    def test_pricing_service_import_failure_returns_fallback(self):
        """ImportError on PricingService falls back to Haiku constants."""
        with patch.dict("sys.modules", {"startd8.costs.pricing": None}):
            # Force an ImportError inside _get_cloud_costs
            with patch(
                "builtins.__import__",
                side_effect=_selective_import_error("startd8.costs.pricing"),
            ):
                input_cost, output_cost = _get_cloud_costs("anthropic:claude-haiku-4-5-20251008")

        assert input_cost == _FALLBACK_CLOUD_INPUT
        assert output_cost == _FALLBACK_CLOUD_OUTPUT

    def test_pricing_service_returns_none_falls_back(self):
        """get_pricing returning None falls back to Haiku constants."""
        mock_service = MagicMock()
        mock_service.get_pricing.return_value = None

        with patch(
            "startd8.micro_prime.metrics.PricingService",
            return_value=mock_service,
            create=True,
        ):
            input_cost, output_cost = _get_cloud_costs("anthropic:unknown-model")

        assert input_cost == _FALLBACK_CLOUD_INPUT
        assert output_cost == _FALLBACK_CLOUD_OUTPUT

    def test_model_catalog_import_failure_returns_fallback(self):
        """If model catalog cannot be imported, default spec falls back."""
        with patch(
            "startd8.micro_prime.metrics.Models",
            side_effect=ImportError("no catalog"),
            create=True,
        ):
            # When model_spec="" and Models import fails
            original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

            def failing_import(name, *args, **kwargs):
                if name == "startd8.model_catalog":
                    raise ImportError("no catalog")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=failing_import):
                input_cost, output_cost = _get_cloud_costs("")

        assert input_cost == _FALLBACK_CLOUD_INPUT
        assert output_cost == _FALLBACK_CLOUD_OUTPUT


class TestLocalCostsAlwaysZero:
    """Local (Ollama) costs should always be zero."""

    def test_local_cost_constants_are_zero(self):
        assert _LOCAL_COST_PER_M_INPUT == 0.0
        assert _LOCAL_COST_PER_M_OUTPUT == 0.0


# ---------------------------------------------------------------------------
# generate_cost_report with cloud_model_spec
# ---------------------------------------------------------------------------


@pytest.fixture
def _minimal_seed_result() -> SeedResult:
    """A seed result with two elements for cost calculations."""
    return SeedResult(
        file_results=[
            FileResult(
                file_path="src/a.py",
                element_results=[
                    ElementResult(
                        element_name="foo",
                        file_path="src/a.py",
                        tier=TierClassification.SIMPLE,
                        success=True,
                        input_tokens=100,
                        output_tokens=200,
                    ),
                    ElementResult(
                        element_name="bar",
                        file_path="src/a.py",
                        tier=TierClassification.SIMPLE,
                        success=True,
                        input_tokens=150,
                        output_tokens=250,
                    ),
                ],
            )
        ]
    )


@pytest.fixture
def _config() -> MicroPrimeConfig:
    return MicroPrimeConfig()


class TestCostReportWithCloudModel:
    """generate_cost_report uses cloud_model_spec for pricing."""

    def test_default_uses_haiku_pricing(self, _minimal_seed_result, _config):
        """Without cloud_model_spec, report uses Haiku-tier pricing."""
        report = generate_cost_report(_minimal_seed_result, _config)
        # baseline_all_cloud_usd should be > 0 (2 elements * baseline tokens)
        assert report.baseline_all_cloud_usd > 0
        assert report.estimated_local_cost_usd == 0.0

    def test_custom_model_changes_baseline(self, _minimal_seed_result, _config):
        """Providing a model spec with different pricing changes the baseline."""
        mock_pricing_obj = MagicMock()
        mock_pricing_obj.input_cost_per_million = 10.0
        mock_pricing_obj.output_cost_per_million = 50.0

        mock_service = MagicMock()
        mock_service.get_pricing.return_value = mock_pricing_obj

        with patch(
            "startd8.micro_prime.metrics.PricingService",
            return_value=mock_service,
            create=True,
        ):
            report_expensive = generate_cost_report(
                _minimal_seed_result, _config, cloud_model_spec="openai:o3"
            )

        # With much higher pricing, baseline should be larger
        report_default = generate_cost_report(_minimal_seed_result, _config)

        # The expensive model's baseline should be higher than default
        # (unless default also resolves to high pricing, but Haiku is cheap)
        assert report_expensive.baseline_all_cloud_usd > 0
        assert report_expensive.baseline_all_cloud_usd != report_default.baseline_all_cloud_usd

    def test_local_cost_always_zero(self, _minimal_seed_result, _config):
        """Local cost remains zero regardless of cloud model spec."""
        report = generate_cost_report(
            _minimal_seed_result, _config, cloud_model_spec="openai:o3"
        )
        assert report.estimated_local_cost_usd == 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _selective_import_error(blocked_module: str):
    """Return an __import__ replacement that raises ImportError for one module."""
    real_import = __import__

    def _import(name, *args, **kwargs):
        if name == blocked_module:
            raise ImportError(f"Simulated: {blocked_module} unavailable")
        return real_import(name, *args, **kwargs)

    return _import
