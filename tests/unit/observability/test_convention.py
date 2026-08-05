"""canonical_red_exprs — the single importable RED convention (ContextCore §4).

Guards that the helper (a) builds the SAME shape the artifact generator emits, and
(b) is null-safe on empty descriptor identities (FR-4a)."""

from __future__ import annotations

from startd8.observability.convention import canonical_red_exprs, red_http
from startd8.observability.metric_descriptor import _PROFILES, profile_for
from startd8.observability.red_taxonomy import RedRole


def test_semconv_http_shape_matches_generator():
    exprs = canonical_red_exprs(profile_for("semconv-http"), "checkout")
    # Same rate shape the generator inlines: sum(rate(<tm><sel>[$__rate_interval]))
    assert exprs[RedRole.RATE] == 'sum(rate(http_server_duration_count{service="checkout"}[$__rate_interval]))'
    assert exprs[RedRole.ERROR].startswith('sum(rate(http_server_duration_count{service="checkout",status=~"5.."}')
    assert "/ sum(rate(http_server_duration_count" in exprs[RedRole.ERROR]
    assert exprs[RedRole.DURATION].startswith("histogram_quantile(0.99, rate(http_server_duration_bucket")


def test_total_throughput_profile_uses_real_metric():
    # span-metrics: throughput is calls_total (a _total counter), not a _count suffix guess.
    exprs = canonical_red_exprs(_PROFILES["span-metrics-connector"], "cart")
    assert "rate(calls_total{" in exprs[RedRole.RATE]


def test_fr4a_empty_error_selector_omits_error():
    # Harbor jobservice: no error dimension → no ERROR expr (not a degenerate 1.0 ratio).
    d = _PROFILES["harbor-jobservice-task"]
    assert d.error_selector == ""
    exprs = canonical_red_exprs(d, "jobservice")
    assert RedRole.RATE in exprs
    assert RedRole.ERROR not in exprs


def test_fr4a_empty_latency_bucket_omits_duration():
    # Harbor core: latency is a summary (empty latency_bucket_metric) → no DURATION expr.
    d = _PROFILES["harbor-core-http"]
    assert d.latency_bucket_metric == ""
    exprs = canonical_red_exprs(d, "core")
    assert RedRole.DURATION not in exprs


def test_red_http_convenience_is_importable():
    exprs = red_http("frontend")
    assert RedRole.RATE in exprs and "http_server_duration_count" in exprs[RedRole.RATE]


# --- TF-1: descriptor-grounded "why" on the OBS-200a coverage warning ---

def test_tf1_obs200a_explains_summary_latency_gap():
    import yaml
    from startd8.validators.observability_artifact_checks import validate_dashboard

    d = _PROFILES["harbor-core-http"]  # empty latency_bucket_metric (summary)
    # Only a Rate panel → Errors + Duration missing → red < 2/3 → OBS-200a warning fires.
    content = yaml.safe_dump({"panels": [
        {"title": "Request Rate", "expr": "sum(rate(harbor_core_http_request_total[5m]))"},
    ]})
    vr = validate_dashboard(content, service_id="core", transport="http", descriptor=d)
    obs = [i for i in vr.issues if i.check == "OBS-200a"]
    assert obs, "expected an OBS-200a warning"
    assert "summary" in obs[0].message.lower(), obs[0].message


def test_tf1_no_descriptor_is_unchanged_message():
    import yaml
    from startd8.validators.observability_artifact_checks import validate_dashboard

    content = yaml.safe_dump({"panels": [{"title": "Request Rate", "expr": "sum(rate(x_total[5m]))"}]})
    vr = validate_dashboard(content, service_id="s", transport="http")  # no descriptor
    obs = [i for i in vr.issues if i.check == "OBS-200a"]
    assert obs and "—" in obs[0].message and "summary" not in obs[0].message.lower()
