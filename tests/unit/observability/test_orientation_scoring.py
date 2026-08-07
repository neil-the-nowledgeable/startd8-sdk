"""Tests for C2 — orientation-aware quality scoring + 3-way metric coverage
(REQ-OAT-050 / 051 / 061 / 062).

Helper-level precision tests for the bridge two-half breakdown, mixed-file
sub-score, and handoff resolution; plus an integration test asserting the
three orientation coverages + continuity aliases through the full generator.
"""

import json

import yaml

from startd8.observability.artifact_generator import (
    ArtifactResult,
    GenerationReport,
    _apply_orientation_scoring,
    _bridge_human_actionable,
    _iter_rule_dicts,
    _produced_service_targets,
    _recording_subscore,
    _score_extended_artifacts,
    _write_quality_report,
    generate_observability_artifacts,
)
from startd8.observability.taxonomy_enums import Orientation


def _alert_yaml(*, severity="warning", summary="high latency",
                runbook=True, dashboard=True):
    rule = {"alert": "HighLatency", "expr": "x > 1", "labels": {}, "annotations": {}}
    if severity:
        rule["labels"]["severity"] = severity
    if summary:
        rule["annotations"]["summary"] = summary
    if runbook:
        rule["annotations"]["runbook_url"] = "https://runbooks.example.com/svc/HighLatency"
    if dashboard:
        rule["annotations"]["dashboard_url"] = "/d/obs-svc"
    return yaml.dump({"groups": [{"name": "g", "rules": [rule]}]})


def _bridge_result(content, service_id="svc"):
    return ArtifactResult(
        artifact_type="alert_rule", service_id=service_id, output_path="alerts/x.yaml",
        status="generated", content=content,
        orientation=Orientation.BRIDGE.value, category="service_observability",
        quality={"score": 1.0, "checks_passed": 5, "checks_total": 5},
    )


# ---------------------------------------------------------------------------
# Rule parsing
# ---------------------------------------------------------------------------


class TestIterRuleDicts:
    def test_grouped_rules(self):
        rules = _iter_rule_dicts(_alert_yaml())
        assert len(rules) == 1 and rules[0]["alert"] == "HighLatency"

    def test_flat_rules(self):
        content = yaml.dump({"rules": [{"alert": "A", "expr": "1"}]})
        assert len(_iter_rule_dicts(content)) == 1

    def test_malformed_is_empty(self):
        assert _iter_rule_dicts(":::not yaml:::") == []
        assert _iter_rule_dicts("[]") == []


# ---------------------------------------------------------------------------
# Bridge actionability (REQ-OAT-061)
# ---------------------------------------------------------------------------


class TestBridgeActionable:
    def test_resolvable_handoff_passes(self):
        # severity + summary + a link AND a dashboard produced for the service.
        r = _bridge_result(_alert_yaml())
        assert _bridge_human_actionable(r, {"svc"}, set()) is True

    def test_broken_handoff_fails(self):
        # links present but NO dashboard/runbook produced for the service.
        r = _bridge_result(_alert_yaml())
        assert _bridge_human_actionable(r, set(), set()) is False

    def test_missing_severity_fails(self):
        r = _bridge_result(_alert_yaml(severity=None))
        assert _bridge_human_actionable(r, {"svc"}, set()) is False

    def test_missing_summary_fails(self):
        r = _bridge_result(_alert_yaml(summary=None))
        assert _bridge_human_actionable(r, {"svc"}, set()) is False

    def test_no_links_fails(self):
        r = _bridge_result(_alert_yaml(runbook=False, dashboard=False))
        assert _bridge_human_actionable(r, {"svc"}, set()) is False

    def test_runbook_target_also_resolves(self):
        r = _bridge_result(_alert_yaml(dashboard=False))
        assert _bridge_human_actionable(r, set(), {"svc"}) is True

    def test_notification_policy_route_present(self):
        content = yaml.dump({"route": {"receiver": "r"}, "receivers": [{"name": "r"}]})
        r = ArtifactResult(
            artifact_type="notification_policy", service_id="svc", output_path="n.yaml",
            status="generated", content=content, orientation=Orientation.BRIDGE.value,
            quality={"score": 1.0, "checks_passed": 3, "checks_total": 3},
        )
        assert _bridge_human_actionable(r, set(), set()) is True


