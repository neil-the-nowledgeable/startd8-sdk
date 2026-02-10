"""Unit tests for the observability manifest."""

import os
from pathlib import Path

import pytest
import yaml

from startd8.observability.manifest import (
    AlertTemplate,
    DashboardRef,
    EventTypeDescriptor,
    LabelDescriptor,
    MetricDescriptor,
    ObservabilityManifest,
    SLOTemplate,
    SpanDescriptor,
    generate_manifest,
)

# Locate the committed YAML relative to repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMITTED_YAML = _REPO_ROOT / "docs" / "capability-index" / "startd8.observability.manifest.yaml"


# ---------------------------------------------------------------------------
# Round-trip serialization
# ---------------------------------------------------------------------------


class TestManifestRoundTrip:
    """from_yaml(to_yaml()) produces identical manifest."""

    def test_round_trip_via_dict(self):
        manifest = generate_manifest()
        d = manifest.to_dict()
        restored = ObservabilityManifest.from_dict(d)

        assert restored.manifest_id == manifest.manifest_id
        assert len(restored.metrics) == len(manifest.metrics)
        assert len(restored.spans) == len(manifest.spans)
        assert len(restored.event_types) == len(manifest.event_types)
        assert len(restored.dashboards) == len(manifest.dashboards)

    def test_round_trip_via_yaml(self, tmp_path):
        manifest = generate_manifest()
        yaml_str = manifest.to_yaml()

        yaml_file = tmp_path / "manifest.yaml"
        yaml_file.write_text(yaml_str, encoding="utf-8")

        restored = ObservabilityManifest.from_yaml(str(yaml_file))

        assert restored.manifest_id == manifest.manifest_id
        assert len(restored.metrics) == len(manifest.metrics)
        assert len(restored.spans) == len(manifest.spans)
        assert len(restored.event_types) == len(manifest.event_types)

        # Verify metric names match
        gen_names = {m.name for m in manifest.metrics}
        res_names = {m.name for m in restored.metrics}
        assert gen_names == res_names

    def test_individual_descriptor_round_trip(self):
        metric = MetricDescriptor(
            name="test.metric",
            instrument="counter",
            unit="USD",
            description="test",
            labels=["a", "b"],
        )
        assert MetricDescriptor.from_dict(metric.to_dict()) == metric

        span = SpanDescriptor(
            name_pattern="test.{id}",
            kind="CLIENT",
            attributes=["x", "y"],
            events=["evt"],
        )
        assert SpanDescriptor.from_dict(span.to_dict()) == span

        evt = EventTypeDescriptor(name="TEST_EVENT", category="test")
        assert EventTypeDescriptor.from_dict(evt.to_dict()) == evt


# ---------------------------------------------------------------------------
# Metric counts
# ---------------------------------------------------------------------------


class TestSessionMetrics:
    """7 metrics from session_tracking."""

    def test_all_session_metrics_present(self):
        manifest = generate_manifest()
        session_metrics = [
            m for m in manifest.metrics
            if m.source_file == "src/startd8/session_tracking.py"
        ]
        assert len(session_metrics) == 7

        expected = {
            "startd8_active_sessions",
            "startd8_requests_total",
            "startd8_tokens_total",
            "startd8_response_time_ms",
            "startd8_context_usage_ratio",
            "startd8_truncations_total",
            "startd8_cost_total",
        }
        actual = {m.name for m in session_metrics}
        assert actual == expected


class TestCostMetrics:
    """4 metrics from cost tracking."""

    def test_all_cost_metrics_present(self):
        manifest = generate_manifest()
        cost_metrics = [
            m for m in manifest.metrics
            if m.source_file == "src/startd8/costs/otel_metrics.py"
        ]
        assert len(cost_metrics) == 4

        expected = {
            "startd8.cost.total",
            "startd8.cost.input_tokens",
            "startd8.cost.output_tokens",
            "startd8.cost.per_request",
        }
        actual = {m.name for m in cost_metrics}
        assert actual == expected


class TestTotalMetricCount:
    """All 12 metrics present."""

    def test_total_metric_count(self):
        manifest = generate_manifest()
        assert len(manifest.metrics) == 12


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


class TestEventTypes:
    """Count matches len(EventType)."""

    def test_all_event_types_present(self):
        from startd8.events.types import EventType

        manifest = generate_manifest()
        assert len(manifest.event_types) == len(EventType)

    def test_event_categories_assigned(self):
        manifest = generate_manifest()
        for evt in manifest.event_types:
            assert evt.category, f"Event {evt.name} has no category"
            assert evt.category != "unknown", f"Event {evt.name} has 'unknown' category"


