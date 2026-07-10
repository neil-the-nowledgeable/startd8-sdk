# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Tests for the live-validation harness (REQ_TARGET_METRIC_BINDING.md FR-8..10).

The Prometheus client is ALWAYS monkeypatched — no test hits a network. We
patch ``prometheus_query.instant_query_count`` / ``list_metric_names`` /
``label_values`` (the canonical, promoted client) at their module home so both
the direct ``run_validation`` calls and the CLI path use the fakes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from startd8.observability import prometheus_query, validate_promql
from startd8.observability.metric_descriptor import resolve_descriptor
from startd8.observability.validate_promql import (
    EXIT_FAIL,
    EXIT_PASS,
    EXIT_UNKNOWN,
    Auth,
    reconstruct_descriptors,
    run_validation,
)


# ─────────────────────────── fixtures / builders ───────────────────────────


def _write_alerts(artifacts: Path, service: str, exprs: dict) -> None:
    """Write an alerts/{service}-alerts.yaml with {alert_name: expr}."""
    (artifacts / "alerts").mkdir(parents=True, exist_ok=True)
    rules = [{"alert": name, "expr": expr} for name, expr in exprs.items()]
    doc = {"groups": [{"name": f"{service}.slo", "rules": rules}]}
    (artifacts / "alerts" / f"{service}-alerts.yaml").write_text(yaml.dump(doc))


def _write_slo(artifacts: Path, service: str, query: str) -> None:
    (artifacts / "slos").mkdir(parents=True, exist_ok=True)
    doc = {
        "apiVersion": "openslo/v1",
        "kind": "SLO",
        "metadata": {"name": f"{service}-availability"},
        "spec": {
            "indicator": {
                "spec": {
                    "ratioMetric": {
                        "total": {"metricSource": {"spec": {"query": query}}}
                    }
                }
            }
        },
    }
    (artifacts / "slos" / f"{service}-slo.yaml").write_text(yaml.dump(doc))


def _write_dashboard(artifacts: Path, service: str, expr: str) -> None:
    (artifacts / "dashboards").mkdir(parents=True, exist_ok=True)
    doc = {"panels": [{"title": "Throughput", "expr": expr}]}
    (artifacts / "dashboards" / f"{service}-dashboard-spec.yaml").write_text(yaml.dump(doc))


def _onboarding(tmp_path: Path, hints: dict) -> Path:
    """Write an onboarding-metadata.json with the given instrumentation_hints."""
    path = tmp_path / "onboarding-metadata.json"
    path.write_text(json.dumps({"instrumentation_hints": hints}))
    return path


def _semconv_onboarding(tmp_path: Path, service="checkoutservice") -> Path:
    return _onboarding(
        tmp_path,
        {
            service: {
                "transport": "http",
                "metrics": {
                    "convention_based": [
                        {"name": "http.server.duration", "type": "histogram"}
                    ]
                },
            }
        },
    )


# ───────────────────────────── all-pass (FR-8/10) ──────────────────────────


def test_all_pass_exit_zero_coverage_one(tmp_path, monkeypatch):
    artifacts = tmp_path / "art"
    _write_alerts(
        artifacts,
        "checkoutservice",
        {
            "checkoutserviceLatencyP99High": "histogram_quantile(0.99, rate(x[5m])) > 0.5",
            "checkoutserviceErrorRateHigh": "rate(y[5m]) > 0.01",
        },
    )
    onboarding = _semconv_onboarding(tmp_path)

    monkeypatch.setattr(prometheus_query, "instant_query_count", lambda *a, **k: 3)
    monkeypatch.setattr(prometheus_query, "list_metric_names", lambda *a, **k: ["x", "y"])
    monkeypatch.setattr(prometheus_query, "label_values", lambda *a, **k: ["checkoutservice"])

    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=1.0,
        auth=Auth(),
    )
    assert report.status == "pass"
    assert report.exit_code() == EXIT_PASS
    assert report.coverage == 1.0
    assert report.queries_replayed == 2
    assert all(v.verdict == "pass" for v in report.verdicts)


# ─────────────── span-metrics-vs-semconv 4-axis mismatch (FR-9) ─────────────


