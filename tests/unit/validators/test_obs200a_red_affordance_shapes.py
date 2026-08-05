"""OBS-200a RED coverage must credit AffordanceMap / Thanos-shaped panels.

Regression for Step 5b: titled Request Rate / Error Rate / Duration panels with
``rate(..._total)`` / ``..._failures_total`` / ``..._duration_seconds`` exprs were
landed by ``_apply_affordance_red_bind_panels`` but OBS-200a still reported 0%
because ``has_rate_panel`` required ``_count`` (HTTP-semconv) only.
"""

from __future__ import annotations

import yaml
from pathlib import Path

import pytest

from startd8.validators.observability_artifact_checks import (
    _compute_red_coverage,
    has_duration_panel,
    has_error_panel,
    has_explicit_error_panel,
    has_explicit_rate_panel,
    has_rate_panel,
    validate_dashboard,
)

# Step 5b recipe OUT (when present) — live AffordanceMap-fed Thanos dashboards.
_STEP5B_OUT = Path("/tmp/step5b-affordance-regen.AgCBkg")


def _panels(*items: dict) -> list[dict]:
    return list(items)


def test_rate_accepts_prometheus_total_counters():
    panels = _panels(
        {
            "title": "Request Rate",
            "expr": "sum(rate(thanos_compact_group_compaction_runs_started_total[$__rate_interval]))",
        }
    )
    assert has_rate_panel(panels) is True
    assert has_error_panel(panels) is False


def test_rate_still_accepts_http_semconv_count():
    panels = _panels(
        {
            "title": "HTTP Rate",
            "expr": 'sum(rate(http_server_request_duration_seconds_count{status!="error"}[5m]))',
        }
    )
    # status in expr is excluded from Rate (legacy); use clean _count
    panels = _panels(
        {"title": "HTTP Rate", "expr": "sum(rate(http_requests_total_count[5m]))"}
    )
    assert has_rate_panel(panels) is True


def test_error_accepts_failures_total():
    panels = _panels(
        {
            "title": "Error Rate",
            "expr": "sum(rate(thanos_compact_garbage_collection_failures_total[$__rate_interval]))",
        }
    )
    assert has_error_panel(panels) is True
    assert has_rate_panel(panels) is False  # failure rate is E, not R


def test_duration_accepts_title_and_delay_seconds():
    titled = _panels(
        {
            "title": "Duration",
            "expr": "sum(rate(thanos_receive_forward_delay_seconds[$__rate_interval]))",
        }
    )
    assert has_duration_panel(titled) is True
    named = _panels(
        {
            "title": "Forward Delay",
            "expr": "sum(rate(thanos_receive_forward_delay_seconds[$__rate_interval]))",
        }
    )
    assert has_duration_panel(named) is True


def test_thanos_affordance_red_triplet_scores_full():
    """Canonical AffordanceMap RED bind shape → OBS-200a 100%."""
    panels = _panels(
        {
            "title": "Request Rate",
            "expr": "sum(rate(thanos_receive_forward_requests_total[$__rate_interval]))",
        },
        {
            "title": "Error Rate",
            "expr": "sum(rate(thanos_receive_hashrings_file_errors_total[$__rate_interval]))",
        },
        {
            "title": "Duration",
            "expr": "sum(rate(thanos_receive_forward_delay_seconds[$__rate_interval]))",
        },
    )
    assert _compute_red_coverage(panels) == pytest.approx(1.0)
    result = validate_dashboard(
        yaml.dump({"title": "receive", "uid": "obs-receive", "panels": panels}),
        file_path="receive-dashboard-spec.yaml",
        service_id="receive",
    )
    assert result.red_coverage == pytest.approx(1.0)
    failed_200a = [i for i in result.issues if i.check == "OBS-200a"]
    assert failed_200a == []


