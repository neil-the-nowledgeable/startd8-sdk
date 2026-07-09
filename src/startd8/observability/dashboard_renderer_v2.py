# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Domain dashboard renderer — **v2 dynamic** variant (dynamic-dashboards M7 adoption).

The follow-on the dynamic-dashboards plan named: a real generator emitting through the reusable
``build_sectioned_v2`` seam. This is a **standalone, additive adapter** — the classic
``dashboard_renderer.render_domain_dashboard`` is **byte-untouched**; this module never imports into its
render path. It projects the same ``ObservabilitySpec`` signals onto a v2 sectioned board (one row per
**severity** — Critical / Warning / Other — each with a timeseries panel per signal), so the same
``observability.yaml`` can drive a Grafana ≥13.1 dynamic board.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..dashboard_creator.v2 import Section, V2Panel, build_sectioned_v2
from .dashboard_renderer import _title
from .spec import ObservabilitySpec, Signal

_DATASOURCE_VAR = "$datasource"


def _timeseries_panel(pid: int, sig: Signal) -> V2Panel:
    """A v2 ``Panel`` (timeseries) for one signal — the metric (thresholded) or the raw expr."""
    expr = sig.name if sig.threshold is not None else (sig.expr or sig.name)
    field_defaults: Dict[str, Any] = {}
    if sig.threshold is not None:
        color = "red" if sig.threshold.severity == "critical" else "orange"
        field_defaults["thresholds"] = {
            "mode": "absolute",
            "steps": [
                {"color": "green", "value": None},
                {"color": color, "value": float(sig.threshold.value)},
            ],
        }
        if sig.threshold.unit:
            field_defaults["unit"] = sig.threshold.unit
    viz_config = {
        "kind": "timeseries",
        "spec": {
            "options": {},
            "fieldConfig": {"defaults": field_defaults, "overrides": []},
        },
    }
    data = {
        "kind": "QueryGroup",
        "spec": {
            "queries": [
                {
                    "kind": "PanelQuery",
                    "spec": {
                        "refId": "A",
                        "hidden": False,
                        "query": {
                            "kind": "DataQuery",
                            "group": "prometheus",
                            "version": "v0",
                            "datasource": {"name": _DATASOURCE_VAR},
                            "spec": {"expr": expr, "refId": "A"},
                        },
                    },
                }
            ],
            "transformations": [],
            "queryOptions": {},
        },
    }
    return V2Panel(id=pid, title=_title(sig.name), viz_config=viz_config, data=data)


def _severity_sections(spec: ObservabilitySpec) -> List[Section]:
    critical = [
        s
        for s in spec.signals
        if s.threshold is not None and s.threshold.severity == "critical"
    ]
    warning = [
        s
        for s in spec.signals
        if s.threshold is not None and s.threshold.severity != "critical"
    ]
    other = [s for s in spec.signals if s.threshold is None]

    sections: List[Section] = []
    pid = 0
    for title, sigs in (("Critical", critical), ("Warning", warning), ("Other", other)):
        if not sigs:
            continue
        panels: List[V2Panel] = []
        for sig in sigs:
            pid += 1
            panels.append(_timeseries_panel(pid, sig))
        sections.append(Section(title=title, panels=list(panels)))
    return sections


def render_domain_dashboard_v2(
    spec: ObservabilitySpec, project_id: str = "domain"
) -> Dict[str, Any]:
    """Render the ``ObservabilitySpec`` as a **v2 dynamic** domain dashboard (a `RowsLayout`, one row per
    severity). Returns the v2 envelope dict (feed to ``v2_json`` / ``provision_v2``). An empty spec yields
    a valid empty board. Additive — the classic renderer is unaffected."""
    return build_sectioned_v2(
        name=f"obs-domain-{project_id}-v2",
        title=f"{project_id} — domain observability (dynamic)",
        layout_kind="rows",
        sections=_severity_sections(spec),
        dashboard_variables=[],
        tags=["observability", "domain", "dynamic"],
        description=(
            "v2 dynamic domain observability dashboard — the same observability.yaml signals as the "
            "classic board, projected through the sectioned v2 builder (severity sections)."
        ),
    )
