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


def test_fidelity_report_suggests_metrics_profile(tmp_path, monkeypatch):
    """Quick-win #1: a semconv-emitted run against a live span-metrics backend
    names the exact metricsProfile fix, per-verdict and rolled up."""
    artifacts = tmp_path / "art"
    _write_alerts(
        artifacts,
        "checkoutservice",
        {
            "checkoutserviceLatencyP99High": (
                'histogram_quantile(0.99, rate(http_server_duration_bucket'
                '{service="checkoutservice"}[5m])) > 0.5'
            ),
        },
    )
    onboarding = _semconv_onboarding(tmp_path)  # expected identity = semconv-http

    # Live backend runs the full span-metrics signature.
    live_names = ["calls_total", "duration_milliseconds_bucket", "duration_milliseconds_count"]
    monkeypatch.setattr(prometheus_query, "instant_query_count", lambda *a, **k: 0)
    monkeypatch.setattr(prometheus_query, "list_metric_names", lambda *a, **k: live_names)
    monkeypatch.setattr(prometheus_query, "label_values", lambda *a, **k: [])

    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=1.0,
        auth=Auth(),
    )
    assert report.status == "fail"
    # Aggregate: the whole run's one-line fix.
    assert report.suggested_metrics_profile == "span-metrics-connector"
    # Per-verdict: the failing expr carries the same concrete suggestion.
    failing = [v for v in report.verdicts if v.verdict == "fail"]
    assert failing and all(v.suggested_profile == "span-metrics-connector" for v in failing)
    # Remediation string names the profile + the manifest key to set.
    joined = " ".join(v.remediation for v in failing)
    assert "span-metrics-connector" in joined and "metricsProfile" in joined
    # Serialized report exposes both surfaces.
    d = report.to_dict()
    assert d["suggested_metrics_profile"] == "span-metrics-connector"
    assert d["verdicts"][0]["suggested_profile"] == "span-metrics-connector"


def test_fidelity_report_no_profile_suggestion_when_all_pass(tmp_path, monkeypatch):
    """A clean run suggests nothing — the field stays empty, not a false nudge."""
    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice", {"ok": "rate(x[5m]) > 0.01"})
    onboarding = _semconv_onboarding(tmp_path)
    monkeypatch.setattr(prometheus_query, "instant_query_count", lambda *a, **k: 1)
    monkeypatch.setattr(prometheus_query, "list_metric_names", lambda *a, **k: ["x"])
    monkeypatch.setattr(prometheus_query, "label_values", lambda *a, **k: ["checkoutservice"])

    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=1.0,
        auth=Auth(),
    )
    assert report.status == "pass"
    assert report.suggested_metrics_profile == ""


# ─────────── replay normalization: threshold / macros / template vars ───────


def test_strip_threshold():
    from startd8.observability.validate_promql import strip_threshold

    assert strip_threshold("rate(x[5m]) > 0.001") == "rate(x[5m])"
    assert strip_threshold("histogram_quantile(0.99, rate(x[5m])) > 500.0").endswith("))")
    assert strip_threshold("( 1 - a / b ) < 0.999").endswith(")")
    # metric-only exprs (no trailing comparison) are unchanged
    assert strip_threshold("rate(calls_total[5m])") == "rate(calls_total[5m])"
    # stripping that would empty the expr is a no-op (fail-safe)
    assert strip_threshold("> 5") == "> 5"


def test_substitute_grafana_macros_and_template_vars():
    from startd8.observability.validate_promql import (
        has_unresolved_template_var,
        substitute_grafana_macros,
    )

    assert "5m" in substitute_grafana_macros("rate(x[$__rate_interval])")
    assert "60000" in substitute_grafana_macros("x offset $__interval_ms")
    # $__interval_ms must not be mangled into 1m + "_ms"
    assert substitute_grafana_macros("y[$__interval_ms]") == "y[60000]"
    assert not has_unresolved_template_var("rate(calls_total[5m])")
    assert has_unresolved_template_var("rate(x{svc=\"$service\"}[5m])")
    assert has_unresolved_template_var("rate(x[${range}])")