@pytest.mark.skipif(
    not (_STEP5B_OUT / "dashboards" / "compact-dashboard-spec.yaml").is_file(),
    reason="Step 5b recipe OUT not on disk",
)
@pytest.mark.parametrize(
    "service,min_red",
    [
        ("compact", 2.0 / 3.0),
        ("receive", 2.0 / 3.0),
        ("store", 2.0 / 3.0),
        ("query", 2.0 / 3.0),
        ("rule", 2.0 / 3.0),
        ("sidecar", 2.0 / 3.0),
        # AffordanceMap bind only landed Request Rate for qf (no E/D families) —
        # scorer must still credit Rate (was 0% with _count-only matcher).
        ("query-frontend", 1.0 / 3.0),
    ],
)
def test_step5b_out_services_meet_obs200a_threshold(service: str, min_red: float):
    path = _STEP5B_OUT / "dashboards" / f"{service}-dashboard-spec.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    panels = data.get("panels") or []
    red = _compute_red_coverage(panels)
    assert red >= min_red, (
        f"{service}: RED={red:.2f} (need ≥{min_red:.2f}); "
        f"rate={has_rate_panel(panels)} err={has_error_panel(panels)} "
        f"dur={has_duration_panel(panels)}"
    )


class TestExplicitRatePanelIsNarrow:
    """``has_explicit_rate_panel`` (GENERATION gate) must NOT match the broad
    ``rate(..._total)`` counters ``has_rate_panel`` (SCORING) credits — otherwise
    non-throughput auto-panels (request_size_total/…) suppress the synthesized
    Request Rate panel (the FR-13 ``_still_gets_synthesized_red`` regression from
    5f6fe5f9, where widening the shared detector for the scorer broke generation).
    """

    def test_broad_credits_total_but_narrow_does_not(self):
        # A non-throughput size counter auto-panel — an OTel-convention _total series.
        size_panel = [{
            "title": "Rpc Server Request Size",
            "expr": "rate(rpc_server_request_size_total{service=\"checkout-api\"}[$__rate_interval])",
        }]
        # Scorer (broad) credits it as Rate coverage — intended for AffordanceMap binds.
        assert has_rate_panel(size_panel) is True
        # Generation (narrow) must NOT treat it as an existing Request Rate panel.
        assert has_explicit_rate_panel(size_panel) is False

    def test_narrow_matches_semconv_count_expr(self):
        count_panel = [{
            "title": "Request Rate",
            "expr": "sum(rate(rpc_server_duration_count{service=\"checkout-api\"}[$__rate_interval]))",
        }]
        assert has_explicit_rate_panel(count_panel) is True

    def test_narrow_matches_titled_rate_panel(self):
        titled = [{"title": "Request Rate", "expr": "some_rate_query"}]
        assert has_explicit_rate_panel(titled) is True

    def test_narrow_ignores_error_count_expr(self):
        # An error-leg _count expr must not be mistaken for the R leg.
        err = [{
            "title": "Error Rate",
            "expr": "sum(rate(rpc_server_duration_count{service=\"x\",grpc_code=~\"Internal\"}[5m]))",
        }]
        assert has_explicit_rate_panel(err) is False

    # -- descriptor-aware path: precise on the real throughput series (_count OR _total) --

    def test_descriptor_aware_detects_total_throughput_panel(self):
        # A span-metrics "Calls" auto-panel rates the real throughput counter
        # (calls_total). Keyed on the descriptor's throughput_metric, the gate
        # must see it → no duplicate Request Rate synthesized (regression: the
        # _count-only heuristic missed it and produced a 2nd panel).
        calls = [{"title": "Calls", "expr": "rate(calls_total{service_name=\"cart\"}[$__rate_interval])"}]
        assert has_explicit_rate_panel(calls, "calls_total") is True
        assert has_explicit_rate_panel(calls) is False  # heuristic (no descriptor) misses _total

    def test_descriptor_aware_ignores_nonthroughput_total_size_counter(self):
        # request_size_total is NOT the throughput series → must not count as Rate.
        size = [{"title": "Rpc Server Request Size",
                 "expr": "rate(rpc_server_request_size_total{service=\"x\"}[$__rate_interval])"}]
        assert has_explicit_rate_panel(size, "rpc_server_duration_count") is False

    def test_descriptor_aware_detects_semconv_count_throughput(self):
        rate = [{"title": "Request Rate",
                 "expr": "sum(rate(rpc_server_duration_count{service=\"x\"}[$__rate_interval]))"}]
        assert has_explicit_rate_panel(rate, "rpc_server_duration_count") is True


