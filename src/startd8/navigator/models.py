"""NODE-SCHEMA node model (renderer-independent).

Copy-port of ContextCore ``navigator/models.py`` (field-compatible) plus the
SDK-owned ``default_confidence`` heuristic (FR-4 — not a CC symbol).

Cite: ``dev-os/NODE-SCHEMA.md`` v0.3.9+.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Dict, Optional, Tuple

# Shared field names with ContextCore Node — field-compat golden (FR-1 / R1-S5).
NODE_SHARED_FIELDS: Tuple[str, ...] = (
    "key",
    "does",
    "status",
    "wont",
    "lives",
    "ships_when",
    "confidence",
    "triggers",
    "children",
    "child_keys",
    "category",
    "orientation",
    "route_state",
    "status_facets",
    "attributes",
)


class NodeStatus:
    """Build-state of a node, derived from evidence × maturity."""

    BUILT = "built"
    THIN = "thin"
    SPEC = "spec"
    DEPRECATED = "deprecated"

    ALL = (BUILT, THIN, SPEC, DEPRECATED)

    GLYPH = {BUILT: "✅", THIN: "\U0001f7e1", SPEC: "\U0001f4c4", DEPRECATED: "⛔"}


@dataclass(frozen=True)
class NodeEvidence:
    """A ``lives`` reference: where the node is realised."""

    type: str  # code | test | doc | link | owned_elsewhere | declared_unimplemented
    ref: str
    note: str = ""


@dataclass(frozen=True)
class StatusFacet:
    """One orthogonal health facet (NODE-SCHEMA inv. 5)."""

    name: str
    value: str
    glyph: str = ""
    color: str = ""


@dataclass(frozen=True)
class Node:
    """A single NODE-SCHEMA node."""

    key: str
    does: str
    status: str = NodeStatus.SPEC
    wont: Tuple[str, ...] = ()
    lives: Tuple[NodeEvidence, ...] = ()
    ships_when: str = ""
    confidence: Optional[float] = None
    triggers: Tuple[str, ...] = ()
    children: Tuple["Node", ...] = ()
    child_keys: Tuple[str, ...] = ()
    category: str = ""
    orientation: str = ""
    route_state: str = ""
    status_facets: Tuple[StatusFacet, ...] = ()
    attributes: Dict[str, str] = field(default_factory=dict)

    @property
    def glyph(self) -> str:
        return NodeStatus.GLYPH.get(self.status, "•")

    @property
    def is_built(self) -> bool:
        return self.status in (NodeStatus.BUILT, NodeStatus.THIN)

    def one_line(self) -> str:
        return f"{self.glyph} {self.key} — {self.does}".strip()


def derive_status(*, has_code_evidence: bool, maturity: str) -> str:
    """Derive NodeStatus from evidence × maturity (NODE-SCHEMA / CC rule).

    ``beta`` / ``stable`` with code → built; ``alpha``/development/experimental → thin;
    no code → spec; maturity deprecated → deprecated.
    """
    m = (maturity or "").strip().lower()
    if m == "deprecated":
        return NodeStatus.DEPRECATED
    if not has_code_evidence:
        return NodeStatus.SPEC
    if m in ("alpha", "development", "experimental"):
        return NodeStatus.THIN
    return NodeStatus.BUILT


def default_confidence(lives: Tuple[NodeEvidence, ...] | list) -> float:
    """SDK-owned confidence heuristic (wireframe navigator rubric / FR-4).

    0.9 = code+test · 0.6 = partial/doc-only · 0.4 = pure spec (no lives).
    """
    types = {getattr(e, "type", "") or (e.get("type") if isinstance(e, dict) else "") for e in lives}
    types.discard("")
    if "code" in types and "test" in types:
        return 0.9
    if types & {"code", "test", "doc", "link"}:
        return 0.6
    return 0.4


def node_field_names() -> Tuple[str, ...]:
    """Runtime field names on :class:`Node` (for the field-compat golden)."""
    return tuple(f.name for f in fields(Node))
