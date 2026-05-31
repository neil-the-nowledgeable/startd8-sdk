"""Tests for taxonomy-axis completeness (REQ-OBS-SHARED-001, R3-F5)."""

from startd8.observability.manifest import (
    MetricDescriptor,
    ObservabilityManifest,
    SpanDescriptor,
)
from startd8.observability.manifest_validation import (
    GRANDFATHERED_SOURCES,
    check_axis_completeness,
)


def test_real_manifest_has_no_axis_violations():
    # With the current grandfather list, every non-grandfathered descriptor is
    # annotated (agent-obs modules) and the rest are tolerated.
    violations = check_axis_completeness()
    assert violations == [], [f"{v.source_file}:{v.name} {v.problems}" for v in violations]


def test_unset_axes_outside_grandfather_is_a_violation():
    man = ObservabilityManifest(metrics=[
        MetricDescriptor(name="x.y", instrument="counter", unit="1", description="d",
                         source_file="src/startd8/new_module.py"),  # not grandfathered, unset
    ])
    violations = check_axis_completeness(man, grandfathered=frozenset())
    assert len(violations) == 1
    assert "category unset" in violations[0].problems
    assert "orientation unset" in violations[0].problems


def test_grandfathered_unset_is_tolerated():
    src = next(iter(GRANDFATHERED_SOURCES))
    man = ObservabilityManifest(spans=[
        SpanDescriptor(name_pattern="phase.{x}", source_file=src),  # unset but grandfathered
    ])
    assert check_axis_completeness(man) == []


def test_set_but_invalid_axis_is_always_a_violation_even_if_grandfathered():
    src = next(iter(GRANDFATHERED_SOURCES))
    man = ObservabilityManifest(metrics=[
        MetricDescriptor(name="x.y", instrument="counter", unit="1", description="d",
                         source_file=src, category="not_a_real_category", orientation="sideways"),
    ])
    violations = check_axis_completeness(man)
    assert len(violations) == 1
    probs = violations[0].problems
    assert any("category 'not_a_real_category'" in p for p in probs)
    assert any("orientation 'sideways'" in p for p in probs)