class TestTotalThroughputDoesNotDuplicate:
    """End-to-end: a _total-throughput profile (span-metrics `calls_total`) whose
    throughput counter is already an auto-panel must NOT get a 2nd synthesized
    Request Rate panel (the boundary the _count-only gate would have regressed).
    """

    def test_span_metrics_service_has_single_throughput_panel(self):
        import re
        from startd8.observability.metric_descriptor import _PROFILES
        from startd8.observability.artifact_generator_generators import generate_dashboard_spec
        from startd8.observability.artifact_generator_models import ServiceHints, ConventionMetric
        from startd8.observability.artifact_generator_context import BusinessContext

        svc = ServiceHints(
            service_id="cartservice", transport="grpc", language="go", kinds=("request",),
            convention_metrics=[ConventionMetric(name="calls", type="counter", source="spanmetrics")],
        )
        biz = BusinessContext(criticality="high", availability="99.9", latency_p99="500ms",
                              throughput="100rps", project_id="ob")
        res = generate_dashboard_spec(svc, biz, descriptor=_PROFILES["span-metrics-connector"])
        titles = [t.strip().strip('"\'') for t in re.findall(r"title:\s*(.+)", res.content)]
        # "Calls" is the throughput panel; a synthesized "Request Rate" would be a duplicate.
        assert "Calls" in titles
        assert "Request Rate" not in titles


class TestExplicitErrorPanelIsNarrow:
    """`has_explicit_error_panel` (GENERATION gate) must not false-positive on a
    non-E panel the way the broad `has_error_panel` (SCORING) does — else it
    suppresses the synthesized Error Rate (the E-leg twin of the Rate regression).
    """

    def test_broad_matches_stray_failure_counter_but_narrow_does_not(self):
        # A per-metric auto-panel for a counter whose name contains "fail" — NOT the
        # RED E leg, but the broad scorer detector matches it on the "fail" substring
        # and would wrongly suppress the synthesized Error Rate.
        stray = [{"title": "Cache Failures", "expr": "rate(cache_failures_total{service=\"x\"}[5m])"}]
        assert has_error_panel(stray) is True                       # broad: "fail" substring
        assert has_explicit_error_panel(stray, "rpc_server_duration_count", 'grpc_code=~"Internal"') is False

    def test_narrow_matches_error_subset_of_throughput(self):
        err = [{"title": "Error Ratio",
                "expr": "sum(rate(rpc_server_duration_count{service=\"x\",grpc_code=~\"Internal\"}[5m]))"
                        " / sum(rate(rpc_server_duration_count{service=\"x\"}[5m]))"}]
        assert has_explicit_error_panel(err, "rpc_server_duration_count", 'grpc_code=~"Internal"') is True

    def test_narrow_matches_error_titled_panel(self):
        assert has_explicit_error_panel([{"title": "Error Rate", "expr": "q"}], "m", "sel") is True

    def test_no_error_selector_service_only_titled_panels_count(self):
        # Harbor jobservice: error_selector="" (no error dimension) — a stray expr
        # must not be read as the E leg.
        stray = [{"title": "Scheduled", "expr": "rate(harbor_task_scheduled_total[5m])"}]
        assert has_explicit_error_panel(stray, "harbor_task_scheduled_total", "") is False
