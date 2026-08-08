"""Phase 0 (issue #226, FR-0/FR-11) — full-output golden/snapshot regression tests.

These lock the CURRENT byte-for-byte output of the observability generator for a
fixture matrix, BEFORE any of the #226 determination changes (FR-12/FR-13) touch the
generators. Every later phase must keep these green; a diff here is a parity break.

The matrix (per CRP R1-S3) deliberately exercises the paths the later phases change:
  - ``http_with_availability`` — full RED triplet + the **Availability (1h) gauge**
    that FR-13a must carve out of the RED-synthesis deletion.
  - ``counter_only`` — an http service whose only convention metric is a counter (no
    ``*duration*`` histogram). Proves the current "resolves to the triplet but emits no
    latency block" behavior that FR-12a's AND-composition must preserve.
  - ``grpc_server`` — grpc-shaped output (distinct descriptor profile).

Goldens live under ``data/http_golden/``. To (re)generate after an *intended* change::

    UPDATE_GOLDENS=1 pytest tests/unit/observability/test_http_golden.py

Then inspect the diff and commit the updated goldens.
"""

import os
from pathlib import Path

import pytest
import yaml

from startd8.observability.artifact_generator import (
    BusinessContext,
    ConventionMetric,
    ServiceHints,
    generate_alert_rules,
    generate_dashboard_spec,
    generate_slo_definitions,
)

_GOLDEN_DIR = Path(__file__).parent / "data" / "http_golden"
# Pin the deterministic-timestamp source so any embedded `generated_at` is stable
# (relies on the #224 fix in `_utc_now_iso`).
_PINNED_TS = "20260722T1000"


