"""#226 Phase 2b — FR-12 (resolve_sli_kinds) + FR-13 (gated signal coverage).

resolve_sli_kinds is the determination core: which SLI kinds is a service observed
by. FR-13 gates the (formerly unconditional) RED synthesis on that set — a service
whose set implies neither throughput nor availability gets NO synthesized panels.
"""

import yaml

from startd8.observability.artifact_generator import (
    BusinessContext,
    ConventionMetric,
    ServiceHints,
    generate_dashboard_spec,
)
from startd8.observability.metric_descriptor import resolve_sli_kinds

RED = frozenset({"latency", "availability", "throughput"})


class TestResolveSliKinds:
    def test_request_transport_no_kind_is_red_triple(self):
        # Byte-parity anchor: a plain http/grpc service resolves to the RED triple.
        assert resolve_sli_kinds(transport="http") == RED
        assert resolve_sli_kinds(transport="grpc") == RED

    def test_worker_kind_is_red_triple_on_messaging_series(self):
        # async_worker/stream get RED (job rate/success/latency) — the descriptor
        # (FR-6) binds these to messaging series, not http.
        assert resolve_sli_kinds(kinds=["async_worker"]) == RED
        assert resolve_sli_kinds(kinds=["stream"]) == RED

    def test_unmapped_kind_no_transport_is_empty_set(self):
        # cron/batch are ungrounded (deferred) → no implied set; with no transport
        # the service resolves to ∅ (FR-9's ∅ class; FR-13 synthesizes nothing).
        assert resolve_sli_kinds(kinds=["cron"]) == frozenset()

    def test_declared_signal_kinds_union_in(self):
        # functional[] signal_kinds (CR-1) enter the set directly.
        assert resolve_sli_kinds(kinds=["cron"], signal_kinds=["freshness"]) == frozenset(
            {"freshness"}
        )
        got = resolve_sli_kinds(transport="http", signal_kinds=["queue_depth"])
        assert got == RED | {"queue_depth"}

    def test_nothing_declared_is_empty(self):
        assert resolve_sli_kinds() == frozenset()


class TestFr13GatedSynthesis:
    def _panels(self, service, business):
        result = generate_dashboard_spec(service, business)
        assert result.status == "generated"
        doc = yaml.safe_load(result.content.split("\n\n", 1)[-1])
        return [p.get("title", "") for p in doc.get("panels", [])]

    def test_request_service_still_gets_synthesized_red(self):
        # Byte-parity-adjacent: an http service keeps its synthesized RED panels.
        titles = self._panels(
            ServiceHints(
                service_id="api",
                transport="http",
                convention_metrics=[
                    ConventionMetric("http.server.request.body.size", "counter", "otel_semconv:http")
                ],
            ),
            BusinessContext(criticality="high", availability="99.5"),
        )
        assert "Request Rate" in titles
        assert "Availability (1h)" in titles

    def test_empty_set_service_gets_no_synthesized_red(self):
        # FR-13 deletion: a cron (unmapped kind, no transport ⇒ ∅) synthesizes no
        # Request Rate / Availability gauge — the fabricated-RED bug is gone.
        titles = self._panels(
            ServiceHints(
                service_id="nightly",
                transport="",
                kinds=["cron"],
                convention_metrics=[
                    ConventionMetric("job.last_success.timestamp", "gauge", "custom")
                ],
            ),
            BusinessContext(criticality="medium", availability="99"),
        )
        assert "Request Rate" not in titles
        assert "Availability (1h)" not in titles
