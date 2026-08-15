"""REQ-04 — the shared audience × fluency lens transform (the second RenderProfile moment).

The audience/fluency **data-layer** lenses were welded into ``wireframe_view/compose.py``: jargon
filtering, label humanisation, the ``need_items`` gap floor, and the end-user section ordering. Any new
renderer (the N-level tree renderer REQ-02, the a11y renderer REQ-03) had to re-fork them. This module
lifts that logic — **verbatim** — into a middleware layer between the SOURCE (``Fᵢ: Domain → Node``)
and the RENDERER (``Gⱼ: Node → View``): a visualization is now ``Gⱼ ∘ apply_node_lenses ∘ Fᵢ``.

``compose()`` delegates to these functions; no copy of the lens logic remains in ``compose.py`` (Kagami).
The scope is a pure factoring — **no new lens behaviour** (NR-1). The app-scaffold wireframe path stays
byte-identical (FR-6): the extracted logic is unchanged, only the call site moved.

Independence constraint (FR-3): this module imports **only** ``wireframe.delivery_roles`` (for
``effective_voice``) and — lazily, inside ``project_nodes`` — ``navigator.models.Node``. It never
imports ``WireframePlan`` / ``WireframeItem`` / ``compose`` / ``view``, so a renderer can pull the
lenses in without dragging the wireframe-plan machinery into its dependency closure. No LLM (Hitsuzen).
"""
from __future__ import annotations

import re
from typing import Optional

from ..wireframe.delivery_roles import effective_voice

# FR-AUD-C1 banned register (R1-F7), word-boundary matched so domain names ("identity", "AiCall") don't
# false-trip. A plan item whose LABEL carries this jargon (e.g. "FastAPI app", "export endpoints") is
# infrastructure the non-technical reader shouldn't see — it is flagged `technical` and hidden from the
# end_user render (the datum still rides in the embed for the architect voice). SINGLE SOURCE for the
# ban — the acceptance test imports this same matcher.
_JARGON_RE = re.compile(
    r"\b(?:entit(?:y|ies)|cruds?|schemas?|prisma|manifests?|cascades?|fastapi|"
    r"endpoints?|openapi|htmx|foreign[- ]keys?|ai pass(?:es)?)\b",
    re.IGNORECASE,
)


def has_jargon(text: str) -> bool:
    """True if *text* contains an FR-AUD-C1 banned term (word-boundary). The one ban matcher (R1-F7)."""
    return bool(_JARGON_RE.search(text or ""))


# Tool-structural items are scaffolding, not user data — so (unlike entity/form names, which we KEEP
# verbatim, FR-AUD-C5) they get plain, path-free wording for the end_user. Fixed structural labels →
# plain; patterned labels (signal:/view:/prompt:/page body:/route/kind/form) → generic rules below.
_END_USER_ITEM_LABELS = {
    "AI service": "What the app writes for you",
    "AI boundary": "What you keep in your control",
    "default top nav": "The menu bar",
    "nav live-toggle admin": "Menu editor",
    "pages router": "Page navigation",
    "authoring UI": "Content editor",
    "home / index page": "Home page",
    "views package": "The overviews",
    "contract models": "The full list",
    "relation graph": "How they connect",
    "excluded": "Filled in automatically",
    "mode": "Setup type",
    "persistence": "Where your data is kept",
    "bind": "Who can reach it",
    "secrets-default": "Security keys",
    "observability": "Monitoring",
    "identity": "Sign-in",
    "run: local": "Runs on your computer",
    "container: Dockerfile": "Ready to run anywhere",
    "migrations: alembic": "Automatic database updates",
}


def _humanize(token: str) -> str:
    """A path/underscore token → plain Title-ish words: 'app/pages/how_it_works.md' → 'How it works'."""
    token = token.rsplit("/", 1)[-1]
    if token.endswith(".md"):
        token = token[:-3]
    token = token.replace("_", " ").replace("-", " ").strip()
    return (token[:1].upper() + token[1:]) if token else token


