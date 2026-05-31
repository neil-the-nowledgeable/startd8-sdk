"""Tests for the descriptor→manifest_declared bridge (REQ-AAO-008)."""

from startd8.observability.manifest import MetricDescriptor, ObservabilityManifest
from startd8.observability.onboarding_bridge import (
    build_sdk_self_instrumentation_hint,
    manifest_to_declared_metrics,
)


def _manifest(*metrics):
    return ObservabilityManifest(metrics=list(metrics))


def test_entries_use_exported_name_and_type_and_route_state():
    man = _manifest(
        MetricDescriptor(name="startd8.session.cost.total", instrument="counter", unit="USD",
                         description="d", category="ai_agent_observability", orientation="system"),
        MetricDescriptor(name="startd8.active.sessions", instrument="up_down_counter", unit="s",
                         description="d", category="ai_agent_observability", orientation="system"),
    )
    entries = manifest_to_declared_metrics(man)
    by_name = {e["name"]: e for e in entries}

    assert "startd8_session_cost_total" in by_name        # exported (dot->underscore)
    assert by_name["startd8_session_cost_total"]["type"] == "counter"
    assert by_name["startd8_active_sessions"]["type"] == "gauge"   # up_down_counter -> gauge
    for e in entries:
        assert e["source"] == "manifest"
        assert e["route_state"] == "sdk_emitted"
        assert e["category"] == "ai_agent_observability"
        assert e["orientation"] == "system"


def test_unset_axes_are_omitted():
    man = _manifest(
        MetricDescriptor(name="x.y", instrument="counter", unit="1", description="d"),
    )
    e = manifest_to_declared_metrics(man)[0]
    assert "category" not in e and "orientation" not in e
    assert e["route_state"] == "sdk_emitted"


def test_produced_from_manifest_not_hand_authored():
    # R1-S5: mutating a descriptor changes the corresponding manifest_declared entry
    # (a hand-authored copy would not track the change).
    desc = MetricDescriptor(name="startd8.cost.total", instrument="counter", unit="USD",
                            description="d", category="ai_agent_observability", orientation="system")
    man = _manifest(desc)
    before = manifest_to_declared_metrics(man)[0]
    assert before["category"] == "ai_agent_observability"

    desc.category = "project_observability"  # mutate the source descriptor
    after = manifest_to_declared_metrics(man)[0]
    assert after["category"] == "project_observability"
    assert before["category"] != after["category"]


def test_real_manifest_bridges_without_error():
    entries = manifest_to_declared_metrics()
    assert entries, "expected the real manifest to produce declared metrics"
    names = {e["name"] for e in entries}
    # Exported names of the renamed cost metrics are both present and distinct.
    assert "startd8_cost_total" in names              # global (costs module)
    assert "startd8_session_cost_total" in names      # per-session (disambiguated)


def test_self_instrumentation_hint_shape():
    hint = build_sdk_self_instrumentation_hint()
    assert hint["service_id"] == "startd8"
    assert hint["transport"] == "otlp"
    assert hint["metrics"]["manifest_declared"]