def test_span_metrics_mismatch_reports_all_axes(tmp_path, monkeypatch):
    # Generator emitted the semconv surface; live backend runs span-metrics.
    artifacts = tmp_path / "art"
    _write_alerts(
        artifacts,
        "checkoutservice",
        {
            "checkoutserviceErrorRateHigh": (
                'rate(http_server_duration_count{service="checkoutservice",'
                'status=~"5.."}[5m]) > 0.01'
            ),
            "checkoutserviceLatencyP99High": (
                'histogram_quantile(0.99, rate(http_server_duration_bucket'
                '{service="checkoutservice"}[5m])) > 0.5'
            ),
        },
    )
    onboarding = _semconv_onboarding(tmp_path)  # expected identity = semconv-http

    # Live system has ONLY span-metrics series.
    live_names = ["calls_total", "duration_milliseconds_bucket", "duration_milliseconds_count"]

    monkeypatch.setattr(prometheus_query, "instant_query_count", lambda *a, **k: 0)
    monkeypatch.setattr(prometheus_query, "list_metric_names", lambda *a, **k: live_names)
    # service label key "service" does not exist; span-metrics uses service_name.
    monkeypatch.setattr(prometheus_query, "label_values", lambda *a, **k: [])

    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=1.0,
        auth=Auth(),
    )
    assert report.status == "fail"
    assert report.exit_code() == EXIT_FAIL

    # Union of mismatched axes across the two exprs must include name + label
    # (+ selector + unit). All axes reported, not just the first.
    all_axes = set()
    for v in report.verdicts:
        all_axes.update(v.mismatched_axes)
    assert any(a.startswith("metric_name") for a in all_axes), all_axes
    assert "service_label_key" in all_axes, all_axes
    assert "error_selector" in all_axes, all_axes
    assert "unit" in all_axes, all_axes  # semconv 's' vs live 'ms'

    # Remediation names the real span-metrics shape.
    joined = " ".join(v.remediation for v in report.verdicts)
    assert "span-metrics" in joined

    # Probe budget respected per failed expr.
    assert report.per_axis  # rolled up


def test_diagnosis_does_not_short_circuit_first_axis(tmp_path, monkeypatch):
    # A single expr whose descriptor misses on >1 axis must report >1.
    artifacts = tmp_path / "art"
    _write_alerts(
        artifacts,
        "checkoutservice",
        {
            "checkoutserviceErrorRateHigh": (
                'rate(http_server_duration_count{service="checkoutservice",'
                'status=~"5.."}[5m]) > 0.01'
            )
        },
    )
    onboarding = _semconv_onboarding(tmp_path)
    monkeypatch.setattr(prometheus_query, "instant_query_count", lambda *a, **k: 0)
    monkeypatch.setattr(
        prometheus_query, "list_metric_names", lambda *a, **k: ["calls_total"]
    )
    monkeypatch.setattr(prometheus_query, "label_values", lambda *a, **k: [])

    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=1.0,
        auth=Auth(),
    )
    [v] = report.verdicts
    assert len(v.mismatched_axes) >= 2, v.mismatched_axes


# ─────────────────────── zero queries replayed (FR-10) ─────────────────────


def test_empty_artifacts_dir_is_unknown_not_pass(tmp_path, monkeypatch):
    artifacts = tmp_path / "art"
    artifacts.mkdir()
    onboarding = _semconv_onboarding(tmp_path)
    # Client would return >0 if called — but nothing should be replayed.
    monkeypatch.setattr(prometheus_query, "instant_query_count", lambda *a, **k: 5)

    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=1.0,
        auth=Auth(),
    )
    assert report.status == "unknown"
    assert report.exit_code() == EXIT_UNKNOWN
    assert report.exit_code() not in (EXIT_PASS,)
    assert report.queries_replayed == 0


# ─────────────────────── backend unreachable (FR-10) ──────────────────────


def test_backend_unreachable_is_unknown_not_pass(tmp_path, monkeypatch):
    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice", {"checkoutserviceLatencyP99High": "up"})
    onboarding = _semconv_onboarding(tmp_path)

    def _boom(*a, **k):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(prometheus_query, "instant_query_count", _boom)

    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=1.0,
        auth=Auth(),
    )
    assert report.status == "unknown"
    assert report.exit_code() == EXIT_UNKNOWN
    assert report.status != "pass"


# ─────────────────── coverage below threshold ⇒ non-zero (FR-10) ────────────


def test_coverage_below_min_exits_nonzero(tmp_path, monkeypatch):
    artifacts = tmp_path / "art"
    _write_alerts(
        artifacts,
        "checkoutservice",
        {
            "checkoutserviceLatencyP99High": "expr_pass",
            "checkoutserviceErrorRateHigh": "expr_fail",
        },
    )
    onboarding = _semconv_onboarding(tmp_path)

    def _count(base, expr, **k):
        return 4 if expr == "expr_pass" else 0

    monkeypatch.setattr(prometheus_query, "instant_query_count", _count)
    monkeypatch.setattr(prometheus_query, "list_metric_names", lambda *a, **k: [])
    monkeypatch.setattr(prometheus_query, "label_values", lambda *a, **k: [])

    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=1.0,
        auth=Auth(),
    )
    assert report.coverage == 0.5
    assert report.status == "fail"
    assert report.exit_code() == EXIT_FAIL
    assert report.exit_code() != 0


# ───────────────────────── credential redaction (FR-8b) ────────────────────


def test_credentials_never_appear_in_report(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMETHEUS_BEARER_TOKEN", "super-secret-token-123")
    monkeypatch.setenv("PROMETHEUS_ORG_ID", "tenant-xyz")

    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice", {"checkoutserviceLatencyP99High": "up"})
    onboarding = _semconv_onboarding(tmp_path)

    captured = {}

    def _count(base, expr, *, auth=None, **k):
        captured["auth"] = auth
        return 2

    monkeypatch.setattr(prometheus_query, "instant_query_count", _count)

    auth = Auth.from_env()
    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=1.0,
        auth=auth,
    )
    payload = validate_promql.redact(json.dumps(report.to_dict()), auth.redactions())
    assert "super-secret-token-123" not in payload
    assert "tenant-xyz" not in payload
    # The auth WAS threaded to the client (token used, just not leaked).
    assert captured["auth"].bearer_token == "super-secret-token-123"
    assert captured["auth"].headers()["X-Scope-OrgID"] == "tenant-xyz"


