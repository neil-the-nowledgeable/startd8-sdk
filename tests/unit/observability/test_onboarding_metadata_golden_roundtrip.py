"""Cross-repo golden round-trip: the real ``onboarding-metadata.json`` ContextCore emits, driven
through the *actual* SDK loader (``generate_observability_artifacts``), asserting every cross-repo
producer→consumer contract binds end-to-end.

Why this exists (the gap it closes):
    The per-contract tests elsewhere are **mirror tests** — the producer side (ContextCore) and the
    consumer side (this SDK) each hand-build a matching dict from the same fixture and assert opposite
    ends of the same shape. That proves the *logic*, but a mirror test is structurally blind to a
    silent **field rename or re-nesting** on one side: rename ``error_selector`` → ``error_matcher``,
    or move ``declared_span_signals`` out from under ``metrics``, and both sides' mirror tests keep
    passing while the live contract goes dead. This test pipes ONE metadata document — authored to the
    EXACT nesting the ContextCore producer emits — through the real SDK loader, so any such drift
    breaks it here.

Provenance of the fixture nesting (verified against the ContextCore producer, 2026-07-27):
  - ``instrumentation_hints[svc].service_name`` (slash-preserving)     — CC ``utils/instrumentation.py:532-534`` (#39 / REQ-CCL-105)
  - ``…metrics.declared_emitted_series[].error_selector``              — CC ``utils/instrumentation.py:558-559`` + ``cli/init_from_plan_ops.py:347`` (#43 / REQ-CCL-108)
  - ``…metrics_surface`` + ``…metrics.declared_span_signals[]`` (keyed ``name``) — CC ``cli/init_from_plan_ops.py:568-591`` + ``utils/instrumentation.py:539-570`` (#58 / REQ-CCL-109)
  SDK consumer of the same paths: ``artifact_generator_context.py:445-498`` (``extract_service_hints``),
  ``_parse_declared_series`` (:333), ``_parse_declared_span_signals`` (:360).

Contracts asserted:
  A. #43       error_selector → availability binds as a good/total ``ratioMetric`` on the real series.
  B. #39       the real OTel ``service.name`` (``mastodon/sidekiq``, slash intact) is the SLI label VALUE.
  C. #58       ``metrics_surface: spanmetrics`` + a span signal → ``traces_spanmetrics_*{service_name, span_name}``.
  D. #42/#44   ``declared_emitted_series`` covering latency/throughput → binds the REAL series (declared > convention).
  E. #30 CR-3  ``instrumentation_hints[svc].kind`` (ungrounded workload) → suppresses incidental transport RED + gap.
  F. #28 CR-1  the ContextManifest's ``spec.requirements.functional[]`` (a SECOND artifact, via ``manifest_path``)
               → a per-FR functional SLO binds on the named service.

Out of scope for this golden (a DIFFERENT loader, noted to avoid a false coverage claim):
  - #29 CR-2  ``ingestion-traceability.json`` (FR→service traceability) is NOT consumed by
    ``generate_observability_artifacts`` (no path arg; absent from ``load_business_context``). It is a
    plan-ingestion concern — a separate golden, not this one. Verified 2026-07-27.
"""

import copy
import json

import yaml

from startd8.observability.artifact_generator import generate_observability_artifacts

#: Number of services the golden declares — the guard-the-guards assert this so a mis-nesting test
#: can't pass vacuously by a service being dropped from extraction.
_N_SERVICES = 3


