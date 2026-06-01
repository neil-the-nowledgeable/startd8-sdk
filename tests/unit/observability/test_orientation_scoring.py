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
