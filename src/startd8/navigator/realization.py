"""Realization regime derivation (REQ-18) — how each node was realized, derived from its edges.

Approach (a): a **declared** regime read through a **confidence-aware provenance SEAM**. The seam is the
(b)-ready integrity firewall: it reads regime from an OPTIONAL provenance source and, when that source is
absent OR its match confidence is below the threshold, **degrades to the declared regime (or ``unknown``)
— it never asserts a measurement it cannot ground.** In (a) no source is wired, so the declared value
always stands; REQ-19 (b) fills the seam with measured construction provenance without a rewrite.

**No construction-subsystem import (NR-2).** This module must not import ``backend_codegen`` /
``contractors`` / ``micro_prime`` — the seam references provenance only through the stable typed
:class:`ProvenanceSource` contract; (b) implements that contract on the construction side.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterator, Mapping, Optional, Protocol, Tuple

from .models import DerivationEdge, Node, RealizationRegime

# The seam's confidence floor — a provenance match strictly below this degrades to the declared value
# (the firewall: never assert a low-confidence measurement). (b) may tune it; (a) never crosses it.
CONFIDENCE_THRESHOLD = 0.5


class ProvenanceSource(Protocol):
    """The (b)-ready seam contract. A measured-provenance source (built in REQ-19) implements this; in
    (a) none is wired. ``regime_for`` returns ``(measured_regime, confidence)`` for an edge, or ``None``
    when it cannot match the edge to construction provenance."""

    def regime_for(self, node: Node, edge: DerivationEdge) -> Optional[Tuple[str, float]]:
        ...


def _declared(edge: DerivationEdge) -> str:
    """The edge's declared regime, normalized — a declarable value or ``unknown`` (never ``None``/junk)."""
    return edge.regime if edge.regime in RealizationRegime.DECLARABLE else RealizationRegime.UNKNOWN


def resolve_edge_regime(
    node: Node, edge: DerivationEdge, provenance: Optional[ProvenanceSource] = None
) -> str:
    """Resolve ONE edge's regime through the seam (FR-2 — the firewall).

    Returns the declared regime unless a provenance source returns a match **at or above** the confidence
    threshold; an absent source, a no-match, a below-threshold confidence, or a non-declarable measured
    value all **degrade to the declared value** — the seam never asserts what it cannot ground.
    """
    declared = _declared(edge)
    if provenance is None:
        return declared
    match = provenance.regime_for(node, edge)
    if match is None:
        return declared
    measured, confidence = match
    if confidence < CONFIDENCE_THRESHOLD or measured not in RealizationRegime.DECLARABLE:
        return declared  # firewall: low-confidence / invalid measurement never overrides the declared value
    return measured


def node_regime(node: Node, provenance: Optional[ProvenanceSource] = None) -> str:
    """A single node's OWN realization regime, through the seam. From its incoming derivation edge(s):
    edges of one regime → that; differing → ``mixed``. When the node has NO edge-derived regime, REQ-19
    (b) grounds it directly from a **measured** provenance match on its ``lives`` file (threshold-gated) —
    so a generated requirement node (lives, no edge) still gets a measured regime; else ``unknown``."""
    regimes = {resolve_edge_regime(node, e, provenance) for e in node.derivation}
    regimes.discard(RealizationRegime.UNKNOWN)
    if len(regimes) == 1:
        return next(iter(regimes))
    if len(regimes) > 1:
        return RealizationRegime.MIXED
    # No edge-derived regime → REQ-19 FR-4/5: a measured per-node match via lives (edge-less generated
    # nodes). Threshold-gated exactly like the edge seam, so a weak join degrades to unknown, never asserts.
    measured = _measured_node_regime(node, provenance)
    return measured if measured is not None else RealizationRegime.UNKNOWN


def _measured_node_regime(node: Node, provenance: Optional[ProvenanceSource]) -> Optional[str]:
    """REQ-19 FR-4: the measured regime for a node from a provenance match on its ``lives`` file, gated by
    :data:`CONFIDENCE_THRESHOLD` (the seam's honesty firewall). ``None`` when no source, no match, a
    below-threshold match, or a non-declarable value — never asserts what it cannot ground."""
    if provenance is None:
        return None
    match = provenance.regime_for(node, None)  # a measured source joins on the node's lives, not an edge
    if match is None:
        return None
    regime, confidence = match
    if confidence < CONFIDENCE_THRESHOLD or regime not in RealizationRegime.DECLARABLE:
        return None
    return regime


def _walk(node: Node) -> Iterator[Node]:
    """The node's subtree (itself + all containment descendants via ``children``)."""
    yield node
    for child in node.children:
        yield from _walk(child)


