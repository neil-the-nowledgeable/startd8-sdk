"""Pure NODE-SCHEMA → GraphModel projection.

This promotes the proven ``dev-os/visual-editor/spikes/nodeschema_to_graph.py``
bridge into the producer that already owns the Navigator ``Node`` model.  The
projection is deliberately generic: identity always comes from ``Node.key`` and
new node kinds survive without adding another prefix-specific branch.

Graph section nodes are presentation markers.  Every source node remains in the
graph with the exact same key, while semantic relationships (``child_keys``,
``Serves``, ``built_by``, and plan ``delivers``) remain distinguishable from
section-containment edges.
"""

from __future__ import annotations

import dataclasses
import re
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence

from .models import Node


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "other"


def _kind(node: Node) -> str:
    return node.attributes.get("kind") or node.category or "node"


def _section(node: Node) -> str:
    return node.attributes.get("section") or _kind(node).replace("_", " ").title()


def _split_ids(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in (value or "").split(",") if part.strip())


def _flatten(nodes: Iterable[Node]) -> tuple[list[Node], list[tuple[str, str]]]:
    """Return unique nodes plus explicit parent→child containment relationships."""
    found: OrderedDict[str, Node] = OrderedDict()
    nested_edges: list[tuple[str, str]] = []

    def visit(node: Node, parent: str = "") -> None:
        if node.key in found and found[node.key] != node:
            raise ValueError(f"Duplicate NODE-SCHEMA key with different content: {node.key}")
        found.setdefault(node.key, node)
        if parent:
            nested_edges.append((parent, node.key))
        for child in node.children:
            visit(child, node.key)

    for item in nodes:
        visit(item)
    return list(found.values()), nested_edges


def _node_payload(node: Node, at: Mapping[str, float]) -> dict:
    attrs = dict(sorted(node.attributes.items()))
    verify = attrs.get("verify", "")
    description = attrs.get("description", "")
    does = description or node.does
    return {
        "id": node.key,
        "kind": _kind(node),
        "route_state": node.route_state,
        "status": node.status,
        "does": does,
        "verify": verify,
        "wont": list(node.wont),
        "label": (does or node.key)[:60],
        "at": dict(at),
        "data": {
            "source_key": node.key,
            "attributes": attrs,
            "lives": [dataclasses.asdict(evidence) for evidence in node.lives],
            "ships_when": node.ships_when,
            "confidence": node.confidence,
            "triggers": list(node.triggers),
            "category": node.category,
            "orientation": node.orientation,
        },
    }


def nodes_to_graph(nodes: Sequence[Node]) -> dict:
    """Project Navigator nodes into a valid, deterministic GraphModel.

    Source identity is never inferred from display prose.  Derived section nodes
    use the reserved ``view:section:`` prefix and carry ``view_marker=true`` so
    parity checks can exclude them without guessing.
    """
    flat, nested_edges = _flatten(nodes)
    if not flat:
        raise ValueError("Cannot project an empty NODE-SCHEMA collection")

    by_id = {node.key: node for node in flat}
    roots = [node for node in flat if _kind(node) == "masthead"]
    root = roots[0] if roots else None

    grouped: OrderedDict[str, list[Node]] = OrderedDict()
    for node in flat:
        if root is not None and node.key == root.key:
            continue
        grouped.setdefault(_section(node), []).append(node)

    graph_nodes: list[dict] = []
    if root is not None:
        graph_nodes.append(_node_payload(root, {"x": 0.04, "y": 0.5}))
        root_id = root.key
    else:
        root_id = "view:root"
        graph_nodes.append(
            {
                "id": root_id,
                "kind": "root",
                "role": "precondition",
                "label": "artifact",
                "at": {"x": 0.04, "y": 0.5},
                "data": {"view_marker": True},
            }
        )

    edges: list[dict] = []
    edge_ids: set[str] = set()

    def add_edge(source: str, target: str, label: str, *, semantic: bool) -> None:
        if source not in {node["id"] for node in graph_nodes} and source not in by_id:
            return
        if target not in {node["id"] for node in graph_nodes} and target not in by_id:
            return
        base = f"{source}->{target}:{label}"
        edge_id = base
        serial = 2
        while edge_id in edge_ids:
            edge_id = f"{base}:{serial}"
            serial += 1
        edge_ids.add(edge_id)
        edges.append(
            {
                "id": edge_id,
                "from": source,
                "to": target,
                "label": label,
                "data": {"semantic": semantic},
            }
        )

    section_count = max(len(grouped), 1)
    for section_index, (section, members) in enumerate(grouped.items()):
        x = round(0.18 + (0.76 * section_index / max(section_count - 1, 1)), 3)
        section_id = f"view:section:{_slug(section)}"
        graph_nodes.append(
            {
                "id": section_id,
                "kind": "section",
                "role": "read",
                "label": section,
                "at": {"x": x, "y": 0.06},
                "data": {"view_marker": True},
            }
        )
        add_edge(root_id, section_id, "has-section", semantic=False)
        for member_index, node in enumerate(members):
            y = round(0.16 + 0.8 * (member_index + 1) / (len(members) + 1), 3)
            graph_nodes.append(_node_payload(node, {"x": x, "y": y}))
            add_edge(section_id, node.key, "contains", semantic=False)

    def add_semantic(source: str, target: str, label: str) -> None:
        if source in by_id and target in by_id:
            add_edge(source, target, label, semantic=True)

    for parent, child in nested_edges:
        add_semantic(parent, child, "contains-child")

    for node in flat:
        for target in node.child_keys:
            add_semantic(node.key, target, "depends-on")
        for target in _split_ids(node.attributes.get("serves", "")):
            add_semantic(node.key, target, "serves")
        for target in _split_ids(node.attributes.get("built_by", "")):
            add_semantic(node.key, target, "built-by")
        for target in _split_ids(node.attributes.get("delivers", "")):
            add_semantic(node.key, target, "delivers")
        # REQ-20 FR-6: the typed derivation edges — forward `derived-from` (REQ-16) and the backward
        # `revises` feedback edge (REQ-20), each carried as its own labelled edge so the renderer
        # distinguishes the feedback loop visually (no new HTML shell).
        for e in getattr(node, "derivation", ()) or ():
            add_semantic(node.key, e.from_key, e.relation)

    return {
        "schema": "visual-editor.graph-model/21",
        "nodes": graph_nodes,
        "edges": edges,
    }


def validate_graph_model(graph: Mapping[str, object]) -> tuple[str, ...]:
    """Return deterministic structural issues; an empty tuple means valid."""
    issues: list[str] = []
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return ("GraphModel requires list fields: nodes and edges",)

    ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    if len(ids) != len(nodes) or any(not isinstance(node_id, str) or not node_id for node_id in ids):
        issues.append("Every graph node requires a non-empty string id")
    duplicates = sorted({node_id for node_id in ids if ids.count(node_id) > 1})
    if duplicates:
        issues.append(f"Duplicate graph node ids: {', '.join(duplicates)}")
    known = set(ids)
    for edge in edges:
        if not isinstance(edge, dict):
            issues.append("Every graph edge must be an object")
            continue
        source, target = edge.get("from"), edge.get("to")
        if source not in known or target not in known:
            issues.append(f"Dangling graph edge: {source!r} -> {target!r}")
    return tuple(issues)
