# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""FR-11: compare-live gate metrics emit to OTel (in-memory reader — no exporter/network)."""

from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry")  # optional 'all'/'otel' extra — skip on the dev-only CI install

from opentelemetry import metrics as otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from startd8.observability import compare_live_metrics as clm
from startd8.observability.compare import ComparisonReport
from startd8.observability.validate_promql import ExprVerdict, FidelityReport
from startd8.observability import compare_live


def _report(status="fail"):
    fid = FidelityReport(
        status=status, reason="x", queries_replayed=3, coverage=0.25, min_coverage=1.0,
        binding_coverage=0.25,
        verdicts=[ExprVerdict("web", "latency", "histogram(x)", "slos/web.yaml", 0, "fail")],
    )
    return compare_live.build_live_comparison(ComparisonReport(emitted=[], gaps={}), fid, {})


@pytest.fixture()
def in_memory_metrics(monkeypatch):
    """A real MeterProvider + in-memory reader wired into the compare_live_metrics singleton."""
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    # point the module's get_meter at this provider, and reset its lazy singleton
    monkeypatch.setattr(clm, "_otel_metrics", otel_metrics)
    monkeypatch.setattr(otel_metrics, "get_meter", lambda name: provider.get_meter(name))
    monkeypatch.setattr(clm, "_GATE_METRICS", clm._GateMetrics())
    return reader


def _collect(reader):
    """{metric_name: [data_points]} from the in-memory reader."""
    out = {}
    data = reader.get_metrics_data()
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                out[m.name] = list(m.data.data_points)
    return out


def test_records_gate_runs_and_histograms(in_memory_metrics):
    ok = clm.record_gate_metrics(_report("fail"), new_fail_count=1, subject="mysubject:1")
    assert ok is True
    metrics = _collect(in_memory_metrics)
    runs = metrics["startd8.observability.compare_live.gate_runs"]
    assert runs[0].value == 1
    assert runs[0].attributes["status"] == "fail"
    assert runs[0].attributes["subject"] == "mysubject:1"
    assert metrics["startd8.observability.compare_live.dead_sli_count"][0].count == 1
    assert metrics["startd8.observability.compare_live.new_fail_count"][0].sum == 1
    cov = metrics["startd8.observability.compare_live.binding_coverage"][0]
    assert cov.sum == pytest.approx(0.25)


# ─────────────────────── per-service coverage (REQ-TCP-112) ─────────────────

from startd8.observability import coverage_reconcile as cr  # noqa: E402


def _service_records():
    live = {
        "report_version": 2, "status": "fail", "reason": "x",
        "tier_a": {"gaps": {}},
        "tier_b": {
            "per_service": {
                "web": {"total": 1, "passed": 1, "coverage": 1.0, "signals": {}},
                "cart": {"total": 1, "passed": 0, "coverage": 0.0, "signals": {}},
            },
            "target_drift": {"declared_absent": ["pay"], "checked": True},
            "verdicts": [],
        },
        "pending_verdicts": [],
    }
    recs = cr.reconcile(live, criticality_map={"web": "critical", "cart": "critical", "pay": "high"})
    return [r.to_dict() for r in recs]


def test_service_coverage_emits_per_service_histogram_and_presence(in_memory_metrics):
    n = clm.record_service_coverage(_service_records(), subject="boutique:1")
    assert n == 3
    metrics = _collect(in_memory_metrics)

    # histogram only for numeric-coverage services (web=1.0, cart=0.0), NOT declared-absent pay
    cov = metrics["startd8.observability.compare_live.service_binding_coverage"]
    by_service = {p.attributes["service"]: p for p in cov}
    assert set(by_service) == {"web", "cart"}
    assert by_service["web"].sum == pytest.approx(1.0)
    assert by_service["web"].attributes["criticality"] == "critical"
    assert by_service["web"].attributes["subject"] == "boutique:1"

    # presence counter carries EVERY service incl. declared_absent, with its status
    pres = metrics["startd8.observability.compare_live.service_presence"]
    status_by_service = {p.attributes["service"]: p.attributes["presence_status"] for p in pres}
    assert status_by_service == {"web": "bound", "cart": "no_telemetry", "pay": "declared_absent"}


def test_service_coverage_is_noop_when_meter_unavailable(monkeypatch):
    monkeypatch.setattr(clm, "_GATE_METRICS", clm._GateMetrics())
    monkeypatch.setattr(clm._otel_metrics, "get_meter",
                        lambda name: (_ for _ in ()).throw(RuntimeError("no provider")))
    assert clm.record_service_coverage(_service_records(), subject="s") == 0


def test_subject_label_prefers_image_then_hostname_never_full_url():
    assert clm.subject_label("img:1", None) == "img:1"
    # a URL with credentials/params → only the hostname is used (FR-7 redaction)
    assert clm.subject_label(None, "http://user:sekret@prom.internal:9090/x?t=1") == "prom.internal"
    assert clm.subject_label(None, None) == "unknown"


def test_record_is_noop_when_otel_meter_unavailable(monkeypatch):
    # simulate get_meter raising (no provider / broken) → returns False, no exception
    monkeypatch.setattr(clm, "_GATE_METRICS", clm._GateMetrics())
    monkeypatch.setattr(clm._otel_metrics, "get_meter",
                        lambda name: (_ for _ in ()).throw(RuntimeError("no provider")))
    assert clm.record_gate_metrics(_report("pass"), new_fail_count=0, subject="s") is False


@pytest.mark.skipif(not clm._OTEL_AVAILABLE, reason="OTel not installed")
def test_cli_emit_metrics_note_without_endpoint(monkeypatch, tmp_path):
    """--emit-metrics with no OTEL endpoint → prints the 'nothing emitted' note, gate unaffected."""
    from typer.testing import CliRunner
    from startd8.observability import compare_live as cl
    from startd8.observability.cli import observability_app

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    # force record to no-op regardless of ambient provider
    monkeypatch.setattr(
        "startd8.observability.compare_live_metrics.record_gate_metrics",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(cl, "run_live_comparison", lambda **kw: _report("fail"))
    manifest = tmp_path / "m.yaml"
    manifest.write_text("fr_coverage: {}\n")
    res = CliRunner().invoke(
        observability_app,
        ["compare-live", "-m", str(manifest), "--subject-image", "x:1", "--emit-metrics"],
    )
    assert "nothing emitted" in res.output
    assert res.exit_code == 2  # the gate verdict (fail) is unaffected by metrics
