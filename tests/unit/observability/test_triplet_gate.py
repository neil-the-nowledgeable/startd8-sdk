"""#226 FR-12a — the alert/SLO triplet blocks are gated on the SLI-kind set, ANDed
with the existing per-metric gate (never replacing it).

Byte-parity: a request service resolves to the RED triple ⇒ every gate passes ⇒
identical output. Value: a service resolving to ∅ (or a set lacking latency/
availability) emits no latency/availability alert or SLO EVEN IF fed a duration
histogram upstream — the §0.3 "worker fed http metrics" failure source, closed.
"""

import yaml

from startd8.observability.artifact_generator import (
    BusinessContext,
    ConventionMetric,
    ServiceHints,
    generate_alert_rules,
    generate_slo_definitions,
)

_HTTP_DUR = ConventionMetric("http.server.duration", "histogram", "otel_semconv:http")


def _biz():
    return BusinessContext(criticality="high", availability="99.5", latency_p99="400ms")


class TestTripletGate:
    def test_request_service_still_emits_full_triplet(self):
        # Byte-parity anchor: http service → RED triple → all three alerts present.
        svc = ServiceHints(service_id="api", transport="http", convention_metrics=[_HTTP_DUR])
        rules = yaml.safe_load(
            generate_alert_rules(svc, _biz()).content.split("\n\n", 1)[-1]
        )["groups"][0]["rules"]
        names = {r["alert"] for r in rules}
        assert any(n.endswith("LatencyP99High") for n in names)
        assert any(n.endswith("ErrorRateHigh") for n in names)
        assert any(n.endswith("AvailabilityLow") for n in names)

    def test_empty_set_service_with_duration_histogram_emits_no_alerts(self):
        # The FR-12a AND-gate: a cron (kind=cron, no transport ⇒ ∅) that was mis-fed an
        # http_server_duration metric still gets NO latency/availability/error alert.
        svc = ServiceHints(
            service_id="nightly", transport="", kinds=["cron"], convention_metrics=[_HTTP_DUR]
        )
        result = generate_alert_rules(svc, _biz())
        # No RED alerts (the metric-presence gate alone would have emitted them).
        assert result.status in ("skipped", "generated")
        if result.status == "generated":
            rules = yaml.safe_load(result.content.split("\n\n", 1)[-1])["groups"][0]["rules"]
            names = {r["alert"] for r in rules}
            assert not any(
                n.endswith(("LatencyP99High", "ErrorRateHigh", "AvailabilityLow")) for n in names
            )
        else:
            assert result.status == "skipped"

    def test_empty_set_service_emits_no_slos(self):
        svc = ServiceHints(
            service_id="nightly", transport="", kinds=["cron"], convention_metrics=[_HTTP_DUR]
        )
        result = generate_slo_definitions(svc, _biz())
        body = result.content.split("\n\n", 1)[-1] if result.status == "generated" else ""
        docs = [d for d in yaml.safe_load_all(body) if d] if body else []
        names = [d.get("metadata", {}).get("name", "") for d in docs]
        assert not any("availability" in n or "latency" in n for n in names)
