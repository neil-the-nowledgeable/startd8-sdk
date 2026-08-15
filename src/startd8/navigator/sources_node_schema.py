"""Visualize the Node structure ITSELF — the NODE-SCHEMA shape rendered as Nodes.

Kagami (鏡) mirror: the field list, types, and defaults are **introspected from ``models.py``** via
``dataclasses.fields(Node)`` — never hand-drawn — so the view reflects the source and a field added to
``Node`` appears here even if unannotated (the mirror can't silently drop it). The per-field semantic
name / meaning / category / provenance are curated annotations layered on top of that structural truth.

This is the self-referential dogfood: the node visualizer rendering its own schema, grounded in the
git blob that defines it.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import List, Optional

from startd8.wireframe.profile import RenderProfile, StatusStyle

from .git_lives import prefer_git_ref
from .models import Node, NodeEvidence, NodeStatus, node_field_names  # noqa: F401
from .naming import name_forms

MODELS_REL = "src/startd8/navigator/models.py"

NODE_SCHEMA_PROFILE = RenderProfile(
    statuses=(
        StatusStyle("authored", "Authored", "#3d7a57", "a human writes this field", 0),
        StatusStyle("derived", "Derived", "#2b7382", "computed from evidence × maturity", 1),
        StatusStyle("computed", "Computed", "#6b6252", "assembled by the harness", 1),
        StatusStyle("meta", "Meta", "#948b78", "open extension bag", 2),
    ),
    title="Node structure — a first look",
    eyebrow="NODE-SCHEMA",
    section_lead="What a Node is made of",
    headline="A first look at the Node structure",
    gap_noun="field",
    summary_meta=(
        "The Node model rendered as Nodes — a Kagami mirror of models.py (field names/types/defaults "
        "introspected, not hand-drawn).",
    ),
    why="Each field IS a node: what it holds, its type/default (from the code), and who fills it "
        "(authored · derived · computed · meta).",
    do="Read by group — identity, descriptive, evidence, axes, hierarchy, derived, meta. A field "
       "present in models.py but missing an annotation below is a gap to fill.",
)

# Curated annotation per Node field. Structural truth (type/default) comes from introspection; this
# supplies the semantic name, meaning, group, and provenance class. Keyed by dataclass field name.
_FIELD_META = {
    "key":          ("identity",    "authored", "the node's stable identity / short reference"),
    "does":         ("descriptive", "authored", "the WHAT — the behaviour or capability the node delivers"),
    "status":       ("derived",     "derived",  "build-state (built/thin/spec/deprecated), from evidence × maturity"),
    "wont":         ("descriptive", "authored", "explicit non-goals / out-of-scope constraints"),
    "lives":        ("evidence",    "computed", "typed evidence references (code/test/doc/link) — where it's realised"),
    "ships_when":   ("descriptive", "authored", "activation condition when there is no evidence yet"),
    "confidence":   ("derived",     "derived",  "0.9/0.6/0.4 grounding heuristic (default_confidence) unless authored"),
    "triggers":     ("axis",        "authored", "signals/conditions that activate the node"),
    "children":     ("hierarchy",   "computed", "nested child Nodes (the sub-tree)"),
    "child_keys":   ("hierarchy",   "authored", "keys of dependency/child nodes (DEPENDS-ON)"),
    "category":     ("axis",        "authored", "grouping axis (which section the node lands in)"),
    "orientation":  ("axis",        "authored", "NODE-SCHEMA orientation axis (e.g. bridge)"),
    "route_state":  ("axis",        "derived",  "routing / honest-skip (sdk_emitted, owned_elsewhere, …)"),
    "status_facets":("derived",     "computed", "orthogonal health facets (NODE-SCHEMA inv. 5)"),
    "attributes":   ("meta",        "meta",     "open extension bag (name/handle/verify/approve/…)"),
}


def _type_str(t) -> str:
    """Stringify a dataclass field type annotation (introspected, so it mirrors the code)."""
    s = t if isinstance(t, str) else getattr(t, "__name__", repr(t))
    return s.replace("typing.", "").replace("startd8.navigator.models.", "")


def _default_str(f: "dataclasses.Field") -> str:
    if f.default is not dataclasses.MISSING:
        return repr(f.default)
    if f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
        return f"{f.default_factory.__name__}()"
    return "(required)"


def nodes_from_node_schema(*, repo: Optional[Path] = None) -> List[Node]:
    """Project each ``Node`` dataclass field into a Node (the schema visualized as nodes)."""
    repo_root = Path(repo) if repo else _repo_root()
    src_ref = prefer_git_ref(MODELS_REL, repo=repo_root)
    order = {g: i for i, g in enumerate(
        ("identity", "descriptive", "evidence", "axis", "hierarchy", "derived", "meta"))}
    nodes: List[Node] = []
    for f in dataclasses.fields(Node):
        group, provenance, meaning = _FIELD_META.get(
            f.name, ("meta", "meta", "(unannotated field — present in models.py; add an annotation)"))
        type_str, default_str = _type_str(f.type), _default_str(f)
        does = f"{meaning} — type {type_str}, default {default_str}"
        semantic = f"Node.{f.name} holds {meaning}"
        attrs = {
            "kind": "node-field",
            "title": f"Node.{f.name}",
            "field_type": type_str,
            "field_default": default_str,
            "provenance": provenance,
            "status_key": provenance,          # colour by who fills the field
            "section_order": str(order.get(group, 9) * 10),
        }
        attrs.update(name_forms(semantic, f.name, initiative="node-schema", kind="schema-field"))
        nodes.append(Node(
            key=f"Node.{f.name}",
            does=does,
            status=NodeStatus.BUILT,           # every field exists in the model (grounded in code)
            lives=(NodeEvidence(type="code", ref=src_ref, note=f"field {f.name}"),),
            category=group,
            orientation="schema",
            route_state="sdk_emitted",
            attributes=attrs,
        ))
    return nodes


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]
