"""Tests for instrumentation coverage computation (REQ-TCW-402/403)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.validators.instrumentation_coverage import (
    CoverageResult,
    compute_instrumentation_coverage,
    extract_promql_metrics,
    validate_dashboard_coverage,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_java_file(d: Path, name: str, content: str) -> Path:
    f = d / name
    f.write_text(content, encoding="utf-8")
    return f


JAVA_WITH_METRICS = """\
package hipstershop;
import io.opentelemetry.api.metrics.Meter;
public class AdService {
    void initMetrics(Meter meter) {
        meter.counterBuilder("rpc_server_duration_seconds").build();
        meter.counterBuilder("ad_request_total").build();
    }
}
"""

JAVA_WITH_TRACES = """\
package hipstershop;
import io.opentelemetry.api.trace.Tracer;
public class AdService {
    void initTracing(Tracer tracer) {
        tracer.spanBuilder("ad.serve").startSpan();
    }
}
"""


CONTRACT_FULL = {
    "metrics": {
        "required": [
            {"name": "rpc_server_duration_seconds"},
            {"name": "ad_request_total"},
            {"name": "ad_cache_hits_total"},
        ],
    },
    "traces": {
        "required": [
            {"name": "ad.serve"},
        ],
    },
}

CONTRACT_CONTEXTCORE = {
    "metrics": {
        "convention_based": [
            {"name": "rpc_server_duration_seconds"},
        ],
        "manifest_declared": [
            {"name": "ad_request_total"},
        ],
    },
}


# ---------------------------------------------------------------------------
# Tests: compute_instrumentation_coverage
# ---------------------------------------------------------------------------

class TestComputeCoverage:

    def test_none_contract_returns_empty(self, tmp_path):
        result = compute_instrumentation_coverage(tmp_path, None)
        assert result.contract_entries == 0
        assert result.coverage_pct == 0.0

    def test_empty_contract_returns_empty(self, tmp_path):
        result = compute_instrumentation_coverage(tmp_path, {})
        assert result.contract_entries == 0

    def test_full_coverage(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write_java_file(src, "AdService.java", JAVA_WITH_METRICS + JAVA_WITH_TRACES)

        contract = {
            "metrics": {"required": [
                {"name": "rpc_server_duration_seconds"},
                {"name": "ad_request_total"},
            ]},
            "traces": {"required": [{"name": "ad.serve"}]},
        }
        result = compute_instrumentation_coverage(tmp_path, contract)
        assert result.contract_entries == 3
        assert result.satisfied_entries == 3
        assert result.coverage_pct == 100.0
        assert len(result.gaps) == 0

    def test_partial_coverage(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write_java_file(src, "AdService.java", JAVA_WITH_METRICS)

        result = compute_instrumentation_coverage(tmp_path, CONTRACT_FULL)
        # 2 metrics found, 1 metric + 1 trace missing? Actually ad.serve is missing
        assert result.contract_entries == 4
        assert result.satisfied_entries == 2
        assert result.coverage_pct == 50.0
        assert len(result.gaps) == 2
        gap_names = {g["name"] for g in result.gaps}
        assert "ad_cache_hits_total" in gap_names
        assert "ad.serve" in gap_names

    def test_zero_coverage(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write_java_file(src, "Empty.java", "package foo;\npublic class Empty {}\n")

        result = compute_instrumentation_coverage(tmp_path, CONTRACT_FULL)
        assert result.coverage_pct == 0.0
        assert result.satisfied_entries == 0
        assert len(result.gaps) == 4

    def test_contextcore_schema_handled(self, tmp_path):
        """Handles convention_based + manifest_declared without normalization."""
        src = tmp_path / "src"
        src.mkdir()
        _write_java_file(src, "AdService.java", JAVA_WITH_METRICS)

        result = compute_instrumentation_coverage(tmp_path, CONTRACT_CONTEXTCORE)
        assert result.contract_entries == 2
        assert result.satisfied_entries == 2
        assert result.coverage_pct == 100.0

    def test_dedup_across_keys(self, tmp_path):
        """Same metric in required and convention_based is counted once."""
        src = tmp_path / "src"
        src.mkdir()
        _write_java_file(src, "A.java", 'meter.counter("foo_total");')

        contract = {
            "metrics": {
                "required": [{"name": "foo_total"}],
                "convention_based": [{"name": "foo_total"}],
            },
        }
        result = compute_instrumentation_coverage(tmp_path, contract)
        assert result.contract_entries == 1
        assert result.satisfied_entries == 1

    def test_extension_filtering(self, tmp_path):
        """Only searches files with matching extensions."""
        (tmp_path / "readme.md").write_text("rpc_server_duration_seconds")
        result = compute_instrumentation_coverage(
            tmp_path,
            {"metrics": {"required": [{"name": "rpc_server_duration_seconds"}]}},
            extensions=(".java",),
        )
        assert result.satisfied_entries == 0

    def test_satisfied_includes_location(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        _write_java_file(src, "Svc.java", 'meter.counter("foo_bar_total");')

        contract = {"metrics": {"required": [{"name": "foo_bar_total"}]}}
        result = compute_instrumentation_coverage(tmp_path, contract)
        assert len(result.satisfied) == 1
        assert result.satisfied[0]["name"] == "foo_bar_total"
        assert "found_in" in result.satisfied[0]
        assert result.satisfied[0]["line"] >= 1

    def test_nested_directory_search(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        _write_java_file(deep, "Deep.java", 'span("deep_span");')

        contract = {"traces": {"required": [{"name": "deep_span"}]}}
        result = compute_instrumentation_coverage(tmp_path, contract)
        assert result.satisfied_entries == 1

    def test_metric_name_field_alias(self, tmp_path):
        """Accepts metric_name as an alias for name."""
        src = tmp_path / "src"
        src.mkdir()
        _write_java_file(src, "A.java", 'counter("alt_metric");')

        contract = {"metrics": {"required": [{"metric_name": "alt_metric"}]}}
        result = compute_instrumentation_coverage(tmp_path, contract)
        assert result.satisfied_entries == 1


# ---------------------------------------------------------------------------
# Tests: extract_promql_metrics
# ---------------------------------------------------------------------------

class TestExtractPromqlMetrics:

    def test_simple_expr(self):
        dashboard = {
            "panels": [{
                "targets": [{"expr": 'rate(http_requests_total{job="api"}[5m])'}],
            }],
        }
        metrics = extract_promql_metrics(dashboard)
        assert "http_requests_total" in metrics

    def test_multiple_metrics(self):
        dashboard = {
            "panels": [{
                "targets": [{
                    "expr": 'sum(rate(http_requests_total[5m])) / sum(rate(http_errors_total[5m]))',
                }],
            }],
        }
        metrics = extract_promql_metrics(dashboard)
        assert "http_requests_total" in metrics
        assert "http_errors_total" in metrics

    def test_ignores_builtins(self):
        dashboard = {
            "panels": [{
                "targets": [{"expr": 'sum(rate(my_metric{a="b"}[5m]))'}],
            }],
        }
        metrics = extract_promql_metrics(dashboard)
        assert "sum" not in metrics
        assert "rate" not in metrics
        assert "my_metric" in metrics

    def test_nested_rows(self):
        dashboard = {
            "panels": [{
                "type": "row",
                "panels": [{
                    "targets": [{"expr": 'nested_metric{x="1"}'}],
                }],
            }],
        }
        metrics = extract_promql_metrics(dashboard)
        assert "nested_metric" in metrics

    def test_empty_dashboard(self):
        assert extract_promql_metrics({}) == set()
        assert extract_promql_metrics({"panels": []}) == set()


# ---------------------------------------------------------------------------
# Tests: validate_dashboard_coverage
# ---------------------------------------------------------------------------

class TestValidateDashboardCoverage:

    def test_missing_metric_in_code(self, tmp_path):
        dash_dir = tmp_path / "dashboards"
        dash_dir.mkdir()
        (dash_dir / "test.json").write_text(json.dumps({
            "panels": [{
                "targets": [{"expr": 'rate(missing_metric{job="x"}[5m])'}],
            }],
        }))

        src = tmp_path / "src"
        src.mkdir()
        _write_java_file(src, "Empty.java", "// nothing here")

        gaps = validate_dashboard_coverage(tmp_path, {}, dash_dir)
        assert len(gaps) == 1
        assert gaps[0]["name"] == "missing_metric"
        assert gaps[0]["source"] == "dashboard"

    def test_no_gaps_when_found(self, tmp_path):
        dash_dir = tmp_path / "dashboards"
        dash_dir.mkdir()
        (dash_dir / "test.json").write_text(json.dumps({
            "panels": [{
                "targets": [{"expr": 'rate(found_metric{job="x"}[5m])'}],
            }],
        }))

        src = tmp_path / "src"
        src.mkdir()
        _write_java_file(src, "Svc.java", 'counter("found_metric");')

        gaps = validate_dashboard_coverage(tmp_path, {}, dash_dir)
        assert len(gaps) == 0