# ── The golden document: exactly the shape ContextCore writes to onboarding-metadata.json. ──
# Three services span the contracts: `web` carries the declared-Prometheus-series surface (A/D) with a
# slash-bearing service.name (B); `sidekiq` carries the spanmetrics surface (C+B); `ranker` carries an
# ungrounded workload kind with an incidental serve port (E) and is the target of the #28 functional FR.
GOLDEN_ONBOARDING_METADATA = {
    "project_id": "mastodon",
    "instrumentation_hints": {
        "web": {
            "service_id": "web",
            # (B) #39: the real OTel service.name, slash preserved — distinct from the sanitized id.
            "service_name": "mastodon/web",
            "kind": "http_server",
            "transport": "http",
            "metrics_surface": "prometheus_exporter",
            "traces": True,
            "metrics": {
                "convention_based": [
                    {"name": "http.server.duration", "type": "histogram", "source": "otel_semconv:http"}
                ],
                # (A) #43: a real counter covering availability WITH the error subset selector,
                # and (D) #44: the SAME counter also covers throughput (each cover binds independently).
                "declared_emitted_series": [
                    {
                        "name": "http_requests_total",
                        "type": "counter",
                        "labels": {"job": "web"},
                        "covers": ["availability", "throughput"],
                        "error_selector": 'status=~"5.."',
                    },
                    # (D) #42: a real latency histogram — must bind the REAL series, not the
                    # convention http_server_duration (declared > convention).
                    {
                        "name": "http_request_duration_seconds",
                        "type": "histogram",
                        "labels": {"method": "POST"},
                        "covers": ["latency"],
                    },
                ],
            },
        },
        # (E) #30 (CR-3): a recognized-but-ungrounded workload KIND with an INCIDENTAL http serve port —
        # the #231 silent-danger trap. If the SDK stops reading `kind`, this falls to the transport
        # default and gets a fabricated 500ms HTTP-latency SLO; with `kind` honored it is suppressed and
        # surfaced as a coverage gap. Also the subject of the (F) #28 functional FR (see GOLDEN_MANIFEST).
        "ranker": {
            "service_id": "ranker",
            "service_name": "mastodon/ranker",
            "kind": "ml_inference",
            "transport": "http",
            "traces": True,
            "metrics": {
                "convention_based": [
                    {"name": "http.server.duration", "type": "histogram", "source": "otel_semconv:http"}
                ]
            },
        },
        "sidekiq": {
            "service_id": "sidekiq",
            # (B) #39: slash-bearing service.name on the async tier — the FIRST place the fix shows in
            # a span-metrics SLO selector (#307).
            "service_name": "mastodon/sidekiq",
            "kind": "async_worker",
            "transport": "",
            # (C) #58: the trace surface — span-metrics, not Prometheus.
            "metrics_surface": "spanmetrics",
            "traces": True,
            "metrics": {
                "declared_span_signals": [
                    {"name": "FeedInsertWorker", "covers": ["latency"]}
                ]
            },
        },
    },
}


# ── The ContextManifest (.contextcore.yaml) surface — the SECOND producer artifact (#28 / CR-1). ──
# spec.requirements.functional[] is forwarded from the plan; the SDK reads it in load_business_context
# (artifact_generator_context.py:574) into ctx.functional_requirements, and generate_declared_functional_slos
# binds a per-FR SLO. A saturation FR with a target binds the convention series resource_utilization_ratio.
GOLDEN_MANIFEST = {
    "spec": {
        "requirements": {
            "functional": [
                {
                    "id": "FR-SAT-1",
                    "signal_kind": "saturation",
                    "target": "0.8",
                    "service": "ranker",
                    "description": "GPU/accelerator saturation on the ranker",
                }
            ]
        }
    }
}


def _generated_slo_contents(report):
    """Every generated SLO definition's rendered content (the PromQL the operator ships)."""
    return [
        a.content
        for a in report.artifacts
        if a.artifact_type == "slo_definition" and a.status == "generated"
    ]


def _run_golden(tmp_path, doc=None, manifest=None):
    meta = tmp_path / "onboarding-metadata.json"
    meta.write_text(json.dumps(doc if doc is not None else GOLDEN_ONBOARDING_METADATA))
    manifest_path = None
    if manifest is not None:
        manifest_path = tmp_path / ".contextcore.yaml"
        manifest_path.write_text(yaml.safe_dump(manifest))
    return generate_observability_artifacts(
        onboarding_metadata_path=meta,
        output_dir=tmp_path / "out",
        manifest_path=manifest_path,
        dry_run=False,
    )


