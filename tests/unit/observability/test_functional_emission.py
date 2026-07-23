"""#226 Phase 2b — FR-5 emission (functional SLOs) + FR-9 coverage report.

FR-5: each declared non-triplet functional[] FR emits an SLO on a convention series
(FR-6a) with the FR's target + a `source_fr` label (FR-8). FRs the emitter can't
ground become FR-9's `unfulfilled` class — never faked. FR-9: the report distinguishes
∅ services from unfulfilled FRs (the pilot's "6 of 7 → nothing" made visible).
"""

import json

import yaml

from startd8.observability.artifact_generator import (
    BusinessContext,
    ConventionMetric,
    FunctionalRequirement,
    ServiceHints,
    generate_functional_slos,
    generate_observability_artifacts,
)
from startd8.observability.metric_descriptor import resolve_sli_kinds


def _worker(signal_kinds_targets):
    return ServiceHints(service_id="mailer", transport="", kinds=["async_worker"])


class TestAiAgentSignalKinds:
    """docs/design/ai-agent-observability FR-1/FR-1a/FR-2a: the SDK emits SLOs for its own
    hosted-LLM telemetry (cost/tokens/context) — grounded, live series; values deferred (OQ-1).
    Distinct from #231 GPU ml_inference (§5)."""

    def _svc(self):
        # an 'agent' service anchoring the project-scoped AI FRs (per-service dedup = OQ-2).
        return ServiceHints(service_id="agent", transport="", kinds=["async_worker"])

    def _emit(self, signal_kind, target):
        business = BusinessContext(
            criticality="high",
            functional_requirements=[
                FunctionalRequirement(id="FR-AI", signal_kind=signal_kind, target=target,
                                      service="agent"),
            ],
        )
        return generate_functional_slos(self._svc(), business)

    def test_llm_cost_per_request_emits_histogram_quantile(self):
        r = self._emit("llm_cost_per_request", "0.05")
        assert r.status == "generated"
        assert "histogram_quantile(0.99, sum by (le) (rate(startd8_cost_per_request_USD_bucket[5m])))" in r.content
        assert "target: '0.05'" in r.content or 'target: "0.05"' in r.content or "target: 0.05" in r.content

    def test_token_throughput_emits_rate(self):
        r = self._emit("token_throughput", "500")
        assert "sum(rate(startd8_cost_output_tokens_total[5m]))" in r.content

    def test_context_saturation_emits_gauge_max(self):
        r = self._emit("context_saturation", "0.8")
        assert "max(startd8_context_usage_ratio)" in r.content

    def test_ai_slis_are_project_scoped_never_service_selector(self):
        # FR-2a: AI series are model/project-labeled — a {service=...} selector would match
        # nothing. The query must be aggregate (matches the live-verified §6 PromQL).
        for kind, tgt in [("llm_cost_per_request", "0.05"), ("token_throughput", "500"),
                          ("context_saturation", "0.8")]:
            r = self._emit(kind, tgt)
            assert "service=" not in r.content and "service_name=" not in r.content

    def test_ai_rows_are_inert_without_a_declared_ai_fr(self):
        # FR-0 byte-parity: a worker with no AI FR emits nothing AI-shaped (skipped).
        assert generate_functional_slos(self._svc(), BusinessContext()).status == "skipped"


class TestGroundedWorkerSeries:
    """Grounded worker-series fix (evidence: live OTel-demo Kafka-consumer fleet, 2026-07-22).
    A `lag` FR must bind to a series that REALLY exists, and prefer what the service declares."""

    def _lag_business(self):
        return BusinessContext(
            functional_requirements=[
                FunctionalRequirement(id="FR-LAG", signal_kind="lag", target="1000"),
            ],
        )

    def test_lag_default_binds_to_the_verified_kafka_series_not_the_absent_semconv_name(self):
        # A worker that reports no metrics (OQ-5) falls back to the PRIMARY candidate —
        # which must be the series verified to exist, not messaging_client_* (returns 0).
        svc = ServiceHints(service_id="fraud", transport="", kinds=["async_worker"])
        result = generate_functional_slos(svc, self._lag_business())
        assert result.status == "generated"
        assert "kafka_consumer_records_lag_max" in result.content
        assert "messaging_client_consumer_lag_messages" not in result.content

    def test_lag_binds_to_the_metric_the_service_actually_declares(self):
        # Service-declared series wins (FR-6a), dot/underscore-insensitive.
        svc = ServiceHints(
            service_id="fraud", transport="", kinds=["async_worker"],
            convention_metrics=[ConventionMetric("kafka.consumer.records.lag", "gauge", "kafka_jmx")],
        )
        result = generate_functional_slos(svc, self._lag_business())
        assert "kafka_consumer_records_lag" in result.content
        assert "kafka_consumer_records_lag_max" not in result.content  # the exact declared one, not the default

    def test_semconv_name_still_honored_when_a_service_emits_it(self):
        # A service instrumented via OTel semconv (not JMX) still binds correctly —
        # the candidate list is not Kafka-only overfit; what the service emits decides.
        svc = ServiceHints(
            service_id="w", transport="", kinds=["async_worker"],
            declared_metrics=[ConventionMetric("messaging.client.consumer.lag.messages", "gauge", "otel")],
        )
        result = generate_functional_slos(svc, self._lag_business())
        assert "messaging_client_consumer_lag_messages" in result.content


