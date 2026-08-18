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

from .models import DerivationEdge, Node, NodeEvidence, NodeStatus

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
        rank = (
            _STATUS_SEVERITY.index(s)
            if s in _STATUS_SEVERITY
            else len(_STATUS_SEVERITY)
        )
        if rank > worst_rank:
            worst_rank, worst = rank, s
    return worst


def _node_meta(node: Node) -> str:
    """Compact structural metadata for the structure-only view — type · default · provenance · ← origin.

    The metadata a reader wants when the prose is stripped: what the field holds structurally and
    where it comes from. Origin is the source file of the first (git-anchored) Lives ref.
    """
    a = node.attributes
    bits: List[str] = []
    if a.get("field_type"):
        bits.append(a["field_type"])
    if a.get("field_default"):
        bits.append(f"default {a['field_default']}")
    if a.get("provenance"):
        bits.append(a["provenance"])
    if node.lives:
        bits.append("← " + node.lives[0].ref.split(":")[-1])
    return " · ".join(bits)


# Touches-kind classification (REQ-requirement-detail-on-navigator-card FR-4): a source-bound kind per
# authored Touches entry, derived deterministically from the path alone (never guessed from meaning).
# The test rule mirrors sources_requirements._TEST_PATH (one stable regex, cross-referenced here).
_TOUCH_TEST = re.compile(r"(?:^|/)tests?(?:/|_)|(?:^|/)test_|_test\.")
_TOUCH_CODE_EXT = {
    ".py",
    ".go",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".cs",
    ".rb",
    ".rs",
    ".c",
    ".cpp",
    ".cc",
    ".h",
    ".hpp",
    ".sh",
    ".sql",
}
_TOUCH_CONFIG_EXT = {".yaml", ".yml", ".toml", ".json", ".ini", ".env", ".cfg", ".conf"}
_TOUCH_DOC_EXT = {".md", ".rst", ".txt"}
_TOUCH_BUILD_NAMES = {"dockerfile", "makefile", "go.mod", "go.sum"}


def _classify_touch(path: str) -> str:
    """Source-bound kind for one authored Touches entry, from its path/extension alone."""
    p = path.strip().strip("`").strip().lower()
    if not p:
        return "other"
    base = p.rsplit("/", 1)[-1]
    if base in _TOUCH_BUILD_NAMES or base.endswith((".mk", ".lock")):
        return "build"
    if _TOUCH_TEST.search(p):
        return "test"
    ext = base[base.rfind(".") :] if "." in base else ""
    if ext in _TOUCH_CODE_EXT:
        return "code"
    if ext in _TOUCH_CONFIG_EXT:
        return "config"
    if ext in _TOUCH_DOC_EXT:
        return "doc"
    return "other"  # a bare projection token (e.g. "navigator-build") or an unknown extension


def _typed_touches(attr_touches: str) -> List[tuple]:
    """Split the node's joined ``touches`` attribute back to entries and tag each with its kind — the
    full authored blast-radius, typed. Deterministic + source-bound; the split is over a comma-joined
    path list (authored paths carry no ``, ``), and backticks/whitespace are stripped per entry.
    """
    out: List[tuple] = []
    for raw in (attr_touches or "").split(", "):
        p = raw.strip().strip("`").strip()
        if p:
            out.append((p, _classify_touch(p)))
    return out


def _node_fields(node: Node) -> Dict[str, str]:
    """The requirement's fields, STRUCTURED — the single extraction the HTML card reads by key (via
    ``WireframeItem.fields``) and that ``_node_detail`` formats its text/JSON string from. Only fields
    with no first-class ``WireframeItem`` slot live here; ``confidence``/``ships_when`` stay first-class
    (the card reads ``item.confidence``/``item.ships_when``) so they are not double-carried.
    """
    a = node.attributes
    f: Dict[str, str] = {}
    if a.get("name"):
        f["name"] = a["name"]
    if a.get(
        "archetype"
    ):  # functional archetype (what kind of requirement) + its plain gloss
        f["archetype"] = a["archetype"]
        if a.get("archetype_gloss"):
            f["archetype_gloss"] = a["archetype_gloss"]
    if a.get("touches_count"):  # scope / blast-radius — how many files it touches
        f["touches_count"] = a["touches_count"]
    if a.get("handle"):
        f["handle"] = a["handle"]
    desc = a.get("description") or node.does
    if desc and desc != node.does:
        f["statement"] = desc.strip()
    if a.get("verify"):
        f["verify"] = a["verify"]
    if a.get("serves"):
        f["serves"] = a["serves"]
        if a.get(
            "serves_objective"
        ):  # the joined objective text — the 'why / system benefit'
            f["serves_objective"] = a["serves_objective"]
    if a.get("fr_health"):
        f["fr_health"] = a["fr_health"]
    if node.wont:
        f["wont"] = "; ".join(node.wont)
    if node.child_keys:
        f["depends"] = ", ".join(node.child_keys)
    return f