class TestOnboardingMetadataGoldenRoundTrip:
    """One real-shape metadata doc → the real loader → all three cross-repo contracts bind."""

    def test_error_selector_binds_availability_ratio(self, tmp_path):
        # (A) #43: error_selector on a declared series → an OpenSLO good/total ratioMetric on the
        # REAL series, not a deferred/suppressed availability SLI.
        report = _run_golden(tmp_path)
        contents = _generated_slo_contents(report)
        ratio = [c for c in contents if "ratioMetric" in c and "http_requests_total" in c]
        assert ratio, "availability ratioMetric on the declared series was not emitted"
        blob = "\n".join(ratio)
        # total = base selector; good = base labels + the error subset.
        assert 'rate(http_requests_total{job="web"}[5m])' in blob
        assert 'rate(http_requests_total{job="web",status=~"5.."}[5m])' in blob
        # recorded as a positive binding (not double-recorded as deferred).
        assert any(
            b["kind"] == "availability" and b["series"] == "http_requests_total"
            for b in report.fr_coverage["bound_declared_series"]
        )
        assert all(
            d["kind"] != "availability" or d["service"] != "web"
            for d in report.fr_coverage["deferred_declared_kinds"]
        )

    def test_spanmetrics_binds_with_real_slash_service_name(self, tmp_path):
        # (B) #39 + (C) #58: the span signal binds to the Tempo span-metrics series, carrying the real
        # slash-bearing service.name as the label VALUE and the declared span name.
        report = _run_golden(tmp_path)
        contents = _generated_slo_contents(report)
        span = [c for c in contents if "traces_spanmetrics_latency_seconds_bucket" in c]
        assert span, "span-metrics latency SLO was not emitted for the declared span signal"
        blob = "\n".join(span)
        # the #307 acceptance query, byte-for-byte on the slash-bearing name.
        assert 'traces_spanmetrics_latency_seconds_bucket{service_name="mastodon/sidekiq"' in blob
        assert 'span_name="FeedInsertWorker"' in blob
        # the sanitized id must NOT be the selector value (it would never match real telemetry).
        assert "mastodonsidekiq" not in blob
        assert any(
            b["kind"] == "latency" and b["series"] == "FeedInsertWorker"
            for b in report.fr_coverage["bound_declared_span"]
        )

    def test_declared_latency_binds_real_series_not_convention(self, tmp_path):
        # (D) #42: a declared latency histogram binds the REAL series (http_request_duration_seconds
        # with its declared labels), NOT the convention http_server_duration — declared > convention.
        report = _run_golden(tmp_path)
        blob = "\n".join(_generated_slo_contents(report))
        assert "http_request_duration_seconds_bucket" in blob
        assert 'method="POST"' in blob
        assert "http_server_duration" not in blob  # convention suppressed for the bound kind
        assert any(
            b["kind"] == "latency" and b["series"] == "http_request_duration_seconds"
            for b in report.fr_coverage["bound_declared_series"]
        )

    def test_declared_throughput_binds_rate_query(self, tmp_path):
        # (D) #44: the counter also covers throughput → sum(rate(...)) on the real series.
        report = _run_golden(tmp_path)
        blob = "\n".join(_generated_slo_contents(report))
        assert 'sum(rate(http_requests_total{job="web"}[5m]))' in blob
        assert any(
            b["kind"] == "throughput" and b["series"] == "http_requests_total"
            for b in report.fr_coverage["bound_declared_series"]
        )

    def test_ungrounded_kind_suppresses_incidental_red_and_reports_gap(self, tmp_path):
        # (E) #30 (CR-3): `ranker` is kind=ml_inference with an INCIDENTAL http port. The SDK must
        # read `kind` and SUPPRESS the transport RED triple (no fabricated 500ms HTTP-latency SLO —
        # the #231 silent danger) and surface the ungrounded kind as a coverage gap. If `kind` were
        # ignored, ranker would fall to the http transport default and emit an http_server_duration SLO.
        report = _run_golden(tmp_path)
        ranker_slos = [
            a.content
            for a in report.artifacts
            if a.artifact_type == "slo_definition" and a.status == "generated"
            and a.service_id == "ranker"
        ]
        assert all("http_server_duration" not in c for c in ranker_slos), (
            "ranker got a convention HTTP-latency SLO — the SDK is not honoring instrumentation_hints.kind"
        )
        ung = report.fr_coverage.get("ungrounded_kinds", [])
        entry = next((u for u in ung if u["service"] == "ranker"), None)
        assert entry is not None and entry["kind"] == "ml_inference", (
            "ranker's ungrounded kind was not surfaced as a coverage gap — kind contract not consumed"
        )

    def test_functional_requirement_from_manifest_binds_saturation_slo(self, tmp_path):
        # (F) #28 (CR-1): a functional[] FR in the ContextManifest (a SECOND artifact, via manifest_path)
        # binds a per-FR functional SLO on the named service. Proves the manifest→functional[] wire is
        # live (load_business_context reads spec.requirements.functional[]). Without the manifest, no
        # such SLO exists — so this also proves the FR is what produced it.
        report = _run_golden(tmp_path, manifest=GOLDEN_MANIFEST)
        ranker_fn = [
            a.content
            for a in report.artifacts
            if a.artifact_type == "slo_definition" and a.status == "generated"
            and a.service_id == "ranker" and "functional" in (a.output_path or "")
        ]
        assert ranker_fn, "no functional SLO emitted for ranker — the manifest functional[] wire is dead"
        blob = "\n".join(ranker_fn)
        # the saturation FR binds the convention series with its authored target, traceable to the FR id.
        assert "resource_utilization_ratio" in blob
        assert "source_fr: FR-SAT-1" in blob
        assert "target: '0.8'" in blob
        # and it grounded — the FR is NOT recorded unfulfilled.
        assert all(
            u.get("id") != "FR-SAT-1" for u in report.fr_coverage.get("unfulfilled", [])
        ), "FR-SAT-1 was consumed but recorded unfulfilled — it should have bound the saturation series"

    def test_functional_requirement_absent_without_manifest(self, tmp_path):
        # Guard-the-guard for (F): with NO manifest, the saturation SLO must be absent — proving the
        # binding above is produced BY the manifest FR, not by something in the onboarding metadata.
        report = _run_golden(tmp_path)  # no manifest
        blob = "\n".join(_generated_slo_contents(report))
        assert "resource_utilization_ratio" not in blob
        assert "FR-SAT-1" not in blob

    def test_nesting_sensitivity_guard_declared_series_must_ride_under_metrics(self, tmp_path):
        # Prove the round-trip is sensitive to RE-NESTING (the drift a mirror test can't catch): move
        # declared_emitted_series OUT from under `metrics` to the hint top level and the availability
        # ratio must NOT bind — the SDK reads the specific documented path `metrics.declared_emitted_series`.
        drifted = copy.deepcopy(GOLDEN_ONBOARDING_METADATA)
        web = drifted["instrumentation_hints"]["web"]
        web["declared_emitted_series"] = web["metrics"].pop("declared_emitted_series")  # wrong nesting
        report = _run_golden(tmp_path, doc=drifted)
        # Guard-the-guard: prove the service is still PROCESSED (not silently dropped), so "nothing
        # bound" below reflects the loader ignoring the mis-nested path — not a vacuous pass because
        # `web` vanished from extraction (which a future extract_service_hints change could cause).
        assert report.services_processed == _N_SERVICES
        contents = _generated_slo_contents(report)
        assert not [c for c in contents if "ratioMetric" in c and "http_requests_total" in c], (
            "mis-nested declared_emitted_series still bound — the loader is not reading the documented "
            "`metrics.declared_emitted_series` path, so this golden would not catch producer re-nesting"
        )
        # bound_declared_series is one of the 8 always-present fr_coverage keys (artifact_generator.py:731).
        assert not report.fr_coverage["bound_declared_series"]

    def test_span_signal_nesting_sensitivity_guard(self, tmp_path):
        # Same guard for the span contract: declared_span_signals must ride under `metrics`.
        drifted = copy.deepcopy(GOLDEN_ONBOARDING_METADATA)
        sk = drifted["instrumentation_hints"]["sidekiq"]
        sk["declared_span_signals"] = sk["metrics"].pop("declared_span_signals")  # wrong nesting
        report = _run_golden(tmp_path, doc=drifted)
        # Guard-the-guard (see sibling): sidekiq's metrics is now {} after the pop, so absence of a
        # span SLO would be trivially true if it were dropped — assert it's still processed so the
        # result provably reflects the loader ignoring the mis-nested `declared_span_signals` path.
        assert report.services_processed == _N_SERVICES
        contents = _generated_slo_contents(report)
        assert not [c for c in contents if "traces_spanmetrics_latency_seconds_bucket" in c], (
            "mis-nested declared_span_signals still bound — loader not reading `metrics.declared_span_signals`"
        )
        # bound_declared_span is deliberately absent-when-empty (artifact_generator.py:731 — byte-identity
        # with pre-#307 goldens), so read it tolerantly.
        assert not report.fr_coverage.get("bound_declared_span", [])
