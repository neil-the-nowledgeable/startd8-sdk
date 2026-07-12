"""FR-E22 — Prometheus alert rules for the cloud authorization grant.

Every rule fires on the **FR-E4 `startd8_cloud_grant_denied_total{reason}`** counter (Mimir mangles the
dotted OTel name to underscores + `_total`) — so this is fully self-contained on shipped metrics, no new
emission. The `reason` label is what discriminates a security event (origin/api-key probing) from a
benign lifecycle one (expired/exhausted in use) from an infra fault (store unavailable).

This module is the **source of truth**; `render_rules_yaml()` emits the committed
`cloud-grant-alerts.rules.yaml`, and the test asserts the two never drift.
"""
from __future__ import annotations

from typing import Any, Dict

_DENIED = "startd8_cloud_grant_denied_total"
_SOURCE = "startd8.cloud_grant (FR-E4 metrics)"


def _rule(name: str, expr: str, *, severity: str, for_: str, summary: str, description: str) -> Dict[str, Any]:
    return {
        "alert": name,
        "expr": expr,
        "for": for_,
        "labels": {"severity": severity, "component": "cloud-grant"},
        "annotations": {"summary": summary, "description": description, "source": _SOURCE},
    }


# The rule group (source of truth). Order = most-security-relevant first.
CLOUD_GRANT_ALERT_RULES: Dict[str, Any] = {
    "groups": [
        {
            "name": "cloud-grant.alerts",
            "rules": [
                _rule(
                    "CloudGrantOriginProbing",
                    f'sum(rate({_DENIED}{{reason="origin_rejected"}}[5m])) > 0.1',
                    severity="critical", for_="5m",
                    summary="Cloud-grant requests from an unconfigured Origin",
                    description="Sustained origin_rejected denials — a leaked or guessed /kickoff/enter "
                    "endpoint is being probed from an Origin not in the configured allow-list. Investigate "
                    "the source; rotate the link/grant if a token leaked.",
                ),
                _rule(
                    "CloudGrantApiKeyProbing",
                    f'sum(rate({_DENIED}{{reason="api_key_invalid"}}[5m])) > 0.1',
                    severity="critical", for_="5m",
                    summary="Cloud-grant requests with an invalid API key",
                    description="Sustained api_key_invalid denials — credential guessing against the "
                    "programmatic grant path. Confirm the consumer key hasn't leaked; consider rotating it.",
                ),
                _rule(
                    "CloudGrantStoreUnavailable",
                    f'sum(rate({_DENIED}{{reason="store_unavailable"}}[5m])) > 0',
                    severity="critical", for_="5m",
                    summary="Cloud-grant store cannot be read/written",
                    description="store_unavailable denials mean the grant store (file/SQLite) is failing — "
                    "an INFRA fault, not the caller. Grants fail closed (deny), so the door is down. Check "
                    "the store path, permissions, and disk.",
                ),
                _rule(
                    "CloudGrantDenialSpike",
                    f"sum(rate({_DENIED}[5m])) > 0.2",
                    severity="warning", for_="10m",
                    summary="Elevated cloud-grant denial rate",
                    description="Aggregate denial rate is elevated across all reasons — misconfiguration or "
                    "abuse. Break down by `reason` (see the Cloud Grant Usage dashboard) to classify.",
                ),
                _rule(
                    "CloudGrantExpiredInUse",
                    f'sum(rate({_DENIED}{{reason="expired"}}[5m])) > 0',
                    severity="warning", for_="5m",
                    summary="A client is hitting an expired cloud grant (reissue)",
                    description="expired denials while the deployment is in use = a session/link outlived its "
                    "grant (the near-expiry signal). Issue a fresh grant/link (`cloud-grant issue`).",
                ),
                _rule(
                    "CloudGrantExhaustedInUse",
                    f'sum(rate({_DENIED}{{reason="exhausted"}}[5m])) > 0',
                    severity="info", for_="5m",
                    summary="A client is hitting an exhausted cloud grant (reissue)",
                    description="exhausted denials = the grant's uses are spent while clients still arrive. "
                    "Issue a fresh grant, or raise `--uses` when the workload warrants it.",
                ),
            ],
        }
    ]
}


def render_rules_yaml() -> str:
    """Render the committed Prometheus rules artifact (standard rule-group YAML — NOT Grafana JSON)."""
    import yaml

    header = (
        "# FR-E22 — Cloud Authorization Grant alert rules.\n"
        "# GENERATED from startd8.kickoff_experience.cloud_grant_alerts — do not hand-edit; edit the\n"
        "# module + re-render. Fires on the FR-E4 startd8_cloud_grant_denied_total{reason} counter.\n"
        "# Provision into Prometheus/Mimir alerting (loaded like any rule file).\n\n"
    )
    return header + yaml.dump(CLOUD_GRANT_ALERT_RULES, default_flow_style=False, sort_keys=False)
