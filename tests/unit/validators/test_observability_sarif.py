"""Route observability validation findings through the SARIF sink (rung 2 — the o11y bridge).

Module: src/startd8/validators/observability_sarif.py — proves the parent→issue file-stamp pattern
(the issue dict has no file; file_path lives on the parent *ValidationResult).
"""

from __future__ import annotations

from startd8.coverage_map.findings_sarif import SARIF_SCHEMA_URI
from startd8.validators.observability_artifact_validators import (
    DashboardValidationResult,
    SloValidationResult,
    _issue,
)
from startd8.validators.observability_sarif import render_observability_sarif


def _run0(doc):
    return doc["runs"][0]


def test_parent_file_is_stamped_onto_each_issue():
    r = DashboardValidationResult(
        file_path="dashboards/api.yaml",
        issues=[_issue("OBS-100d", "error", "No panels defined")],
    )
    doc = render_observability_sarif([r], corpus=".")
    assert doc["$schema"] == SARIF_SCHEMA_URI and doc["version"] == "2.1.0"
    run = _run0(doc)
    assert run["tool"]["driver"]["name"] == "startd8-obs"
    res = run["results"][0]
    assert res["ruleId"] == "OBS-100d"
    assert res["level"] == "error"
    loc = res["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "dashboards/api.yaml"   # from the PARENT, not the issue
    assert "region" not in loc                                       # issues carry no line


def test_issues_from_multiple_results_keep_their_own_parent_file():
    dash = DashboardValidationResult(file_path="d.yaml", issues=[_issue("OBS-100d", "error", "x")])
    slo = SloValidationResult(file_path="s.yaml", issues=[_issue("OBS-102j", "error", "y")])
    uris = {
        r["ruleId"]: r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        for r in _run0(render_observability_sarif([dash, slo]))["results"]
    }
    assert uris == {"OBS-100d": "d.yaml", "OBS-102j": "s.yaml"}


def test_info_issue_maps_to_note_level():
    r = DashboardValidationResult(file_path="d.yaml", issues=[_issue("OBS-100j", "info", "no vars")])
    assert _run0(render_observability_sarif([r]))["results"][0]["level"] == "note"


def test_issue_whose_parent_has_no_file_is_skipped_and_counted():
    keep = DashboardValidationResult(file_path="d.yaml", issues=[_issue("OBS-100d", "error", "x")])
    orphan = DashboardValidationResult(file_path="", issues=[_issue("OBS-100a", "error", "no file")])
    run = _run0(render_observability_sarif([keep, orphan]))
    assert len(run["results"]) == 1
    assert run["invocations"][0]["properties"]["skipped"] == 1
