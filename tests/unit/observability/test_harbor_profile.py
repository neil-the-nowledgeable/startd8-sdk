# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Name-scoped identity + the grounded Harbor profiles (Harbor pilot, 2026-08-03).

Harbor is the archetypal Prometheus-classic surface: the component is in the metric
NAME (`harbor_core_*`) and there is NO per-service label. These tests pin (a) that an
empty ``service_label_key`` yields a clean no-identity selector and (b) that the drafted
``harbor-*`` profiles render selectors that bind to Harbor's real, grounded series.
"""
from __future__ import annotations

from startd8.observability.metric_descriptor import resolve_descriptor, profile_for


def test_empty_service_label_key_yields_no_identity_matcher():
    d = resolve_descriptor(profile="harbor-core-http")
    # name-scoped: no `service="core"` matcher — the metric name is the identity.
    assert d.selector("core") == "{}"
    assert d.selector("core", error=True) == '{code=~"5.."}'


def test_existing_profiles_keep_their_identity_matcher():
    # the empty-key path must not perturb the labelled OTel presets (byte-identity).
    assert resolve_descriptor(profile="semconv-http").selector("svc") == '{service="svc"}'
    assert (
        resolve_descriptor(profile="span-metrics-connector").selector("svc")
        == '{service_name="svc"}'
    )


def test_harbor_core_http_axes_are_grounded():
    d = profile_for("harbor-core-http")
    assert d.throughput_metric == "harbor_core_http_request_total"
    assert d.error_selector == 'code=~"5.."'          # label is `code`, not semconv `status`
    assert d.latency_bucket_metric == ""              # summary, not histogram (EC-SUMMARY-TYPE)
    assert d.service_label_key == ""                  # name-scoped


def test_harbor_jobservice_task_binds_throughput_only():
    d = profile_for("harbor-jobservice-task")
    assert d.throughput_metric == "harbor_task_scheduled_total"   # real name, not harbor_jobservice_task_total
    assert d.error_selector == ""                                 # no error dimension on the counter
    assert d.selector("jobservice") == "{}"


def test_extra_selectors_survive_name_scoped_filtering():
    # a name-scoped profile that ALSO declares extra_selectors keeps them (empty identity dropped).
    from dataclasses import replace
    d = replace(profile_for("harbor-core-http"), extra_selectors=('operation!=""',))
    assert d.selector("core") == '{operation!=""}'
    assert d.selector("core", error=True) == '{operation!="",code=~"5.."}'


def test_verifier_skips_service_label_axis_for_name_scoped_profile():
    # diagnose_axes must NOT emit a service_label_key finding when the profile is
    # name-scoped — the query binds by metric name; there is no service label to check.
    from startd8.observability.validate_promql import diagnose_axes
    findings = diagnose_axes(
        profile_for("harbor-core-http"),
        "core",
        live_metric_names=["harbor_core_http_request_total"],
        label_values_fn=lambda k: (_ for _ in ()).throw(AssertionError("must not probe an empty key")),
        probe_budget=[0],
    )
    axes = {f.axis for f in findings}
    assert "service_label_key" not in axes           # skipped, not flagged
    # a labelled profile still checks it (regression guard)
    labelled = diagnose_axes(
        profile_for("semconv-http"), "svc",
        live_metric_names=[], label_values_fn=lambda k: [], probe_budget=[0],
    )
    assert "service_label_key" in {f.axis for f in labelled}


def test_db_panel_selector_has_no_leading_comma_when_name_scoped():
    # the DB panel builds its selector by hand; a name-scoped (empty) service_matcher
    # must not render `{,db_system=...}` (a PromQL parse error / live HTTP 400).
    from startd8.observability.metric_descriptor import profile_for as _pf
    d = _pf("harbor-core-http")
    matcher = d.service_matcher("core")            # "" for name-scoped
    sel = ",".join(p for p in (matcher, 'db_system="postgresql"') if p)
    assert sel == 'db_system="postgresql"'         # no leading comma
    assert not sel.startswith(",")
    # labelled profile still includes the identity matcher
    matcher2 = _pf("semconv-http").service_matcher("svc")
    sel2 = ",".join(p for p in (matcher2, 'db_system="postgresql"') if p)
    assert sel2 == 'service="svc",db_system="postgresql"'


# ---------------------------------------------------------------------------
# REQ-01 FR-3 — manifest-declarable metric profiles (subject identity as DATA,
# not an SDK code edit to _PROFILES). The declared tier resolves with the same
# precedence as built-ins; a built-in name wins on collision.
# ---------------------------------------------------------------------------

#: the grounded harbor-core-http axes, expressed as manifest DATA (what a subject
#: would put under spec.observability.metricsProfiles instead of editing _PROFILES).
_HARBOR_CORE_AS_DATA = {
    "service_label_key": "",
    "error_selector": 'code=~"5.."',
    "throughput_metric": "harbor_core_http_request_total",
    "latency_bucket_metric": "",
    "latency_unit": "s",
}


def _axes(d):
    from dataclasses import fields
    return {f.name: getattr(d, f.name) for f in fields(d) if f.name != "profile"}


def test_declared_profile_binds_identically_to_the_built_in():
    """FR-3 acceptance: a manifest-declared profile with the harbor-core-http axes
    resolves to the same descriptor (bar its provenance name) as the built-in —
    proving the harbor-* profiles CAN move out of _PROFILES code into data."""
    from startd8.observability.metric_descriptor import resolve_descriptor, _PROFILES

    declared = resolve_descriptor(
        profile="harbor-core-http-data",
        transport="http",
        declared_profiles={"harbor-core-http-data": _HARBOR_CORE_AS_DATA},
    )
    assert _axes(declared) == _axes(_PROFILES["harbor-core-http"])
    # selectors render identically (the load-bearing behavior)
    assert declared.selector("core") == "{}"
    assert declared.selector("core", error=True) == '{code=~"5.."}'


def test_declared_profile_partial_inherits_transport_base():
    from startd8.observability.metric_descriptor import resolve_descriptor

    d = resolve_descriptor(
        profile="p", transport="http",
        declared_profiles={"p": {"throughput_metric": "my_total"}},
    )
    assert d.throughput_metric == "my_total"
    # unset axes inherit semconv-http (labelled identity)
    assert d.service_label_key == "service"


def test_builtin_wins_on_name_collision():
    """A declared profile MUST NOT silently shadow a built-in (e.g. semconv-http)."""
    from startd8.observability.metric_descriptor import resolve_descriptor

    d = resolve_descriptor(
        profile="semconv-http", transport="http",
        declared_profiles={"semconv-http": {"error_selector": "SHADOWED"}},
    )
    assert d.error_selector != "SHADOWED"
    assert d.profile == "semconv-http"


def test_unknown_profile_degrades_not_raises():
    from startd8.observability.metric_descriptor import resolve_descriptor

    d = resolve_descriptor(profile="nope", transport="http", declared_profiles={})
    assert d.profile == "semconv-http"


def test_no_declared_profiles_is_byte_identical():
    """Absent declared_profiles ⇒ pre-FR-3 behavior (built-in resolves, unknown degrades)."""
    from startd8.observability.metric_descriptor import resolve_descriptor

    assert resolve_descriptor(profile="harbor-core-http").profile == "harbor-core-http"
    assert resolve_descriptor(profile="ghost").profile == "semconv-http"


def test_declared_profile_flows_through_generation(tmp_path):
    """End-to-end: a service selecting a metadata-declared profile binds to the
    declared axes through generate_observability_artifacts (no _PROFILES edit)."""
    import json
    from startd8.observability.artifact_generator import generate_observability_artifacts

    meta = {
        "project_id": "demo",
        # FR-3 definitions on the export path (top-level metadata.metricsProfiles)
        "metricsProfiles": {"acme-http": _HARBOR_CORE_AS_DATA},
        "instrumentation_hints": {
            "svc": {
                "service_id": "svc", "transport": "http",
                "metricsProfile": "acme-http",          # the selector
                "metrics": {"convention_based": [
                    {"name": "harbor_core_http_request_total", "type": "counter", "source": "prom"},
                ]},
            },
        },
    }
    mp = tmp_path / "onboarding-metadata.json"
    mp.write_text(json.dumps(meta))
    report = generate_observability_artifacts(
        onboarding_metadata_path=mp, output_dir=tmp_path / "out",
    )
    # the declared throughput series appears in a generated artifact (bound, not semconv default)
    blob = "\n".join(a.content for a in report.artifacts if a.content)
    assert "harbor_core_http_request_total" in blob
