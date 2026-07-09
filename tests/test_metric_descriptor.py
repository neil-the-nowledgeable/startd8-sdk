"""Tests for MetricDescriptor + convention profiles (Step 2).

Covers ContextCore REQ_TARGET_METRIC_BINDING.md FR-1, FR-1a, FR-5, FR-5a.
The three built-in profiles are asserted against the *normative* FR-5 table so
this file doubles as a drift check against the requirements' single source of
truth.
"""

import pytest

from startd8.observability.metric_descriptor import (
    MetricDescriptor,
    available_profiles,
    profile_for,
    profile_for_transport,
    resolve_descriptor,
    SEMCONV_PROFILES,
    SPAN_METRICS_PROFILE,
)
from startd8.observability.artifact_generator_context import extract_service_hints


# ── FR-5: the three profiles resolve to the normative table ────────────────
class TestProfilePresets:
    def test_all_three_profiles_present(self):
        assert set(available_profiles()) == {
            "semconv-http",
            "semconv-grpc",
            "span-metrics-connector",
        }

    def test_semconv_http_matches_fr5(self):
        d = profile_for("semconv-http")
        assert d.service_label_key == "service"
        assert d.error_selector == 'status=~"5.."'
        assert d.throughput_metric == "http_server_duration_count"
        assert d.latency_bucket_metric == "http_server_duration_bucket"
        assert d.latency_unit == "s"

    def test_semconv_grpc_matches_fr5(self):
        d = profile_for("semconv-grpc")
        assert d.service_label_key == "service"
        assert d.error_selector == 'grpc_code=~"Unavailable|Internal|Unimplemented|DataLoss"'
        assert d.throughput_metric == "rpc_server_duration_count"
        assert d.latency_bucket_metric == "rpc_server_duration_bucket"
        assert d.latency_unit == "s"

    def test_span_metrics_matches_fr5(self):
        d = profile_for("span-metrics-connector")
        assert d.service_label_key == "service_name"
        assert d.error_selector == 'status_code="STATUS_CODE_ERROR"'
        assert d.throughput_metric == "calls_total"
        assert d.latency_bucket_metric == "duration_milliseconds_bucket"
        assert d.latency_unit == "ms"


# ── FR-5a: SDK-semconv and span-metrics are co-equal, first-class ──────────
class TestCoEqualSurfaces:
    def test_both_surfaces_named(self):
        assert set(SEMCONV_PROFILES) == {"semconv-http", "semconv-grpc"}
        assert SPAN_METRICS_PROFILE == "span-metrics-connector"

    def test_both_surfaces_resolvable(self):
        # Neither surface is privileged; both resolve via the same entrypoint.
        for name in (*SEMCONV_PROFILES, SPAN_METRICS_PROFILE):
            assert isinstance(profile_for(name), MetricDescriptor)

    def test_surfaces_differ_on_all_four_axes(self):
        semconv = profile_for("semconv-grpc")
        span = profile_for("span-metrics-connector")
        assert semconv.service_label_key != span.service_label_key   # label
        assert semconv.error_selector != span.error_selector         # selector
        assert semconv.latency_bucket_metric != span.latency_bucket_metric  # name
        assert semconv.latency_unit != span.latency_unit             # unit


# ── unknown / alias resolution ─────────────────────────────────────────────
class TestResolution:
    def test_unknown_profile_raises(self):
        with pytest.raises(ValueError, match="unknown metric convention profile"):
            profile_for("prometheus-native")

    @pytest.mark.parametrize(
        "transport,expected",
        [("grpc", "semconv-grpc"), ("grpc-web", "semconv-grpc"),
         ("http", "semconv-http"), ("HTTP", "semconv-http")],
    )
    def test_transport_default(self, transport, expected):
        assert profile_for_transport(transport).profile == expected

    def test_unknown_transport_falls_back_to_http(self):
        # Matches today's generator behavior: http is the transport default.
        assert profile_for_transport("thrift").profile == "semconv-http"


# ── selector rendering (FR-1) ──────────────────────────────────────────────
class TestSelectorRendering:
    def test_span_metrics_error_selector(self):
        d = profile_for("span-metrics-connector")
        assert d.selector("checkoutservice", error=True) == (
            '{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}'
        )

    def test_span_metrics_total_selector_omits_error(self):
        d = profile_for("span-metrics-connector")
        assert d.selector("checkoutservice") == '{service_name="checkoutservice"}'

    def test_semconv_http_error_selector(self):
        d = profile_for("semconv-http")
        assert d.selector("frontend", error=True) == '{service="frontend",status=~"5.."}'

    def test_compound_extra_selectors_are_anded(self):
        d = MetricDescriptor(
            profile="custom",
            service_label_key="service_name",
            error_selector='status_code="STATUS_CODE_ERROR"',
            extra_selectors=('span_kind="SPAN_KIND_SERVER"',),
        )
        assert d.selector("checkout", error=True) == (
            '{service_name="checkout",span_kind="SPAN_KIND_SERVER",status_code="STATUS_CODE_ERROR"}'
        )

    def test_service_value_template(self):
        d = MetricDescriptor(
            profile="custom",
            service_label_key="service",
            service_label_value_tpl="contextcore-{service_id}",
        )
        assert d.service_matcher("frontend") == 'service="contextcore-frontend"'


