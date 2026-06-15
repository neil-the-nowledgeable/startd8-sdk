"""Tests for declarative observability policy maps (obs_config) — extends the persona loader pattern."""

from pathlib import Path

from startd8.observability.obs_config import (
    load_default_thresholds,
    load_quality_thresholds,
    load_severity_map,
)

_BENCH_MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "docs/design/deterministic-sre-onboarding/benchmark.contextcore.yaml"
)


# --- defaults (no manifest) fall back to the hardcoded maps ---

def test_severity_defaults():
    m = load_severity_map(None)
    assert m["critical"] == "critical" and m["medium"] == "warning" and m["low"] == "info"


def test_default_thresholds_defaults():
    m = load_default_thresholds(None)
    assert "availability" in m and "latency_p99" in m


def test_quality_thresholds_defaults():
    assert load_quality_thresholds(None) == {"warning": 0.6, "healthy": 0.8}


# --- manifest override merges over the defaults ---

def test_severity_override_merges():
    manifest = {"spec": {"observability": {"severityMapping": {"medium": "critical"}}}}
    m = load_severity_map(manifest)
    assert m["medium"] == "critical"   # overridden
    assert m["low"] == "info"          # default preserved


def test_quality_threshold_override():
    manifest = {"spec": {"observability": {"qualityThresholds": {"warning": 0.7}}}}
    m = load_quality_thresholds(manifest)
    assert m["warning"] == 0.7 and m["healthy"] == 0.8


# --- the maps reach BusinessContext + flow into the generator severity ---

def test_business_context_carries_maps_and_severity_flows():
    from types import SimpleNamespace

    from startd8.observability.artifact_generator_context import load_business_context

    ctx = load_business_context(_BENCH_MANIFEST, {})
    assert ctx.severity_map and ctx.default_thresholds and ctx.quality_thresholds

    # an override on a BusinessContext changes the derived alert severity (no code change)
    from startd8.observability.artifact_generator_generators import _severity_for

    biz = SimpleNamespace(criticality="medium", severity_map={"medium": "critical"})
    assert _severity_for(biz, []) == "critical"
    # default path (no map) still works
    biz2 = SimpleNamespace(criticality="medium", severity_map=None)
    assert _severity_for(biz2, []) == "warning"