class TestFunctionalEmission:
    def test_queue_depth_fr_emits_slo_on_convention_series(self):
        business = BusinessContext(
            criticality="high",
            functional_requirements=[
                FunctionalRequirement(id="FR-006", signal_kind="queue_depth", target="1000"),
            ],
        )
        result = generate_functional_slos(_worker(None), business)
        assert result.status == "generated"
        assert "messaging_client_queued_messages" in result.content
        assert "source_fr: FR-006" in result.content
        assert result.quality["emitted_fr_ids"] == ["FR-006"]
        assert "http_server_duration" not in result.content

    def test_custom_fr_uses_its_own_query(self):
        business = BusinessContext(
            functional_requirements=[
                FunctionalRequirement(id="FR-X", signal_kind="custom", target="my_metric{a=\"b\"} > 5"),
            ],
        )
        result = generate_functional_slos(_worker(None), business)
        assert 'my_metric{a="b"} > 5' in result.content

    def test_ungroundable_fr_is_unfulfilled_not_faked(self):
        business = BusinessContext(
            functional_requirements=[
                FunctionalRequirement(id="FR-Z", signal_kind="freshness"),  # no target
                FunctionalRequirement(id="FR-Q", signal_kind="mystery", target="1"),  # unknown kind
            ],
        )
        result = generate_functional_slos(_worker(None), business)
        assert result.status == "skipped"  # nothing groundable
        ids = {u["id"] for u in result.quality["unfulfilled"]}
        assert ids == {"FR-Z", "FR-Q"}

    def test_triplet_kinds_skipped_here(self):
        # availability/latency/throughput are the convention triplet, not functional SLOs.
        business = BusinessContext(
            functional_requirements=[FunctionalRequirement(id="FR-1", signal_kind="latency", target="500ms")],
        )
        assert generate_functional_slos(_worker(None), business).status == "skipped"

    def test_no_functional_is_skipped(self):
        assert generate_functional_slos(_worker(None), BusinessContext()).status == "skipped"

    def test_fr_scoped_to_other_service_skipped(self):
        business = BusinessContext(
            functional_requirements=[
                FunctionalRequirement(id="FR-9", signal_kind="queue_depth", target="1", service="someone-else"),
            ],
        )
        assert generate_functional_slos(_worker(None), business).status == "skipped"