# ── FR-4a: unit-aware threshold scaling ────────────────────────────────────
class TestThresholdScaling:
    def test_seconds_profile_keeps_seconds(self):
        # semconv-http latency is in seconds → 500ms stays 0.5
        assert profile_for("semconv-http").scale_threshold_seconds(0.5) == 0.5

    def test_millisecond_profile_scales_1000x(self):
        # span-metrics latency is in ms → 500ms becomes 500
        assert profile_for("span-metrics-connector").scale_threshold_seconds(0.5) == 500.0


# ── FR-1a: non-RED artifacts ───────────────────────────────────────────────
class TestNonRedFields:
    def test_logql_stream_key_falls_back_to_service_label(self):
        d = profile_for("span-metrics-connector")
        assert d.logql_stream_key() == "service_name"

    def test_logql_stream_key_override(self):
        d = MetricDescriptor(
            profile="custom", service_label_key="service_name", logql_label_key="service"
        )
        assert d.logql_stream_key() == "service"

    def test_db_system_label_default(self):
        assert profile_for("semconv-http").db_system_label_key == "db_system"


# ── descriptor is safe to share (frozen) ───────────────────────────────────
def test_descriptor_is_frozen():
    d = profile_for("semconv-http")
    with pytest.raises(Exception):
        d.service_label_key = "changed"  # type: ignore[misc]


# ── resolve_descriptor: FR-7 ladder terminus + FR-3 leniency ───────────────
class TestResolveDescriptor:
    def test_explicit_profile_wins(self):
        d = resolve_descriptor(profile="span-metrics-connector", transport="grpc")
        assert d.profile == "span-metrics-connector"
        assert d.service_label_key == "service_name"

    def test_no_profile_falls_back_to_transport(self):
        # FR-7 tier 6: semconv-{transport} default.
        assert resolve_descriptor(profile=None, transport="grpc").profile == "semconv-grpc"
        assert resolve_descriptor(profile="", transport="http").profile == "semconv-http"

    def test_overrides_apply_per_axis(self):
        # Start from a profile, override a single axis (FR-1 escape hatch).
        d = resolve_descriptor(
            profile="semconv-http",
            overrides={"service_label_key": "service_name"},
        )
        assert d.service_label_key == "service_name"          # overridden
        assert d.error_selector == 'status=~"5.."'            # inherited
        assert d.profile == "semconv-http+override"

    def test_extra_selectors_override_coerced_to_tuple(self):
        d = resolve_descriptor(
            profile="span-metrics-connector",
            overrides={"extra_selectors": ['span_kind="SPAN_KIND_SERVER"']},
        )
        assert d.extra_selectors == ('span_kind="SPAN_KIND_SERVER"',)

    def test_unknown_profile_is_lenient_not_raising(self):
        # FR-3 skew: a newer manifest must not crash an older generator.
        d = resolve_descriptor(profile="prometheus-native", transport="grpc")
        assert d.profile == "semconv-grpc"  # fell back to transport default

    def test_unknown_override_key_ignored(self):
        d = resolve_descriptor(
            profile="semconv-http",
            overrides={"bogus_axis": "x", "latency_unit": "ms"},
        )
        assert d.latency_unit == "ms"           # known key applied
        assert not hasattr(d, "bogus_axis")     # unknown key ignored, no crash


# ── extract_service_hints reads the binding fields (FR-3 contract) ─────────
class TestServiceHintsBinding:
    def _meta(self, metrics_block):
        return {
            "instrumentation_hints": {
                "checkoutservice": {"transport": "grpc", "metrics": metrics_block}
            }
        }

    def test_reads_convention_profile_and_overrides(self):
        meta = self._meta({
            "convention_based": [{"name": "calls", "type": "counter"}],
            "convention_profile": "span-metrics-connector",
            "descriptor_overrides": {"latency_unit": "ms"},
        })
        [h] = extract_service_hints(meta)
        assert h.metric_profile == "span-metrics-connector"
        assert h.descriptor_overrides == {"latency_unit": "ms"}
        # end-to-end: hints → resolved descriptor
        d = resolve_descriptor(
            profile=h.metric_profile, transport=h.transport, overrides=h.descriptor_overrides
        )
        assert d.service_label_key == "service_name"

    def test_legacy_metadata_without_binding_fields(self):
        # FR-3 back-compat: a new generator reading legacy metadata (no
        # profile) yields transport-default behavior, not a crash.
        meta = self._meta({"convention_based": [{"name": "rpc.server.duration", "type": "histogram"}]})
        [h] = extract_service_hints(meta)
        assert h.metric_profile == ""
        assert h.descriptor_overrides == {}
        assert resolve_descriptor(profile=h.metric_profile, transport=h.transport).profile == "semconv-grpc"

    def test_malformed_overrides_coerced_to_empty(self):
        meta = self._meta({
            "convention_based": [],
            "descriptor_overrides": "not-a-dict",
        })
        [h] = extract_service_hints(meta)
        assert h.descriptor_overrides == {}
