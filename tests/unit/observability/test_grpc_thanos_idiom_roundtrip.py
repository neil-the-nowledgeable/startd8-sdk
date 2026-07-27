"""gRPC-idiom golden round-trip — the SDK side of the RepoProbe **Thanos** pilot (CNCF Pilot 2).

The existing cross-repo golden (``test_onboarding_metadata_golden_roundtrip.py``) proves the contracts
in the **HTTP** idiom (Mastodon). Thanos is the first **gRPC/Go** subject the pipeline runs, and its
plan deliberately stresses the *same* contracts in a non-HTTP idiom (see ContextCore
``docs/design/repoprobe/pilots/THANOS_NEXT_STEPS.md`` + ``repoprobe/data/go_thanos_fr_map.json``):

  - **gRPC ``error_selector``** — ``grpc_code=~"Unknown|Internal|Unavailable|DataLoss|DeadlineExceeded"``,
    NOT HTTP ``status=~"5.."`` (a REQ-CCL-108 / #43 stress "in a different idiom than Istio's").
  - **``grpc_server_handled_total``** declared series (mixin-declared), covers availability+throughput.
  - **gRPC transport** → ``semconv-grpc`` profile.
  - **``compactor`` = batch** (singleton downsampling/retention worker) → ``UNGROUNDED_KINDS``.

This test proves the SDK already generates correct observability for that idiom — the artifacts a
downstream RepoProbe Thanos run consumes — so the pilot's SDK-side ask arrives pre-satisfied, and a
future refactor can't silently HTTP-hardcode the binder and break gRPC subjects.

Fixture signals are grounded in the pilot's real emitted surface (``go_thanos_fr_map.json`` FR-1,
Thanos @ v0.42.2): ``grpc_server_handled_total{grpc_code,grpc_method,grpc_service}`` from
go-grpc-middleware, declared via ``mixin/alerts/*.libsonnet``.
"""

import json

from startd8.observability.artifact_generator import generate_observability_artifacts

# The gRPC error subset the Thanos mixin encodes — gRPC status codes, not HTTP 5xx.
_GRPC_ERROR_SELECTOR = 'grpc_code=~"Unknown|Internal|Unavailable|DataLoss|DeadlineExceeded"'

# A Thanos-shaped onboarding-metadata: gRPC StoreAPI (store) + a batch compactor.
THANOS_ONBOARDING_METADATA = {
    "project_id": "thanos",
    "instrumentation_hints": {
        "store": {
            "service_id": "store",
            "service_name": "thanos-store",
            "kind": "grpc_server",
            "transport": "grpc",
            "metrics_surface": "prometheus_exporter",
            "traces": True,
            "metrics": {
                "declared_emitted_series": [
                    {
                        "name": "grpc_server_handled_total",
                        "type": "counter",
                        "labels": {"grpc_service": "thanos.Store"},
                        "covers": ["availability", "throughput"],
                        "error_selector": _GRPC_ERROR_SELECTOR,
                    }
                ]
            },
        },
        # compactor: singleton batch worker (downsampling/retention) — no listen port.
        "compactor": {
            "service_id": "compactor",
            "service_name": "thanos-compact",
            "kind": "batch",
            "transport": "",
            "metrics": {"convention_based": []},
        },
    },
}


def _slo_contents(report):
    return [
        a.content
        for a in report.artifacts
        if a.artifact_type == "slo_definition" and a.status == "generated"
    ]


def _run(tmp_path, doc=None):
    meta = tmp_path / "onboarding-metadata.json"
    meta.write_text(json.dumps(doc if doc is not None else THANOS_ONBOARDING_METADATA))
    return generate_observability_artifacts(
        onboarding_metadata_path=meta, output_dir=tmp_path / "out", dry_run=False
    )


class TestGrpcThanosIdiom:
    def test_grpc_availability_binds_ratio_with_grpc_code_error_subset(self, tmp_path):
        # REQ-CCL-108 / #43 in the gRPC idiom: availability binds a good/total ratioMetric whose error
        # subset is gRPC status codes — the raw error_selector must render verbatim (no HTTP assumption,
        # and the `|` alternation must survive the matcher-key de-dup).
        report = _run(tmp_path)
        ratio = [c for c in _slo_contents(report) if "ratioMetric" in c and "grpc_server_handled_total" in c]
        assert ratio, "gRPC availability ratioMetric was not emitted"
        blob = "\n".join(ratio)
        assert 'rate(grpc_server_handled_total{grpc_service="thanos.Store"}[5m])' in blob  # total
        assert _GRPC_ERROR_SELECTOR in blob                                                # error subset verbatim
        assert "5.." not in blob                                                           # NOT HTTP-hardcoded
        assert any(
            b["kind"] == "availability" and b["series"] == "grpc_server_handled_total"
            for b in report.fr_coverage["bound_declared_series"]
        )

    def test_grpc_throughput_binds_rate(self, tmp_path):
        report = _run(tmp_path)
        blob = "\n".join(_slo_contents(report))
        assert 'sum(rate(grpc_server_handled_total{grpc_service="thanos.Store"}[5m]))' in blob
        assert any(
            b["kind"] == "throughput" and b["series"] == "grpc_server_handled_total"
            for b in report.fr_coverage["bound_declared_series"]
        )

    def test_compactor_batch_kind_suppresses_red_and_reports_gap(self, tmp_path):
        # `compactor`=batch must NOT get RED SLOs (no metrics, no listen port); it surfaces as an
        # ungrounded-kind coverage gap. Proves the SDK reads `kind` for a Go batch worker.
        report = _run(tmp_path)
        comp = [
            a.content for a in report.artifacts
            if a.artifact_type == "slo_definition" and a.status == "generated"
            and a.service_id == "compactor"
        ]
        assert all("http_server_duration" not in c and "grpc_server" not in c for c in comp)
        assert any(
            u["service"] == "compactor" and u["kind"] == "batch"
            for u in report.fr_coverage.get("ungrounded_kinds", [])
        )

    def test_no_metric_prefix_filter_drops_grpc_series(self, tmp_path):
        # RepoProbe's CoverageScorer drops grpc_* via _METRIC_PREFIXES (its own filed finding); the SDK
        # generator has no such allowlist — guard that a grpc_-prefixed series still binds here, so the
        # SDK never grows the prefix-blindness the scorer has.
        report = _run(tmp_path)
        assert report.fr_coverage["bound_declared_series"], "grpc_* declared series were dropped by the SDK"
