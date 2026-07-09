"""Schema-aware v2 validation (dynamic-dashboards M5, FR-7).

The classic ``json_validator.validate_dashboard_json`` **discriminates on ``apiVersion``** and delegates
here for a v2 board (R2-S4). This path **positively asserts** the v2 envelope (``apiVersion``/``kind``/
``spec`` + ``spec.title``/``layout``/``elements``) and enforces the UID via ``metadata.name`` — it never
runs the classic UID/panel-count/``panels``-is-list checks (R1-S5, no v2 analog). It also rejects
out-of-scope layout/variable kinds (R1-F7 / NR-6) using the M0-verified allowlists in `constructs.py`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .constructs import (
    LAYOUT_KINDS,
    V2_API_VERSION,
    V2_KIND,
    VARIABLE_KINDS,
)


def validate_v2_dashboard(
    data: Dict[str, Any], expected_uid: Optional[str] = None
) -> List[str]:
    """Return a list of v2 validation errors (empty ⇒ valid). Pure; no I/O."""
    errors: List[str] = []

    if data.get("apiVersion") != V2_API_VERSION:
        errors.append(
            f"v2 board must have apiVersion '{V2_API_VERSION}', got {data.get('apiVersion')!r}"
        )
    if data.get("kind") != V2_KIND:
        errors.append(f"v2 board must have kind '{V2_KIND}', got {data.get('kind')!r}")

    spec = data.get("spec")
    if not isinstance(spec, dict):
        errors.append("v2 board must have an object 'spec'")
        return errors  # nothing more to check without a spec

    if not spec.get("title"):
        errors.append("v2 spec must have a non-empty 'title'")

    elements = spec.get("elements")
    if not isinstance(elements, dict):
        errors.append(
            f"v2 spec.elements must be an object (id→element), got {type(elements).__name__}"
        )

    layout = spec.get("layout")
    if not isinstance(layout, dict) or "kind" not in layout:
        errors.append("v2 spec.layout must be an object with a 'kind'")
    elif layout.get("kind") not in LAYOUT_KINDS:
        errors.append(
            f"v2 spec.layout.kind {layout.get('kind')!r} is not a supported layout "
            f"(one of {sorted(LAYOUT_KINDS)})"
        )

    # UID is carried by metadata.name (NOT a top-level 'uid' — that's classic, R1-S5)
    if expected_uid is not None:
        actual = (data.get("metadata") or {}).get("name")
        if actual is not None and actual != expected_uid:
            errors.append(
                f"UID mismatch: expected '{expected_uid}', got metadata.name '{actual}'"
            )

    # NR-6 (R1-F7): reject out-of-scope layout / variable kinds anywhere in the board.
    errors.extend(_out_of_scope_kind_errors(data))
    return errors


def _out_of_scope_kind_errors(node: Any) -> List[str]:
    """Any ``*Layout`` kind must be supported; any ``*Variable`` kind (excluding the conditional-render
    variable, which is a condition not a dashboard variable) must be a supported variable kind.
    """
    errors: List[str] = []
    _walk_kinds(node, errors)
    return errors


def _walk_kinds(node: Any, errors: List[str]) -> None:
    if isinstance(node, dict):
        kind = node.get("kind")
        if isinstance(kind, str):
            if kind.endswith("Layout") and kind not in LAYOUT_KINDS:
                errors.append(f"unsupported v2 layout kind {kind!r} (NR-6)")
            elif (
                kind.endswith("Variable")
                and kind != "ConditionalRenderingVariable"
                and kind not in VARIABLE_KINDS
            ):
                errors.append(f"unsupported v2 variable kind {kind!r} (NR-6)")
        for v in node.values():
            _walk_kinds(v, errors)
    elif isinstance(node, list):
        for v in node:
            _walk_kinds(v, errors)
