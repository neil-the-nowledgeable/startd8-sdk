# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Instrumentation-generation framework (REQ FR-XC) — ports the Harbor reference impl's selftest.

Each test mirrors an assertion from `analysis/instrumentation-gen/framework.py::_selftest` (which was green
alongside the compile + emit gates against real Harbor source), plus the Envoy runtime-composed boundary.
"""

import pytest

from startd8.scaffold_codegen.instrumentation_gen import (
    TIER_DETERMINISTIC,
    TIER_LLM_FILL,
    GoOtelRenderer,
    InstrumentationContract,
    InstrumentationGap,
    close_gap,
    default_registry,
    harbor_core_reference_gap,
)


def test_contract_derives_http_meter_provider_from_grounded_gap():
    """A grounded otelhttp/http.server gap → the language-agnostic meter-provider-on-existing-http contract."""
    contract = InstrumentationContract.from_gap(harbor_core_reference_gap())
    assert contract.via == "otel-meter-provider-on-existing-http-instrumentation"
    assert contract.source_instrumentable is True


def test_go_renderer_deterministic_patch_adds_with_meter_provider():
    """The proven Harbor case: deterministic tier, and the one-line core of the fix (WithMeterProvider) is present."""
    patch = close_gap(
        harbor_core_reference_gap(),
        {
            "trace_provider": "src/lib/trace/trace.go",
            "http_options": "src/lib/trace/helper.go",
            "http_options_anchor": "otelhttp.WithTracerProvider(otel.GetTracerProvider()),",
        },
    )
    assert patch.language == "go"
    assert patch.tier == TIER_DETERMINISTIC
    assert any("WithMeterProvider" in e.content for e in patch.edits), "must attach a MeterProvider"


def test_scrape_default_uses_prometheus_exporter_on_default_registry():
    """Export-mechanism awareness: the default (prometheus-scrape) variant registers the OTel Prometheus
    exporter on the default registry — NOT otlp-push (which would verify nothing against a scraper)."""
    patch = close_gap(harbor_core_reference_gap(), {})
    assert any("exporters/prometheus" in d for d in patch.new_deps), patch.new_deps
    assert any("otelprom.New()" in e.content for e in patch.edits), "scrape variant registers on the default registry"


def test_otlp_push_variant_uses_otlpmetrichttp():
    """A subject that pushes (otlp-push) gets the otlpmetrichttp exporter instead."""
    gap = InstrumentationGap(
        subject="s",
        service="svc",
        language="go",
        missing_families=["http.server.request.duration"],
        mechanism="otelhttp present",
        export_mechanism="otlp-push",
        source_evidence={"trace_provider": "t", "http_options": "h"},
    )
    patch = close_gap(gap, {})
    assert any("otlpmetrichttp" in d for d in patch.new_deps), patch.new_deps


def test_unregistered_language_raises_register_one_renderer():
    """Language-agnostic guard: an unregistered language fails loud with the 'register one renderer' guidance."""
    gap = InstrumentationGap("x", "s", "rust", ["http.server.request.duration"], "m")
    with pytest.raises(NotImplementedError) as ei:
        close_gap(gap, {})
    assert "rust" in str(ei.value) and "renderer" in str(ei.value)


def test_tier_degrades_honestly_without_evidence():
    """Missing source_evidence ⇒ LLM-fill, never a fabricated 'deterministic' template."""
    gap = InstrumentationGap("harbor", "core", "go", ["http.server.request.duration"], "otelhttp present", {})
    contract = InstrumentationContract.from_gap(gap)
    assert GoOtelRenderer().resolve_tier(contract) == TIER_LLM_FILL


def test_runtime_composed_envoy_is_not_source_instrumentable():
    """The Envoy boundary is baked in: a runtime-composed gap yields a non-source-instrumentable contract
    (closeable only by live-scrape, never by generation)."""
    gap = InstrumentationGap(
        subject="istio",
        service="proxy",
        language="cpp-envoy",
        missing_families=["istio_requests_total"],
        mechanism="runtime-composed envoy data-plane stats sink",
    )
    contract = InstrumentationContract.from_gap(gap)
    assert contract.source_instrumentable is False
    assert contract.via == "runtime-composed"


def test_close_gap_enforces_source_instrumentable_boundary():
    """The Envoy boundary is ENFORCED at the entry point, not just computed: close_gap refuses a
    runtime-composed gap with the honest 'live-scrape, not a missing renderer' message — never the
    misleading 'register one renderer' error (code-review hardening: source_instrumentable was
    set-but-unread)."""
    gap = InstrumentationGap(
        subject="istio", service="proxy", language="cpp-envoy",
        missing_families=["istio_requests_total"],
        mechanism="runtime-composed envoy data-plane stats sink",
    )
    with pytest.raises(NotImplementedError) as ei:
        close_gap(gap, {})
    msg = str(ei.value).lower()
    assert "source-instrumentable" in msg and "live-scrape" in msg
    assert "register one renderer" not in msg  # NOT the misleading missing-renderer error


def test_go_renderer_rejects_generic_via_instead_of_wrong_http_patch():
    """A non-http Go gap resolves to the GENERIC contract, which GoOtelRenderer has no template for —
    close_gap must fail LOUD, not emit the otelhttp http.server patch (render() is http-specific
    regardless of via). Code-review hardening: supports() was over-permissive (startswith)."""
    gap = InstrumentationGap(
        subject="s", service="cache", language="go",
        missing_families=["db.client.operation.duration"],  # not http.server → generic contract
        mechanism="prometheus client present, no meter provider",
        source_evidence={"trace_provider": "t"},
    )
    assert InstrumentationContract.from_gap(gap).via == "otel-meter-provider-generic"
    with pytest.raises(NotImplementedError) as ei:
        close_gap(gap, {})
    assert "does not support" in str(ei.value)


def test_default_registry_ships_go_only():
    """GoOtelRenderer is registered; the rest are PLANNED_RENDERERS TODOs (register one to add a language)."""
    assert default_registry().languages() == ["go"]