class TestFr9Coverage:
    def test_report_fr_coverage_populated(self, tmp_path):
        # Onboarding metadata with a worker; manifest with a groundable + an
        # ungroundable FR → report.fr_coverage shows emitted + unfulfilled.
        meta = tmp_path / "onboarding-metadata.json"
        meta.write_text(json.dumps({
            "project_id": "p",
            "instrumentation_hints": {
                "mailer": {
                    "service_id": "mailer",
                    "kind": "async_worker",
                    "metrics": {"convention_based": [
                        {"name": "messaging.process.duration", "type": "histogram", "source": "otel_semconv:messaging"}
                    ]},
                },
            },
        }))
        manifest = tmp_path / ".contextcore.yaml"
        manifest.write_text(
            "spec:\n"
            "  business: {criticality: high}\n"
            "  requirements:\n"
            "    functional:\n"
            "      - {id: FR-006, signal_kind: queue_depth, target: '1000'}\n"
            "      - {id: FR-007, signal_kind: freshness}\n"
        )
        report = generate_observability_artifacts(
            onboarding_metadata_path=meta, output_dir=tmp_path / "out",
            manifest_path=manifest, dry_run=True,
        )
        cov = report.fr_coverage
        assert "FR-006" in cov["emitted"]
        assert any(u["id"] == "FR-007" for u in cov["unfulfilled"])

    def test_emitting_fr_does_not_crash_index_write(self, tmp_path):
        # Regression (#254): a functional[] FR with a target actually EMITS an
        # SLO, whose quality dict lacks `score`. The non-dry-run index/quality
        # writers must not KeyError on that scoreless quality dict.
        meta = tmp_path / "onboarding-metadata.json"
        meta.write_text(json.dumps({
            "project_id": "p",
            "instrumentation_hints": {
                "mailer": {
                    "service_id": "mailer",
                    "kind": "async_worker",
                    "metrics": {"convention_based": [
                        {"name": "messaging.process.duration", "type": "histogram", "source": "otel_semconv:messaging"}
                    ]},
                },
            },
        }))
        manifest = tmp_path / ".contextcore.yaml"
        manifest.write_text(
            "spec:\n"
            "  business: {criticality: high}\n"
            "  requirements:\n"
            "    functional:\n"
            "      - {id: FR-006, signal_kind: queue_depth, target: '1000'}\n"
        )
        out = tmp_path / "out"
        report = generate_observability_artifacts(
            onboarding_metadata_path=meta, output_dir=out,
            manifest_path=manifest, dry_run=False,  # exercises _write_index + _write_quality_report
        )
        assert "FR-006" in report.fr_coverage["emitted"]
        # Index was written; the functional-SLO artifact appears without a quality_score key.
        index = yaml.safe_load((out / "observability-manifest.yaml").read_text())
        func_slo = [a for a in index["artifacts"] if "functional-slo" in a.get("path", "")]
        assert func_slo and all("quality_score" not in a for a in func_slo)


class TestUngroundedKindCoverage:
    """#230/#231/#233 grounding-free slice: a recognized-but-ungrounded workload kind
    (batch/cron/ml_inference) is surfaced explicitly in fr_coverage — named, with the
    actionable next step — rather than silently receiving HTTP artifacts or nothing."""

    def test_ml_inference_service_is_flagged_ungrounded_not_fabricated(self, tmp_path):
        meta = tmp_path / "onboarding-metadata.json"
        meta.write_text(json.dumps({
            "project_id": "p",
            "instrumentation_hints": {
                "ranker": {
                    "service_id": "ranker",
                    "kind": "ml_inference",
                    "transport": "http",  # incidental serve port — must NOT yield HTTP SLOs
                    "metrics": {"convention_based": [
                        {"name": "http.server.duration", "type": "histogram", "source": "otel_semconv:http"}
                    ]},
                },
            },
        }))
        report = generate_observability_artifacts(
            onboarding_metadata_path=meta, output_dir=tmp_path / "out", dry_run=True,
        )
        ung = report.fr_coverage["ungrounded_kinds"]
        entry = next(u for u in ung if u["service"] == "ranker")
        assert entry["kind"] == "ml_inference"
        # P1a: the hint is KIND-SPECIFIC (saturation/lag for ml_inference), not generic.
        assert entry["suggested_signals"] == ["saturation", "lag"]
        assert "saturation/lag" in entry["reason"]
        assert "run_success/freshness/saturation/lag" not in entry["reason"]  # not the generic menu
        # P1b: an ungrounded service with no FRs is ALSO observed by nothing — cross-referenced.
        assert entry["observed_by_nothing"] is True
        assert "ranker" in report.fr_coverage["empty_services"]
        # #231: the incidental http transport must not have produced a latency SLO.
        assert "latency" not in resolve_sli_kinds(["ml_inference"], [], "http")


class TestServiceNameLabelValue:
    """#275: the SLI label VALUE must be the real OTel service.name (slash preserved), not the
    sanitized graph id — else the selector never matches real telemetry."""

    def test_real_service_name_is_the_selector_value(self):
        from startd8.observability.artifact_generator_generators import _descriptor_for
        svc = ServiceHints(service_id="mastodonweb", service_name="mastodon/web", transport="http",
                           kinds=["http_server"])
        d = _descriptor_for(svc, None)
        assert d.selector("mastodonweb") .startswith('{service="mastodon/web"') \
            or 'service="mastodon/web"' in d.selector("mastodonweb")
        assert "mastodonweb" not in d.selector("mastodonweb")  # the sanitized id is gone

    def test_absent_service_name_is_byte_identical(self):
        from startd8.observability.artifact_generator_generators import _descriptor_for
        svc = ServiceHints(service_id="checkoutservice", transport="grpc", kinds=["grpc_server"])
        d = _descriptor_for(svc, None)
        assert 'service_name="checkoutservice"' in d.selector("checkoutservice") \
            or 'service="checkoutservice"' in d.selector("checkoutservice")