# ---------------------------------------------------------------------------
# Two-half breakdown (REQ-OAT-050) + mixed file (REQ-OAT-062)
# ---------------------------------------------------------------------------


class TestApplyOrientationScoring:
    def test_bridge_both_halves_complete(self):
        report = GenerationReport(project_id="p", generated_at="t")
        report.artifacts = [
            _bridge_result(_alert_yaml()),
            ArtifactResult(artifact_type="dashboard_spec", service_id="svc",
                           output_path="d.yaml", status="generated", content="x",
                           orientation=Orientation.HUMAN.value),
        ]
        _apply_orientation_scoring(report)
        alert = report.artifacts[0]
        assert alert.quality["orientation_breakdown"] == {"system": True, "human": True}
        assert alert.quality["orientation_partial"] is False
        assert alert.quality["orientation"] == "bridge"

    def test_bridge_partial_when_handoff_broken(self):
        # no dashboard/runbook produced → human half fails → partial.
        report = GenerationReport(project_id="p", generated_at="t")
        report.artifacts = [_bridge_result(_alert_yaml())]
        _apply_orientation_scoring(report)
        q = report.artifacts[0].quality
        assert q["orientation_breakdown"] == {"system": True, "human": False}
        assert q["orientation_partial"] is True

    def test_bridge_partial_when_structurally_invalid(self):
        report = GenerationReport(project_id="p", generated_at="t")
        bad = _bridge_result(_alert_yaml())
        bad.quality = {"score": 0.5, "checks_passed": 2, "checks_total": 5}  # system half fails
        report.artifacts = [
            bad,
            ArtifactResult(artifact_type="dashboard_spec", service_id="svc",
                           output_path="d.yaml", status="generated", content="x",
                           orientation=Orientation.HUMAN.value),
        ]
        _apply_orientation_scoring(report)
        q = report.artifacts[0].quality
        assert q["orientation_breakdown"] == {"system": False, "human": True}
        assert q["orientation_partial"] is True

    def test_non_bridge_gets_axes_only(self):
        report = GenerationReport(project_id="p", generated_at="t")
        report.artifacts = [
            ArtifactResult(artifact_type="slo_definition", service_id="svc",
                           output_path="s.yaml", status="generated", content="x",
                           orientation=Orientation.SYSTEM.value, category="service_observability",
                           quality={"score": 1.0, "checks_passed": 3, "checks_total": 3}),
        ]
        _apply_orientation_scoring(report)
        q = report.artifacts[0].quality
        assert q["orientation"] == "system"
        assert "orientation_breakdown" not in q  # only bridge gets the two-half split

    def test_skips_untouched(self):
        report = GenerationReport(project_id="p", generated_at="t")
        report.artifacts = [
            ArtifactResult(artifact_type="trace_config", service_id="p",
                           output_path="(skip)", status="skipped", quality=None),
        ]
        _apply_orientation_scoring(report)  # must not raise on quality=None
        assert report.artifacts[0].quality is None


class TestMixedFileSubScore:
    def test_recording_plus_alerting_yields_subscore(self):
        content = yaml.dump({"groups": [{"name": "g", "rules": [
            {"alert": "A", "expr": "x > 1", "labels": {"severity": "warning"},
             "annotations": {"summary": "s", "runbook_url": "u"}},
            {"record": "job:x:rate", "expr": "rate(x[5m])"},
        ]}]})
        sub = _recording_subscore(content)
        assert sub is not None
        assert sub["orientation"] == "system"
        assert sub["rules"] == 1 and sub["valid"] == 1 and sub["score"] == 1.0

    def test_alerting_only_no_subscore(self):
        assert _recording_subscore(_alert_yaml()) is None


