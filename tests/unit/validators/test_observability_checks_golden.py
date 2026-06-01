"""Golden-score parity tests for the three structural validators (D-9).

These lock the EXACT scoring behavior of validate_dashboard / validate_alerts /
validate_slo (checks_passed, checks_total, score, the set of (check, severity)
issues, repairs) BEFORE the D-9 check-runner refactor, and must remain
byte-identical AFTER it. They are intentionally value-frozen: if a number here
changes, the refactor changed behavior and must be fixed.

Captured 2026-05-31 against the pre-refactor implementation.
"""

import yaml

from startd8.validators.observability_artifact_checks import (
    validate_alerts,
    validate_dashboard,
    validate_slo,
)


def _snap(r):
    return {
        "passed": r.checks_passed,
        "total": r.checks_total,
        "score": round(r.score, 6),
        "issues": sorted([i.check, i.severity] for i in r.issues),
        "repairs": sorted(r.repairs_applied),
    }


# --- fixed inputs (reused verbatim by the golden assertions) ---

_GOOD_DASH = yaml.dump({
    "title": "t", "uid": "obs-svc", "datasources": ["prom"], "variables": ["x"],
    "panels": [
        {"type": "timeseries", "unit": "s", "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
         "targets": [{"expr": 'rate(http_server_duration_count{service="svc"}[5m])'}]},
        {"type": "timeseries", "unit": "s", "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
         "targets": [{"expr": 'rate(http_server_errors_total{service="svc"}[5m])'}]},
        {"type": "timeseries", "unit": "s", "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
         "targets": [{"expr": 'histogram_quantile(0.99, rate(http_server_duration_bucket{service="svc"}[5m]))'}]},
    ],
})
_BAD_DASH = yaml.dump({"panels": []})
_PARSE_ERR = "::: not: [valid"

_GOOD_ALERT = yaml.dump({"groups": [{"name": "g", "rules": [
    {"alert": "HighLatency", "expr": "x>1", "for": "5m",
     "labels": {"severity": "warning", "service": "svc"}, "annotations": {"summary": "s"}},
]}]})
_BAD_ALERT = yaml.dump({"groups": []})

_GOOD_SLO = yaml.dump({
    "apiVersion": "openslo/v1", "kind": "SLO",
    "metadata": {"name": "n", "labels": {"service": "svc"}},
    "spec": {"target": 0.99, "timeWindow": [{"duration": "30d"}],
             "indicator": {"spec": {"thresholdMetric": {"metricSource": {"spec": {"query": "http_server_duration"}}}}},
             "alerting": {}}})
_MULTI_SLO = _GOOD_SLO + "---\n" + _GOOD_SLO


class TestDashboardGolden:
    def test_good(self):
        assert _snap(validate_dashboard(_GOOD_DASH, "d.yaml", service_id="svc", transport="http")) == {
            "passed": 12, "total": 12, "score": 1.0, "issues": [], "repairs": []}

    def test_bad_empty_panels(self):
        # OBS-100e/f/g/h increment total but yield neither pass nor issue (the
        # "third state" the refactor must preserve).
        assert _snap(validate_dashboard(_BAD_DASH, "d.yaml")) == {
            "passed": 2, "total": 12, "score": 0.166667,
            "issues": [["OBS-100b", "error"], ["OBS-100c", "error"], ["OBS-100d", "error"],
                       ["OBS-100i", "warning"], ["OBS-100j", "info"], ["OBS-200a", "warning"]],
            "repairs": []}

    def test_parse_error(self):
        assert _snap(validate_dashboard(_PARSE_ERR, "d.yaml")) == {
            "passed": 0, "total": 1, "score": 0.0, "issues": [["OBS-100a", "error"]], "repairs": []}


class TestAlertGolden:
    def test_good(self):
        assert _snap(validate_alerts(_GOOD_ALERT, "a.yaml", service_id="svc", transport="http")) == {
            "passed": 10, "total": 10, "score": 1.0, "issues": [], "repairs": []}

    def test_good_with_availability_coverage(self):
        assert _snap(validate_alerts(_GOOD_ALERT, "a.yaml", manifest_availability=0.99)) == {
            "passed": 9, "total": 10, "score": 0.9, "issues": [["OBS-710d", "warning"]], "repairs": []}

    def test_bad_no_rules(self):
        assert _snap(validate_alerts(_BAD_ALERT, "a.yaml")) == {
            "passed": 2, "total": 4, "score": 0.5,
            "issues": [["OBS-101b", "error"], ["OBS-710d", "warning"]], "repairs": []}


class TestSloGolden:
    def test_good(self):
        assert _snap(validate_slo(_GOOD_SLO, "s.yaml", manifest_availability=0.99,
                                  service_id="svc", transport="http")) == {
            "passed": 10, "total": 11, "score": 0.909091,
            "issues": [["OBS-102i", "info"]], "repairs": []}

    def test_good_no_availability(self):
        assert _snap(validate_slo(_GOOD_SLO, "s.yaml")) == {
            "passed": 10, "total": 11, "score": 0.909091,
            "issues": [["OBS-102i", "info"]], "repairs": []}

    def test_multi_doc_merges(self):
        assert _snap(validate_slo(_MULTI_SLO, "s.yaml", manifest_availability=0.99)) == {
            "passed": 20, "total": 22, "score": 0.909091,
            "issues": [["OBS-102i", "info"], ["OBS-102i", "info"]], "repairs": []}

    def test_parse_error(self):
        assert _snap(validate_slo(_PARSE_ERR, "s.yaml")) == {
            "passed": 0, "total": 1, "score": 0.0, "issues": [["OBS-102a", "error"]], "repairs": []}