def _plain_item_label(label: str) -> str:
    """Plain, path-free end_user wording for a structural item label (FR-AUD-C1/C1b). Real data names
    (entities/forms) fall through unchanged (FR-AUD-C5)."""
    if label in _END_USER_ITEM_LABELS:
        return _END_USER_ITEM_LABELS[label]
    if label.startswith("signal: "):
        return label[len("signal: "):]                                  # keep the record name
    if label.startswith("view: "):
        return _humanize(label[len("view: "):])
    if label.startswith("prompt: "):
        return "Instructions: " + _humanize(label[len("prompt: "):])
    if label.startswith("page body: "):
        return _humanize(label[len("page body: "):]) + " page"
    if label.startswith("app: "):
        return "App name: " + label[len("app: "):]
    if label.endswith(" create/edit form"):
        return label[: -len(" create/edit form")] + " — add or edit"
    m = re.match(r"^/\S*\s+—\s+(.+)$", label)                            # "/jobs — Jobs" → "Jobs"
    if m:
        return m.group(1)
    m = re.match(r"^(.+?)\s+\([a-z0-9-]+\)$", label)                     # "value_map (detail-compose)" → "Value map"
    if m:
        return _humanize(m.group(1))
    return label


def _display_label(label: str, role: str) -> str:
    return _plain_item_label(label) if role == "end_user" else label


# Item statuses that mean "this still needs the author's input" — the computed floor under NEED (R1-F1).
GAP_STATUSES = {"not_defined", "placeholder", "invalid"}

# NODE-SCHEMA inv. 7 honest-skips — excluded from need_items even if status looks gappy (FR-3).
HONEST_SKIP_ROUTES = frozenset({"owned_elsewhere", "declared_unimplemented"})


def _is_gap_item(item) -> bool:
    """True when the item counts toward attention/gap (SV-10 floor + honest-skip exclusion)."""
    route = getattr(item, "route_state", "") or ""
    if route in HONEST_SKIP_ROUTES:
        return False
    return item.status in GAP_STATUSES


# End-user section order: lead with what the author experiences (screens → forms → content they must
# write → the things tracked), then the supporting/technical sections. Presentation only — the section
# SET, statuses, and items are unchanged (FR-AUD-4); the architect keeps the plan's data-model order.
_END_USER_ORDER = [
    "pages", "forms", "content", "entities", "views",
    "services", "display", "completeness", "deployment", "scaffold",
]


def _iv_status(item_view) -> str:
    """The status of an item-view — a dict (compose path) or an object (raw plan item)."""
    if isinstance(item_view, dict):
        return item_view.get("status", "")
    return getattr(item_view, "status", "")


def _iv_route(item_view) -> str:
    """The route_state of an item-view — dict or object."""
    if isinstance(item_view, dict):
        return item_view.get("route_state", "") or ""
    return getattr(item_view, "route_state", "") or ""


def _iv_is_gap(item_view) -> bool:
    """The gap floor applied to an item-view dict/object (mirrors ``_is_gap_item`` for dicts)."""
    if _iv_route(item_view) in HONEST_SKIP_ROUTES:
        return False
    return _iv_status(item_view) in GAP_STATUSES


def apply_node_lenses(
    item_views: list, *, role: str = "architect", fluency: str = "intermediate",
    voice: Optional[str] = None,
) -> list:
    """Apply the audience × fluency data-layer lenses to a flat list of item-view dicts.

    Each element of *item_views* is a ``dict`` carrying at least ``label`` and ``status`` (the shape
    ``compose._item_view`` produces). Returns a new list of item-view dicts where:

    - ``label`` is passed through :func:`_display_label` for the effective *voice* (end_user → plain);
    - ``technical`` marks a jargon label (R1-F7) — hidden from an end_user render;
    - ``need_items`` carries the per-item gap floor as a boolean (``_is_gap_item`` semantics).

    ``voice`` defaults to ``effective_voice(role)`` (a kit renders as its base voice). This is the
    renderer-facing transform used by :func:`project_nodes`; ``compose`` builds its own item-views via
    ``_item_view`` (which already applies ``_display_label``/``has_jargon``) and calls
    :func:`apply_section_lenses` for the section-level ordering + aggregation. No new behaviour (NR-1)."""
    v = voice or effective_voice(role)
    out: list = []
    for iv in item_views:
        raw_label = iv.get("label", "") if isinstance(iv, dict) else getattr(iv, "label", "")
        new_iv = dict(iv) if isinstance(iv, dict) else {"label": raw_label, "status": _iv_status(iv)}
        new_iv["label"] = _display_label(raw_label, v)
        new_iv["technical"] = has_jargon(raw_label)
        new_iv["need_items"] = _iv_is_gap(iv)
        out.append(new_iv)
    return out