class TestProducedServiceTargets:
    def test_collects_dashboard_and_runbook_services(self):
        report = GenerationReport(project_id="p", generated_at="t")
        report.artifacts = [
            ArtifactResult(artifact_type="dashboard", service_id="a", output_path="",
                           status="generated"),
            ArtifactResult(artifact_type="runbook", service_id="b", output_path="",
                           status="generated"),
            ArtifactResult(artifact_type="runbook", service_id="c", output_path="",
                           status="error"),  # not produced
        ]
        dash, run = _produced_service_targets(report)
        assert dash == {"a"} and run == {"b"}


# ---------------------------------------------------------------------------
# Integration: 3-way coverage + aliases (REQ-OAT-051)
# ---------------------------------------------------------------------------


class TestThreeWayCoverageIntegration:
    def _meta(self):
        return {
            "project_id": "demo",
            "instrumentation_hints": {
                "api": {
                    "service_id": "api", "transport": "http",
                    "metrics": {"convention_based": [
                        {"name": "http.server.duration", "type": "histogram", "source": "otel"},
                    ]},
                },
            },
        }

    def test_quality_report_has_three_orientations_and_aliases(self, tmp_path):
        meta_path = tmp_path / "onboarding-metadata.json"
        meta_path.write_text(json.dumps(self._meta()))
        out = tmp_path / "out"
        generate_observability_artifacts(
            onboarding_metadata_path=meta_path, output_dir=out,
        )
        quality = json.loads((out / "observability-quality.json").read_text())
        svc = quality["services"]["api"]
        # Three orientation coverages present.
        for k in ("metric_coverage_human", "metric_coverage_system", "metric_coverage_bridge"):
            assert k in svc, k
        # Continuity aliases equal their orientation counterparts.
        assert svc["metric_coverage_dashboarded"] == svc["metric_coverage_human"]
        assert svc["metric_coverage_alerted"] == svc["metric_coverage_bridge"]
        agg = quality["aggregate"]
        assert "avg_metric_coverage_score" in agg  # the CLI gate field survives
        assert agg["avg_metric_coverage_dashboarded"] == agg["avg_metric_coverage_human"]
        # scored == generated invariant (REQ-OAT-050) is surfaced.
        assert agg["artifacts_scored"] == agg["artifacts_generated"]
        # CCbC single-source invariant (REQ-01 FR-7 principle): every per-artifact-
        # type score present in `services` has a matching avg_{atype}_score in the
        # aggregate — so a producer cannot silently drop the per-type rollup (the
        # merge_quality_services class, bus 93e86298). Guards the GENERATE producer.
        present_types = {
            k
            for sv in quality["services"].values()
            if isinstance(sv, dict)
            for k, v in sv.items()
            if isinstance(v, dict) and "score" in v
        }
        assert present_types, "expected at least one scored per-service artifact type"
        assert all(f"avg_{t}_score" in agg for t in present_types), [
            t for t in present_types if f"avg_{t}_score" not in agg
        ]