def test_alert_threshold_not_a_fidelity_fail(tmp_path):
    """A non-firing alert (threshold not met) must not be scored as a binding miss:
    the query is replayed with the trailing comparison stripped."""
    artifacts = tmp_path / "art"
    _write_alerts(
        artifacts,
        "checkoutservice",
        {"HighErr": 'rate(http_server_duration_count{service="checkoutservice"}[5m]) > 0.01'},
    )
    onboarding = _semconv_onboarding(tmp_path)

    seen = {}

    def _q(base, expr, **k):
        seen["expr"] = expr
        # The metric resolves; only the '> 0.01' comparison would have emptied it.
        return 3

    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=1.0,
        auth=Auth(),
        query_fn=_q,
    )
    assert report.status == "pass"
    assert "> 0.01" not in seen["expr"]  # threshold stripped before replay
    assert report.verdicts[0].replayed_expr  # recorded, since it differed


def test_dashboard_template_var_is_skipped_not_failed(tmp_path):
    """A dashboard expr with an unresolvable $var is skipped (not counted), while
    its $__rate_interval sibling is macro-substituted and replayed."""
    from startd8.observability.validate_promql import run_validation as _rv

    (artifacts := tmp_path / "art" / "dashboards").mkdir(parents=True)
    doc = {"panels": [
        {"title": "A", "expr": 'rate(calls_total{service_name="checkoutservice"}[$__rate_interval])'},
        {"title": "B", "expr": 'rate(calls_total{service_name="$service"}[5m])'},
    ]}
    (artifacts / "checkoutservice-dashboard.yaml").write_text(yaml.dump(doc))
    onboarding = _onboarding(tmp_path, {"checkoutservice": {
        "transport": "grpc",
        "metrics": {"convention_based": [{"name": "rpc.server.duration", "type": "histogram"}]},
    }})

    report = _rv(
        artifacts_dir=tmp_path / "art",
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=0.0,
        auth=Auth(),
        query_fn=lambda base, expr, **k: (0 if "$" in expr else 1),
    )
    assert report.queries_skipped == 1          # panel B skipped
    assert report.queries_replayed == 1          # panel A replayed (macro resolved)
    assert "$__rate_interval" not in report.verdicts[0].replayed_expr


def test_rejected_query_is_error_not_unreachable(tmp_path):
    """A backend HTTP 400 on one expr records a per-expr 'error' verdict and keeps
    going — it does NOT flip the whole run to unknown/unreachable."""
    import urllib.error

    artifacts = tmp_path / "art"
    _write_alerts(
        artifacts,
        "checkoutservice",
        {"A": "rate(x[5m])", "B": "this is not promql"},
    )
    onboarding = _semconv_onboarding(tmp_path)

    def _q(base, expr, **k):
        if "not promql" in expr:
            raise urllib.error.HTTPError(base, 400, "bad_data", {}, None)
        return 2

    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=0.0,
        auth=Auth(),
        query_fn=_q,
    )
    assert report.status != "unknown"  # not flipped to unreachable
    verdicts = {v.verdict for v in report.verdicts}
    assert "error" in verdicts
    err = next(v for v in report.verdicts if v.verdict == "error")
    assert "HTTP 400" in err.remediation


def test_connection_error_still_flips_to_unknown(tmp_path):
    """A genuine connection error (not an HTTP status) is still fail-loud unknown."""
    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice", {"A": "rate(x[5m])"})
    onboarding = _semconv_onboarding(tmp_path)

    def _q(base, expr, **k):
        raise ConnectionRefusedError("no backend")

    report = run_validation(
        artifacts_dir=artifacts,
        onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090",
        min_coverage=0.0,
        auth=Auth(),
        query_fn=_q,
    )
    assert report.status == "unknown"


# ───────────────────── A1: exclusion taxonomy ──────────────────────────────


def test_scan_excluded_artifacts(tmp_path):
    from startd8.observability.validate_promql import scan_excluded_artifacts

    art = tmp_path / "art"
    (art / "service-monitors").mkdir(parents=True)
    (art / "service-monitors" / "a-servicemonitor.yaml").write_text("x")
    (art / "service-monitors" / "b-servicemonitor.yaml").write_text("x")
    (art / "loki-rules").mkdir()
    (art / "loki-rules" / "a-loki.yaml").write_text("x")
    (art / "alerts").mkdir()  # replayable — must NOT be counted as excluded
    got = scan_excluded_artifacts(art)
    assert got == {"service_monitor": 2, "loki_rule": 1}


