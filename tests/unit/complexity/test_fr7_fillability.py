"""RUN-007 FR-7 (Step 5): an empty-fillable feature must not classify SIMPLE."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from startd8.complexity.models import TaskComplexitySignals, ComplexityTier
from startd8.complexity.classifier import classify_tier
from startd8.complexity.signals import extract_signals_from_feature


def _simple_signals(**kw):
    """Signals that otherwise satisfy every SIMPLE condition."""
    base = dict(
        manifest_coverage="full", blast_radius=0, edit_mode="create",
        caller_count=0, estimated_loc=10, target_file_count=1,
    )
    base.update(kw)
    return TaskComplexitySignals(**base)


@pytest.mark.unit
class TestFr7ClassifierGuard:
    def test_empty_fillable_is_not_simple(self):
        tier, reason = classify_tier(_simple_signals(has_fillable_elements=False))
        assert tier != ComplexityTier.SIMPLE
        assert "FR-7" in reason

    def test_fillable_stays_simple(self):
        tier, _ = classify_tier(_simple_signals(has_fillable_elements=True))
        assert tier == ComplexityTier.SIMPLE

    def test_unknown_stays_simple(self):
        # default None (no manifest) → guard does not fire; gate stays authoritative
        tier, _ = classify_tier(_simple_signals())
        assert tier == ComplexityTier.SIMPLE


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
class TestFr7SignalPopulation:
    def test_class_only_spec_not_fillable(self, tmp_path):
        m = _manifest({"lib/value-model.ts": _spec([{"kind": "class", "name": "value-model"}])})
        s = extract_signals_from_feature(_feature(["lib/value-model.ts"]), tmp_path, manifest=m)
        assert s.has_fillable_elements is False

    def test_function_spec_fillable(self, tmp_path):
        m = _manifest({"lib/db.ts": _spec([{"kind": "function", "name": "getClient"}])})
        s = extract_signals_from_feature(_feature(["lib/db.ts"]), tmp_path, manifest=m)
        assert s.has_fillable_elements is True

    def test_registry_config_is_fillable_tiebreak(self, tmp_path):
        # next.config.mjs matches FRAMEWORK_CONFIG_DEFAULTS even with empty
        # elements → treated as fillable so it stays SIMPLE ($0.00 registry path)
        m = _manifest({"next.config.mjs": _spec([])})
        s = extract_signals_from_feature(_feature(["next.config.mjs"]), tmp_path, manifest=m)
        assert s.has_fillable_elements is True

    def test_no_manifest_is_unknown(self, tmp_path):
        s = extract_signals_from_feature(_feature(["x.ts"]), tmp_path)
        assert s.has_fillable_elements is None