def test_auth_from_env_reads_bearer_and_org():
    a = Auth.from_env({"PROMETHEUS_BEARER_TOKEN": "tok", "X_SCOPE_ORGID": "t1"})
    assert a.headers()["Authorization"] == "Bearer tok"
    assert a.headers()["X-Scope-OrgID"] == "t1"
    assert set(a.redactions()) == {"tok", "t1"}


# ───────────── descriptor reconstruction matches generator (FR-8) ──────────


def test_reconstruct_descriptors_matches_generator_resolution(tmp_path):
    onboarding = _onboarding(
        tmp_path,
        {
            "checkoutservice": {
                "transport": "grpc",
                "metrics": {
                    "convention_based": [{"name": "calls", "type": "counter"}],
                    "convention_profile": "span-metrics-connector",
                    "descriptor_overrides": {"latency_unit": "ms"},
                },
            },
            "frontend": {
                "transport": "http",
                "metrics": {
                    "convention_based": [{"name": "http.server.duration", "type": "histogram"}]
                },
            },
        },
    )
    descriptors = reconstruct_descriptors(onboarding)

    # Same resolution the generator runs (artifact_generator.py:484-487).
    expected_checkout = resolve_descriptor(
        profile="span-metrics-connector", transport="grpc", overrides={"latency_unit": "ms"}
    )
    expected_frontend = resolve_descriptor(profile=None, transport="http")

    assert descriptors["checkoutservice"] == expected_checkout
    assert descriptors["checkoutservice"].service_label_key == "service_name"
    assert descriptors["frontend"] == expected_frontend
    assert descriptors["frontend"].service_label_key == "service"


# ───────────────────────── FR-8c guardrails ────────────────────────────────


def test_prod_backend_refused_without_allow_prod(tmp_path):
    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice", {"checkoutserviceLatencyP99High": "up"})
    onboarding = _semconv_onboarding(tmp_path)
    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="https://prod-prometheus.example.com",
        min_coverage=1.0,
        auth=Auth(),
    )
    assert report.status == "unknown"
    assert report.exit_code() == EXIT_UNKNOWN


def test_dry_run_reports_query_count_without_querying(tmp_path, monkeypatch):
    artifacts = tmp_path / "art"
    _write_alerts(
        artifacts,
        "checkoutservice",
        {"a": "up1", "b": "up2"},
    )
    onboarding = _semconv_onboarding(tmp_path)

    def _boom(*a, **k):
        raise AssertionError("dry-run must not query the backend")

    monkeypatch.setattr(prometheus_query, "instant_query_count", _boom)
    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=1.0,
        dry_run=True,
        auth=Auth(),
    )
    assert report.status == "unknown"
    assert report.queries_replayed == 0
    assert "dry-run" in report.reason
    assert "2 queries" in report.reason


# ───────────────────────── expr extraction shapes ─────────────────────────


def test_extracts_from_alerts_slos_and_dashboards(tmp_path, monkeypatch):
    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice", {"checkoutserviceLatencyP99High": "expr_a"})
    _write_slo(artifacts, "checkoutservice", "expr_b")
    _write_dashboard(artifacts, "checkoutservice", "expr_c")

    exprs = validate_promql.extract_exprs(artifacts)
    got = {(e.source_kind, e.expr) for e in exprs}
    assert ("alert", "expr_a") in got
    assert ("slo", "expr_b") in got
    assert ("dashboard", "expr_c") in got
    assert all(e.service == "checkoutservice" for e in exprs)


# ────────────────────────────── CLI wiring ────────────────────────────────


def test_cli_validate_promql_exit_codes(tmp_path, monkeypatch):
    typer_testing = pytest.importorskip("typer.testing")
    from startd8.observability.cli import observability_app

    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice", {"checkoutserviceLatencyP99High": "up"})
    onboarding = _semconv_onboarding(tmp_path)
    report_path = tmp_path / "report.json"

    monkeypatch.setattr(prometheus_query, "instant_query_count", lambda *a, **k: 1)

    runner = typer_testing.CliRunner()
    result = runner.invoke(
        observability_app,
        [
            "validate-promql",
            "--artifacts-dir",
            str(artifacts),
            "--onboarding-metadata",
            str(onboarding),
            "--prometheus",
            "http://localhost:9090",
            "--min-coverage",
            "1.0",
            "--report",
            str(report_path),
        ],
    )
    assert result.exit_code == EXIT_PASS, result.output
    data = json.loads(report_path.read_text())
    assert data["status"] == "pass"
    assert "offline structural smoke" in data["static_gate_note"]
