"""REQ-18 — realization regime derivation + the confidence-aware seam (the firewall).

The load-bearing test is the FIREWALL (FR-2): a stub low-confidence provenance match must DEGRADE to the
declared regime, never assert the low-confidence value. That guarantee is what makes REQ-19's measured
grounding safe.
"""

from __future__ import annotations

from startd8.navigator.models import DerivationEdge, Node, RealizationRegime
from startd8.navigator.realization import (
    CONFIDENCE_THRESHOLD,
    derive_realization,
    determinism_pct,
    format_determinism_line,
    node_regime,
    realization_facet,
    resolve_edge_regime,
)


def _leaf(key, regime):
    return Node(key=key, does="", derivation=(DerivationEdge(from_key="up", regime=regime),))


# ── FR-2 — the confidence-aware seam (the (b)-ready firewall) ──────────────────────────────────────

def test_seam_returns_declared_when_no_provenance_source():
    """FR-2 (a): with no provenance source wired, the declared regime always stands."""
    e = DerivationEdge(from_key="up", regime=RealizationRegime.DETERMINISTIC)
    assert resolve_edge_regime(Node(key="x", does=""), e, provenance=None) == "deterministic"


def test_seam_degrades_low_confidence_match_to_declared():
    """FR-2 FIREWALL: a stub provenance match BELOW the confidence threshold degrades to the declared
    value — it never asserts the low-confidence measurement. This is the integrity guarantee for (b)."""
    class LowConfidenceSource:
        def regime_for(self, node, edge):
            return (RealizationRegime.LLM, CONFIDENCE_THRESHOLD - 0.01)   # says llm, but not confidently

    e = DerivationEdge(from_key="up", regime=RealizationRegime.DETERMINISTIC)
    # declared=deterministic; the low-confidence 'llm' must NOT override → stays deterministic
    assert resolve_edge_regime(Node(key="x", does=""), e, LowConfidenceSource()) == "deterministic"


def test_seam_degrades_no_match_and_undeclared_to_unknown():
    """FR-2: a source that can't match an UNDECLARED edge degrades to unknown (never invents)."""
    class NoMatchSource:
        def regime_for(self, node, edge):
            return None

    e = DerivationEdge(from_key="up")  # regime=None → undeclared
    assert resolve_edge_regime(Node(key="x", does=""), e, NoMatchSource()) == "unknown"


def test_seam_accepts_high_confidence_measured_value():
    """FR-2: at/above threshold, a valid measured regime DOES override the declared value (the seam is
    ready for (b) — it isn't inert, it's gated)."""
    class HighConfidenceSource:
        def regime_for(self, node, edge):
            return (RealizationRegime.LLM, 0.99)

    e = DerivationEdge(from_key="up", regime=RealizationRegime.DETERMINISTIC)
    assert resolve_edge_regime(Node(key="x", does=""), e, HighConfidenceSource()) == "llm"


def test_seam_rejects_invalid_measured_value():
    """FR-2 firewall: a high-confidence but non-declarable measured value degrades to declared."""
    class JunkSource:
        def regime_for(self, node, edge):
            return ("banana", 0.99)

    e = DerivationEdge(from_key="up", regime=RealizationRegime.HUMAN)
    assert resolve_edge_regime(Node(key="x", does=""), e, JunkSource()) == "human"


# ── FR-1 / node_regime — a node's own regime from its edges ─────────────────────────────────────────

def test_node_regime_from_single_edge_and_undeclared():
    assert node_regime(_leaf("a", RealizationRegime.LLM)) == "llm"
    assert node_regime(Node(key="b", does="")) == "unknown"                 # no edge
    assert node_regime(Node(key="c", does="", derivation=(DerivationEdge(from_key="u"),))) == "unknown"


def test_node_with_differing_edges_is_mixed():
    n = Node(key="m", does="", derivation=(
        DerivationEdge(from_key="a", regime="deterministic"),
        DerivationEdge(from_key="b", regime="llm"),
    ))
    assert node_regime(n) == "mixed"


# ── FR-3 — distribution over the subtree (not a min-rollup) ─────────────────────────────────────────

def test_leaf_distribution_is_its_single_regime():
    assert derive_realization(_leaf("a", RealizationRegime.DETERMINISTIC)) == {"deterministic": 1}


def test_parent_distribution_aggregates_subtree_counts():
    """FR-3 Verify: a parent over two deterministic + one llm leaf → {deterministic: 2, llm: 1}."""
    parent = Node(key="p", does="", children=(
        _leaf("l1", "deterministic"), _leaf("l2", "deterministic"), _leaf("l3", "llm"),
    ))
    assert derive_realization(parent) == {"deterministic": 2, "llm": 1}   # parent itself is unknown → excluded


# ── FR-6 — the derived facet (incl. mixed) ──────────────────────────────────────────────────────────

def test_facet_single_regime_mixed_and_unknown():
    assert realization_facet(_leaf("a", "llm")) == "llm"
    assert realization_facet(Node(key="bare", does="")) == "unknown"
    spanning = Node(key="p", does="", children=(_leaf("l1", "deterministic"), _leaf("l2", "llm")))
    assert realization_facet(spanning) == "mixed"


def test_facet_query_selects_llm_realized_nodes():
    """FR-6: faceting a corpus by realization:llm returns the llm-realized nodes."""
    nodes = [_leaf("a", "deterministic"), _leaf("b", "llm"), _leaf("c", "llm"), Node(key="d", does="")]
    llm = [n.key for n in nodes if realization_facet(n) == "llm"]
    assert llm == ["b", "c"]


# ── FR-4 — determinism-% + honestly-labeled line ───────────────────────────────────────────────────

def test_determinism_pct_and_empty():
    assert determinism_pct({"deterministic": 9, "llm": 1}) == 0.9
    assert determinism_pct({}) is None


def test_format_line_labeled_declared_and_none_when_empty():
    line = format_determinism_line({"deterministic": 9, "llm": 1})
    assert "90% $0" in line and "(declared)" in line and "9 deterministic / 1 llm / 0 human" in line
    assert "measured" not in line                                    # (a) is declared, never measured
    assert format_determinism_line({}) is None                       # no regime data → no line
    assert "(measured)" in format_determinism_line({"deterministic": 1}, grounded=True)  # (b) relabels


def test_fr6_realization_facet_exposed_in_tree_facet_engine():
    """FR-6 wired: the tree renderer's facet engine (_facets_html) exposes realization:<regime> for a
    node with a declared regime, and nothing for an unknown node (byte-identical for regimeless graphs)."""
    from startd8.navigator.render_tree import _facets_html

    assert "realization:deterministic" in _facets_html(_leaf("a", "deterministic"))
    assert _facets_html(Node(key="bare", does="")) == ""      # no regime, no status facets → no chip
