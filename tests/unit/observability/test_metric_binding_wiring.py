# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Step 3 wiring tests: MetricDescriptor threaded into PromQL emission.

Covers REQ_TARGET_METRIC_BINDING FR-4 / FR-4a / FR-1a. Asserts that a service
whose resolved profile is ``span-metrics-connector`` produces PromQL bound to the
span-metrics surface (``service_name=``, ``calls_total``,
``duration_milliseconds_bucket``, ``status_code="STATUS_CODE_ERROR"``, and a
millisecond threshold), and that the ``semconv-grpc`` default output is unchanged
from the transport default (the byte-identical invariant).
"""

import yaml

from startd8.observability.artifact_generator_generators import (
    generate_alert_rules,
    generate_dashboard_spec,
    generate_loki_rule,
    generate_slo_definitions,
)
from startd8.observability.artifact_generator_models import (
    BusinessContext,
    ConventionMetric,
    ServiceHints,
)
from startd8.observability.metric_descriptor import resolve_descriptor


def _business():
    return BusinessContext(
        criticality="high",
        availability="99.9",
        latency_p99="500ms",
        throughput="100rps",
        project_id="bpi-astronomy",
        slo_window="30d",
    )


def _span_metrics_service():
    """A checkout-style service resolved to the span-metrics-connector profile."""
    return ServiceHints(
        service_id="checkoutservice",
        transport="grpc",
        convention_metrics=[
            ConventionMetric("rpc.server.duration", "histogram", "otel_semconv:grpc"),
        ],
        metric_profile="span-metrics-connector",
    )


def _descriptor_for(service):
    return resolve_descriptor(
        profile=service.metric_profile or None,
        transport=service.transport,
        overrides=service.descriptor_overrides,
    )


def _alert_body(result):
    return yaml.safe_load(result.content.split("\n\n", 1)[1])


# ---------------------------------------------------------------------------
# span-metrics surface — alerts
# ---------------------------------------------------------------------------


class TestSpanMetricsAlerts:
    def test_alert_promql_binds_span_metrics_surface(self):
        service = _span_metrics_service()
        descriptor = _descriptor_for(service)
        result = generate_alert_rules(service, _business(), descriptor)
        rules = _alert_body(result)["groups"][0]["rules"]
        exprs = "\n".join(r["expr"] for r in rules)

        # label key: service_name, not service=
        assert 'service_name="checkoutservice"' in exprs
        assert 'service="checkoutservice"' not in exprs
        # throughput/error counter
        assert "calls_total{" in exprs
        # latency histogram
        assert "duration_milliseconds_bucket{" in exprs
        # error selector
        assert 'status_code="STATUS_CODE_ERROR"' in exprs
        assert 'grpc_code=~' not in exprs

    def test_latency_threshold_is_milliseconds(self):
        """FR-4a: a 500ms requirement on a ms descriptor emits > 500, not > 0.5."""
        service = _span_metrics_service()
        descriptor = _descriptor_for(service)
        result = generate_alert_rules(service, _business(), descriptor)
        rules = _alert_body(result)["groups"][0]["rules"]
        latency = [r for r in rules if r["alert"].endswith("LatencyP99High")]
        assert latency, "expected a latency alert"
        expr = latency[0]["expr"]
        assert "> 500" in expr
        assert "> 0.5" not in expr


# ---------------------------------------------------------------------------
# span-metrics surface — SLOs
# ---------------------------------------------------------------------------


class TestSpanMetricsSLOs:
    def test_slo_promql_binds_span_metrics_surface(self):
        service = _span_metrics_service()
        descriptor = _descriptor_for(service)
        result = generate_slo_definitions(service, _business(), descriptor)
        content = result.content
        assert 'service_name="checkoutservice"' in content
        assert 'service="checkoutservice"' not in content
        assert "calls_total{" in content
        assert "duration_milliseconds_bucket{" in content
        assert 'status_code="STATUS_CODE_ERROR"' in content

    def test_latency_slo_threshold_is_milliseconds(self):
        service = _span_metrics_service()
        descriptor = _descriptor_for(service)
        docs = [
            d
            for d in yaml.safe_load_all(
                generate_slo_definitions(service, _business(), descriptor).content.split(
                    "\n\n", 1
                )[1]
            )
            if d
        ]
        latency = [d for d in docs if d["metadata"]["name"].endswith("latency-p99")]
        assert latency, "expected a latency SLO"
        threshold = latency[0]["spec"]["indicator"]["spec"]["thresholdMetric"]["threshold"]
        assert threshold == 500


# ---------------------------------------------------------------------------
# span-metrics surface — dashboards + loki
# ---------------------------------------------------------------------------


class TestSpanMetricsDashboardAndLoki:
    def test_dashboard_promql_binds_span_metrics_surface(self):
        service = _span_metrics_service()
        descriptor = _descriptor_for(service)
        result = generate_dashboard_spec(service, _business(), descriptor)
        spec = yaml.safe_load(result.content.split("\n\n", 1)[1])
        exprs = "\n".join(str(p.get("expr", "")) for p in spec["panels"])
        assert 'service_name="checkoutservice"' in exprs
        assert 'service="checkoutservice"' not in exprs
        assert "duration_milliseconds_bucket{" in exprs
        assert "calls_total{" in exprs

    def test_loki_stream_key_from_descriptor(self):
        """FR-1a: span-metrics LogQL stream key falls back to service_name."""
        service = _span_metrics_service()
        descriptor = _descriptor_for(service)
        result = generate_loki_rule(service, _business(), descriptor)
        rule = yaml.safe_load(result.content.split("\n\n", 1)[1])
        expr = rule["groups"][0]["rules"][0]["expr"]
        assert 'service_name="checkoutservice"' in expr


# ---------------------------------------------------------------------------
# semconv default — byte-identical invariant
# ---------------------------------------------------------------------------


class TestSemconvGrpcUnchanged:
    """A no-profile grpc service must reproduce the transport default exactly."""

    def _grpc_service(self):
        return ServiceHints(
            service_id="checkout-api",
            transport="grpc",
            convention_metrics=[
                ConventionMetric("rpc.server.duration", "histogram", "otel_semconv:grpc"),
            ],
        )

    def test_alerts_match_hardcoded_default(self):
        service = self._grpc_service()
        # No descriptor passed == the pre-Step-3 hardcoded path.
        without = generate_alert_rules(service, _business()).content
        # Explicit transport-default descriptor == what the orchestrator resolves
        # for an unprofiled service.
        descriptor = resolve_descriptor(profile=None, transport="grpc")
        with_desc = generate_alert_rules(service, _business(), descriptor).content
        assert without == with_desc

        rules = _alert_body(generate_alert_rules(service, _business(), descriptor))
        exprs = "\n".join(
            r["expr"] for r in rules["groups"][0]["rules"]
        )
        assert 'service="checkout-api"' in exprs
        assert "rpc_server_duration_bucket{" in exprs
        assert "rpc_server_duration_count{" in exprs
        assert 'grpc_code=~"Unavailable|Internal|Unimplemented|DataLoss"' in exprs
        # seconds threshold, not milliseconds
        assert "> 0.5" in exprs
        assert "> 500" not in exprs

    def test_slo_and_dashboard_match_hardcoded_default(self):
        service = self._grpc_service()
        descriptor = resolve_descriptor(profile=None, transport="grpc")
        assert (
            generate_slo_definitions(service, _business()).content
            == generate_slo_definitions(service, _business(), descriptor).content
        )
        assert (
            generate_dashboard_spec(service, _business()).content
            == generate_dashboard_spec(service, _business(), descriptor).content
        )
