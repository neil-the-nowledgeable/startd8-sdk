"""Project Nodes → WireframePlan / HTML (port of ContextCore navigator/render projection).

Does not import ContextCore. HTML reuses ``wireframe_view.render_to_file``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from startd8.wireframe import (
    ContentCoverageStats,
    EvidenceRef,
    WireframeItem,
    WireframePlan,
    WireframeSection,
)
from startd8.wireframe.profile import RenderProfile

from .models import Node, NodeStatus

_STATUS_MAP = {
    NodeStatus.BUILT: "planned",
    NodeStatus.THIN: "placeholder",
    NodeStatus.SPEC: "not_defined",
    NodeStatus.DEPRECATED: "invalid",
}
# Display-status severity for section rollup (higher = worse). Includes Node profile keys.
_STATUS_SEVERITY = [
    "grounded",
    "built",
    "planned",
    "defaults",
    "thin",
    "placeholder",
    "spec",
    "awaiting",
    "excluded",
    "not_defined",
    "unknown",
    "invalid",
    "deprecated",
]
_PROBLEM_RANK = {
    NodeStatus.DEPRECATED: 0,
    NodeStatus.SPEC: 1,
    NodeStatus.THIN: 2,
    NodeStatus.BUILT: 3,
}


def _problem_rank(node: Node) -> int:
    return _PROBLEM_RANK.get(node.status, 1)


def _section_order(members: List[Node]) -> int:
    vals = []
    for m in members:
        try:
            vals.append(int(m.attributes.get("section_order", 500)))
        except (TypeError, ValueError):
            vals.append(500)
    return min(vals) if vals else 500


def _wf_status(node_status: str) -> str:
    return _STATUS_MAP.get(node_status, "not_defined")


def _rollup(statuses: List[str]) -> str:
    worst = "planned"
    worst_rank = -1
    for s in statuses:
        rank = _STATUS_SEVERITY.index(s) if s in _STATUS_SEVERITY else len(_STATUS_SEVERITY)
        if rank > worst_rank:
            worst_rank, worst = rank, s
    return worst


def _node_detail(node: Node) -> str:
    lines: List[str] = []
    a = node.attributes
    # Deterministic semantic name first (identify by meaning, not the integer key alone).
    if a.get("name"):
        lines.append("NAME → " + a["name"])
    if a.get("handle"):
        lines.append("HANDLE: " + a["handle"])
    desc = a.get("description") or node.does
    if desc and desc != node.does:
        lines.append(desc.strip())
    if a.get("verify"):
        lines.append("VERIFY → " + a["verify"])
    if a.get("serves"):
        lines.append("SERVES → " + a["serves"])
    if a.get("fr_health"):
        lines.append("FR-HEALTH: " + a["fr_health"])
    if node.wont:
        lines.append("WON'T: " + "; ".join(node.wont))
    if node.ships_when:
        lines.append("SHIPS-WHEN: " + node.ships_when)
    if node.child_keys:
        lines.append("DEPENDS-ON: " + ", ".join(node.child_keys))
    if node.confidence is not None:
        lines.append(f"confidence: {node.confidence:.2f}")
    return "\n".join(lines)


def _sv_readiness(nodes: Sequence[Node]) -> Dict[str, str]:
    readiness: Dict[str, str] = {}
    for node in nodes:
        for k, v in node.attributes.items():
            if k.startswith("sv."):
                readiness[k[3:]] = str(v)
    return readiness


def nodes_to_wireframe_plan(
    nodes: Sequence[Node],
    *,
    project_root: str = ".",
    group_by: str = "category",
) -> WireframePlan:
    """Build a WireframePlan from nodes (grouped into sections)."""
    groups: Dict[str, List[Node]] = {}
    for node in nodes:
        key = getattr(node, group_by, None)
        if not key:
            key = node.attributes.get(group_by, "")
        groups.setdefault(str(key) or "uncategorized", []).append(node)

    status_counts: Dict[str, int] = {}
    sections = []
    ordered_keys = sorted(groups, key=lambda gk: (_section_order(groups[gk]), gk))
    for group_key in ordered_keys:
        members = sorted(groups[group_key], key=lambda n: (_problem_rank(n), n.key))
        items = []
        member_statuses = []
        for node in members:
            app_status = _wf_status(node.status)
            disp = node.attributes.get("status_key") or app_status
            # Roll up the *display* status (grounded/spec/…) — not the app-mapped status —
            # so section chrome matches item badges (ATM / cruft: not_defined over grounded).
            member_statuses.append(disp)
            status_counts[disp] = status_counts.get(disp, 0) + 1
            paths = tuple(ev.ref for ev in node.lives if ev.ref)
            does = (node.does or "").strip()
            label = f"{node.key} — {does}" if does and does != node.key else node.key
            conf = node.confidence
            prompts_raw = (node.attributes.get("approve_prompts") or "").strip()
            prompts = tuple(p.strip() for p in re.split(r"\s*[·|;]\s*", prompts_raw) if p.strip())
            was_raw = (node.attributes.get("was") or "").strip()
            was = tuple(w.strip() for w in re.split(r"\s*[·|,;]\s*", was_raw) if w.strip())
            items.append(
                WireframeItem(
                    label=label,
                    status=disp,
                    detail=_node_detail(node),
                    paths=paths,
                    key=node.key,
                    lives=tuple(
                        EvidenceRef(type=ev.type, ref=ev.ref, note=ev.note) for ev in node.lives
                    ),
                    confidence=conf,
                    ships_when=node.ships_when or "",
                    was=was,
                    route_state=node.route_state or "",
                    approve_prompts=prompts,
                )
            )
        sections.append(
            WireframeSection(
                key=group_key.replace(" ", "_").lower(),
                title=group_key,
                status=_rollup(member_statuses),
                items=tuple(items),
            )
        )

    from startd8.wireframe.shape_dialect import reject_app_bound_node_shape

    # Node-domain shape only — never zero-pad app cascade keys (ATM metabolize).
    shape = {"nodes": len(nodes), "sections": len(sections)}
    reject_app_bound_node_shape(shape)

    return WireframePlan(
        project_root=project_root,
        sections=tuple(sections),
        input_provenance={},
        merge_warnings=(),
        shape=shape,
        readiness=_sv_readiness(nodes),
        status_counts=status_counts,
        content_coverage=ContentCoverageStats(),
    )


def nodes_to_json(nodes: Sequence[Node]) -> List[Dict[str, Any]]:
    """JSON-safe Node list (for ``--format json``)."""
    out: List[Dict[str, Any]] = []
    for n in nodes:
        out.append(
            {
                "key": n.key,
                "does": n.does,
                "status": n.status,
                "wont": list(n.wont),
                "lives": [{"type": e.type, "ref": e.ref, "note": e.note} for e in n.lives],
                "ships_when": n.ships_when,
                "confidence": n.confidence,
                "triggers": list(n.triggers),
                "category": n.category,
                "orientation": n.orientation,
                "route_state": n.route_state,
                "attributes": dict(n.attributes),
            }
        )
    return out


def render_nodes_html(
    nodes: Sequence[Node],
    out_path: Path,
    *,
    project_root: str = ".",
    group_by: str = "category",
    role: str = "architect",
    fluency: str = "intermediate",
    profile: Optional[RenderProfile] = None,
) -> Path:
    """Render nodes via wireframe_view (FR-10)."""
    from startd8.wireframe_view import render_to_file

    plan = nodes_to_wireframe_plan(nodes, project_root=project_root, group_by=group_by)
    kwargs: Dict[str, Any] = {"role": role, "fluency": fluency}
    if profile is not None:
        kwargs["profile"] = profile
    return render_to_file(plan, Path(out_path), **kwargs)
