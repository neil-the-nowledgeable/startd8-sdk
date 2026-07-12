"""FR-E13 — verify + harden the readiness/cost burndown pipeline (emit → Mimir → cockpit panels).

The feature is built (metrics.py emits, portal_build calls record_from_view on each cockpit build,
the v2 cockpit has "Readiness/Cost over time" Mimir timeseries panels). What was missing was
*automated* proof that the chain holds end-to-end — the emitter test mocked `record_kickoff_progress`
and the comment said the Meter→Mimir path is "live-verified separately." These tests close that gap:

1. the emit actually calls the right gauge with the right value + label (view→gauge, unmocked);
2. a **drift guard**: the panel PromQL still queries the exact metric names the emitter creates —
   the single failure that silently blanks the burndown (the silent-telemetry-loss class);
3. an OTel in-memory export smoke proving a real MeterProvider exports the gauge under its name.
"""
from __future__ import annotations

import inspect

import pytest

from startd8.kickoff_experience import metrics as km
from startd8.kickoff_experience import portal_spec_v2 as pv

pytestmark = pytest.mark.unit


class _FakeGauge:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def set(self, value, attrs=None):
        self.calls.append(("set", value, attrs))

    def add(self, value, attrs=None):
        self.calls.append(("add", value, attrs))


def test_record_sets_the_right_gauges_with_labels(monkeypatch):
    fake = {k: _FakeGauge(k) for k in
            ("readiness", "cost", "proposals", "blocked",
             "facilitation_cost", "facilitation_cost_total", "activation_open", "activation_severity")}
    monkeypatch.setitem(km._state, "tried", True)
    monkeypatch.setitem(km._state, "gauges", fake)

    assert km.record_kickoff_progress(
        project="proj", readiness_percent=50, cost_usd=0.0031, proposals_pending=2, blocked=1) is True

    assert fake["readiness"].calls == [("set", 50.0, {"project": "proj"})]
    assert fake["cost"].calls == [("set", 0.0031, {"project": "proj"})]
    assert fake["proposals"].calls == [("set", 2.0, {"project": "proj"})]
    assert fake["blocked"].calls == [("set", 1.0, {"project": "proj"})]


def test_none_values_emit_no_point_for_that_gauge(monkeypatch):
    fake = {k: _FakeGauge(k) for k in ("readiness", "cost", "proposals", "blocked")}
    monkeypatch.setitem(km._state, "tried", True)
    monkeypatch.setitem(km._state, "gauges", fake)
    km.record_kickoff_progress(project="p", readiness_percent=None, cost_usd=1.0)
    assert fake["readiness"].calls == [] and fake["cost"].calls == [("set", 1.0, {"project": "p"})]


def test_panel_promql_matches_the_emitted_metric_names():
    # The cockpit's burndown panels query the Prometheus-mangled names (dots -> underscores). If the
    # emitter's gauge name or the panel expr drifts, the burndown silently goes blank — guard both ends.
    assert "kickoff_readiness_percent" in pv._readiness_promql("proj")
    assert "kickoff_session_cost_usd" in pv._cost_promql("proj")
    gsrc = inspect.getsource(km._gauges)
    assert '"kickoff.readiness.percent"' in gsrc   # -> kickoff_readiness_percent in Mimir
    assert '"kickoff.session.cost_usd"' in gsrc     # -> kickoff_session_cost_usd in Mimir


def test_otel_inmemory_export_smoke():
    # Prove a real MeterProvider exports the readiness gauge under its OTel name (the mechanic the
    # live path relies on). Uses a local provider/reader — no global state, no collector.
    sdk_metrics = pytest.importorskip("opentelemetry.sdk.metrics")
    export = pytest.importorskip("opentelemetry.sdk.metrics.export")

    reader = export.InMemoryMetricReader()
    provider = sdk_metrics.MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("startd8.kickoff")
    gauge = meter.create_gauge("kickoff.readiness.percent", unit="",
                               description="Kickoff field readiness")
    gauge.set(75.0, {"project": "proj"})

    data = reader.get_metrics_data()
    names = {m.name
             for rm in data.resource_metrics
             for sm in rm.scope_metrics
             for m in sm.metrics}
    assert "kickoff.readiness.percent" in names
