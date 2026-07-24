# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Live-harness proof for collector_enrichment (REQ_COLLECTOR_ENRICHMENT acceptance #5 + FR-7).

Two tiers, mirroring `test_runtime_fidelity.py`:

- **Unit (no binary, always runs):** the `collector_config()` enrichment seam assembles a valid
  pipeline (transform/business processor + traces wiring + spanmetrics dimension), and the
  `SpanMetricsCollector` scrape/parse spine surfaces the enriched label from a *fixtured* `/metrics`.
  Proves everything the SDK owns.

- **Integration (`find_collector_binary`-gated, skips where otelcol-contrib is absent):** boots the
  REAL collector with the enriched config, emits a real span for `service.name=frontend` via the OTLP
  gRPC exporter, and asserts `calls_total{business_criticality="critical"}` appears in the live
  `/metrics`. This is the executable end-to-end proof otelcol actually enriches + promotes the label.
"""

import time

import pytest
import yaml

from startd8.observability import runtime_fidelity as rf
from startd8.observability.artifact_generator_generators import (
    generate_collector_enrichment,
)
from startd8.observability.artifact_generator_models import (
    BusinessContext,
    GenerationReport,
    ServiceHints,
)
from startd8.observability.collector_enrichment_parity import extract_enrichment_map
from startd8.observability.runtime_fidelity import (
    SpanMetricsCollector,
    collector_config,
    find_collector_binary,
)


class _FakeProc:
    pid = 999999999  # nonexistent — teardown's killpg is best-effort/guarded


def _real_enrichment_map():
    """Feed the REAL generator output through the parity parser → {service.name: {attr: value}}."""
    services = [
        ServiceHints(
            service_id="frontend",
            service_name="frontend",
            criticality="critical",
            owner="Annie Jump Cannon",
        ),
        ServiceHints(
            service_id="cartservice", service_name="cartservice", criticality="high"
        ),
    ]
    gen = generate_collector_enrichment(
        services,
        BusinessContext(project_id="ob"),
        GenerationReport(project_id="ob", generated_at="t"),
    )
    return extract_enrichment_map(gen.content)


# ============================ Unit: config seam ============================


class TestEnrichmentConfigSeam:
    def test_default_config_unchanged(self):
        cfg = collector_config()
        assert "transform/business" not in cfg
        assert "dimensions:" not in cfg
        assert (
            yaml.safe_load(cfg)["service"]["pipelines"]["traces"].get("processors")
            is None
        )

    def test_enrichment_injects_processor_pipeline_and_dimension(self):
        cfg = collector_config(
            business_enrichment=_real_enrichment_map(),
            enrichment_dimensions=["business.criticality"],
        )
        doc = yaml.safe_load(cfg)  # valid YAML
        assert doc["service"]["pipelines"]["traces"]["processors"] == [
            "transform/business"
        ]
        assert doc["connectors"]["spanmetrics"]["dimensions"] == [
            {"name": "business.criticality"}
        ]
        tb = doc["processors"]["transform/business"]
        assert tb["error_mode"] == "ignore"
        stmts = tb["trace_statements"][0]["statements"]
        assert any(
            '"business.criticality"], "critical"' in s and '"frontend"' in s
            for s in stmts
        )

    def test_seam_is_deterministic(self):
        emap = _real_enrichment_map()
        a = collector_config(
            business_enrichment=emap, enrichment_dimensions=["business.criticality"]
        )
        b = collector_config(
            business_enrichment=emap, enrichment_dimensions=["business.criticality"]
        )
        assert a == b

    def test_hostile_owner_still_valid_yaml(self):
        svc = [
            ServiceHints(
                service_id="x",
                service_name="x",
                criticality="low",
                owner='O"Brien\\ y: lead',
            )
        ]
        gen = generate_collector_enrichment(
            svc, BusinessContext(), GenerationReport(project_id="p", generated_at="t")
        )
        cfg = collector_config(business_enrichment=extract_enrichment_map(gen.content))
        assert yaml.safe_load(cfg) is not None  # both escaping layers hold


# ============================ Unit: scrape/parse spine (fixtured /metrics) ============================

# A fixtured span-metrics /metrics AS IF the enriched pipeline had run: business_criticality is a label.
_ENRICHED_METRICS = """\
# HELP calls_total spanmetrics
calls_total{service_name="frontend",span_name="GET /",business_criticality="critical"} 5
calls_total{service_name="cartservice",span_name="Add",business_criticality="high"} 3
"""


class TestEnrichedScrapeSpine:
    def test_collector_surfaces_business_label(self, tmp_path):
        col = SpanMetricsCollector(
            "otelcol-contrib",
            tmp_path,
            launcher=lambda argv, cwd: _FakeProc(),
            scrape_fn=lambda url: _ENRICHED_METRICS,
            ready_timeout_s=1.0,
            config=collector_config(
                business_enrichment=_real_enrichment_map(),
                enrichment_dimensions=["business.criticality"],
            ),
        )
        with col as c:
            parsed = rf.parse_prometheus_text(c.scrape())
        crit = {
            row["service_name"]: row.get("business_criticality")
            for row in parsed["calls_total"]
        }
        assert crit == {"frontend": "critical", "cartservice": "high"}

    def test_config_written_is_the_enriched_one(self, tmp_path):
        cfg = collector_config(business_enrichment=_real_enrichment_map())
        col = SpanMetricsCollector(
            "otelcol-contrib",
            tmp_path,
            launcher=lambda argv, cwd: _FakeProc(),
            scrape_fn=lambda url: _ENRICHED_METRICS,
            ready_timeout_s=1.0,
            config=cfg,
        )
        with col:
            written = (tmp_path / "otelcol-spanmetrics.yaml").read_text()
        assert "transform/business" in written


# ============================ Integration: real otelcol-contrib (gated) ============================


@pytest.mark.slow
@pytest.mark.skipif(
    find_collector_binary() is None,
    reason="otelcol-contrib not on PATH / $OTELCOL_CONTRIB_BIN — live enrichment proof skipped",
)
def test_live_enrichment_promotes_business_label(tmp_path):
    """Boot the real collector with the enriched config, emit a span for frontend, assert the label.

    The executable acceptance-#5 / FR-7 proof. Skips wherever the collector binary is absent.
    """
    otlp = "127.0.0.1:4317"
    prom = "127.0.0.1:8889"
    cfg = collector_config(
        otlp,
        prom,
        business_enrichment=_real_enrichment_map(),
        enrichment_dimensions=["business.criticality"],
    )
    binary = find_collector_binary()
    assert binary is not None

    with SpanMetricsCollector(
        binary, tmp_path, otlp_endpoint=otlp, prom_endpoint=prom, config=cfg
    ):
        # Emit one real span with service.name=frontend via the OTLP gRPC exporter.
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        provider = TracerProvider(
            resource=Resource.create({"service.name": "frontend"})
        )
        provider.add_span_processor(
            SimpleSpanProcessor(
                OTLPSpanExporter(endpoint=f"http://{otlp}", insecure=True)
            )
        )
        tracer = provider.get_tracer("live-test")
        for _ in range(5):
            with tracer.start_as_current_span("GET /"):
                pass
        provider.force_flush()

        # Poll /metrics until calls_total carries the enriched label.
        import urllib.request

        deadline = time.monotonic() + 15.0
        found = None
        while time.monotonic() < deadline and found is None:
            try:
                with urllib.request.urlopen(f"http://{prom}/metrics", timeout=1.0) as r:
                    text = r.read().decode()
            except Exception:
                text = ""
            for row in rf.parse_prometheus_text(text).get("calls_total", []):
                if (
                    row.get("service_name") == "frontend"
                    and row.get("business_criticality") == "critical"
                ):
                    found = row
                    break
            if found is None:
                time.sleep(0.5)

        assert (
            found is not None
        ), "calls_total{service_name=frontend,business_criticality=critical} never appeared"