def _node_detail(node: Node) -> str:
    """The terminal text/JSON detail string (``wireframe/render.py`` Rich tree + canonical JSON body).
    Formatted FROM :func:`_node_fields` so the string and the structured card can never drift; the
    first-class ``ships_when``/``confidence`` are appended here (string surface only).
    """
    f = _node_fields(node)
    lines: List[str] = []
    if f.get(
        "name"
    ):  # Deterministic semantic name first (identify by meaning, not the integer key).
        lines.append("NAME → " + f["name"])
    if f.get("archetype"):
        line = "TYPE → " + f["archetype"]
        if f.get("archetype_gloss"):
            line += " · " + f["archetype_gloss"]
        lines.append(line)
    if f.get("touches_count"):
        n = f["touches_count"]
        lines.append("SCOPE → " + n + (" file" if n == "1" else " files"))
    if f.get("handle"):
        lines.append("HANDLE: " + f["handle"])
    if f.get("statement"):
        lines.append(f["statement"])
    if f.get("verify"):
        lines.append("VERIFY → " + f["verify"])
    if f.get("serves"):
        line = "SERVES → " + f["serves"]
        if f.get("serves_objective"):
            line += " · " + f["serves_objective"]
        lines.append(line)
    if f.get("fr_health"):
        lines.append("FR-HEALTH: " + f["fr_health"])
    if f.get("wont"):
        lines.append("WON'T: " + f["wont"])
    if node.ships_when:
        lines.append("SHIPS-WHEN: " + node.ships_when)
    if f.get("depends"):
        lines.append("DEPENDS-ON: " + f["depends"])
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
    realization_provenance=None,
) -> WireframePlan:
    """Build a WireframePlan from nodes (grouped into sections).

    ``realization_provenance`` (REQ-19, optional): a measured :class:`ProvenanceSource`; when supplied and
    it grounds regimes above the seam threshold, the determinism-% relabels ``measured``. Absent (the
    default) → the declared distribution (REQ-18), byte-identical.
    """
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
            prompts = tuple(
                p.strip() for p in re.split(r"\s*[·|;]\s*", prompts_raw) if p.strip()
            )
            was_raw = (node.attributes.get("was") or "").strip()
            was = tuple(
                w.strip() for w in re.split(r"\s*[·|,;]\s*", was_raw) if w.strip()
            )
            items.append(
                WireframeItem(
                    label=label,
                    status=disp,
                    detail=_node_detail(node),
                    paths=paths,
                    key=node.key,
                    lives=tuple(
                        EvidenceRef(type=ev.type, ref=ev.ref, note=ev.note)
                        for ev in node.lives
                    ),
                    confidence=conf,
                    ships_when=node.ships_when or "",
                    was=was,
                    route_state=node.route_state or "",
                    approve_prompts=prompts,
                    meta=_node_meta(node),
                    fields=tuple(_node_fields(node).items()),
                    touches=tuple(_typed_touches(node.attributes.get("touches", ""))),
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

    # REQ-18 FR-4: the realization-regime distribution over the whole node corpus (each top-level node's
    # subtree), for the summary determinism-% line. Empty when no node declares a regime (requirement /
    # capability graphs) → the line does not render → byte-identical (FR-7).
    from .realization import corpus_realization

    # REQ-18 declared / REQ-19 measured: one path — corpus_realization returns the distribution and a
    # `grounded` flag (True only when a provenance source contributed above-threshold measured regimes →
    # the label becomes `measured`; else `declared`). No provenance → empty/declared → byte-identical.
    realization, realization_grounded = corpus_realization(
        nodes, realization_provenance
    )

    return WireframePlan(
        project_root=project_root,
        sections=tuple(sections),
        input_provenance={},
        merge_warnings=(),
        shape=shape,
        readiness=_sv_readiness(nodes),
        status_counts=status_counts,
        content_coverage=ContentCoverageStats(),
        realization=realization,
        realization_grounded=realization_grounded,
    )


def _node_to_json(n: Node) -> Dict[str, Any]:
    """One Node → JSON dict, recursing ``children`` so the full tree round-trips (REQ-02 FR-4).

    EB-1 (NODE-SCHEMA 0.4.0 wire-format): the promoted reliability fields + the typed derivation edge
    are serialized **presence-gated** — a key is emitted only when the field is non-empty. So a node
    that lacks them (every pipeline / node-schema / capability node) is **byte-identical** to the
    pre-0.4.0 export, while a requirements Node carries its oracle/gate/history/derivation through JSON.
    """
    d: Dict[str, Any] = {
        "key": n.key,
        "does": n.does,
        "status": n.status,
        "wont": list(n.wont),
        "lives": [{"type": e.type, "ref": e.ref, "note": e.note} for e in n.lives],
        "ships_when": n.ships_when,
        "confidence": n.confidence,
        "triggers": list(n.triggers),
        "children": [_node_to_json(c) for c in n.children],  # FR-4: carry the tree
        "child_keys": list(n.child_keys),
        "category": n.category,
        "orientation": n.orientation,
        "route_state": n.route_state,
        "attributes": dict(n.attributes),
    }
    # 0.4.0 additive, presence-gated (byte-identical when absent — SOTTO).
    if n.verify:
        d["verify"] = n.verify
    if n.approve:
        d["approve"] = list(n.approve)
    if n.was:
        d["was"] = list(n.was)
    if n.derivation:
        d["derivation"] = [
            {"from_key": e.from_key, "relation": e.relation, "regime": e.regime}
            for e in n.derivation
        ]
    return d


def nodes_to_json(nodes: Sequence[Node]) -> List[Dict[str, Any]]:
    """JSON-safe Node list (for ``--format json``) — carries ``children`` recursively (FR-4)."""
    return [_node_to_json(n) for n in nodes]


def nodes_from_json(data: Sequence[Dict[str, Any]]) -> List[Node]:
    """Inverse of ``nodes_to_json``: reconstruct a Node tree from a pre-projected NODE-SCHEMA-JSON
    graph (REQ-02 FR-2, ``--source nodes-json``). ``children`` recurse; unknown keys are ignored.
    """
    out: List[Node] = []
    for d in data:
        out.append(
            Node(
                key=str(d.get("key", "")),
                does=str(d.get("does", "")),
                status=str(d.get("status", NodeStatus.SPEC)),
                wont=tuple(d.get("wont") or ()),
                lives=tuple(
                    NodeEvidence(
                        type=str(e.get("type", "")),
                        ref=str(e.get("ref", "")),
                        note=str(e.get("note", "")),
                    )
                    for e in (d.get("lives") or [])
                ),
                ships_when=str(d.get("ships_when", "")),
                confidence=d.get("confidence"),
                triggers=tuple(d.get("triggers") or ()),
                children=tuple(
                    nodes_from_json(d.get("children") or [])
                ),  # recurse the tree
                child_keys=tuple(d.get("child_keys") or ()),
                category=str(d.get("category", "")),
                orientation=str(d.get("orientation", "")),
                route_state=str(d.get("route_state", "")),
                attributes=dict(d.get("attributes") or {}),
                # EB-1 (0.4.0): read back the reliability fields + derivation edge when present (absent
                # → empty defaults, so pre-0.4.0 NODE-SCHEMA-JSON still loads unchanged).
                verify=str(d.get("verify", "")),
                approve=tuple(d.get("approve") or ()),
                was=tuple(d.get("was") or ()),
                derivation=tuple(
                    DerivationEdge(
                        from_key=str(e.get("from_key", "")),
                        relation=str(e.get("relation", "derived-from")),
                        regime=(
                            str(e["regime"]) if e.get("regime") is not None else None
                        ),
                    )
                    for e in (d.get("derivation") or [])
                    if isinstance(e, dict) and e.get("from_key")
                ),
            )
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
    frame: bool = False,
    realization_provenance=None,
    cross_links: Optional[dict] = None,
) -> Path:
    """Render nodes via wireframe_view (FR-10). ``frame`` (REQ-15) renders scaffold-only bare frame.
    ``realization_provenance`` (REQ-19): a measured ProvenanceSource → the determinism-% relabels
    ``measured`` when it grounds regimes above threshold (else the declared fallback, byte-identical).
    """
    from startd8.wireframe_view import render_to_file

    plan = nodes_to_wireframe_plan(
        nodes,
        project_root=project_root,
        group_by=group_by,
        realization_provenance=realization_provenance,
    )
    kwargs: Dict[str, Any] = {"role": role, "fluency": fluency}
    if frame:
        kwargs["frame"] = True
    # REQ-navigator-cross-topology-links (Move 1) FR-3: forward the authored cross-links map (embedded
    # only under a profile downstream → app path byte-identical).
    if cross_links:
        kwargs["cross_links"] = cross_links
    if profile is not None:
        kwargs["profile"] = profile
        # Live chrome-provenance readout for the debug panel: "all content is cruft until proven"
        # — an element with no traceable origin is unproven (cruft). Embed the score + orphans.
        from .provenance import chrome_provenance

        rows = chrome_provenance(nodes, plan, profile)
        present = sum(1 for r in rows if r["present"])
        kwargs["chrome"] = {
            "score": round(present / len(rows), 3) if rows else 0.0,
            "present": present,
            "total": len(rows),
            "orphans": [r["element"] for r in rows if not r["present"]],
        }
    return render_to_file(plan, Path(out_path), **kwargs)
