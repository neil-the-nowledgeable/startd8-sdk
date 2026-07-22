"""#226 Phase 2a — FR-6/FR-6a: kind→profile table (workload-aware descriptors).

A declared workload `kind` selects a MetricDescriptor profile that wins over
transport, so a worker gets job-shaped series (OTel messaging semconv) instead of
`http_server_duration`. Empty kinds ⇒ the transport default (byte-identical to
pre-#226 — the Phase-0 goldens are the guard).
"""

import yaml

from startd8.observability.artifact_generator import (
    BusinessContext,
    ConventionMetric,
    ServiceHints,
    generate_slo_definitions,
)
from startd8.observability.metric_descriptor import (
    profile_for_kinds,
    profile_for_transport,
    resolve_descriptor,
)


class TestProfileForKinds:
    def test_async_worker_maps_to_messaging_semconv(self):
        d = profile_for_kinds(["async_worker"], transport="http")
        assert d.profile == "messaging-semconv"
        assert d.latency_bucket_metric == "messaging_process_duration_bucket"
        assert "http_server_duration" not in d.throughput_metric

    def test_stream_maps_to_messaging_semconv(self):
        assert profile_for_kinds(["stream"], "http").profile == "messaging-semconv"

    def test_empty_kinds_is_transport_default_byte_parity(self):
        # The load-bearing byte-parity invariant.
        assert profile_for_kinds([], "http") == profile_for_transport("http")
        assert profile_for_kinds([], "grpc") == profile_for_transport("grpc")
        assert profile_for_kinds(None, "http") == profile_for_transport("http")

    def test_hybrid_falls_back_to_request_profile(self):
        # http_server + async_worker → the request (transport) descriptor; the
        # worker SLIs are added later by the FR-5 signal_kind derivation.
        d = profile_for_kinds(["http_server", "async_worker"], "http")
        assert d.profile == "semconv-http"

    def test_unmapped_kind_falls_back_to_transport(self):
        # batch/cron are intentionally ungrounded (OQ-5) → transport default, not invented.
        assert profile_for_kinds(["batch"], "grpc").profile == "semconv-grpc"


class TestResolveDescriptorKindTier:
    def test_kind_wins_over_transport(self):
        d = resolve_descriptor(kinds=["async_worker"], transport="http")
        assert d.profile == "messaging-semconv"

    def test_explicit_profile_still_wins_over_kind(self):
        d = resolve_descriptor(profile="semconv-grpc", kinds=["async_worker"], transport="http")
        assert d.profile == "semconv-grpc"

    def test_no_kind_is_transport_default(self):
        assert resolve_descriptor(transport="grpc").profile == "semconv-grpc"
        assert resolve_descriptor(kinds=[], transport="http").profile == "semconv-http"


class TestWorkerGetsJobShapedSLO:
    """End-to-end FR-6: a worker with a job-processing histogram emits a job-shaped
    SLO on the messaging series — never `http_server_duration`."""

    def test_worker_slo_uses_messaging_series_not_http(self):
        business = BusinessContext(criticality="high", availability="99.5", latency_p99="400ms")
        worker = ServiceHints(
            service_id="mailer",
            transport="",  # a worker has no listen transport (FR-14)
            kinds=["async_worker"],
            convention_metrics=[
                ConventionMetric("messaging.process.duration", "histogram", "otel_semconv:messaging"),
            ],
        )
        result = generate_slo_definitions(worker, business)  # descriptor resolved from kind
        assert result.status == "generated"
        assert "messaging_process_duration" in result.content
        assert "http_server_duration" not in result.content
