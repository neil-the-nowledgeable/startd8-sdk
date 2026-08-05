"""Unit tests for red_taxonomy — the one RED-role classifier + derived questions +
deduping synthesizer (RED_TAXONOMY_UNIFICATION_REQUIREMENTS.md v0.4, FR-1..FR-10 + R1)."""

from __future__ import annotations

import pytest

from startd8.observability.metric_descriptor import _PROFILES
from startd8.observability.red_taxonomy import (
    RED_ROLES,
    RedPanel,
    RedRole,
    classify_red_role,
    has_red_role,
    is_red_protected,
    red_coverage,
    red_roles_present,
    synthesize_red_panels,
)


def _panel(title="", expr=""):
    return {"title": title, "expr": expr}


# --- FR-1 ---------------------------------------------------------------------

def test_fr1_enum_and_triple():
    assert {r for r in RedRole} == {RedRole.RATE, RedRole.ERROR, RedRole.DURATION, RedRole.NONE}
    assert RED_ROLES == frozenset({RedRole.RATE, RedRole.ERROR, RedRole.DURATION})
    assert RedRole.NONE not in RED_ROLES


# --- FR-2: RATE for each _total-throughput profile (no _count suffix dependence) ---

@pytest.mark.parametrize("profile", [
    "span-metrics-connector",       # calls_total
    "tempo-spanmetrics",            # traces_spanmetrics_calls_total
    "harbor-core-http",             # harbor_core_http_request_total
    "harbor-jobservice-task",       # harbor_task_scheduled_total
])
def test_fr2_rate_for_total_throughput_profiles(profile):
    d = _PROFILES[profile]
    tm = d.throughput_metric
    assert tm.endswith("_total"), "precondition: this profile is a _total-throughput one"
    panel = _panel("Request Rate", f"sum(rate({tm}[$__rate_interval]))")
    assert classify_red_role(panel, d) is RedRole.RATE


def test_fr2_rate_for_count_profiles():
    d = _PROFILES["semconv-grpc"]  # rpc_server_duration_count
    panel = _panel("Request Rate", f"sum(rate({d.throughput_metric}[5m]))")
    assert classify_red_role(panel, d) is RedRole.RATE


# --- FR-2a: a non-throughput _total sibling must NOT be RATE ---

def test_fr2a_non_throughput_total_is_not_rate():
    d = _PROFILES["semconv-grpc"]  # throughput = rpc_server_duration_count
    size = _panel("Rpc Server Request Size", 'rate(rpc_server_request_size_total{service="x"}[5m])')
    assert classify_red_role(size, d) is RedRole.NONE


# --- FR-3: error-ratio (throughput filtered by error_selector) is ERROR not RATE ---

def test_fr3_error_ratio_is_error_not_rate():
    d = _PROFILES["semconv-grpc"]
    tm, es = d.throughput_metric, d.error_selector
    err = _panel("Error Rate", f"sum(rate({tm}{{{es}}}[5m])) / sum(rate({tm}[5m]))")
    assert classify_red_role(err, d) is RedRole.ERROR


# --- FR-4: DURATION via real bucket; stricter freeform rule ---

def test_fr4_duration_via_bucket():
    d = _PROFILES["semconv-grpc"]  # rpc_server_duration_bucket
    panel = _panel("Latency (p99)", f"histogram_quantile(0.99, rate({d.latency_bucket_metric}[5m]))")
    assert classify_red_role(panel, d) is RedRole.DURATION


def test_fr4_bare_histogram_quantile_over_size_is_not_duration_freeform():
    # descriptor-free stricter rule: a histogram_quantile over a non-latency bucket
    # (no duration/latency token) is NOT Duration (B3 fix).
    panel = _panel("Size p99", "histogram_quantile(0.99, rate(http_server_response_size_bucket[5m]))")
    assert classify_red_role(panel, None) is RedRole.NONE


# --- FR-4a: empty descriptor identity must never fabricate a role (the critical bug) ---

def test_fr4a_empty_latency_bucket_does_not_fabricate_duration():
    d = _PROFILES["harbor-core-http"]
    assert d.latency_bucket_metric == "", "precondition: summary subject, empty bucket"
    # A throughput panel — must be RATE (via the real throughput_metric), never DURATION
    # from the empty latency_bucket_metric matching via `"" in expr`.
    panel = _panel("Request Rate", f"rate({d.throughput_metric}[5m])")
    role = classify_red_role(panel, d)
    assert role is RedRole.RATE
    assert role is not RedRole.DURATION


def test_fr4a_empty_error_selector_does_not_fabricate_error():
    d = _PROFILES["harbor-jobservice-task"]
    assert d.error_selector == "", "precondition: no error dimension"
    panel = _panel("Scheduled", f"rate({d.throughput_metric}[5m])")
    role = classify_red_role(panel, d)
    assert role is RedRole.RATE
    assert role is not RedRole.ERROR


def test_fr4a_harbor_duration_only_via_title():
    d = _PROFILES["harbor-core-http"]  # empty latency_bucket_metric
    titled = _panel("Duration", "harbor_core_http_request_duration_seconds{quantile=\"0.99\"}")
    assert classify_red_role(titled, d) is RedRole.DURATION


# --- Derived questions ---

def test_derived_questions_agree_within_tier():
    panels = [
        _panel("Request Rate", "sum(rate(rpc_server_duration_count[5m]))"),
        _panel("Error Rate", 'sum(rate(rpc_server_duration_count{grpc_code=~"Internal"}[5m]))'),
        _panel("Latency", "histogram_quantile(0.99, rate(rpc_server_duration_bucket[5m]))"),
    ]
    roles = red_roles_present(panels)
    assert roles == RED_ROLES
    assert red_coverage(panels) == 1.0
    assert has_red_role(RedRole.RATE, panels)
    # FR-7: scored ⟺ protected within the same (descriptor-free) tier
    for p in panels:
        assert is_red_protected(p) == (classify_red_role(p) is not RedRole.NONE)


# --- FR-9 / FR-10: deduping synthesizer ---

def _cand(role, ident, title):
    return RedPanel(role=role, metric_identity=ident, title=title, expr="q", unit="u", group="g")


def test_fr9_skips_role_already_present():
    existing = [_panel("Request Rate", "sum(rate(calls_total[5m]))")]
    out = synthesize_red_panels(
        existing, descriptor=None, want_roles=RED_ROLES,
        candidates=[_cand(RedRole.RATE, "calls_total", "Request Rate")],
    )
    assert out == []  # RATE already present → not synthesized


def test_fr10_dedup_by_role_and_identity():
    # Two candidates, same (role, identity) from two sources → collapse to one.
    out = synthesize_red_panels(
        [], descriptor=None, want_roles=RED_ROLES,
        candidates=[
            _cand(RedRole.RATE, "calls_total", "Request Rate (descriptor)"),
            _cand(RedRole.RATE, "calls_total", "Request Rate (locus)"),
        ],
    )
    assert len(out) == 1


def test_fr9_at_most_one_per_role():
    out = synthesize_red_panels(
        [], descriptor=None, want_roles=RED_ROLES,
        candidates=[
            _cand(RedRole.RATE, "a_total", "R"),
            _cand(RedRole.ERROR, "a_total", "E"),
            _cand(RedRole.DURATION, "a_bucket", "D"),
        ],
    )
    assert {c.role for c in out} == RED_ROLES
    assert len(out) == 3
