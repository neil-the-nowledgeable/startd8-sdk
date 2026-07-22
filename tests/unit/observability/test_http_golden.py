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
