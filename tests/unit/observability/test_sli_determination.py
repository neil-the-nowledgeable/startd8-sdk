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
from startd8.observability.metric_descriptor import (
    resolve_sli_kinds,
    suggested_signals_for,
)


class TestSuggestedSignals:
    """P1a (#230/#231/#233): kind-specific signal SHAPE hint (never a threshold value)."""

    def test_each_ungrounded_kind_has_its_own_shape(self):
        assert suggested_signals_for("cron") == ("freshness", "run_success")
        assert suggested_signals_for("batch") == ("run_success", "freshness")
        assert suggested_signals_for("ml_inference") == ("saturation", "lag")

    def test_unknown_kind_falls_back_to_the_generic_non_request_set(self):
        got = suggested_signals_for("something_new")
        assert set(got) == {"run_success", "freshness", "saturation", "lag"}

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

    # --- #231 grounding-free slice: an ungrounded workload kind suppresses the
    # incidental transport RED triple (the silent 500ms-HTTP-latency SLO). ---

    def test_ml_inference_with_http_transport_suppresses_red(self):
        # THE #231 SILENT DANGER: an ml_inference service that exposes an http
        # health/serve port must NOT inherit the 500ms HTTP-latency RED triple.
        # Its transport is incidental; it gets only what it declares.
        assert resolve_sli_kinds(kinds=["ml_inference"], transport="http") == frozenset()

    def test_batch_and_cron_with_transport_suppress_red(self):
        assert resolve_sli_kinds(kinds=["batch"], transport="http") == frozenset()
        assert resolve_sli_kinds(kinds=["cron"], transport="grpc") == frozenset()

    def test_ungrounded_kind_still_gets_declared_signals(self):
        # Suppression removes only the incidental transport base — declared
        # functional[] signals still resolve (the actionable path forward).
        assert resolve_sli_kinds(
            kinds=["ml_inference"], signal_kinds=["saturation"], transport="http"
        ) == frozenset({"saturation"})

    def test_hybrid_request_kind_keeps_red_despite_ungrounded_kind(self):
        # A service that ALSO explicitly declares http_server genuinely serves
        # requests → the transport is NOT incidental → RED is preserved.
        assert resolve_sli_kinds(
            kinds=["ml_inference", "http_server"], transport="http"
        ) == RED

    def test_parity_unchanged_for_non_ungrounded_services(self):
        # FR-11 anchor: the suppression is inert for every non-ungrounded service.
        assert resolve_sli_kinds(transport="http") == RED
        assert resolve_sli_kinds(kinds=["async_worker"], transport="http") == RED


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
