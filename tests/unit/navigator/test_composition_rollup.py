"""REQ-feature-capability-composition-rollup — FR-keyed regression pins.

Mostly reuse: a feature declares (via Serves:/Composes:) the capability it composes up to, the combined
source joins both node sets, the EXISTING `serves` edge draws it, and a ground-up rank puts capabilities
above their features. These pin FR-1..FR-6 including the backward-compat + byte-identity guards.
"""

from __future__ import annotations

import pytest

from startd8.navigator.det_req import parse_fr_lines
from startd8.navigator.graph_projection import nodes_to_graph
from startd8.navigator.render_graph import _layout
from startd8.navigator.sources_capability import (
    default_capability_index_path,
    nodes_from_capability_index,
)
from startd8.navigator.sources_requirements import nodes_from_requirements

pytestmark = pytest.mark.unit


def _serves(line: str):
    frs = parse_fr_lines(line)
    return frs[0]["serves"] if frs else None


_REQ = """# Widget — Requirements

**Format:** det-req/0.1
> **Semantic name:** *w.*
> **Canonical ref:** `cc:intent:x:feature:req-w`

## Objectives
- **O-1:** builds.

## Functional requirements
- **FR-1 — Build.** Name: build. Touches: `src/x.py`. Verify: ok. Serves: O-1, startd8.provider.registry
"""


# ── FR-1: parser (backward-compatible) ─────────────────────────────────────────────────────────────


def test_fr1a_objectives_still_parse_byte_for_byte():
    assert _serves("- **FR-1 — X.** does. Verify: ok. Serves: O-1, O-2") == [
        "O-1",
        "O-2",
    ]


def test_fr1b_capability_target_parses_alongside_objective():
    assert _serves(
        "- **FR-1 — X.** does. Verify: ok. Serves: O-2, startd8.provider.registry"
    ) == ["O-2", "startd8.provider.registry"]


def test_fr1c_composes_dotted_and_cap_handle_parse_whole():
    assert _serves(
        "- **FR-1 — X.** does. Verify: ok. Composes: startd8.provider.registry"
    ) == ["startd8.provider.registry"]
    assert _serves("- **FR-1 — X.** does. Verify: ok. Composes: CAP-7") == ["CAP-7"]


# ── FR-2/FR-3: combined source joins both, existing serves edge draws it ──────────────────────────


def test_fr2_combined_source_joins_and_draws_the_composition_edge(tmp_path):
    req = tmp_path / "REQ-w.md"
    req.write_text(_REQ, encoding="utf-8")
    nodes = list(nodes_from_requirements(req)) + list(
        nodes_from_capability_index(default_capability_index_path())
    )
    g = nodes_to_graph(nodes)
    ids = {n["id"] for n in g["nodes"]}
    assert any(i.startswith("FR") for i in ids)  # feature node present
    assert "startd8.provider.registry" in ids  # capability node present
    comp = [
        e
        for e in g["edges"]
        if e["label"] == "serves"
        and e["from"].startswith("FR")
        and e["to"] == "startd8.provider.registry"
    ]
    assert comp, "the feature→capability serves edge is drawn in the joined graph"
    assert comp[0]["data"]["semantic"] is True


def test_fr3_no_new_edge_kind_for_composition():
    # the composition edge REUSES `serves` — no composes-specific edge label was added to the projection.
    import inspect

    import startd8.navigator.graph_projection as gp

    src = inspect.getsource(gp)
    assert "composes-edge" not in src and '"composes"' not in src


# ── FR-4: ground-up rank ─────────────────────────────────────────────────────────────────────────


def test_fr4_ground_up_ranks_capability_above_features():
    gnodes = [
        {"id": "FR-1", "at": {"x": 0.5, "y": 0.5}},
        {"id": "cap.x", "at": {"x": 0.5, "y": 0.5}},
    ]
    edges = [{"from": "FR-1", "to": "cap.x", "label": "serves"}]
    gu = _layout(gnodes, edges, rank_direction="ground-up")
    assert (
        gu["cap.x"][1] < gu["FR-1"][1]
    )  # capability (root band) above the feature (base)


def test_fr4_default_layout_byte_identical():
    gnodes = [
        {"id": "FR-1", "at": {"x": 0.4, "y": 0.6}},
        {"id": "cap.x", "at": {"x": 0.6, "y": 0.3}},
    ]
    edges = [{"from": "FR-1", "to": "cap.x", "label": "serves"}]
    assert _layout(gnodes, edges) == _layout(gnodes, edges, rank_direction=None)


# ── FR-5: corpus-agnostic primitive (generic, not FR-special-cased) ──────────────────────────────


def test_fr5_serves_edge_is_generic_not_fr_special_cased():
    # a non-FR-keyed node with a `serves` attribute also yields a `serves` edge (the primitive is at the
    # Node level, the SDK realization of ContextCore EB-4 objective→objective).
    from startd8.navigator.models import Node

    src = Node(key="O-1", does="an objective", attributes={"serves": "cap.top"})
    tgt = Node(key="cap.top", does="a capability")
    g = nodes_to_graph([src, tgt])
    assert any(
        e["label"] == "serves" and e["from"] == "O-1" and e["to"] == "cap.top"
        for e in g["edges"]
    )


# ── FR-6: byte-identity / backward-compat ─────────────────────────────────────────────────────────


def test_fr6_all_objectives_req_unchanged():
    # an all-O-N req parses exactly as before (the extended token tries O-N first).
    assert _serves("- **FR-9 — X.** does. Verify: ok. Serves: O-1, O-2, O-3") == [
        "O-1",
        "O-2",
        "O-3",
    ]