class TestUnverifiedBaseMetricsAdvisory:
    """#274 (ADR-003): a trace-instrumented service whose base RED SLIs rest on convention
    metrics with NO manifest_declared backing is the traces-only RISK profile — flagged as an
    ADVISORY (SLIs still emit; not a false-gap), because the SDK can't verify emission."""

    def test_traces_only_risk_profile_is_flagged(self, tmp_path):
        meta = tmp_path / "onboarding-metadata.json"
        meta.write_text(json.dumps({
            "project_id": "p",
            "instrumentation_hints": {
                "web": {
                    "service_id": "web", "kind": "http_server", "transport": "http",
                    "traces": {"required": [{"span_name": "GET /"}]},   # trace-instrumented
                    "metrics": {
                        "convention_based": [{"name": "http.server.duration", "type": "histogram",
                                              "source": "otel_semconv:http"}],
                        "manifest_declared": [],                          # NOTHING emission-verified
                    },
                },
            },
        }))
        report = generate_observability_artifacts(
            onboarding_metadata_path=meta, output_dir=tmp_path / "out", dry_run=True,
        )
        adv = report.fr_coverage["unverified_base_metrics"]
        assert any(u["service"] == "web" for u in adv)
        assert any("verified as emitted" in u["reason"] for u in adv)

    def test_declared_metrics_backing_suppresses_the_advisory(self, tmp_path):
        # a service that DECLARES its emitted metrics is not flagged (emission-verified).
        meta = tmp_path / "onboarding-metadata.json"
        meta.write_text(json.dumps({
            "project_id": "p",
            "instrumentation_hints": {
                "web": {
                    "service_id": "web", "kind": "http_server", "transport": "http",
                    "traces": {"required": []},
                    "metrics": {
                        "convention_based": [{"name": "http.server.duration", "type": "histogram", "source": "s"}],
                        "manifest_declared": [{"name": "http.server.duration", "type": "histogram", "source": "s"}],
                    },
                },
            },
        }))
        report = generate_observability_artifacts(
            onboarding_metadata_path=meta, output_dir=tmp_path / "out", dry_run=True,
        )
        assert not report.fr_coverage["unverified_base_metrics"]


class TestMetricsSurfaceStrictSuppression:
    """#274 / REQ-CCL-106: a DECLARED non-emitting metrics_surface suppresses the dead base RED
    SLIs (strict fix) and records the gap; an UNKNOWN surface falls back to the #277 advisory."""

    def _meta(self, tmp_path, surface, with_fr=False):
        hint = {
            "service_id": "web", "kind": "http_server", "transport": "http",
            "traces": {"required": [{"span_name": "GET /"}]},
            "metrics": {"convention_based": [
                {"name": "http.server.duration", "type": "histogram", "source": "otel_semconv:http"}]},
        }
        if surface:
            hint["metrics_surface"] = surface
        doc = {"project_id": "p", "instrumentation_hints": {"web": hint}}
        if with_fr:
            doc["spec"] = {"requirements": {"functional": [
                {"id": "FR-1", "signal_kind": "queue_depth", "target": "1000", "service": "web"}]}}
        m = tmp_path / "onboarding-metadata.json"
        m.write_text(json.dumps(doc))
        return m

    def _run(self, tmp_path, surface, with_fr=False):
        kw = {}
        if with_fr:  # FRs come from the manifest, not the onboarding metadata
            man = tmp_path / ".contextcore.yaml"
            man.write_text(
                "spec:\n  business: {criticality: high}\n  requirements:\n    functional:\n"
                "      - {id: FR-1, signal_kind: queue_depth, target: '1000', service: web}\n"
            )
            kw["manifest_path"] = man
        return generate_observability_artifacts(
            onboarding_metadata_path=self._meta(tmp_path, surface, with_fr=False),
            output_dir=tmp_path / "out", dry_run=False, **kw,
        )

    def test_traces_only_suppresses_the_base_red_slis(self, tmp_path):
        report = self._run(tmp_path, "traces_only")
        cov = report.fr_coverage
        # strict gap recorded; advisory NOT fired (superseded by the signal).
        assert any(u["service"] == "web" and u["metrics_surface"] == "traces_only"
                   for u in cov["suppressed_base_metrics"])
        assert not cov["unverified_base_metrics"]
        # no dead availability/latency SLO shipped.
        slo = [a for a in report.artifacts if a.artifact_type == "slo_definition"
               and a.service_id == "web" and a.status == "generated"
               and "functional" not in a.output_path]
        joined = " ".join(a.content for a in slo)
        assert "http_server_duration" not in joined
        # #274 dashboard gate: no dead convention-metric panel in the dashboard spec either.
        dash = [a for a in report.artifacts if a.artifact_type == "dashboard_spec"
                and a.service_id == "web" and a.status == "generated"]
        assert all("http_server_duration" not in a.content for a in dash)

    def test_otel_sdk_meter_still_emits_red(self, tmp_path):
        # the surface that DOES emit the convention metric → unchanged behavior.
        report = self._run(tmp_path, "otel_sdk_meter")
        assert not report.fr_coverage["suppressed_base_metrics"]
        assert any("http_server_duration" in a.content for a in report.artifacts
                   if a.artifact_type == "slo_definition" and a.status == "generated")

    def test_absent_surface_falls_back_to_advisory(self, tmp_path):
        report = self._run(tmp_path, "")
        assert not report.fr_coverage["suppressed_base_metrics"]
        assert any(u["service"] == "web" for u in report.fr_coverage["unverified_base_metrics"])

    def test_declared_functional_fr_still_emits_under_traces_only(self, tmp_path):
        # suppression drops only the RED triple; a declared queue_depth FR still emits its SLO.
        report = self._run(tmp_path, "traces_only", with_fr=True)
        assert "FR-1" in report.fr_coverage["emitted"]


