"""FR-E22 — cloud-grant alert rules: valid structure, exprs bound to the real FR-E4 metric + real
GrantDeny reasons, and the committed artifact never drifts from the module source of truth."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience.cloud_grant import GrantDeny  # noqa: E402
from startd8.kickoff_experience.cloud_grant_alerts import (  # noqa: E402
    CLOUD_GRANT_ALERT_RULES,
    render_rules_yaml,
)

_ARTIFACT = Path(__file__).resolve().parents[3] / "docs/design/kickoff/cloud-grant-alerts.rules.yaml"


def _rules():
    return CLOUD_GRANT_ALERT_RULES["groups"][0]["rules"]


def test_rules_are_well_formed():
    rules = _rules()
    assert len(rules) >= 5
    names = [r["alert"] for r in rules]
    assert len(names) == len(set(names))                      # unique alert names
    for r in rules:
        assert r["expr"] and r["for"]
        assert r["labels"]["severity"] in ("info", "warning", "critical")
        assert r["labels"]["component"] == "cloud-grant"
        assert r["annotations"]["summary"] and r["annotations"]["description"]


def test_exprs_bind_to_the_shipped_e4_metric():
    for r in _rules():
        assert "startd8_cloud_grant_denied_total" in r["expr"]   # the FR-E4 counter (self-contained)


def test_reason_labels_are_real_grant_deny_values():
    import re

    valid = {d.value for d in GrantDeny}
    for r in _rules():
        for reason in re.findall(r'reason="([^"]+)"', r["expr"]):
            assert reason in valid, f"{reason} is not a GrantDeny value"


def test_security_alerts_are_critical():
    by_name = {r["alert"]: r for r in _rules()}
    for name in ("CloudGrantOriginProbing", "CloudGrantApiKeyProbing", "CloudGrantStoreUnavailable"):
        assert by_name[name]["labels"]["severity"] == "critical"


def test_committed_artifact_matches_module():
    assert _ARTIFACT.is_file(), "run render_rules_yaml() to (re)generate the committed artifact"
    assert _ARTIFACT.read_text(encoding="utf-8") == render_rules_yaml(), \
        "cloud-grant-alerts.rules.yaml drifted from the module — re-render it"


def test_rendered_yaml_parses_as_a_rule_group():
    doc = yaml.safe_load(render_rules_yaml())
    assert doc["groups"][0]["name"] == "cloud-grant.alerts"
    assert len(doc["groups"][0]["rules"]) == len(_rules())
