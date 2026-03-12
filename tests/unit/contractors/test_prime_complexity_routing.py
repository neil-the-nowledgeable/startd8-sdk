"""Tests for PrimeContractorWorkflow complexity routing integration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.complexity import ComplexityRoutingConfig, ComplexityTier, TaskComplexitySignals
from startd8.contractors.protocols import GenerationResult


# ── Helpers ──────────────────────────────────────────────────────────


_WORKFLOW_PREFIX = "startd8.contractors.prime_contractor.PrimeContractorWorkflow"


def _make_workflow(**kwargs):
    """Build a PrimeContractorWorkflow with a mock code_generator."""
    from startd8.contractors.prime_contractor import PrimeContractorWorkflow

    mock_gen = MagicMock()
    mock_gen.generate.return_value = GenerationResult(
        success=True,
        generated_files=[Path("out.py")],
        cost_usd=0.01,
        input_tokens=100,
        output_tokens=50,
        model="mock",
    )
    mock_gen.output_dir = Path("/tmp/generated")

    defaults = dict(
        project_root=Path("/tmp/test_project"),
        code_generator=mock_gen,
    )
    defaults.update(kwargs)
    wf = PrimeContractorWorkflow(**defaults)
    return wf, mock_gen


def _make_feature(name="test-feature", target_files=None, description="Implement foo", metadata=None):
    """Build a mock FeatureSpec."""
    from startd8.contractors.queue import FeatureSpec

    feat = MagicMock(spec=FeatureSpec)
    feat.name = name
    feat.id = f"F-{name}"
    feat.target_files = target_files or ["mod.py"]
    feat.description = description
    feat.metadata = metadata if metadata is not None else {}
    feat.status = None
    feat.generated_files = []
    feat.copy_source_task_id = None
    feat.copy_source_file = None
    feat.dependencies = []
    return feat


# Shared patches for develop_feature internals
_DEVELOP_PATCHES = [
    patch(f"{_WORKFLOW_PREFIX}.pre_flight_validation", return_value=(True, {})),
    patch(f"{_WORKFLOW_PREFIX}._populate_existing_files"),
    patch(f"{_WORKFLOW_PREFIX}._save_queue_state_with_mode"),
    patch(f"{_WORKFLOW_PREFIX}._get_domain_enrichment", return_value=None),
    patch(f"{_WORKFLOW_PREFIX}._check_file_provenance", return_value={}),
]


def _apply_develop_patches(func):
    """Apply all develop_feature patches to a test method."""
    for p in reversed(_DEVELOP_PATCHES):
        func = p(func)
    return func


# ── enable_complexity_routing ────────────────────────────────────────


class TestEnableComplexityRouting:
    def test_sets_internal_state(self):
        wf, _ = _make_workflow()
        assert wf._complexity_routing_enabled is False
        wf.enable_complexity_routing()
        assert wf._complexity_routing_enabled is True
        assert wf._complexity_config is not None
        assert wf._complexity_router is not None

    def test_custom_config(self):
        wf, _ = _make_workflow()
        cfg = ComplexityRoutingConfig(blast_radius_complex_threshold=10)
        wf.enable_complexity_routing(config=cfg)
        assert wf._complexity_config.blast_radius_complex_threshold == 10

    def test_no_tier3_agent_uses_default_for_all(self):
        wf, default_gen = _make_workflow()
        wf.enable_complexity_routing()
        router = wf._complexity_router
        assert router.select(ComplexityTier.MODERATE) is default_gen
        assert router.select(ComplexityTier.COMPLEX) is default_gen

    def test_default_state_is_disabled(self):
        wf, _ = _make_workflow()
        assert wf._complexity_routing_enabled is False
        assert wf._complexity_config is None
        assert wf._complexity_router is None

    def test_trivial_generator_wired(self):
        """REQ-MP-700: trivial_generator param routes TRIVIAL tier."""
        wf, default_gen = _make_workflow()
        trivial_gen = MagicMock()
        wf.enable_complexity_routing(trivial_generator=trivial_gen)
        router = wf._complexity_router
        assert router.select(ComplexityTier.TRIVIAL) is trivial_gen
        assert router.select(ComplexityTier.MODERATE) is default_gen

    def test_simple_generator_wired(self):
        """REQ-MP-700: simple_generator param routes SIMPLE tier."""
        wf, default_gen = _make_workflow()
        simple_gen = MagicMock()
        wf.enable_complexity_routing(simple_generator=simple_gen)
        router = wf._complexity_router
        assert router.select(ComplexityTier.SIMPLE) is simple_gen
        assert router.select(ComplexityTier.MODERATE) is default_gen

    def test_both_low_tier_generators_wired(self):
        """REQ-MP-700: both trivial and simple generators coexist with defaults."""
        wf, default_gen = _make_workflow()
        micro_prime_gen = MagicMock()
        wf.enable_complexity_routing(
            trivial_generator=micro_prime_gen,
            simple_generator=micro_prime_gen,
        )
        router = wf._complexity_router
        assert router.select(ComplexityTier.TRIVIAL) is micro_prime_gen
        assert router.select(ComplexityTier.SIMPLE) is micro_prime_gen
        assert router.select(ComplexityTier.MODERATE) is default_gen
        assert router.select(ComplexityTier.COMPLEX) is default_gen


# ── develop_feature with complexity routing ──────────────────────────


class TestDevelopFeatureRouting:
    @_apply_develop_patches
    def test_routing_disabled_uses_default_generator(self, *_mocks):
        wf, default_gen = _make_workflow()
        wf._context_strategy = MagicMock()
        wf._context_strategy.resolve_task_context.return_value = {}
        wf._context_strategy.mode = "standalone"
        wf.queue.start_feature = MagicMock()

        feature = _make_feature()
        feature.generated_files = []  # no cached files
        wf.develop_feature(feature)
        default_gen.generate.assert_called_once()

    @_apply_develop_patches
    def test_routing_enabled_classifies_feature(self, *_mocks):
        wf, default_gen = _make_workflow()
        wf._context_strategy = MagicMock()
        wf._context_strategy.resolve_task_context.return_value = {}
        wf._context_strategy.mode = "standalone"
        wf.queue.start_feature = MagicMock()

        wf.enable_complexity_routing()

        feature = _make_feature(metadata={})
        feature.generated_files = []

        wf.develop_feature(feature)

        # Classification metadata should be stashed
        assert "_complexity_tier" in feature.metadata
        assert "_complexity_reason" in feature.metadata
        assert "_complexity_signals" in feature.metadata

    @_apply_develop_patches
    def test_high_blast_radius_uses_complex_generator(self, *_mocks):
        wf, default_gen = _make_workflow()
        wf._context_strategy = MagicMock()
        wf._context_strategy.resolve_task_context.return_value = {}
        wf._context_strategy.mode = "standalone"
        wf.queue.start_feature = MagicMock()

        complex_gen = MagicMock()
        complex_gen.generate.return_value = GenerationResult(
            success=True,
            generated_files=[Path("out.py")],
            cost_usd=0.05,
            input_tokens=500,
            output_tokens=200,
            model="opus",
        )

        wf.enable_complexity_routing()
        wf._complexity_router._generators[ComplexityTier.COMPLEX] = complex_gen

        feature = _make_feature(metadata={})
        feature.generated_files = []

        with patch(
            "startd8.complexity.extract_signals_from_feature",
            return_value=TaskComplexitySignals(blast_radius=10),
        ):
            wf.develop_feature(feature)

        complex_gen.generate.assert_called_once()
        default_gen.generate.assert_not_called()

    @_apply_develop_patches
    def test_moderate_feature_uses_default_generator(self, *_mocks):
        wf, default_gen = _make_workflow()
        wf._context_strategy = MagicMock()
        wf._context_strategy.resolve_task_context.return_value = {}
        wf._context_strategy.mode = "standalone"
        wf.queue.start_feature = MagicMock()

        wf.enable_complexity_routing()

        feature = _make_feature(metadata={})
        feature.generated_files = []

        with patch(
            "startd8.complexity.extract_signals_from_feature",
            return_value=TaskComplexitySignals(),
        ):
            wf.develop_feature(feature)

        default_gen.generate.assert_called_once()
        assert feature.metadata["_complexity_tier"] == "moderate"

    @_apply_develop_patches
    def test_classification_error_graceful_fallback(self, *_mocks):
        wf, default_gen = _make_workflow()
        wf._context_strategy = MagicMock()
        wf._context_strategy.resolve_task_context.return_value = {}
        wf._context_strategy.mode = "standalone"
        wf.queue.start_feature = MagicMock()

        wf.enable_complexity_routing()

        feature = _make_feature(metadata={})
        feature.generated_files = []

        with patch(
            "startd8.complexity.extract_signals_from_feature",
            side_effect=RuntimeError("boom"),
        ):
            result = wf.develop_feature(feature)

        # Should still succeed using default generator
        assert result is True
        default_gen.generate.assert_called_once()

    @_apply_develop_patches
    def test_metadata_populated_on_feature(self, *_mocks):
        wf, _ = _make_workflow()
        wf._context_strategy = MagicMock()
        wf._context_strategy.resolve_task_context.return_value = {}
        wf._context_strategy.mode = "standalone"
        wf.queue.start_feature = MagicMock()

        wf.enable_complexity_routing()

        feature = _make_feature(metadata={})
        feature.generated_files = []

        with patch(
            "startd8.complexity.extract_signals_from_feature",
            return_value=TaskComplexitySignals(blast_radius=10),
        ):
            wf.develop_feature(feature)

        assert feature.metadata["_complexity_tier"] == "complex"
        assert "blast_radius" in feature.metadata["_complexity_reason"]
        assert feature.metadata["_complexity_signals"]["blast_radius"] == 10

    @_apply_develop_patches
    def test_simple_feature_uses_simple_generator(self, *_mocks):
        """REQ-MP-700: SIMPLE-tier features route to simple_generator."""
        wf, default_gen = _make_workflow()
        wf._context_strategy = MagicMock()
        wf._context_strategy.resolve_task_context.return_value = {}
        wf._context_strategy.mode = "standalone"
        wf.queue.start_feature = MagicMock()

        micro_prime_gen = MagicMock()
        micro_prime_gen.generate.return_value = GenerationResult(
            success=True,
            generated_files=[Path("out.py")],
            cost_usd=0.001,
            input_tokens=20,
            output_tokens=30,
            model="micro-prime",
        )

        wf.enable_complexity_routing(simple_generator=micro_prime_gen)

        feature = _make_feature(metadata={})
        feature.generated_files = []

        # SIMPLE: single new file, small LOC, full manifest coverage, no callers
        with patch(
            "startd8.complexity.extract_signals_from_feature",
            return_value=TaskComplexitySignals(
                target_file_count=1,
                estimated_loc=20,
                edit_mode="create",
                manifest_coverage="full",
                blast_radius=0,
                caller_count=0,
            ),
        ):
            wf.develop_feature(feature)

        micro_prime_gen.generate.assert_called_once()
        default_gen.generate.assert_not_called()
        assert feature.metadata["_complexity_tier"] == "simple"