class TestServiceMonitorScrapeSurfaceGate:
    """#285: a ServiceMonitor is a Prometheus /metrics scrape config; suppress it for a service whose
    declared metrics_surface serves NO scrape endpoint (traces_only/none), else it ships a dead
    scrape target (the ADR-003 FP-3 the Mastodon pilot found). Mirrors #274's base-RED gate."""

    def _run(self, tmp_path, surface):
        hint = {
            "service_id": "web", "kind": "http_server", "transport": "http",
            "traces": {"required": [{"span_name": "GET /"}]},
            "metrics": {"convention_based": [
                {"name": "http.server.duration", "type": "histogram", "source": "otel_semconv:http"}]},
        }
        if surface:
            hint["metrics_surface"] = surface
        doc = {
            "project_id": "p",
            "instrumentation_hints": {"web": hint},
            # service_monitor only emits when DECLARED (Closure 3A) — declare it so the gate is exercised.
            "artifact_types": ["service_monitor"],
        }
        m = tmp_path / "onboarding-metadata.json"
        m.write_text(json.dumps(doc))
        return generate_observability_artifacts(
            onboarding_metadata_path=m, output_dir=tmp_path / "out", dry_run=False,
        )

    def _monitors(self, report):
        return [a for a in report.artifacts if a.artifact_type == "service_monitor"
                and a.service_id == "web" and a.status == "generated"]

    def test_traces_only_suppresses_the_service_monitor(self, tmp_path):
        report = self._run(tmp_path, "traces_only")
        assert self._monitors(report) == []          # no dead scrape config shipped
        assert any(u["service"] == "web" and u["metrics_surface"] == "traces_only"
                   for u in report.fr_coverage["suppressed_scrape_configs"])

    def test_none_surface_suppresses_the_service_monitor(self, tmp_path):
        report = self._run(tmp_path, "none")
        assert self._monitors(report) == []
        assert any(u["service"] == "web" for u in report.fr_coverage["suppressed_scrape_configs"])

    def test_prometheus_exporter_keeps_the_service_monitor(self, tmp_path):
        # a scrapeable surface (serves /metrics, different names) still gets its ServiceMonitor.
        report = self._run(tmp_path, "prometheus_exporter")
        assert len(self._monitors(report)) == 1
        assert not report.fr_coverage["suppressed_scrape_configs"]

    def test_absent_surface_keeps_the_service_monitor(self, tmp_path):
        # unknown surface must NOT be gated (would false-suppress a real scrapeable service).
        report = self._run(tmp_path, "")
        assert len(self._monitors(report)) == 1
        assert not report.fr_coverage["suppressed_scrape_configs"]
