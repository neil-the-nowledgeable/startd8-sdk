# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Tests for the static observability-fidelity SPIKE prototype.

Covers the three moving parts:
  * emitted extraction per language (Python / Go / Node) + transport implication,
  * referenced extraction (bare metric names out of PromQL, reusing extract_exprs),
  * the static_fidelity verdict/coverage math, including the no-silent-green rule.
"""

from __future__ import annotations

import json

import yaml

from startd8.observability.observability_fidelity_static import (
    bare_metrics_from_expr,
    emitted_from_descriptor,
    extract_emitted_metrics,
    extract_referenced_metrics,
    score_services,
    sniff_transports,
    static_fidelity,
)
from startd8.observability.metric_descriptor import profile_for


# ─────────────────────────── emitted: Python ───────────────────────────────


def test_emitted_python_otel_and_prometheus_client(tmp_path):
    src = tmp_path / "svc.py"
    src.write_text(
        "from opentelemetry import metrics\n"
        "from prometheus_client import Counter, Histogram\n"
        "meter = metrics.get_meter('svc')\n"
        "c = meter.create_counter('app_requests_total')\n"
        "h = meter.create_histogram('op_latency_ms')\n"
        "pc = Counter('prom_hits_total', 'help')\n"
    )
    emitted = extract_emitted_metrics(src, expand_families=False)
    assert {"app_requests_total", "op_latency_ms", "prom_hits_total"} <= emitted


def test_emitted_python_transport_implication_grpc(tmp_path):
    src = tmp_path / "svc.py"
    src.write_text(
        "import grpc\n"
        "from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer\n"
        "GrpcInstrumentorServer().instrument()\n"
    )
    emitted = extract_emitted_metrics(src)
    assert "rpc_server_duration" in emitted
    assert "rpc_server_duration_bucket" in emitted  # family expansion on


# ───────────────────────────── emitted: Go ─────────────────────────────────


def test_emitted_go_otel_and_promauto(tmp_path):
    src = tmp_path / "main.go"
    src.write_text(
        'meter := otel.Meter("svc")\n'
        'orders, _ := meter.Int64Counter("app_orders_total")\n'
        "lat := promauto.NewHistogram(prometheus.HistogramOpts{\n"
        '    Name: "pipeline_seconds",\n'
        "})\n"
    )
    emitted = extract_emitted_metrics(src, expand_families=False)
    assert {"app_orders_total", "pipeline_seconds"} <= emitted


# ──────────────────────────── emitted: Node ────────────────────────────────


def test_emitted_node_otel_and_prom_client(tmp_path):
    src = tmp_path / "server.js"
    src.write_text(
        "const { metrics } = require('@opentelemetry/api');\n"
        "const client = require('prom-client');\n"
        "const meter = metrics.getMeter('svc');\n"
        "const served = meter.createCounter('app_served_total');\n"
        "const hits = new client.Counter({ name: 'cache_hits_total' });\n"
    )
    emitted = extract_emitted_metrics(src, expand_families=False)
    assert {"app_served_total", "cache_hits_total"} <= emitted


def test_sniff_transports():
    assert "grpc" in sniff_transports("import grpc\n")
    assert "http" in sniff_transports("from flask import Flask\n")
    assert sniff_transports("x = 1\n") == set()


# ───────────────────── referenced: bare metric extraction ──────────────────


def test_bare_metrics_strips_functions_labels_ranges_and_threshold():
    expr = (
        'histogram_quantile(0.99, rate(duration_milliseconds_bucket'
        '{service_name="checkoutservice"}[5m])) > 500.0'
    )
    names = bare_metrics_from_expr(expr)
    assert names == {"duration_milliseconds_bucket"}
    # No function names, no label key/value, no [5m] duration letter leak.
    assert "rate" not in names and "histogram_quantile" not in names
    assert "m" not in names and "service_name" not in names


def test_bare_metrics_two_metric_ratio():
    expr = (
        'rate(calls_total{service_name="s",status_code="STATUS_CODE_ERROR"}[5m])'
        ' / rate(calls_total{service_name="s"}[5m])'
    )
    assert bare_metrics_from_expr(expr) == {"calls_total"}


def test_extract_referenced_metrics_from_artifact_tree(tmp_path):
    alerts = tmp_path / "alerts"
    alerts.mkdir()
    doc = {
        "groups": [
            {
                "name": "svc.slo",
                "rules": [
                    {
                        "alert": "SvcErrorRateHigh",
                        "expr": 'rate(calls_total{service_name="svc"}[5m]) > 0.001',
                    }
                ],
            }
        ]
    }
    (alerts / "svc-alerts.yaml").write_text(yaml.dump(doc))
    ref = extract_referenced_metrics(tmp_path)
    assert ref == {"svc": {"calls_total"}}


# ───────────────────────────── verdict math ────────────────────────────────


def test_static_fidelity_pass():
    r = static_fidelity({"a", "b", "c"}, {"a", "b"})
    assert r["verdict"] == "pass" and r["coverage"] == 1.0
    assert r["unbound"] == []


def test_static_fidelity_partial():
    r = static_fidelity({"a"}, {"a", "b"})
    assert r["verdict"] == "partial" and r["coverage"] == 0.5
    assert r["unbound"] == ["b"] and r["bound"] == ["a"]


def test_static_fidelity_fail_profile_mismatch():
    # The load-bearing case: service emits rpc_server_duration, alerts reference
    # calls_total → nothing binds.
    r = static_fidelity(
        {"rpc_server_duration", "rpc_server_duration_bucket"},
        {"calls_total", "duration_milliseconds_bucket"},
    )
    assert r["verdict"] == "fail" and r["coverage"] == 0.0
    assert set(r["unbound"]) == {"calls_total", "duration_milliseconds_bucket"}


def test_static_fidelity_no_silent_green_on_empty():
    # Empty referenced or empty emitted → unknown, NEVER pass.
    assert static_fidelity({"a"}, set())["verdict"] == "unknown"
    assert static_fidelity(set(), {"a"})["verdict"] == "unknown"


# ─────────────── G2: manifest / MetricDescriptor emitted side ───────────────


def test_emitted_from_descriptor_span_metrics():
    # The span-metrics profile's RED surface — produced by the collector, declared by
    # the profile — must appear in the emitted set (closes the source-only false neg).
    emitted = emitted_from_descriptor(profile_for("span-metrics-connector"))
    assert "calls_total" in emitted
    assert "duration_milliseconds_bucket" in emitted
    # family expansion of the throughput base
    assert "calls_total_bucket" in emitted or "calls_total" in emitted


def test_emitted_from_descriptor_semconv_grpc():
    emitted = emitted_from_descriptor(profile_for("semconv-grpc"))
    assert "rpc_server_duration_count" in emitted
    assert "rpc_server_duration_bucket" in emitted


def test_score_services_descriptor_fold_binds_red(tmp_path):
    """G2 end-to-end: alerts referencing span-metrics RED bind via the descriptor even
    with no service source (the collector produces them; the profile declares them)."""
    alerts = tmp_path / "art" / "alerts"
    alerts.mkdir(parents=True)
    doc = {"groups": [{"name": "checkout.slo", "rules": [
        {"alert": "Err", "expr": 'rate(calls_total{service_name="checkoutservice",'
                                  'status_code="STATUS_CODE_ERROR"}[5m]) > 0.01'},
        {"alert": "Lat", "expr": 'histogram_quantile(0.99, rate('
                                 'duration_milliseconds_bucket{service_name="checkoutservice"}[5m])) > 500'},
    ]}]}
    (alerts / "checkoutservice-alerts.yaml").write_text(yaml.dump(doc))
    onboarding = tmp_path / "onboarding-metadata.json"
    onboarding.write_text(json.dumps({"instrumentation_hints": {"checkoutservice": {
        "transport": "grpc",
        "metrics": {"convention_based": [], "convention_profile": "span-metrics-connector"},
    }}}))

    got = score_services(artifacts_dir=tmp_path / "art", onboarding_metadata=onboarding)
    v = got["checkoutservice"]
    assert v["verdict"] == "pass"          # both RED metrics bind via the descriptor
    assert v["coverage"] == 1.0
    assert v["emitted_sources"] == {"descriptor": True, "source_scan": False}
