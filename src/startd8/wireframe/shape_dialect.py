"""Shape dialect + poka-yoke for app-cascade bleed on Node plans.

Metabolizes ATM class ``app-bound wireframe summary/chrome on non-app Node consumers``
(generality + cruft + lacuna, 2026-08-14): a plan that carries ``nodes`` must not also
zero-pad the app cascade keys (entities / crud_routes / pages / views / ai_passes).
"""

from __future__ import annotations

from typing import Any, List, Mapping

# Canonical app-cascade shape keys (wireframe `$0` landscape). Present together ⇒ app dialect.
APP_CASCADE_SHAPE_KEYS = ("entities", "crud_routes", "pages", "views", "ai_passes")

# App-build *apex* prose (masthead sub-headline + Why/Do whybox) authored for the app-scaffold
# domain (WIREFRAME_META + descriptive.yaml summary narration). A profiled non-app consumer
# (requirements / capability navigator) must not carry these in its rendered HTML — the second
# face of the metabolized ATM class (``app-bound wireframe summary/chrome on non-app Node
# consumers``), beyond the shape/footer already guarded. Discriminating substrings only —
# ``Wireframe Preview`` is deliberately excluded (it is the template's inert JS fallback literal,
# present in every render including a legitimate app title, so not a bleed signal).
APP_APEX_BLEED_TOKENS = (
    "entity count IS the contract",
    "DATA MODEL bookend",
    "deterministic $0 generation your manifests",
    "core-vs-derived",
)


def find_app_apex_bleed(html_text: str) -> List[str]:
    """Return the app-build apex tokens present in ``html_text`` (empty ⇒ clean).

    A profiled navigator render should return ``[]``; a non-empty list is the app summary
    narration leaking into a Node consumer's masthead — the guarded regression.
    """
    return [tok for tok in APP_APEX_BLEED_TOKENS if tok in html_text]


def is_app_cascade_shape(shape: Mapping[str, Any]) -> bool:
    """True when ``shape`` speaks the app cascade dialect.

    Full five-key dicts and partial fixtures that still use cascade keys (entities/
    pages/…) count as app dialect. A shape that only has ``nodes``/``sections`` does not.
    """
    if any(k in shape for k in APP_CASCADE_SHAPE_KEYS):
        return True
    return False


def reject_app_bound_node_shape(shape: Mapping[str, Any]) -> None:
    """Fail-loud: Node-domain plans must not carry the app cascade keyset.

    A plan with ``nodes > 0`` that also includes entities/crud_routes/… is the
    metabolized class (zero-padded app chrome on a requirements/capability consumer).
    """
    nodes = int(shape.get("nodes") or 0)
    if nodes <= 0:
        return
    if any(k in shape for k in APP_CASCADE_SHAPE_KEYS):
        raise ValueError(
            "app-bound cascade shape on a node plan "
            f"(nodes={nodes}, keys={sorted(shape)}); "
            "emit node-domain shape only (nodes/sections), not zero-padded "
            "entities/crud_routes/pages/views/ai_passes"
        )


def format_shape_line(shape: Mapping[str, Any]) -> str:
    """Architect glance Shape cell — dialect follows the keys present."""
    if is_app_cascade_shape(shape):
        return (
            f"Entities: {shape.get('entities', 0)} | CRUD routes: {shape.get('crud_routes', 0)} | "
            f"Pages: {shape.get('pages', 0)} | Views: {shape.get('views', 0)} | "
            f"AI passes: {shape.get('ai_passes', 0)}"
        )
    parts = []
    if "nodes" in shape:
        parts.append(f"Nodes: {shape.get('nodes', 0)}")
    if "sections" in shape:
        parts.append(f"Sections: {shape.get('sections', 0)}")
    for k, v in sorted(shape.items()):
        if k in ("nodes", "sections"):
            continue
        if isinstance(v, int):
            parts.append(f"{k.replace('_', ' ').title()}: {v}")
    return " | ".join(parts) if parts else "Nodes: 0"


def format_status_counts_line(counts: Mapping[str, Any]) -> str:
    """Status band: prefer actual keys (grounded/spec/…) over hard-coded app enum."""
    app_order = ("planned", "defaults", "placeholder", "not_defined", "invalid")
    if any(k in counts for k in app_order) and not any(
        k in counts for k in ("grounded", "spec", "unknown", "awaiting", "excluded")
    ):
        return (
            f"{counts.get('planned', 0)} planned / {counts.get('defaults', 0)} defaults / "
            f"{counts.get('placeholder', 0)} placeholder / "
            f"{counts.get('not_defined', 0)} not defined / "
            f"{counts.get('invalid', 0)} invalid"
        )
    parts = [f"{v} {k}" for k, v in sorted(counts.items()) if isinstance(v, int)]
    return " / ".join(parts) if parts else "0 statuses"
