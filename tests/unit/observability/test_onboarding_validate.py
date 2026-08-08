"""$0 onboarding-metadata preflight (CEP CH-4) — validation logic + CLI."""

import json

from typer.testing import CliRunner

from startd8.observability.onboarding_validate import validate_onboarding_metadata
from startd8.observability.cli import observability_app

runner = CliRunner()


def _w(tmp_path, doc):
    p = tmp_path / "onboarding-metadata.json"
    p.write_text(json.dumps(doc))
    return p


def test_clean_metadata_has_no_findings(tmp_path):
    doc = {
        "project_id": "p", "schema_version": "1.0",
        "instrumentation_hints": {
            "web": {"service_id": "web", "service_name": "web", "kind": "http_server",
                    "transport": "http", "metrics_surface": "prometheus_exporter",
                    "metrics": {"convention_based": []}},
        },
    }
    r = validate_onboarding_metadata(_w(tmp_path, doc))
    assert r.ok and not r.findings


def test_typo_key_gets_did_you_mean(tmp_path):
    doc = {"project_id": "p", "instrumentation_hints": {
        "web": {"service_id": "web", "kind": "http_server", "transport": "http",
                "servce_name": "web"}}}  # typo: servce_name
    r = validate_onboarding_metadata(_w(tmp_path, doc))
    w = [f for f in r.warnings if "servce_name" in f.message]
    assert w and "did you mean 'service_name'" in w[0].message
    assert not r.ok


def test_missing_transport_and_kind_is_flagged_dropped(tmp_path):
    doc = {"project_id": "p", "instrumentation_hints": {"web": {"service_id": "web"}}}
    r = validate_onboarding_metadata(_w(tmp_path, doc))
    assert any("DROPPED" in f.message for f in r.warnings)


def test_malformed_metrics_and_datasources_flagged(tmp_path):
    doc = {"project_id": "p", "instrumentation_hints": {
        "web": {"service_id": "web", "kind": "http_server", "transport": "http",
                "datasources": ["not-a-dict"], "metrics": "not-a-dict"}}}
    r = validate_onboarding_metadata(_w(tmp_path, doc))
    msgs = " ".join(f.message for f in r.warnings)
    assert "datasources" in msgs and "metrics" in msgs


def test_non_dict_hint_is_error(tmp_path):
    doc = {"project_id": "p", "instrumentation_hints": {"web": "nope"}}
    r = validate_onboarding_metadata(_w(tmp_path, doc))
    assert any(f.level == "error" and "web" in f.where for f in r.findings)


def test_bad_json_is_error_not_raise(tmp_path):
    p = tmp_path / "onboarding-metadata.json"
    p.write_text('{"instrumentation_hints": {')  # invalid
    r = validate_onboarding_metadata(p)  # must not raise
    assert r.errors and "not valid JSON" in r.errors[0].message


def test_missing_file_is_error(tmp_path):
    r = validate_onboarding_metadata(tmp_path / "nope.json")
    assert r.errors and not r.ok


# --- CLI ---

def test_cli_clean_exits_0(tmp_path):
    doc = {"project_id": "p", "instrumentation_hints": {
        "web": {"service_id": "web", "service_name": "web", "kind": "http_server",
                "transport": "http", "metrics_surface": "prometheus_exporter"}}}
    res = runner.invoke(observability_app, ["validate-onboarding", "-m", str(_w(tmp_path, doc))])
    assert res.exit_code == 0
    assert "no issues" in res.stdout


def test_cli_typo_exits_1_and_json(tmp_path):
    doc = {"project_id": "p", "instrumentation_hints": {
        "web": {"service_id": "web", "kind": "http_server", "transport": "http", "kindd": "x"}}}
    res = runner.invoke(observability_app, ["validate-onboarding", "-m", str(_w(tmp_path, doc)), "--json"])
    assert res.exit_code == 1
    payload = json.loads(res.stdout)
    assert payload["ok"] is False and payload["counts"]["warning"] >= 1
