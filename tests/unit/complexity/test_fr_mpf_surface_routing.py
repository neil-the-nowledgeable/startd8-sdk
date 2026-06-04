"""FR-MPF-2/3: forward-manifest surface-area signal + surface-aware MODERATE floor.

FR-MPF-2 adds ``manifest_element_count`` (computed in a single pass alongside the FR-7
fillability guard). FR-MPF-3 uses it to keep a *rich* spec off the no-LLM/economy SIMPLE
tier — emitting an explicit MODERATE floor (NOT COMPLEX: over-specified != under-specified,
and over-provisioning the premium tier is a cost regression). The guard ships DISABLED
(``manifest_element_simple_max == 0``) until calibrated against the FR-MPF-5 measurement.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from startd8.complexity.classifier import classify_tier
from startd8.complexity.models import (
    ComplexityRoutingConfig,
    ComplexityTier,
    TaskComplexitySignals,
)
from startd8.complexity.signals import extract_signals_from_feature


def _simple_signals(**kw):
    """Signals that otherwise satisfy every SIMPLE condition (fillable so FR-7 is quiet)."""
    base = dict(
        manifest_coverage="full", blast_radius=0, edit_mode="create",
        caller_count=0, estimated_loc=10, target_file_count=1,
        has_fillable_elements=True,
    )
    base.update(kw)
    return TaskComplexitySignals(**base)


@pytest.mark.unit
class TestFrMpf3RoutingGuard:
    def test_disabled_by_default_rich_spec_still_simple(self):
        # default config: manifest_element_simple_max == 0 → guard off → behaviour-preserving
        tier, _ = classify_tier(_simple_signals(manifest_element_count=99))
        assert tier == ComplexityTier.SIMPLE

    def test_rich_spec_gets_moderate_floor_when_enabled(self):
        cfg = ComplexityRoutingConfig(manifest_element_simple_max=5)
        tier, reason = classify_tier(_simple_signals(manifest_element_count=12), cfg)
        assert tier == ComplexityTier.MODERATE  # not SIMPLE, and NOT COMPLEX
        assert "FR-MPF-3" in reason

    def test_small_spec_still_simple_when_enabled(self):
        cfg = ComplexityRoutingConfig(manifest_element_simple_max=5)
        tier, _ = classify_tier(_simple_signals(manifest_element_count=3), cfg)
        assert tier == ComplexityTier.SIMPLE

    def test_genuine_complex_trigger_still_wins(self):
        cfg = ComplexityRoutingConfig(manifest_element_simple_max=5)
        # rich spec that ALSO trips a real COMPLEX trigger (blast radius) → COMPLEX, not MODERATE
        tier, _ = classify_tier(
            _simple_signals(manifest_element_count=12, blast_radius=99), cfg
        )
        assert tier == ComplexityTier.COMPLEX


def _manifest(specs):
    return SimpleNamespace(file_specs=specs)


def _spec(elements):
    return SimpleNamespace(elements=elements)


def _feature(target_files):
    f = MagicMock()
    f.target_files = target_files
    f.description = "implement it"
    f.metadata = {}
    f.estimated_loc = 10
    return f


@pytest.mark.unit
class TestFrMpf2SignalPopulation:
    def test_element_count_summed_across_targets(self, tmp_path):
        m = _manifest({
            "a.ts": _spec([{"kind": "function", "name": "f"}, {"kind": "function", "name": "g"}]),
            "b.ts": _spec([{"kind": "class", "name": "C"}]),
        })
        s = extract_signals_from_feature(_feature(["a.ts", "b.ts"]), tmp_path, manifest=m)
        assert s.manifest_element_count == 3

    def test_zero_without_manifest(self, tmp_path):
        s = extract_signals_from_feature(_feature(["x.ts"]), tmp_path)
        assert s.manifest_element_count == 0

    def test_empty_spec_is_zero(self, tmp_path):
        m = _manifest({"next.config.mjs": _spec([])})
        s = extract_signals_from_feature(_feature(["next.config.mjs"]), tmp_path, manifest=m)
        assert s.manifest_element_count == 0

    def test_single_pass_preserves_fillability(self, tmp_path):
        # the single-loop refactor must NOT change has_fillable_elements (FR-7 still works)
        m = _manifest({"lib/db.ts": _spec([{"kind": "function", "name": "getClient"}])})
        s = extract_signals_from_feature(_feature(["lib/db.ts"]), tmp_path, manifest=m)
        assert s.has_fillable_elements is True
        assert s.manifest_element_count == 1
