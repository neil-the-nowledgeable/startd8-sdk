"""v2 dashboard emitter (dynamic-dashboards M1 foundation).

Assembles the M0-verified ``dashboard.grafana.app/v2`` envelope from the model tree and serializes it
with the **exact classic serializer** (`output.persist_dashboard` → ``json.dumps(sort_keys=True,
indent=2) + "\\n"`` + atomic tmp-then-``os.replace``), so v2 byte-stability + write atomicity cannot
fork from classic (R1-S4/R2-S7). No jsonnet, no LLM, ``$0`` (OQ-2).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    V2_API_VERSION,
    V2_KIND,
    AutoGridLayout,
    CustomVariable,
    GridLayout,
    Layout,
    RowsLayout,
    TabsLayout,
    V2Panel,
    V2ValidationError,
)

_LAYOUT_TYPES = (GridLayout, RowsLayout, AutoGridLayout, TabsLayout)

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
    if not isinstance(layout, _LAYOUT_TYPES):
        raise V2ValidationError(
            "layout must be a GridLayout / RowsLayout / AutoGridLayout / TabsLayout, "
            f"got {type(layout).__name__}"
        )
    if not name:
        raise V2ValidationError(
            "v2 dashboard requires a non-empty name (metadata.name / uid)"
        )

    layout_v2 = layout.to_v2()
    _validate_element_refs(layout_v2, set(elements))
    # a conditional may reference a dashboard-level OR a section-level (M4) variable — both are declared
    declared_vars = {v.name for v in (variables or [])} | _collect_section_var_names(
        layout_v2
    )
    _validate_conditional_variables(layout_v2, declared_vars)
    _validate_section_variable_refs(layout_v2)

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


def _validate_conditional_variables(
    layout_v2: Dict[str, Any], declared_vars: set
) -> None:
    """Every ``ConditionalRenderingVariable`` in the layout must reference a declared dashboard variable
    (M3/FR-11): a conditional keyed on a non-existent variable renders as a silently-broken (always-
    hidden/shown) section. Walks the rendered layout for the condition kind."""
    referenced = _collect_conditional_vars(layout_v2)
    missing = sorted(referenced - declared_vars)
    if missing:
        raise V2ValidationError(
            f"conditional rendering references undeclared variable(s): {missing} "
            f"(declared: {sorted(declared_vars)})"
        )


def _collect_conditional_vars(node: Any) -> set:
    names: set = set()
    if isinstance(node, dict):
        if node.get("kind") == "ConditionalRenderingVariable":
            var = node.get("spec", {}).get("variable")
            if isinstance(var, str):
                names.add(var)
        for v in node.values():
            names |= _collect_conditional_vars(v)
    elif isinstance(node, list):
        for v in node:
            names |= _collect_conditional_vars(v)
    return names


def _collect_section_var_names(layout_v2: Dict[str, Any]) -> set:
    """Every ``CustomVariable`` name declared inside the layout is a *section* variable (M4) — dashboard-
    level variables live in ``spec.variables``, never in the layout tree."""
    names: set = set()
    for name, _query in _iter_section_vars(layout_v2):
        names.add(name)
    return names


def _iter_section_vars(node: Any):
    """Yield ``(name, query)`` for each section ``CustomVariable`` anywhere in the layout tree."""
    if isinstance(node, dict):
        if node.get("kind") == "CustomVariable":
            spec = node.get("spec", {})
            yield spec.get("name"), spec.get("query", "")
        for v in node.values():
            yield from _iter_section_vars(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_section_vars(v)


_VAR_REF = re.compile(r"\$\{?(\w+)\}?")


def _validate_section_variable_refs(layout_v2: Dict[str, Any]) -> None:
    """Grafana #122553 (R1-F6): a section variable cannot reference another section variable **in the
    same tab**. Enforced at build time — a same-tab cross-reference raises rather than shipping a board
    that renders broken. Each ``TabsLayoutTab`` is its own scope; nested tabs are separate scopes.
    """
    for tab in _find_tab_nodes(layout_v2):
        scope: Dict[str, str] = {}
        _collect_tab_scope_vars(tab.get("spec", {}), scope)
        names = set(scope)
        for name, query in scope.items():
            refs = set(_VAR_REF.findall(query or ""))
            bad = sorted(refs & (names - {name}))
            if bad:
                raise V2ValidationError(
                    f"section variable {name!r} references same-tab section variable(s) {bad} — "
                    "unsupported by Grafana (#122553); move it to dashboard-level or a different tab"
                )


def _find_tab_nodes(node: Any):
    """Yield every ``TabsLayoutTab`` dict anywhere in the tree (each opens its own section-var scope)."""
    if isinstance(node, dict):
        if node.get("kind") == "TabsLayoutTab":
            yield node
        for v in node.values():
            yield from _find_tab_nodes(v)
    elif isinstance(node, list):
        for v in node:
            yield from _find_tab_nodes(v)


def _collect_tab_scope_vars(node: Any, scope: Dict[str, str]) -> None:
    """Collect the section variables in one tab's scope — its own + nested rows' — but STOP at a nested
    ``TabsLayoutTab`` (a separate scope, validated on its own)."""
    if isinstance(node, dict):
        if node.get("kind") == "CustomVariable":
            spec = node.get("spec", {})
            if isinstance(spec.get("name"), str):
                scope[spec["name"]] = spec.get("query", "")
            return
        if node.get("kind") == "TabsLayoutTab":
            # a nested tab starts a fresh scope — don't pull its vars into this one
            return
        for v in node.values():
            _collect_tab_scope_vars(v, scope)
    elif isinstance(node, list):
        for v in node:
            _collect_tab_scope_vars(v, scope)


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
