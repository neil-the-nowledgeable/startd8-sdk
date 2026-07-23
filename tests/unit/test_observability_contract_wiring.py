"""Issue #268 R2 — OPI-300 contractor prompt consumption of the observability contract.

The enriched convention metrics reach the seed (R1) but until this, no prompt consumed them,
so generated services got generic instrumentation. These assert the spec/draft prompt section
(REQ-OPI-300) lists exact metric names + instrument types + SDK packages + transport, reads the
per-task `convention_metrics` first and the seed `observability_contract` as a fallback (OPI-601),
and injects NOTHING when absent (OPI-302).
"""

from __future__ import annotations

from startd8.implementation_engine.spec_builder import (
    _build_observability_guidance_section,
)


_METRICS = [
    {"name": "rpc.server.duration", "type": "histogram", "source": "otel_semconv:grpc"},
    {"name": "rpc.server.requests", "type": "counter"},
]


class TestObservabilityGuidanceSection:
    def test_per_task_convention_metrics_produce_guidance(self):
        # REQ-OPI-300: exact names + instrument, transport, SDK packages.
        s = _build_observability_guidance_section({
            "convention_metrics": _METRICS,
            "transport": "grpc",
            "sdk_packages": ["opentelemetry-instrumentation-grpc"],
            "alert_thresholds": {"latency_p99": "500ms"},
        })
        assert "REQ-OPI-300" in s
        assert "`rpc.server.duration` — histogram" in s
        assert "`rpc.server.requests` — counter" in s
        assert "grpc" in s  # transport → interceptor hint
        assert "opentelemetry-instrumentation-grpc" in s  # exact import package
        assert "500ms" in s  # alert threshold

    def test_absent_metrics_inject_nothing(self):
        # REQ-OPI-302: no metrics ⇒ empty section, contractor operates exactly as today.
        assert _build_observability_guidance_section({}) == ""
        assert _build_observability_guidance_section({"transport": "grpc"}) == ""
        assert _build_observability_guidance_section({"convention_metrics": []}) == ""

    def test_fallback_to_seed_contract_via_service_name(self):
        # OPI-601: when the per-task field is absent, derive from the seed observability_contract
        # keyed by the task's (normalized) service_name.
        s = _build_observability_guidance_section({
            "service_name": "checkoutservice",
            "observability_contract": {
                "services": {
                    "checkout-service": {  # original id (hyphen) — matched normalized
                        "transport": "grpc",
                        "convention_metrics": _METRICS,
                        "sdk_packages": ["opentelemetry-instrumentation-grpc"],
                    },
                },
            },
        })
        assert "`rpc.server.duration` — histogram" in s
        assert "opentelemetry-instrumentation-grpc" in s

    def test_fallback_no_matching_service_injects_nothing(self):
        s = _build_observability_guidance_section({
            "service_name": "paymentservice",
            "observability_contract": {"services": {"checkoutservice": {"convention_metrics": _METRICS}}},
        })
        assert s == ""

    def test_v2_split_names_at_p1_thresholds_at_p2(self):
        # REQ-OPI-300 V2 (#268 backlog QW-1): metric names + SDK packages survive budget
        # pressure at P1 (never trimmed); alert thresholds are the trimmable P2 detail.
        from startd8.implementation_engine.spec_builder import (
            build_observability_guidance_sections,
        )
        p1, p2 = build_observability_guidance_sections({
            "convention_metrics": _METRICS,
            "sdk_packages": ["opentelemetry-instrumentation-grpc"],
            "alert_thresholds": {"latency_p99": "500ms"},
        })
        # P1 carries the load-bearing anti-wrong-import content...
        assert "rpc.server.duration" in p1 and "opentelemetry-instrumentation-grpc" in p1
        assert "500ms" not in p1                      # ...but NOT the trimmable thresholds
        assert "500ms" in p2                          # P2 detail carries the thresholds
        # no thresholds ⇒ empty P2, non-empty P1 (still injects the names)
        p1b, p2b = build_observability_guidance_sections({"convention_metrics": _METRICS})
        assert p1b and p2b == ""

    def test_wired_at_p1_and_p2_in_the_prompt_assembly(self):
        # REQ-OPI-301: names at P1 (priority 1), thresholds at P2 (priority 2).
        import inspect
        from startd8.implementation_engine import spec_builder
        src = inspect.getsource(spec_builder.build_spec_prompt)
        assert 'build_observability_guidance_sections' in src
        assert '(1, "observability_contract"' in src   # P1: names/packages, never trimmed
        assert '(2, "observability_thresholds"' in src  # P2: thresholds, trimmable
