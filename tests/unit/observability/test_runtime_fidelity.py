# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Tests for the runtime observability-fidelity core (B1 runtime).

Fully fixture-driven — a fake collector (injected launcher + scrape fn) + a fixtured
`/metrics`, so the parser / binding / lifecycle logic is exercised with no live otelcol.
"""

from __future__ import annotations

import pytest

from startd8.observability.metric_descriptor import profile_for
from startd8.observability.runtime_fidelity import (
    CollectorUnavailable,
    RuntimeBinding,
    SpanMetricsCollector,
    check_descriptor_binding,
    parse_prometheus_text,
    resolve_instrumentation,
)

_METRICS = """# HELP calls_total spanmetrics
# TYPE calls_total counter
calls_total{service_name="checkoutservice",status_code="STATUS_CODE_OK",span_name="Charge"} 8
calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR",span_name="Charge"} 3
duration_milliseconds_bucket{service_name="checkoutservice",le="100"} 5
"""

_METRICS_ZERO = 'calls_total{service_name="checkoutservice",status_code="STATUS_CODE_OK"} 0\n'


class _FakeProc:
    pid = 999999999  # nonexistent — teardown's killpg is best-effort/guarded


# ─────────────────────────────── parser ────────────────────────────────────


def test_parse_prometheus_text():
    parsed = parse_prometheus_text(_METRICS)
    assert set(parsed) == {"calls_total", "duration_milliseconds_bucket"}
    assert len(parsed["calls_total"]) == 2
    assert parsed["calls_total"][0]["service_name"] == "checkoutservice"


# ──────────────────────── descriptor binding (4 axes) ──────────────────────


def test_check_descriptor_binding_all_axes():
    desc = profile_for("span-metrics-connector")
    r = check_descriptor_binding(parse_prometheus_text(_METRICS), desc, "checkoutservice")
    assert r.outcome == "bound" and r.coverage == 1.0
    assert all(r.axes.values())


def test_check_descriptor_binding_partial():
    desc = profile_for("span-metrics-connector")
    # wrong service id → service_identity axis unbound; others still present
    r = check_descriptor_binding(parse_prometheus_text(_METRICS), desc, "otherservice")
    assert r.outcome == "bound" and 0.0 < r.coverage < 1.0
    assert r.axes["service_identity"] is False
    assert r.axes["throughput_metric"] is True


def test_check_descriptor_binding_wrong_profile_low():
    # semconv referenced against a span-metrics /metrics → throughput name absent
    desc = profile_for("semconv-http")
    r = check_descriptor_binding(parse_prometheus_text(_METRICS), desc, "checkoutservice")
    assert r.axes["throughput_metric"] is False


# ─────────────────────── instrumentation resolution ────────────────────────


def test_resolve_instrumentation_python():
    spec = resolve_instrumentation("python", otlp_endpoint="127.0.0.1:4317", service_id="checkout")
    assert spec.argv_prefix == ["opentelemetry-instrument"]
    assert spec.env["OTEL_TRACES_EXPORTER"] == "otlp"
    assert spec.env["OTEL_SERVICE_NAME"] == "checkout"


def test_resolve_instrumentation_node():
    spec = resolve_instrumentation("nodejs", otlp_endpoint="127.0.0.1:4317", service_id="ad")
    assert "--require" in spec.env["NODE_OPTIONS"]


def test_resolve_instrumentation_go_unsupported():
    assert resolve_instrumentation("go", otlp_endpoint="127.0.0.1:4317", service_id="checkout") is None


# ─────────────────────────── collector lifecycle ───────────────────────────


def _collector(tmp_path, scrape_returns, ready_timeout_s=1.0):
    return SpanMetricsCollector(
        "otelcol-contrib", tmp_path,
        launcher=lambda argv, cwd: _FakeProc(),
        scrape_fn=lambda url: scrape_returns(),
        ready_timeout_s=ready_timeout_s,
    )


def test_collector_ready_and_binds(tmp_path):
    desc = profile_for("span-metrics-connector")
    with _collector(tmp_path, lambda: _METRICS) as c:
        r = c.poll_binding(desc, "checkoutservice", settle_s=0.1, cap_s=1.0)
    assert r.outcome == "bound" and r.coverage == 1.0
    # the collector config was written into the workdir
    assert (tmp_path / "otelcol-spanmetrics.yaml").exists()


def test_collector_no_telemetry_on_zero_throughput(tmp_path):
    desc = profile_for("span-metrics-connector")
    with _collector(tmp_path, lambda: _METRICS_ZERO) as c:
        r = c.poll_binding(desc, "checkoutservice", settle_s=0.1, cap_s=0.4)
    assert r.outcome == "no_telemetry" and r.coverage is None  # excluded, not 0.0


def test_collector_unavailable_when_never_ready(tmp_path):
    c = _collector(tmp_path, lambda: None, ready_timeout_s=0.2)
    with pytest.raises(CollectorUnavailable):
        c.__enter__()


def test_runtime_binding_to_dict():
    d = RuntimeBinding(outcome="bound", coverage=0.75, axes={"throughput_metric": True}).to_dict()
    assert d["outcome"] == "bound" and d["coverage"] == 0.75


# ─────────────────── probe orchestrator (executor seam) ─────────────────────

from startd8.observability.runtime_fidelity import probe_service_runtime_observability


def test_probe_bound_when_instrumentable_and_collector_present(tmp_path, monkeypatch):
    import startd8.observability.runtime_fidelity as rf
    monkeypatch.setattr(rf, "find_collector_binary", lambda explicit=None: "otelcol-contrib")
    desc = profile_for("span-metrics-connector")
    ran = {}

    def _run(argv, env):
        ran["argv"], ran["env"] = argv, env
        return "SR"

    sr, obs = probe_service_runtime_observability(
        service_id="checkoutservice", language="python", descriptor=desc, workdir=tmp_path,
        argv=["python3", "app.py"], extra_env={"PORT": "1"}, run_service=_run,
        launcher=lambda a, cwd: _FakeProc(), scrape_fn=lambda url: _METRICS, settle_s=0.1, cap_s=1.0,
    )
    assert sr == "SR"
    assert obs["outcome"] == "bound" and obs["coverage"] == 1.0
    assert ran["argv"][0] == "opentelemetry-instrument"          # instrumented
    assert ran["env"]["OTEL_TRACES_EXPORTER"] == "otlp"


def test_probe_degraded_for_go_runs_service_plainly(tmp_path):
    desc = profile_for("semconv-grpc")
    ran = {}

    def _run(a, e):
        ran["argv"] = a
        return "SR"

    sr, obs = probe_service_runtime_observability(
        service_id="checkoutservice", language="go", descriptor=desc, workdir=tmp_path,
        argv=["./server"], extra_env={"PORT": "1"}, run_service=_run,
    )
    assert sr == "SR" and obs["outcome"] == "degraded"
    assert ran["argv"] == ["./server"]                            # NOT instrumented — ran plainly


def test_probe_degraded_when_no_collector_binary(tmp_path, monkeypatch):
    import startd8.observability.runtime_fidelity as rf
    monkeypatch.setattr(rf, "find_collector_binary", lambda explicit=None: None)
    sr, obs = probe_service_runtime_observability(
        service_id="s", language="python", descriptor=profile_for("semconv-http"), workdir=tmp_path,
        argv=["python3", "app.py"], extra_env={}, run_service=lambda a, e: "SR",
    )
    assert sr == "SR" and obs["outcome"] == "degraded" and "binary not found" in obs["reason"]