def test_report_enumerates_excluded_artifacts(tmp_path):
    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice", {"A": "rate(x[5m])"})
    (artifacts / "loki-rules").mkdir()
    (artifacts / "loki-rules" / "checkoutservice-loki.yaml").write_text("groups: []")
    onboarding = _semconv_onboarding(tmp_path)

    report = run_validation(
        artifacts_dir=artifacts, onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090", min_coverage=1.0, auth=Auth(),
        query_fn=lambda *a, **k: 1,
    )
    assert report.excluded_artifacts == {"loki_rule": 1}
    # excluded artifacts do not lower binding_coverage
    assert report.binding_coverage == 1.0
    assert report.to_dict()["excluded_artifacts"] == {"loki_rule": 1}


def test_exclude_kinds_removes_from_denominator(tmp_path):
    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice", {"A": "rate(x[5m])"})
    _write_dashboard(artifacts, "checkoutservice", "rate(y[5m])")
    onboarding = _semconv_onboarding(tmp_path)

    report = run_validation(
        artifacts_dir=artifacts, onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090", min_coverage=1.0, auth=Auth(),
        query_fn=lambda *a, **k: 1, exclude_kinds={"dashboard"},
    )
    assert report.queries_replayed == 1  # dashboard expr excluded from replay
    assert report.excluded_by_reason == {"kind_excluded:dashboard": 1}
    assert report.to_dict()["queries_excluded"] == 1


def test_template_var_skip_folds_into_excluded_by_reason(tmp_path):
    (art := tmp_path / "art" / "dashboards").mkdir(parents=True)
    doc = {"panels": [
        {"title": "A", "expr": 'rate(calls_total{service_name="checkoutservice"}[5m])'},
        {"title": "B", "expr": 'rate(calls_total{service_name="$svc"}[5m])'},  # template var
    ]}
    (art / "checkoutservice-dashboard.yaml").write_text(yaml.dump(doc))
    onboarding = _onboarding(tmp_path, {"checkoutservice": {
        "transport": "grpc",
        "metrics": {"convention_based": [{"name": "rpc.server.duration", "type": "histogram"}]},
    }})
    report = run_validation(
        artifacts_dir=tmp_path / "art", onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090", min_coverage=0.0, auth=Auth(),
        query_fn=lambda base, expr, **k: 0 if "$" in expr else 1,
    )
    assert report.queries_skipped == 1
    assert report.excluded_by_reason.get("unresolved_template_var") == 1


# ─────────────── target drift + service-level exclusion ────────────────────


def test_detect_target_drift_lists_absent_services():
    from startd8.observability.validate_promql import detect_target_drift
    from startd8.observability.metric_descriptor import profile_for

    descriptors = {
        "checkout": profile_for("span-metrics-connector"),
        "cart": profile_for("span-metrics-connector"),
    }
    # backend knows "cart" but has never emitted "checkout"
    drift = detect_target_drift(["checkout", "cart"], descriptors, lambda key: ["cart"])
    assert drift["declared_absent"] == ["checkout"]
    assert drift["checked"] is True


def test_detect_target_drift_unreachable_is_inconclusive_not_false_drift():
    from startd8.observability.validate_promql import detect_target_drift
    from startd8.observability.metric_descriptor import profile_for

    def _boom(key):
        raise RuntimeError("backend down")

    drift = detect_target_drift(["x"], {"x": profile_for("semconv-http")}, _boom)
    assert drift["declared_absent"] == [] and drift["checked"] is False