def _check_golden(name: str, content: str) -> None:
    """Compare *content* to the committed golden *name*, or (re)write it when
    UPDATE_GOLDENS is set. A missing golden without the flag is a hard failure —
    goldens must be committed, never silently created on a normal run."""
    path = _GOLDEN_DIR / name
    if os.environ.get("UPDATE_GOLDENS"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return
    assert path.exists(), (
        f"Missing golden {path}. Generate it first with "
        f"`UPDATE_GOLDENS=1 pytest {Path(__file__).name}` and commit it."
    )
    expected = path.read_text(encoding="utf-8")
    assert content == expected, (
        f"Golden drift for {name}: generator output changed. If intended, "
        f"regenerate with UPDATE_GOLDENS=1 and review the diff."
    )


@pytest.fixture(autouse=True)
def _pin_timestamp(monkeypatch):
    monkeypatch.setenv("CDP_DETERMINISTIC_RUN_TIMESTAMP", _PINNED_TS)


@pytest.fixture
def business():
    return BusinessContext(
        criticality="high",
        availability="99.9",
        latency_p99="500ms",
        throughput="100rps",
        project_id="golden-test",
        slo_window="30d",
    )


@pytest.fixture
def http_with_availability():
    return ServiceHints(
        service_id="http-with-avail",
        transport="http",
        language="python",
        convention_metrics=[
            ConventionMetric("http.server.duration", "histogram", "otel_semconv:http"),
            ConventionMetric("http.server.request.body.size", "counter", "otel_semconv:http"),
            ConventionMetric("http.server.response.body.size", "counter", "otel_semconv:http"),
        ],
    )


@pytest.fixture
def counter_only():
    return ServiceHints(
        service_id="counter-only",
        transport="http",
        language="python",
        convention_metrics=[
            ConventionMetric("http.server.request.body.size", "counter", "otel_semconv:http"),
        ],
    )


@pytest.fixture
def grpc_server():
    return ServiceHints(
        service_id="checkout-api",
        transport="grpc",
        language="go",
        detected_databases=["postgresql"],
        convention_metrics=[
            ConventionMetric("rpc.server.duration", "histogram", "otel_semconv:grpc"),
            ConventionMetric("rpc.server.request.size", "counter", "otel_semconv:grpc"),
            ConventionMetric("rpc.server.response.size", "counter", "otel_semconv:grpc"),
            ConventionMetric("rpc.server.requests_per_rpc", "counter", "otel_semconv:grpc"),
        ],
    )


class TestHttpWithAvailabilityGolden:
    def test_alerts(self, business, http_with_availability):
        result = generate_alert_rules(http_with_availability, business)
        assert result.status == "generated"
        _check_golden("http_with_avail-alerts.yaml", result.content)

    def test_dashboard(self, business, http_with_availability):
        # Exercises _ensure_red_coverage (RED synthesis + Availability(1h) gauge).
        result = generate_dashboard_spec(http_with_availability, business)
        assert result.status == "generated"
        _check_golden("http_with_avail-dashboard.yaml", result.content)

    def test_slos(self, business, http_with_availability):
        result = generate_slo_definitions(http_with_availability, business)
        assert result.status == "generated"
        _check_golden("http_with_avail-slos.yaml", result.content)


class TestCounterOnlyGolden:
    def test_alerts_skipped(self, business, counter_only):
        # No duration histogram ⇒ no RED alerts today. FR-12a must preserve this.
        result = generate_alert_rules(counter_only, business)
        assert result.status == "skipped"

    def test_dashboard(self, business, counter_only):
        result = generate_dashboard_spec(counter_only, business)
        assert result.status == "generated"
        _check_golden("counter_only-dashboard.yaml", result.content)

    def test_slos_no_latency_block(self, business, counter_only):
        result = generate_slo_definitions(counter_only, business)
        assert result.status == "generated"
        # The load-bearing parity fact FR-12a must preserve: no latency SLO without a histogram.
        docs = [
            d
            for d in yaml.safe_load_all(result.content.split("\n\n", 1)[-1])
            if d
        ]
        latency = [
            d for d in docs if "latency" in str(d.get("metadata", {}).get("name", "")).lower()
        ]
        assert not latency, "counter-only service must not emit a latency SLO"
        _check_golden("counter_only-slos.yaml", result.content)


@pytest.fixture
def gauge_only():
    # A Prometheus-style exporter emitting only gauge state metrics (Harbor
    # exporter/core/jobservice shape). No histogram/counter ⇒ no RED alerts.
    return ServiceHints(
        service_id="gauge-exporter",
        transport="http",
        language="go",
        convention_metrics=[
            ConventionMetric("harbor_exporter_task_pending", "gauge", "prometheus"),
            ConventionMetric("harbor_exporter_up", "gauge", "prometheus"),
        ],
    )


class TestGaugeAbsenceAlerts:
    """Regression: gauge-only services used to produce a ``skipped`` alert artifact
    ⇒ a FALSE 0 ``metric_coverage_bridge`` (the Harbor exporter/core/jobservice
    bridge=0 root cause). Each gauge now gets a real absence/staleness alert."""

    def test_gauge_only_gets_absence_alerts(self, business, gauge_only):
        result = generate_alert_rules(gauge_only, business)
        assert result.status == "generated"  # was "skipped" before the fix
        assert "absent(harbor_exporter_task_pending{})" in result.content
        assert "absent(harbor_exporter_up{})" in result.content
        # Real signal, not a tautological `>= 0` coverage bind (FR-26).
        assert ">= 0" not in result.content

    def test_absence_alert_lifts_bridge_coverage(self, business, gauge_only):
        from startd8.validators.observability_artifact_checks import (
            compute_metric_coverage,
        )

        result = generate_alert_rules(gauge_only, business)
        cov = compute_metric_coverage(
            ["harbor_exporter_task_pending", "harbor_exporter_up"], [result.content]
        )
        assert cov.score == 1.0  # was 0.0 (skipped artifact → no referenced metrics)


class TestErrorCounterAlerts:
    """Lacuna-audit ⭐: an error/failure-named COUNTER got no alert (understated
    bridge). Now gets a conservative increase(...[15m])>0 alert. Non-error counters
    stay skipped (a generic counter has no safe generic alert) — so the counter
    goldens are byte-identical (the fixtures use non-error counters)."""

    def _svc(self, metric_name):
        return ServiceHints(
            service_id="s",
            transport="http",
            language="go",
            convention_metrics=[ConventionMetric(metric_name, "counter", "prometheus")],
        )

    def test_error_counter_gets_increase_alert(self, business):
        result = generate_alert_rules(self._svc("harbor_registry_errors_total"), business)
        assert result.status == "generated"  # was "skipped"
        assert "increase(harbor_registry_errors_total{}[15m]) > 0" in result.content

    def test_failure_counter_matches_too(self, business):
        result = generate_alert_rules(self._svc("job_failed_total"), business)
        assert result.status == "generated"
        assert "increase(job_failed_total{}[15m]) > 0" in result.content

    def test_non_error_counter_stays_skipped(self, business):
        # The over-fill guard: a generic counter has no safe generic alert.
        result = generate_alert_rules(self._svc("http_requests_total"), business)
        assert result.status == "skipped"


class TestGrpcServerGolden:
    def test_alerts(self, business, grpc_server):
        result = generate_alert_rules(grpc_server, business)
        assert result.status == "generated"
        _check_golden("grpc-alerts.yaml", result.content)

    def test_dashboard(self, business, grpc_server):
        result = generate_dashboard_spec(grpc_server, business)
        assert result.status == "generated"
        _check_golden("grpc-dashboard.yaml", result.content)

    def test_slos(self, business, grpc_server):
        result = generate_slo_definitions(grpc_server, business)
        assert result.status == "generated"
        _check_golden("grpc-slos.yaml", result.content)


class TestScore3SummaryLatencySlo:
    """SCORE-3 (system axis): a SUMMARY duration family (Harbor core's
    harbor_core_http_request_duration_seconds) gets an AVG-latency SLO via
    _sum/_count — NOT a dead histogram_quantile(_bucket) (L1c). This references the
    summary family, lifting system coverage. Histogram services are byte-identical
    (the summary branch requires a summary AND no histogram)."""

    def _svc(self, metrics):
        return ServiceHints(
            service_id="core", transport="http", language="go",
            convention_metrics=metrics,
        )

    def test_summary_gets_avg_latency_slo(self, business):
        svc = self._svc([
            ConventionMetric("harbor_core_http_request_total", "counter", "prometheus"),
            ConventionMetric("harbor_core_http_request_duration_seconds", "summary", "prometheus"),
        ])
        result = generate_slo_definitions(svc, business)
        assert result.status == "generated"
        assert "harbor_core_http_request_duration_seconds_sum" in result.content
        assert "harbor_core_http_request_duration_seconds_count" in result.content
        # L1c: the summary must NOT be rendered as a histogram quantile on a _bucket.
        assert "harbor_core_http_request_duration_seconds_bucket" not in result.content

    def test_histogram_service_no_avg_slo(self, business):
        # A histogram already yields the p99 SLO; the summary branch must not fire.
        svc = self._svc([
            ConventionMetric("http.server.duration", "histogram", "otel_semconv:http"),
        ])
        result = generate_slo_definitions(svc, business)
        assert "-latency-avg" not in result.content  # only the histogram p99 path


class TestScore4SummaryDashboardPanel:
    """SCORE-4 (human axis): a SUMMARY duration family gets a dashboard panel — the
    avg latency (_sum/_count), L1c-safe — so it's referenced by the dashboard,
    lifting human coverage. Non-summary services are byte-identical."""

    def test_summary_gets_avg_dashboard_panel(self, business):
        svc = ServiceHints(
            service_id="core", transport="http", language="go",
            convention_metrics=[
                ConventionMetric("harbor_core_http_request_duration_seconds", "summary", "prometheus"),
            ],
        )
        result = generate_dashboard_spec(svc, business)
        assert result.status == "generated"
        assert "harbor_core_http_request_duration_seconds_sum" in result.content
        assert "harbor_core_http_request_duration_seconds_count" in result.content
        # L1c: never a histogram quantile on a nonexistent _bucket.
        assert "harbor_core_http_request_duration_seconds_bucket" not in result.content


class TestScore4CounterTotalNotDoubled:
    """SCORE-4: a Prometheus-native counter already ends in `_total`; the counter
    panel template appends `_total`, so without a strip it produced `_total_total`
    — which the coverage normalizer maps to a different base, reading the counter
    UNCOVERED on the dashboard. The panel must reference the real single-`_total`
    series. OTel counters (no `_total`) are byte-identical."""

    def test_prometheus_counter_single_total(self, business):
        svc = ServiceHints(
            service_id="core", transport="http", language="go",
            convention_metrics=[
                ConventionMetric("harbor_core_http_request_total", "counter", "prometheus"),
            ],
        )
        result = generate_dashboard_spec(svc, business)
        assert "harbor_core_http_request_total_total" not in result.content
        assert "rate(harbor_core_http_request_total{" in result.content

    def test_otel_counter_unchanged(self, business):
        # An OTel counter with no `_total` still gets the appended `_total`.
        svc = ServiceHints(
            service_id="s", transport="http", language="go",
            convention_metrics=[
                ConventionMetric("http.server.request.count", "counter", "otel_semconv:http"),
            ],
        )
        result = generate_dashboard_spec(svc, business)
        assert "http_server_request_count_total" in result.content


class TestScore3GaugeFreshnessSlo:
    """SCORE-3 "best of both worlds" (gauge system axis): a plain COUNT gauge has no
    groundable saturation threshold (a magnitude SLO would be fabricated — FR-26), but
    its DATA AVAILABILITY (is it being scraped) is a real objective with no fabricated
    magnitude. In INSTALLED (local) mode the gauge gets a freshness SLO at the forgiving
    installed availability default → references the gauge, lifting system coverage. In
    DEPLOYED/default mode it DEFERS (no fabricated production SLO) — byte-identical."""

    def _svc(self):
        return ServiceHints(
            service_id="exporter", transport="http", language="go",
            convention_metrics=[
                ConventionMetric("harbor_queue_depth", "gauge", "prometheus"),
                ConventionMetric("harbor_inflight_jobs", "gauge", "prometheus"),
            ],
        )

    def _biz(self, deployment_mode, metrics_interval="30s"):
        return BusinessContext(
            criticality="high",
            availability="99.9",
            latency_p99="500ms",
            throughput="100rps",
            project_id="golden-test",
            slo_window="30d",
            deployment_mode=deployment_mode,
            metrics_interval=metrics_interval,
        )

    def test_installed_gauge_gets_freshness_slo(self):
        result = generate_slo_definitions(self._svc(), self._biz("installed"))
        assert result.status == "generated"
        # Each gauge referenced by a freshness SLO (count_over_time / samples-per-hour).
        assert "harbor_queue_depth-freshness" in result.content
        assert "harbor_inflight_jobs-freshness" in result.content
        assert "count_over_time(harbor_queue_depth{" in result.content
        # 30s interval → 3600/30 = 120 expected samples per hour.
        assert "/ 120" in result.content
        # No fabricated magnitude threshold on the raw gauge value.
        assert "histogram_quantile" not in result.content

    def test_deployed_gauge_defers(self):
        # DEPLOYED mode: no fabricated production SLO for a plain gauge.
        result = generate_slo_definitions(self._svc(), self._biz("deployed"))
        assert "freshness" not in result.content

    def test_default_mode_defers(self):
        # No deployment_mode set (the common fixture) → defers, byte-identical.
        biz = BusinessContext(
            criticality="high", availability="99.9", latency_p99="500ms",
            throughput="100rps", project_id="golden-test", slo_window="30d",
        )
        result = generate_slo_definitions(self._svc(), biz)
        assert "freshness" not in result.content

    def test_interval_scales_samples_per_hour(self):
        # 15s interval → 3600/15 = 240 expected samples per hour.
        result = generate_slo_definitions(self._svc(), self._biz("installed", "15s"))
        assert "/ 240" in result.content

    def test_no_double_slo_when_gauge_also_declared_fr(self):
        # Guard: the convention-freshness path (this) and the declared-functional
        # SLO path must stay disjoint for a real gauge — a gauge declared ALSO as a
        # freshness FR must NOT get two freshness SLOs (which would double-count it on
        # the system axis). Exactly one freshness SLO references the gauge.
        from startd8.observability.artifact_generator_models import FunctionalRequirement
        svc = ServiceHints(
            service_id="exporter", transport="http", language="go",
            convention_metrics=[ConventionMetric("harbor_queue_depth", "gauge", "prometheus")],
        )
        biz = BusinessContext(
            criticality="high", availability="99.9", latency_p99="500ms",
            throughput="100rps", project_id="golden-test", slo_window="30d",
            deployment_mode="installed", metrics_interval="30s",
            functional_requirements=[
                FunctionalRequirement(id="f1", signal_kind="freshness",
                                      service="exporter", target="99"),
            ],
        )
        result = generate_slo_definitions(svc, biz)
        # exactly one freshness SLO (3 name-slots per SLO: metadata + sli + alert).
        assert result.content.count("harbor_queue_depth-freshness") == 3


class TestScore3SecondaryRedFamilies:
    """S7 (system axis): a service can emit MORE than one RED-shaped family. The primary
    counter/summary get their groundable SLOs; SECONDARY counters/summaries have no
    groundable magnitude here (business declares only request latency), so each gets the
    honest data-availability treatment (installed mode). Lifts the jobservice residual;
    single-family services + deployed mode are byte-identical."""

    def _multi(self):
        return ServiceHints(
            service_id="jobservice", transport="http", language="go",
            convention_metrics=[
                ConventionMetric("job_http_request_total", "counter", "prometheus"),        # primary
                ConventionMetric("job_http_request_duration_seconds", "summary", "prometheus"),  # primary
                ConventionMetric("job_task_total", "counter", "prometheus"),                 # secondary
                ConventionMetric("job_task_process_time_seconds", "summary", "prometheus"),  # secondary
            ],
        )

    def _biz(self, mode):
        return BusinessContext(
            criticality="high", availability="99.9", latency_p99="500ms", throughput="100rps",
            project_id="golden-test", slo_window="30d", deployment_mode=mode, metrics_interval="30s",
        )

    def test_installed_covers_secondary_families(self):
        c = generate_slo_definitions(self._multi(), self._biz("installed")).content
        # secondary counter → freshness on its bare series
        assert "job_task_total-freshness" in c
        assert "count_over_time(job_task_total{" in c
        # secondary summary → freshness on its _count series (a summary has no bare series)
        assert "job_task_process_time_seconds-freshness" in c
        assert "count_over_time(job_task_process_time_seconds_count{" in c
        # marked for the cross-pilot rollup
        assert "red_leg: secondary" in c
        # the PRIMARY families keep their groundable SLOs, NOT freshness
        assert "job_http_request_total-freshness" not in c

    def test_deployed_defers_secondary(self):
        c = generate_slo_definitions(self._multi(), self._biz("deployed")).content
        assert "-freshness" not in c  # no fabricated production SLO
        assert "red_leg" not in c

    def test_single_family_service_byte_identical(self):
        # only primary counter + summary → no secondary block fires (installed).
        svc = ServiceHints(
            service_id="core", transport="http", language="go",
            convention_metrics=[
                ConventionMetric("core_http_request_total", "counter", "prometheus"),
                ConventionMetric("core_http_request_duration_seconds", "summary", "prometheus"),
            ],
        )
        c = generate_slo_definitions(svc, self._biz("installed")).content
        assert "red_leg" not in c
        assert "-freshness" not in c


class TestOpenSloHelperParity:
    """Mirror test for the distilled `_openslo_doc` scaffold: it must reproduce EXACTLY the dict the
    5 hand-written SLO blocks used to build (key order included — yaml.dump(sort_keys=False) is
    order-sensitive), so the consolidation can't silently drift the byte output. Covers both
    indicator shapes (threshold + ratio) and the latency-p99 sli/alert-name override."""

    def test_threshold_scaffold_matches_reference(self):
        from startd8.observability.artifact_generator_generators import (
            _openslo_doc, _threshold_indicator,
        )
        got = _openslo_doc(
            name="svc-latency-avg",
            labels={"service": "svc", "protocol": "http", "generated_by": "startd8"},
            description="Average latency SLO for svc",
            target=99.9,
            window="30d",
            severity="critical",
            indicator_spec=_threshold_indicator("sum(rate(x_sum[5m]))/sum(rate(x_count[5m]))", 0.5, "lte"),
        )
        expected = {
            "apiVersion": "openslo/v1", "kind": "SLO",
            "metadata": {"name": "svc-latency-avg",
                         "labels": {"service": "svc", "protocol": "http", "generated_by": "startd8"}},
            "spec": {
                "description": "Average latency SLO for svc", "target": 99.9,
                "timeWindow": {"duration": "30d", "isRolling": True}, "budgetPolicy": "occurrences",
                "indicator": {"metadata": {"name": "svc-latency-avg-sli"},
                              "spec": {"thresholdMetric": {
                                  "metricSource": {"type": "prometheus",
                                                   "spec": {"query": "sum(rate(x_sum[5m]))/sum(rate(x_count[5m]))"}},
                                  "threshold": 0.5, "operator": "lte"}}},
                "alerting": {"name": "svc-latency-avg-alert", "labels": {"severity": "critical"}},
            },
        }
        assert got == expected
        # key ORDER parity (yaml.dump is order-sensitive) — the whole point of the mirror test
        assert list(got["spec"].keys()) == list(expected["spec"].keys())

    def test_ratio_scaffold_and_sli_override(self):
        from startd8.observability.artifact_generator_generators import _openslo_doc
        ind = {"ratioMetric": {"counter": {"metricSource": {"type": "prometheus", "spec": {"query": "rate(t[5m])"}}},
                               "good": {"metricSource": {"type": "prometheus", "spec": {"query": "rate(g[5m])"}}}}}
        got = _openslo_doc(name="svc-latency-p99", labels={"service": "svc"}, description="d",
                           target=99.0, window="30d", severity="warning", indicator_spec=ind,
                           sli_name="svc-latency-sli", alert_name="svc-latency-alert")
        # the p99 quirk: sli/alert are the OVERRIDES, not {name}-sli
        assert got["spec"]["indicator"]["metadata"]["name"] == "svc-latency-sli"
        assert got["spec"]["alerting"]["name"] == "svc-latency-alert"
        assert got["spec"]["indicator"]["spec"] == ind  # ratio shape passed through verbatim

    def test_sli_alert_default_naming(self):
        from startd8.observability.artifact_generator_generators import _openslo_doc, _threshold_indicator
        got = _openslo_doc(name="svc-x-freshness", labels={}, description="d", target=97.0,
                           window="30d", severity="warning",
                           indicator_spec=_threshold_indicator("count_over_time(x[1h])/120", 0.97, "gte"))
        assert got["spec"]["indicator"]["metadata"]["name"] == "svc-x-freshness-sli"
        assert got["spec"]["alerting"]["name"] == "svc-x-freshness-alert"