class TestSLOScoringFeedRegression:
    """Regression for the Harbor metric-coverage false-zero (agent-bus 01968b33).

    SLO generators pre-attach a binding-metadata quality dict
    (``bound_declared_series``) that carries NO ``"score"``. The old
    ``_score_extended_artifacts`` guard (``a.quality is not None``) let that
    metadata shadow the scorer, so SLOs were generated-but-unscored — which both
    violated the scored==generated invariant (REQ-OAT-050) and dropped SLO
    content from the metric-coverage feed (``metric_coverage_system`` pinned to
    0.0). The scorer must score a quality dict that lacks a score while
    preserving the binding metadata.
    """

    _SLO = (
        "apiVersion: openslo/v1\nkind: SLO\nmetadata:\n  name: core-availability\n"
        "spec:\n  description: bound to harbor_core_http_request_total\n"
        "  indicator:\n    spec:\n      thresholdMetric:\n"
        "        metricSource:\n          spec:\n"
        "            query: sum(rate(harbor_core_http_request_total[5m]))\n"
    )
    _CONTRACT = {"slo_definition": {
        "max_lines": 1000, "max_tokens": 100000,
        "completeness_markers": [], "red_flag": [], "fields": [],
    }}

    def _slo_artifact(self):
        bound = [{"service": "core", "kind": "availability",
                  "series": "harbor_core_http_request_total", "enabling_flag": ""}]
        return ArtifactResult(
            artifact_type="slo_definition", service_id="core",
            output_path="slos/core-declared-base-slo.yaml", status="generated",
            content=self._SLO,
            quality={"bound_declared_series": bound, "deferred_declared_kinds": []},
        )

    def test_binding_metadata_no_longer_shadows_the_scorer(self):
        art = self._slo_artifact()
        report = GenerationReport(project_id="p", generated_at="t", artifacts=[art])
        _score_extended_artifacts(report, self._CONTRACT)
        # Now structurally scored (enters artifacts_scored + the coverage feed).
        assert art.quality is not None and "score" in art.quality
        # …without clobbering the binding metadata the generator attached.
        assert art.quality["bound_declared_series"][0]["series"] == \
            "harbor_core_http_request_total"

    def test_already_scored_artifact_is_left_untouched(self):
        art = self._slo_artifact()
        art.quality = {"score": 0.5, "checks_passed": 1, "checks_total": 2}
        report = GenerationReport(project_id="p", generated_at="t", artifacts=[art])
        _score_extended_artifacts(report, self._CONTRACT)
        assert art.quality["score"] == 0.5  # not re-scored


class TestL1dNonScrapeableExclusion:
    """L1d: a DECLARED non-scrapeable service (metrics_surface none/traces_only/
    spanmetrics) has no coverable /metrics surface, so it's excluded from the
    metric_coverage DENOMINATOR (not a gap) — but a scrapeable service scoring 0
    STAYS counted (a real gap), and the exclusion is carried explicitly."""

    def _slo(self, svc, metric):
        return ArtifactResult(
            artifact_type="slo_definition", service_id=svc,
            output_path=f"slos/{svc}.yaml", status="generated",
            content=f"query: sum(rate({metric}[5m]))",
            quality={"score": 1.0, "checks_passed": 1, "checks_total": 1},
        )

    def test_declared_nonscrapeable_excluded_but_scrapeable_zero_kept(self, tmp_path):
        # keep: references the expected metric -> coverage 1.0 (scrapeable)
        # gap:  scrapeable but references the WRONG metric -> coverage 0.0 (REAL gap, stays)
        # cron: declared non-scrapeable -> coverage 0.0 but EXCLUDED from denominator
        arts = [
            self._slo("keep", "mymetric_total"),
            self._slo("gap", "other_total"),
            self._slo("cron", "other_total"),
        ]
        service_metrics = {
            "keep": {"mymetric_total"},
            "gap": {"mymetric_total"},
            "cron": {"mymetric_total"},
        }
        _write_quality_report(
            arts, tmp_path, service_metrics=service_metrics,
            nonscrapeable_service_ids={"cron"},
        )
        q = json.loads((tmp_path / "observability-quality.json").read_text())
        agg = q["aggregate"]
        # cron carried + marked excluded (never silently dropped)
        assert q["services"]["cron"]["metric_coverage_excluded"] is True
        assert q["services"]["cron"]["metric_coverage_excluded_reason"] == "non_scrapeable_surface"
        # gap is a scrapeable 0 — MUST stay counted, not excluded
        assert "metric_coverage_excluded" not in q["services"]["gap"]
        # BASE counts the FULL population (keep 1.0, gap 0.0, cron 0.0) — L1d NOT baked
        # into the base (FR-25 / FDE bus 0666fd54: base stays honest).
        assert agg["avg_metric_coverage_system"] == round(1 / 3, 4)
        # L1d is a SEPARATE grade-ready field: {keep, gap} only (cron dropped) → higher.
        assert agg["metric_coverage_excluded_count"] == 1
        assert agg["avg_metric_coverage_score_scrapeable"] > agg["avg_metric_coverage_score"]
