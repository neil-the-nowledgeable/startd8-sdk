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

        evt = EventTypeDescriptor(name="TEST_EVENT", event_group="test")
        assert EventTypeDescriptor.from_dict(evt.to_dict()) == evt


# ---------------------------------------------------------------------------
# Taxonomy axes (REQ-OBS-SHARED-001) + collector pass-through (R3-F1)
# ---------------------------------------------------------------------------


class TestTaxonomyAxes:
    """category/orientation fields, their serialization, and the collector
    pass-through that the R3 review found was silently dropping fields."""

    def test_descriptor_axes_round_trip(self):
        m = MetricDescriptor(
            name="x.y", instrument="counter", unit="1", description="d",
            category="ai_agent_observability", orientation="system",
        )
        m2 = MetricDescriptor.from_dict(m.to_dict())
        assert m2.category == "ai_agent_observability"
        assert m2.orientation == "system"

        s = SpanDescriptor(
            name_pattern="a.{id}", category="project_observability", orientation="system",
        )
        s2 = SpanDescriptor.from_dict(s.to_dict())
        assert s2.category == "project_observability"
        assert s2.orientation == "system"

    def test_empty_axes_omitted(self):
        # Backward-compat: unset axes do not appear in the serialized form.
        d = MetricDescriptor(
            name="a", instrument="counter", unit="1", description="d"
        ).to_dict()
        assert "category" not in d
        assert "orientation" not in d

    def test_collector_passes_axes_and_optional_fields_through(self, monkeypatch):
        # R3-F1 (critical): collect_*_descriptors() must NOT drop category/
        # orientation/prometheus_name/dashboard_hints from the _OTEL_DESCRIPTORS
        # dicts, or the generated manifest carries empty axes.
        from startd8.observability import collector

        fake = {
            "metrics": [{
                "name": "fake.metric", "instrument": "counter", "unit": "1",
                "description": "d", "prometheus_name": "fake_metric",
                "dashboard_hints": {"panel": "stat"},
                "category": "ai_agent_observability", "orientation": "system",
            }],
            "spans": [{
                "name_pattern": "fake.{id}",
                "category": "project_observability", "orientation": "system",
            }],
        }
        monkeypatch.setattr(collector, "_load_descriptors", lambda mp, sf: fake)

        m = next(x for x in collector.collect_metric_descriptors() if x.name == "fake.metric")
        assert m.category == "ai_agent_observability"
        assert m.orientation == "system"
        assert m.prometheus_name == "fake_metric"
        assert m.dashboard_hints == {"panel": "stat"}
        assert m.to_dict()["category"] == "ai_agent_observability"

        s = next(x for x in collector.collect_span_descriptors() if x.name_pattern == "fake.{id}")
        assert s.category == "project_observability"
        assert s.orientation == "system"

    def test_enum_axis_serializes_to_plain_string(self):
        # Defensive: a Category/Orientation enum member must serialize to its
        # str value, not a PyYAML !!python/object tag.
        from startd8.observability.taxonomy_enums import Category, Orientation

        d = MetricDescriptor(
            name="e", instrument="counter", unit="1", description="d",
            category=Category.AI_AGENT, orientation=Orientation.SYSTEM,
        ).to_dict()
        assert d["category"] == "ai_agent_observability"
        assert d["orientation"] == "system"
        assert "python/object" not in yaml.dump(d)


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
    """Declared metrics are real — parity, not a brittle magic count (REQ-OBS-SHARED-002)."""

    def test_declared_metrics_are_emitted(self):
        # Replaces the old `len(metrics) == 12` magic assertion: the meaningful
        # invariant is that every DECLARED metric has an actual emission site.
        from startd8.observability.parity import check_metric_bijection

        manifest = generate_manifest()
        assert manifest.metrics, "manifest declares no metrics"
        result = check_metric_bijection(manifest)
        assert result.declared_not_emitted == [], (
            f"declared metrics with no emission site: {result.declared_not_emitted}"
        )

    def test_no_hard_parity_violations_in_bootstrap(self):
        # Bootstrap mode: no declared-not-emitted, no un-owned emitted-not-declared,
        # no un-tolerated exported-name collisions. Known gaps live in the registry.
        from startd8.observability.parity import run_parity

        result = run_parity()
        assert result.ok, (
            f"hard parity violations: emitted_not_declared={result.emitted_not_declared}, "
            f"collisions={result.exported_name_collisions}, "
            f"declared_not_emitted={result.declared_not_emitted}"
        )


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


class TestEventTypes:
    """Count matches len(EventType)."""

    def test_all_event_types_present(self):
        from startd8.events.types import EventType

        manifest = generate_manifest()
        assert len(manifest.event_types) == len(EventType)

    def test_event_groups_assigned(self):
        # EventTypeDescriptor.category was renamed to event_group (REQ-OBS-SHARED-001a).
        manifest = generate_manifest()
        for evt in manifest.event_types:
            assert evt.event_group, f"Event {evt.name} has no event_group"
            assert evt.event_group != "unknown", f"Event {evt.name} has 'unknown' event_group"

    def test_legacy_category_key_deserializes_via_alias(self):
        # R2-F4: saved YAML using the old `category` key must still load for one
        # release; output uses `event_group` only.
        legacy = {"name": "AGENT_CALL_START", "category": "agent"}
        evt = EventTypeDescriptor.from_dict(legacy)
        assert evt.event_group == "agent"
        assert evt.to_dict() == {"name": "AGENT_CALL_START", "event_group": "agent"}


# ---------------------------------------------------------------------------
# Spans
# ---------------------------------------------------------------------------


class TestSpans:
    """Span descriptors are present and correspond to real span sites."""

    def test_spans_present_and_have_sites(self):
        # Replaces the old `len(spans) == 9` magic assertion: assert spans exist and
        # each declared name-pattern matches a real span site (or is dynamic).
        from startd8.observability.parity import check_span_name_patterns

        manifest = generate_manifest()
        assert manifest.spans, "manifest declares no spans"
        missing = check_span_name_patterns(manifest)
        assert missing == [], f"declared span patterns with no runtime site: {missing}"

    def test_known_span_patterns_present(self):
        # Content check made non-brittle: the known patterns are a SUBSET (additions
        # are allowed without breaking the test).
        manifest = generate_manifest()
        patterns = {s.name_pattern for s in manifest.spans}
        expected = {
            "agent.generate:{agent_name}",
            "workflow.{workflow_id}",
            "pipeline.{name}",
            "pipeline.{name}.step.{step_name}",
            "{caller_defined_name}",
            "artisan.workflow.{workflow_id}",
            "artisan.workflow.{workflow_id}.phase.{phase}",
            "PhaseRunner.run",
            "phase.{phase_type}.attempt.{attempt_number}",
        }
        assert expected <= patterns, f"missing expected span patterns: {expected - patterns}"


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
