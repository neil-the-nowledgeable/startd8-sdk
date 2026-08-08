# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Infra dashboard rendering (container-o11y Step 2c, FR-8).

Renders the cross-linked cluster/node/pod/container/control-plane health dashboards from the
infra SLI intent. **Backend-neutral** — Grafana JSON is identical whether the cluster runs
prometheus-operator or Alloy — so this is a standalone function, NOT a ``BackendAdapter`` method
(making it an adapter method would duplicate identical code in both backends; Guard G).

Panels read each SLI's **recorded series** (the ``record`` the ruler evaluates), so every panel
is closure-consistent with what the rules actually produce — we never render a panel that queries
a mixin recording rule we don't emit (that would be a silent no-data panel, the very thing the
FR-14 closure invariant guards against). Dashboards are cross-linked both directions (FR-8) and
carry a no-data sentinel (R3-S7).
"""

from __future__ import annotations

from typing import Any, Dict, List

# top-down ↔ bottom-up ordering for the FR-8 drill-down/roll-up links
_LEVEL_ORDER = ["cluster", "node", "pod", "container", "control_plane", "job"]
_SCHEMA_VERSION = 39


def _uid(level: str) -> str:
    return f"cc-infra-{level.replace('_', '-')}"


def _panel(index: int, rule: Dict[str, Any], datasource: str) -> Dict[str, Any]:
    """One timeseries panel reading a recorded SLI series (2 panels per row)."""
    record = rule["record"]
    unit = rule.get("labels", {}).get("unit", "")
    grafana_unit = {"ratio": "percentunit", "bool": "bool", "seconds": "s", "count": "short"}.get(unit, "")
    return {
        "id": index + 1,
        "title": record.replace("_", " "),
        "type": "timeseries",
        "datasource": {"type": "prometheus", "uid": datasource},
        "gridPos": {"h": 8, "w": 12, "x": (index % 2) * 12, "y": (index // 2) * 8},
        "fieldConfig": {
            "defaults": {
                "unit": grafana_unit,
                # R3-S7 no-data sentinel — an empty series reads as an explicit state, not a blank
                "noValue": "No data — series not emitted (check scrape keep-list / collector).",
            },
            "overrides": [],
        },
        "targets": [
            {
                "refId": "A",
                "datasource": {"type": "prometheus", "uid": datasource},
                # read the RECORDED series the ruler produces (closure-consistent)
                "expr": record,
                "legendFormat": rule.get("labels", {}).get("level", ""),
            }
        ],
    }


def _cross_links(this_level: str, present_levels: List[str]) -> List[Dict[str, Any]]:
    """FR-8: a link to every other level's dashboard (drill-down + roll-up, both directions)."""
    return [
        {
            "title": lvl.replace("_", " ").title(),
            "type": "link",
            "url": f"/d/{_uid(lvl)}",
            "icon": "external link",
            "tooltip": f"Go to the {lvl} health dashboard",
        }
        for lvl in _LEVEL_ORDER
        if lvl in present_levels and lvl != this_level
    ]


def _dashboard(level: str, rules: List[Dict[str, Any]], present_levels: List[str], datasource: str) -> Dict[str, Any]:
    return {
        "uid": _uid(level),
        "title": f"Infra — {level.replace('_', ' ').title()} Health",
        "tags": ["cc-infra", level],
        "schemaVersion": _SCHEMA_VERSION,
        "editable": False,
        "time": {"from": "now-6h", "to": "now"},
        "links": _cross_links(level, present_levels),
        "templating": {
            "list": [
                {
                    "name": "datasource",
                    "type": "datasource",
                    "query": "prometheus",
                    "current": {"text": datasource, "value": datasource},
                }
            ]
        },
        "panels": [_panel(i, r, datasource) for i, r in enumerate(rules)],
    }


def render_infra_dashboards(
    sli_rules: List[Dict[str, Any]], *, datasource: str = "mimir"
) -> Dict[str, Dict[str, Any]]:
    """Render one cross-linked Grafana dashboard per SLI level.

    ``sli_rules`` is the infra-intent bundle's ``sli_rules`` (each ``{record, expr, labels}`` with
    ``labels.level``). Returns ``{level: grafana_dashboard_json}``.
    """
    by_level: Dict[str, List[Dict[str, Any]]] = {}
    for rule in sli_rules:
        level = rule.get("labels", {}).get("level", "cluster")
        by_level.setdefault(level, []).append(rule)

    present = [lvl for lvl in _LEVEL_ORDER if lvl in by_level]
    present += [lvl for lvl in by_level if lvl not in _LEVEL_ORDER]  # any unexpected levels last
    return {level: _dashboard(level, by_level[level], present, datasource) for level in present}
