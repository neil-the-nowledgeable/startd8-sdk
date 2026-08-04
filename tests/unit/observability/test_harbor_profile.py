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
