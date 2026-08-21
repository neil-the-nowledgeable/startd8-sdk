# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

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

from ..dashboard_creator.neutral import (
    Dashboard,
    DatasourceRef,
    Panel,
    Placement,
    Query,
    QueryLanguage,
    Section,
    Threshold as NeutralThreshold,
    VisualizationKind,
)
from ..dashboard_creator.v2 import lower_dashboard_to_grafana_v2
from .dashboard_renderer import _title
from .spec import ObservabilitySpec, Signal

_DATASOURCE_VAR = "$datasource"


def _timeseries_panel(
    pid: int, sig: Signal, datasource_name: str = _DATASOURCE_VAR
) -> Panel:
    """A portable time-series panel for one signal — metric threshold or raw expression."""
    expr = sig.name if sig.threshold is not None else (sig.expr or sig.name)
    thresholds: List[NeutralThreshold] = []
    unit = None
    if sig.threshold is not None:
        color = "red" if sig.threshold.severity == "critical" else "orange"
        thresholds = [
            NeutralThreshold(color="green", value=None),
            NeutralThreshold(color=color, value=float(sig.threshold.value)),
        ]
        unit = sig.threshold.unit or None
    return Panel(
        id=pid,
        title=_title(sig.name),
        visualization=VisualizationKind.TIME_SERIES,
        unit=unit,
        thresholds=thresholds,
        queries=[
            Query(
                expression=expr,
                language=QueryLanguage.PROMQL,
                datasource=DatasourceRef(name=datasource_name),
            )
        ],
    )


def build_domain_dashboard_neutral(
    spec: ObservabilitySpec,
    project_id: str = "domain",
    *,
    explicit_grid: bool = False,
    datasource_name: str = _DATASOURCE_VAR,
) -> Dashboard:
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

    panels = {}
    sections: List[Section] = []
    pid = 0
    for title, sigs in (("Critical", critical), ("Warning", warning), ("Other", other)):
        if not sigs:
            continue
        placements: List[Placement] = []
        for panel_index, sig in enumerate(sigs):
            pid += 1
            key = f"sec{len(sections)}-p{panel_index}"
            panels[key] = _timeseries_panel(pid, sig, datasource_name)
            # Existing Grafana callers retain the pre-extraction y=0 bytes. New portable artifacts
            # request an explicit non-overlapping grid because Perses treats x/y as literal placement.
            placements.append(
                Placement(panel=key, y=panel_index * 6 if explicit_grid else 0, height=6)
            )
        sections.append(Section(title=title, placements=placements))
    return Dashboard(
        name=f"obs-domain-{project_id}-v2",
        title=f"{project_id} — domain observability (dynamic)",
        panels=panels,
        sections=sections,
        tags=["observability", "domain", "dynamic"],
        description=(
            "v2 dynamic domain observability dashboard — the same observability.yaml signals as the "
            "classic board, projected through the sectioned v2 builder (severity sections)."
        ),
    )


def render_domain_dashboard_v2(
    spec: ObservabilitySpec, project_id: str = "domain"
) -> Dict[str, Any]:
    """Render the ``ObservabilitySpec`` as a **v2 dynamic** domain dashboard (a `RowsLayout`, one row per
    severity). Returns the v2 envelope dict (feed to ``v2_json`` / ``provision_v2``). An empty spec yields
    a valid empty board. Additive — the classic renderer is unaffected."""
    return lower_dashboard_to_grafana_v2(build_domain_dashboard_neutral(spec, project_id))
