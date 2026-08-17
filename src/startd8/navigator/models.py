"""NODE-SCHEMA node model (renderer-independent).

Copy-port of ContextCore ``navigator/models.py`` (field-compatible) plus the
SDK-owned ``default_confidence`` heuristic (FR-4 — not a CC symbol).

Cite: ``dev-os/NODE-SCHEMA.md`` v0.4.0+ (SDK-side; the dev-os doc + ContextCore mirror follow as a
coordinated cross-repo handoff — REQ-16 NR-1 / REQ-17 NR-3).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Dict, List, Optional, Sequence, Tuple

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


class RealizationRegime:
    """How a node was realized — which back-end produced it (REQ-18). Carried (declared) on a
    :class:`DerivationEdge`'s ``regime`` slot; a node's realization is *derived* from its incoming edges.

    ``deterministic`` = the ``$0`` deterministic compiler · ``llm`` = the LLM interpreter ·
    ``human`` = human-authored · ``unknown`` = undeclared (an edge with no regime). ``mixed`` is a
    **derived-only** facet value for a parent whose subtree spans regimes — never stored on an edge.
    """

    DETERMINISTIC = "deterministic"
    LLM = "llm"
    HUMAN = "human"
    UNKNOWN = "unknown"
    MIXED = "mixed"  # derived-only (a spanning parent) — never a declared edge value

    DECLARABLE = (DETERMINISTIC, LLM, HUMAN)      # values an edge may declare
    ALL = (DETERMINISTIC, LLM, HUMAN, UNKNOWN)    # values a single node's regime may resolve to


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
class DerivationEdge:
    """A typed **derivation** relation on a Node (REQ-16 FR-1) — distinct from containment ``children``
    and from the generic ``child_keys`` reference edge.

    ``from_key`` is the upstream node this one was derived/compiled *from*; ``relation`` names the
    derivation kind (default ``derived-from``). ``regime`` is an OPTIONAL, currently-**unset** slot
    reserved for edge-carried realization (``deterministic | llm | human``) per the OQ-6 decision — this
    REQ only reserves it; populating it, deriving node realization, and the determinism-% rollup are the
    later realization REQ (REQ-16 NR-6). Keep it ``None`` here.
    """

    from_key: str
    relation: str = "derived-from"
    regime: Optional[str] = None  # reserved (unset) — the realization REQ fills this


class EdgeRelation:
    """The relation values a :class:`DerivationEdge` may carry (no new edge *structure* — REQ-20 NR-3).

    ``DERIVED_FROM`` = the forward compilation relation (REQ-16). ``REVISES`` = a **backward** feedback
    relation (REQ-20): a Lesson node proposing a revision to the upstream node named by ``from_key`` —
    distinct from ``derived-from`` and from containment ``children``, and inert until human-accepted.
    """

    DERIVED_FROM = "derived-from"
    REVISES = "revises"

    ALL = (DERIVED_FROM, REVISES)


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
    # REQ-17 (ADR impl) — reliability semantics carried natively instead of dropped at det_req→Node:
    verify: str = ""                        # the acceptance oracle — the FR's raw Verify clause
    approve: Tuple[str, ...] = ()           # the human-approval gate — the FR's Approve? prompt(s)
    was: Tuple[str, ...] = ()               # the change-history alias — the FR's Was value(s)
    # REQ-16 FR-1 — the typed derivation edge (distinct from containment ``children``); regime unset.
    derivation: Tuple[DerivationEdge, ...] = ()

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


# ── REQ-16 FR-2 — the canonical documented field manifest (the schema-as-Node self-check) ──────────
# The single in-SDK source of truth for what fields the Node carries + a one-line meaning each. The
# field-parity conformance test (``test_schema_conformance``) asserts ``node_field_names()`` equals the
# manifest's keys, so adding a Node field in code without documenting it here fails the gate — the drift
# class that left ``dev-os/NODE-SCHEMA.md`` §1 stale (it omitted category/orientation/…). REQ-17's three
# promoted fields register here (FR-3); a later realization REQ documents ``regime`` once it is populated.
NODE_FIELD_MANIFEST: Tuple[Tuple[str, str], ...] = (
    ("key", "the node's stable identity / short reference"),
    ("does", "the WHAT — the behaviour or capability the node delivers"),
    ("status", "build-state (built/thin/spec/deprecated), derived from evidence × maturity"),
    ("wont", "explicit non-goals / out-of-scope constraints"),
    ("lives", "typed evidence references (code/test/doc/link) — where it is realised"),
    ("ships_when", "activation condition when there is no evidence yet"),
    ("confidence", "0.9/0.6/0.4 grounding heuristic unless authored"),
    ("triggers", "signals/conditions that activate the node"),
    ("children", "nested child Nodes (containment drill — the sub-tree)"),
    ("child_keys", "keys of dependency/reference nodes (DEPENDS-ON)"),
    ("category", "grouping axis (which section the node lands in)"),
    ("orientation", "NODE-SCHEMA orientation axis (e.g. bridge)"),
    ("route_state", "routing / honest-skip (sdk_emitted, owned_elsewhere, …)"),
    ("status_facets", "orthogonal health facets (NODE-SCHEMA inv. 5)"),
    ("attributes", "open extension bag (name/handle/serves/…)"),
    ("verify", "REQ-17 — the acceptance oracle (the FR's raw Verify clause)"),
    ("approve", "REQ-17 — the human-approval gate (the FR's Approve? prompt(s))"),
    ("was", "REQ-17 — the change-history alias (the FR's Was value(s))"),
    ("derivation", "REQ-16 — the typed derivation edge (distinct from containment; regime reserved/unset)"),
)


def field_parity_drift(actual: Sequence[str], manifest: Sequence[str]) -> List[str]:
    """Named drift messages between an actual field set and the documented manifest (REQ-16 FR-2).

    Empty list ⇒ parity holds. A field in code but not the manifest, or in the manifest but not code,
    each produces a distinct, named message so the conformance gate points at exactly what drifted.
    """
    actual_set, manifest_set = set(actual), set(manifest)
    drift: List[str] = []
    for f in actual:
        if f not in manifest_set:
            drift.append(f"Node field {f!r} is present in code but absent from NODE_FIELD_MANIFEST")
    for m in manifest:
        if m not in actual_set:
            drift.append(f"manifest field {m!r} is documented but absent from Node code")
    return drift


# ── REQ-16 FR-3 — the shared status/gap-class taxonomy the SDK classifiers agree on ────────────────
# ``derive_status`` (NodeStatus) and det_req's ``fr_health`` measure different axes but both project onto
# one gap-class taxonomy. The status-derivation agreement test (``test_status_agreement``) pins that both
# SDK classifiers map each shared fixture onto the SAME gap-class, and exports ``status_contract.json`` so
# a cross-repo twin (``extract.py`` / ``req-health.mjs``) can run the same fixtures against its own impl.
GAP_CLASSES: Tuple[str, ...] = ("grounded", "gap", "excluded", "unknown")

_STATUS_TO_GAP = {
    NodeStatus.BUILT: "grounded",
    NodeStatus.THIN: "grounded",
    NodeStatus.SPEC: "gap",
    NodeStatus.DEPRECATED: "excluded",
}
_HEALTH_TO_GAP = {
    "on_track": "grounded",
    "n/a": "gap",
    "skipped": "excluded",
    "unknown": "unknown",
}


def status_gap_class(status: str) -> str:
    """Map a NodeStatus (``derive_status`` output) onto the shared gap-class (REQ-16 FR-3)."""
    return _STATUS_TO_GAP.get(status, "unknown")


def health_gap_class(health: str) -> str:
    """Map a det_req ``fr_health`` verdict onto the shared gap-class (REQ-16 FR-3)."""
    return _HEALTH_TO_GAP.get(health, "unknown")