def derive_realization(node: Node, provenance: Optional[ProvenanceSource] = None) -> Dict[str, int]:
    """The DISTRIBUTION of realization regimes over ``node``'s subtree (FR-3) — derived, not stored (like
    ``status``), and NOT a min-rollup (realization is a spread, not a worst-case).

    Each subtree node contributes its resolved :func:`node_regime`; ``unknown`` is excluded (an undeclared
    node adds no signal). A leaf with one ``deterministic`` edge yields ``{deterministic: 1}``; a parent
    over two ``deterministic`` and one ``llm`` leaf yields ``{deterministic: 2, llm: 1}``.
    """
    dist: Counter = Counter()
    for n in _walk(node):
        regime = node_regime(n, provenance)
        if regime != RealizationRegime.UNKNOWN:
            dist[regime] += 1
    return dict(dist)


def realization_facet(node: Node, provenance: Optional[ProvenanceSource] = None) -> str:
    """The node's derived §3a facet value (FR-6): its single subtree regime, ``mixed`` when the subtree
    spans regimes, or ``unknown`` when the subtree declares none. Faceting a corpus by
    ``realization:llm`` selects nodes whose facet resolves to ``llm``."""
    dist = derive_realization(node, provenance)
    if not dist:
        return RealizationRegime.UNKNOWN
    if len(dist) == 1:
        return next(iter(dist))
    return RealizationRegime.MIXED


def determinism_pct(distribution: Dict[str, int]) -> Optional[float]:
    """The headline determinism fraction = ``deterministic / total`` over a regime distribution, or
    ``None`` when the distribution is empty (no regime data → the summary renders no determinism line)."""
    total = sum(distribution.values())
    if total == 0:
        return None
    return distribution.get(RealizationRegime.DETERMINISTIC, 0) / total


def format_determinism_line(distribution: Dict[str, int], *, grounded: bool = False) -> Optional[str]:
    """The summary-altitude realization line (FR-4), deterministic + speakable (SV-7), e.g.
    ``28 deterministic / 3 llm / 0 human — 90% $0 (declared)``. Labeled ``declared`` in (a) until a
    provenance source grounds it (``grounded=True`` → ``measured``). ``None`` when there is no regime data.
    """
    pct = determinism_pct(distribution)
    if pct is None:
        return None
    counts = " / ".join(
        f"{distribution.get(r, 0)} {r}" for r in RealizationRegime.DECLARABLE
    )
    label = "measured" if grounded else "declared"
    return f"{counts} — {round(pct * 100)}% $0 ({label})"


# ── REQ-19 (b) — measured realization: the join + the labeled corpus rollup ─────────────────────────
# The navigator imports only the CONTRACT (a construction-free coupling surface, FR-7) — never a
# construction subsystem. The per-file regime map is produced by ``realization_provenance.normalize``.

def _path_of_ref(ref: str) -> str:
    """Strip a ``git:<sha>:<path>`` evidence ref down to its bare path (the join key); others pass through."""
    if ref.startswith("git:"):
        parts = ref.split(":", 2)
        return parts[2] if len(parts) == 3 else ref
    return ref


class MeasuredProvenanceSource:
    """REQ-19 FR-4 — a :class:`ProvenanceSource` that joins a normalized per-file regime map to a Node's
    ``lives`` refs by file path, yielding the node's measured ``(regime, source_confidence)`` for REQ-18's
    seam. A node whose lives match no file yields ``None`` (no measured regime — the seam degrades to
    declared; no crash). ``edge`` is ignored: the measurement is per-node/file, not per-transform."""

    def __init__(self, per_file_map: Mapping[str, Any]):
        self._map = per_file_map

    def regime_for(self, node: Node, edge: Optional[DerivationEdge] = None) -> Optional[Tuple[str, float]]:
        for ev in getattr(node, "lives", ()) or ():
            rec = self._map.get(_path_of_ref(ev.ref))
            if rec is not None:
                return (rec.regime, rec.source_confidence)
        return None


def corpus_realization(
    nodes, provenance: Optional[ProvenanceSource] = None
) -> Tuple[Dict[str, int], bool]:
    """REQ-19 FR-5 — the corpus regime distribution over all ``nodes`` PLUS a ``grounded`` flag: ``True``
    when the provenance source contributed at least one **above-threshold measured** regime, so the
    summary relabels ``measured``; else ``declared`` (the honest fallback — a corpus of only low-confidence
    matches stays declared). Returns ``({} , False)`` for an empty/regimeless corpus."""
    dist: Counter = Counter()
    grounded = False
    for root in nodes:
        for n in _walk(root):
            regime = node_regime(n, provenance)
            if regime != RealizationRegime.UNKNOWN:
                dist[regime] += 1
            if provenance is not None and _measured_node_regime(n, provenance) is not None:
                grounded = True
    return dict(dist), grounded
