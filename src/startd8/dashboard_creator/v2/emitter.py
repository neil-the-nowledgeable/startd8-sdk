"""v2 dashboard emitter (dynamic-dashboards M1 foundation).

Assembles the M0-verified ``dashboard.grafana.app/v2`` envelope from the model tree and serializes it
with the **exact classic serializer** (`output.persist_dashboard` → ``json.dumps(sort_keys=True,
indent=2) + "\\n"`` + atomic tmp-then-``os.replace``), so v2 byte-stability + write atomicity cannot
fork from classic (R1-S4/R2-S7). No jsonnet, no LLM, ``$0`` (OQ-2).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    V2_API_VERSION,
    V2_KIND,
    CustomVariable,
    GridLayout,
    Layout,
    RowsLayout,
    V2Panel,
    V2ValidationError,
)

_DEFAULT_TIME = {
    "from": "now-6h",
    "to": "now",
    "autoRefresh": "",
    "autoRefreshIntervals": [],
    "hideTimepicker": False,
    "timezone": "browser",
}


def emit_v2_dashboard(
    *,
    name: str,
    title: str,
    layout: Layout,
    elements: Dict[str, V2Panel],
    variables: Optional[List[CustomVariable]] = None,
    description: str = "",
    tags: Optional[List[str]] = None,
    schema: str = "v2",
    time_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the v2 ``{apiVersion, kind, metadata, spec}`` envelope (a plain, deterministic dict).

    **Single, explicit opt-in trigger (R1-F2):** ``schema`` MUST be ``"v2"`` — any other value raises,
    so a classic caller can never silently reach the v2 path. ``elements`` is the id→``V2Panel`` map;
    every ``GridLayoutItem.element`` in ``layout`` MUST reference a key in it (validated). A layout-only
    board (zero elements) is legal (R1-S9); the classic ``panels min_length=1`` invariant does not apply.
    """
    if schema != "v2":
        raise V2ValidationError(
            f"emit_v2_dashboard requires schema='v2' (the single opt-in trigger); got {schema!r}"
        )
    if not isinstance(layout, (GridLayout, RowsLayout)):
        raise V2ValidationError(
            f"layout must be a GridLayout or RowsLayout, got {type(layout).__name__}"
        )
    if not name:
        raise V2ValidationError(
            "v2 dashboard requires a non-empty name (metadata.name / uid)"
        )

    layout_v2 = layout.to_v2()
    _validate_element_refs(layout_v2, set(elements))

    spec: Dict[str, Any] = {
        "title": title,
        "description": description,
        "tags": list(tags or []),
        "editable": True,
        "preload": False,
        "liveNow": False,
        "cursorSync": "Off",
        "timeSettings": time_settings or dict(_DEFAULT_TIME),
        "links": [],
        "annotations": [],
        "variables": [v.to_v2() for v in (variables or [])],
        "elements": {key: panel.to_v2() for key, panel in elements.items()},
        "layout": layout_v2,
    }
    return {
        "apiVersion": V2_API_VERSION,
        "kind": V2_KIND,
        "metadata": {"name": name},
        "spec": spec,
    }


def _validate_element_refs(layout_v2: Dict[str, Any], element_keys: set) -> None:
    """Every ``ElementReference`` in the layout must resolve to a declared element (fail loud, not a
    broken board at render). Walks GridLayout items and RowsLayout rows."""
    referenced = _collect_element_refs(layout_v2)
    missing = sorted(referenced - element_keys)
    if missing:
        raise V2ValidationError(
            f"layout references undeclared element(s): {missing} (declared: {sorted(element_keys)})"
        )


def _collect_element_refs(node: Any) -> set:
    refs: set = set()
    if isinstance(node, dict):
        if node.get("kind") == "ElementReference" and isinstance(node.get("name"), str):
            refs.add(node["name"])
        for v in node.values():
            refs |= _collect_element_refs(v)
    elif isinstance(node, list):
        for v in node:
            refs |= _collect_element_refs(v)
    return refs


def v2_json(dashboard: Dict[str, Any]) -> str:
    """The canonical serialized bytes — the SAME serializer classic uses (`output.py:44`), so a v2
    golden and a classic golden are produced identically (FR-5, R1-S4)."""
    return json.dumps(dashboard, sort_keys=True, indent=2) + "\n"


def persist_v2_dashboard(
    dashboard: Dict[str, Any],
    *,
    output_dir: Optional[Path] = None,
):
    """Write the v2 board via the classic ``persist_dashboard`` — inherits the atomic tmp-then-replace
    write + the exact serializer (R2-S7). Returns the classic ``PersistenceResult``."""
    from ..output import persist_dashboard

    name = dashboard.get("metadata", {}).get("name")
    if not name:
        raise V2ValidationError("cannot persist a v2 dashboard without metadata.name")
    return persist_dashboard(dashboard, uid=name, output_dir=output_dir)