def apply_section_lenses(sections: list, *, voice: str) -> list:
    """Apply the section-level lenses: end-user ordering only (byte-identical to compose's inline sort).

    *sections* is the list of section view-model dicts ``compose`` builds (each with a ``key``). When
    *voice* is ``end_user`` the sections are sorted by :data:`_END_USER_ORDER` (unknown keys sort last,
    stably); otherwise the plan's data-model order is preserved. Presentation only — the section SET,
    statuses, and items are unchanged (FR-AUD-4). Returns the (possibly reordered) list.

    The per-section ``need_items`` aggregation stays in ``compose`` (it depends on the plan item's
    ``_display_label`` under the effective voice, already applied there); this function owns the
    ordering decision so any renderer gets the same section order from one place."""
    if voice != "end_user":
        return sections
    rank = {k: i for i, k in enumerate(_END_USER_ORDER)}
    ordered = list(sections)
    ordered.sort(key=lambda sec: rank.get(sec["key"], len(rank)))
    return ordered


def project_nodes(
    nodes, *, role: str = "architect", fluency: str = "intermediate",
) -> list:
    """FR-2 bridge: a ``List[Node]`` → a lens-filtered item-view list, WITHOUT a ``WireframePlan``.

    The tree (REQ-02) and a11y (REQ-03) renderers work on raw ``Node`` objects; this opt-in bridge
    gives them the same lens-annotated item-views ``compose`` produces, so a renderer that wants
    plain/technical labels, the ``technical`` jargon flag, and the gap floor doesn't re-derive them.

    Each returned dict has at minimum: ``label``, ``status``, ``detail``, ``technical`` and
    ``need_items`` (a per-item boolean gap floor; ``False`` for a non-gap node). The label + status are
    derived exactly as ``navigator.project.nodes_to_wireframe_plan`` does (``"{key} — {does}"`` and the
    display status), so the labels match ``compose(plan)`` for the same nodes — FR-7 parity guards this.

    Imports ``navigator.models`` lazily (inside the function) so importing this module standalone does
    not pull the navigator package (FR-3)."""
    from ..navigator.models import NodeStatus

    # The Node.status → app display-status map (mirrors navigator.project._STATUS_MAP) so a node's
    # gap floor + status match the compose(plan) projection. status_key attribute wins when present.
    _status_map = {
        NodeStatus.BUILT: "planned",
        NodeStatus.THIN: "placeholder",
        NodeStatus.SPEC: "not_defined",
        NodeStatus.DEPRECATED: "invalid",
    }
    v = effective_voice(role)
    item_views: list = []
    for node in nodes:
        does = (getattr(node, "does", "") or "").strip()
        key = getattr(node, "key", "") or ""
        label = f"{key} — {does}" if does and does != key else key
        attrs = getattr(node, "attributes", {}) or {}
        disp = attrs.get("status_key") or _status_map.get(getattr(node, "status", ""), "not_defined")
        item_views.append({
            "label": label,
            "status": disp,
            "detail": (getattr(node, "does", "") or ""),
            "route_state": getattr(node, "route_state", "") or "",
        })
    return apply_node_lenses(item_views, role=role, fluency=fluency, voice=v)


__all__ = [
    "apply_node_lenses",
    "apply_section_lenses",
    "project_nodes",
    "has_jargon",
    "GAP_STATUSES",
    "HONEST_SKIP_ROUTES",
    "_display_label",
    "_plain_item_label",
    "_is_gap_item",
    "_humanize",
    "_END_USER_ITEM_LABELS",
    "_END_USER_ORDER",
]