def test_run_validation_surfaces_target_drift(tmp_path):
    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "accountingservice",
                  {"Thru": 'rate(calls_total{service_name="accountingservice"}[5m])'})
    onboarding = _onboarding(tmp_path, {"accountingservice": {
        "transport": "grpc",
        "metrics": {"convention_based": [], "convention_profile": "span-metrics-connector"},
    }})
    report = run_validation(
        artifacts_dir=artifacts, onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090", min_coverage=1.0, auth=Auth(),
        query_fn=lambda *a, **k: 0,
        list_names_fn=lambda *a, **k: ["calls_total"],   # metric exists
        label_values_fn=lambda *a, **k: ["frontend"],    # but accountingservice absent
    )
    assert report.target_drift["declared_absent"] == ["accountingservice"]
    assert "TARGET DRIFT" in report.reason


def test_exclude_services_removes_from_denominator(tmp_path):
    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice", {"A": "rate(x[5m])"})
    _write_alerts(artifacts, "accountingservice", {"B": "rate(y[5m])"})
    onboarding = _onboarding(tmp_path, {
        "checkoutservice": {"transport": "grpc", "metrics": {"convention_based": []}},
        "accountingservice": {"transport": "grpc", "metrics": {"convention_based": []}},
    })
    report = run_validation(
        artifacts_dir=artifacts, onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090", min_coverage=1.0, auth=Auth(),
        query_fn=lambda *a, **k: 1, label_values_fn=lambda *a, **k: ["checkoutservice"],
        exclude_services={"accountingservice"},
    )
    assert report.queries_replayed == 1  # accountingservice's query excluded
    assert report.excluded_by_reason == {"service_excluded:accountingservice": 1}
    # an excluded service is not reported as drift
    assert "accountingservice" not in report.target_drift.get("declared_absent", [])


# ───────────── bound_no_data verdict + binding vs data coverage ─────────────


def test_widen_rate_window():
    from startd8.observability.validate_promql import widen_rate_window

    assert widen_rate_window("rate(x[5m])") == "rate(x[1h])"
    assert widen_rate_window("rate(x[30s]) / rate(y[5m])") == "rate(x[1h]) / rate(y[1h])"
    assert widen_rate_window("rate(x[5m])", "6h") == "rate(x[6h])"
    assert widen_rate_window("sum(up)") == "sum(up)"  # no window → unchanged


def test_stale_data_is_bound_no_data_via_wide_probe(tmp_path):
    """FR-3: empty at [5m] but present at [1h] ⇒ bound_no_data (staleness), not fail."""
    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice",
                  {"Thru": 'rate(http_server_duration_count{service="checkoutservice"}[5m])'})
    onboarding = _semconv_onboarding(tmp_path)

    def _q(base, expr, **k):
        return 1 if "[1h]" in expr else 0  # narrow empty, wide resolves

    report = run_validation(
        artifacts_dir=artifacts, onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090", min_coverage=1.0, auth=Auth(), query_fn=_q,
    )
    v = report.verdicts[0]
    assert v.verdict == "bound_no_data"
    assert "[1h]" in v.replayed_expr
    assert report.binding_coverage == 1.0 and report.data_coverage == 0.0
    assert report.status == "pass"                      # gates on binding_coverage
    assert "WARNING" in report.reason and "silent" in report.reason  # FR-5a


def test_no_data_all_axes_present_is_bound_no_data(tmp_path):
    """FR-1: empty even at the wide window, but every descriptor axis present live ⇒
    bound_no_data (healthy service, no series now), decided by two-sided diagnosis."""
    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice",
                  {"Thru": 'rate(http_server_duration_count{service="checkoutservice"}[5m])'})
    onboarding = _semconv_onboarding(tmp_path)

    report = run_validation(
        artifacts_dir=artifacts, onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090", min_coverage=1.0, auth=Auth(),
        query_fn=lambda base, expr, **k: 0,  # empty at every window
        # all axes present: both metric names live, and the service label has the value
        list_names_fn=lambda *a, **k: ["http_server_duration_count", "http_server_duration_bucket"],
        label_values_fn=lambda *a, **k: ["checkoutservice"],
    )
    v = report.verdicts[0]
    assert v.verdict == "bound_no_data", v.verdict
    assert not v.mismatched_axes