# ---------------------------------------------------------------------------
# Spans
# ---------------------------------------------------------------------------


class TestSpans:
    """5 span patterns exist."""

    def test_all_spans_present(self):
        manifest = generate_manifest()
        assert len(manifest.spans) == 5

    def test_span_patterns(self):
        manifest = generate_manifest()
        patterns = {s.name_pattern for s in manifest.spans}
        expected = {
            "agent.generate:{agent_name}",
            "workflow.{workflow_id}",
            "pipeline.{name}",
            "pipeline.{name}.step.{step_name}",
            "{caller_defined_name}",
        }
        assert patterns == expected


# ---------------------------------------------------------------------------
# Dashboard references
# ---------------------------------------------------------------------------


class TestDashboardRefs:
    """Refs match files in dashboards/."""

    def test_dashboard_refs_match_files(self):
        manifest = generate_manifest()
        dashboards_dir = _REPO_ROOT / "dashboards"

        if not dashboards_dir.is_dir():
            pytest.skip("dashboards/ directory not found")

        json_files = set(dashboards_dir.glob("*.json"))
        ref_paths = {_REPO_ROOT / d.file_path for d in manifest.dashboards}

        assert json_files == ref_paths, (
            f"Dashboard mismatch.\n"
            f"  Files: {sorted(p.name for p in json_files)}\n"
            f"  Refs:  {sorted(p.name for p in ref_paths)}"
        )

    def test_dashboard_count(self):
        manifest = generate_manifest()
        assert len(manifest.dashboards) == 4


# ---------------------------------------------------------------------------
# Drift detection (committed YAML matches code-derived sections)
# ---------------------------------------------------------------------------


class TestNoDrift:
    """Generated manifest matches committed YAML (code-derived sections)."""

    @pytest.fixture(autouse=True)
    def _require_committed_yaml(self):
        if not _COMMITTED_YAML.exists():
            pytest.skip("Committed manifest YAML not found")

    def test_no_metric_drift(self):
        generated = generate_manifest()
        committed = ObservabilityManifest.from_yaml(str(_COMMITTED_YAML))

        gen_names = {m.name for m in generated.metrics}
        com_names = {m.name for m in committed.metrics}

        assert gen_names == com_names, (
            f"Metric drift detected.\n"
            f"  New in code:     {sorted(gen_names - com_names)}\n"
            f"  Missing in code: {sorted(com_names - gen_names)}"
        )

    def test_no_span_drift(self):
        generated = generate_manifest()
        committed = ObservabilityManifest.from_yaml(str(_COMMITTED_YAML))

        gen_patterns = {s.name_pattern for s in generated.spans}
        com_patterns = {s.name_pattern for s in committed.spans}

        assert gen_patterns == com_patterns, (
            f"Span drift detected.\n"
            f"  New in code:     {sorted(gen_patterns - com_patterns)}\n"
            f"  Missing in code: {sorted(com_patterns - gen_patterns)}"
        )

    def test_no_event_drift(self):
        generated = generate_manifest()
        committed = ObservabilityManifest.from_yaml(str(_COMMITTED_YAML))

        gen_names = {e.name for e in generated.event_types}
        com_names = {e.name for e in committed.event_types}

        assert gen_names == com_names, (
            f"Event drift detected.\n"
            f"  New in code:     {sorted(gen_names - com_names)}\n"
            f"  Missing in code: {sorted(com_names - gen_names)}"
        )


# ---------------------------------------------------------------------------
# Committed YAML structural tests
# ---------------------------------------------------------------------------


class TestCommittedYAMLStructure:
    """The committed YAML file is valid and has expected sections."""

    @pytest.fixture(autouse=True)
    def _require_committed_yaml(self):
        if not _COMMITTED_YAML.exists():
            pytest.skip("Committed manifest YAML not found")

    def test_yaml_loads(self):
        with open(_COMMITTED_YAML) as f:
            data = yaml.safe_load(f)
        assert data["manifest_id"] == "startd8.observability"

    def test_has_slo_templates(self):
        manifest = ObservabilityManifest.from_yaml(str(_COMMITTED_YAML))
        assert len(manifest.slo_templates) >= 3

    def test_has_alert_templates(self):
        manifest = ObservabilityManifest.from_yaml(str(_COMMITTED_YAML))
        assert len(manifest.alert_templates) >= 3

    def test_has_resource_attributes(self):
        manifest = ObservabilityManifest.from_yaml(str(_COMMITTED_YAML))
        assert "service.name" in manifest.resource_attributes
        assert "io.contextcore.project.id" in manifest.resource_attributes
