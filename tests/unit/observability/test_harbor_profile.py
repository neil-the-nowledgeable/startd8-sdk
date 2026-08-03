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