def test_absent_axis_stays_fail_not_bound_no_data(tmp_path):
    """FR-4: a genuinely absent metric must stay `fail`, never softened to bound_no_data."""
    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice",
                  {"Thru": 'rate(http_server_duration_count{service="checkoutservice"}[5m])'})
    onboarding = _semconv_onboarding(tmp_path)

    report = run_validation(
        artifacts_dir=artifacts, onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090", min_coverage=1.0, auth=Auth(),
        query_fn=lambda base, expr, **k: 0,
        list_names_fn=lambda *a, **k: ["calls_total"],       # emitted metric ABSENT
        label_values_fn=lambda *a, **k: [],
    )
    v = report.verdicts[0]
    assert v.verdict == "fail"
    assert v.mismatched_axes


def test_binding_vs_data_coverage_math(tmp_path):
    """FR-2: data_coverage counts only pass; binding_coverage adds bound_no_data."""
    artifacts = tmp_path / "art"
    _write_alerts(artifacts, "checkoutservice", {
        "A": 'rate(http_server_duration_count{service="checkoutservice"}[5m])',   # pass
        "B": 'rate(http_server_duration_bucket{service="checkoutservice"}[5m])',  # bound_no_data (stale)
    })
    onboarding = _semconv_onboarding(tmp_path)

    def _q(base, expr, **k):
        if "bucket" in expr:
            return 1 if "[1h]" in expr else 0   # B: stale → bound_no_data
        return 3                                 # A: live data → pass

    report = run_validation(
        artifacts_dir=artifacts, onboarding_metadata=onboarding,
        prometheus_url="http://localhost:9090", min_coverage=0.5, auth=Auth(), query_fn=_q,
    )
    assert report.queries_replayed == 2
    assert report.bound_no_data == 1
    assert report.data_coverage == 0.5       # 1 pass / 2
    assert report.binding_coverage == 1.0    # (1 pass + 1 bound) / 2
    assert report.coverage == report.binding_coverage  # back-compat alias
    d = report.to_dict()
    assert d["data_coverage"] == 0.5 and d["binding_coverage"] == 1.0 and d["bound_no_data"] == 1


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


# ─────────────────────── detect-profile CLI (quick-win #2) ──────────────────


def _run_detect_profile(monkeypatch, live_names, extra_args=None):
    typer_testing = pytest.importorskip("typer.testing")
    from startd8.observability import cli as obs_cli

    # cli.py binds `list_metric_names` at import; patch it on the cli module.
    if isinstance(live_names, Exception):
        def _boom(*a, **k):
            raise live_names
        monkeypatch.setattr(obs_cli, "list_metric_names", _boom)
    else:
        monkeypatch.setattr(obs_cli, "list_metric_names", lambda *a, **k: live_names)

    runner = typer_testing.CliRunner()
    return runner.invoke(
        obs_cli.observability_app,
        ["detect-profile", "--prometheus", "http://localhost:9090", *(extra_args or [])],
    )


def test_detect_profile_matches_span_metrics(monkeypatch):
    result = _run_detect_profile(
        monkeypatch,
        ["calls_total", "duration_milliseconds_bucket", "up", "process_cpu"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "matched"
    assert data["suggested_metrics_profile"] == "span-metrics-connector"
    assert "span-metrics-connector" in data["matched_profiles"]
    assert data["profiles"]["span-metrics-connector"]["matches"] is True
    assert data["profiles"]["semconv-http"]["matches"] is False


def test_detect_profile_no_match_exits_two(monkeypatch):
    # Metrics exist but no profile's full signature is present.
    result = _run_detect_profile(monkeypatch, ["calls_total", "up"])
    assert result.exit_code == 2, result.output
    data = json.loads(result.output)
    assert data["status"] == "no-match"
    assert data["suggested_metrics_profile"] == ""


def test_detect_profile_empty_backend_is_unknown(monkeypatch):
    result = _run_detect_profile(monkeypatch, [])
    assert result.exit_code == 3, result.output
    assert json.loads(result.output)["status"] == "unknown"


def test_detect_profile_unreachable_is_unknown(monkeypatch):
    result = _run_detect_profile(monkeypatch, RuntimeError("connection refused"))
    assert result.exit_code == 3, result.output
    assert json.loads(result.output)["status"] == "unknown"
