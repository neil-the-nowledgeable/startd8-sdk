# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""The `$0` schema-grounded baseline (FR-MS-1 — composite, NOT CRUD; single-root, join-gated).

Emits a **starter dashboard view** over the primary entities as authoring-contract prose, deterministically
and with no LLM. Two CRP-triaged corrections baked in:

* **Single `Root` + join-gated relations (R1-F2/R2-F2).** ``extract_views`` resolves exactly **one**
  ``Root:`` entity; additional entities enter only via ``Shows: A→B`` and only when an **M2M
  ``join_between``** actually connects them (an FK 1:N does not satisfy ``Shows:``). So the baseline
  picks one root and adds ``Shows:`` lines **only** for entities the graph's derived joins connect —
  otherwise the ``$0`` default would fail the very round-trip it exists to satisfy (Ask 4/Ask 5).
* **Built on the extractor's own ``EntityGraph`` (R2-F2/R2-S2).** ``graph_from_prisma(parse_prisma_schema)``
  — the *exact* object the round-trip extractor uses — so the baseline's "grounded" verdict and the
  extractor's "round-trips" verdict cannot diverge.

Degrades safely: with no joins, it emits a bare single-root dashboard (always round-trip-clean, Ask 5).
"""

from __future__ import annotations

from typing import List, Optional

from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.manifest_extraction.entities import EntityGraph, graph_from_prisma

from startd8.manifest_suggester.models import KIND_VIEW, PROV_BASELINE, ScreenCandidate

__all__ = ["build_graph", "pick_root", "baseline_views"]


def build_graph(schema_text: str) -> EntityGraph:
    """The extractor's own ``EntityGraph`` for *schema_text* (R2-F2 — same object, not a parallel type)."""
    return graph_from_prisma(parse_prisma_schema(schema_text or ""))


def _degree(graph: EntityGraph, entity: str) -> int:
    """Connection count: FK parents/children + M2M join memberships (root-selection heuristic)."""
    deg = len(graph.fk_parents.get(entity, []))
    deg += sum(1 for child, parents in graph.fk_parents.items() if entity in parents)
    deg += sum(1 for j in graph.joins if entity in (j.left, j.right))
    return deg


def pick_root(graph: EntityGraph) -> Optional[str]:
    """The most-connected entity (deterministic tie-break: schema-declaration order)."""
    names = list(graph.entities.keys())
    if not names:
        return None
    return max(names, key=lambda e: (_degree(graph, e), -names.index(e)))


def _joined_partners(graph: EntityGraph, root: str) -> List[str]:
    """Entities connected to *root* by an M2M derived join (the only valid ``Shows:`` targets)."""
    partners: List[str] = []
    for j in graph.joins:
        if root == j.left and j.right not in partners:
            partners.append(j.right)
        elif root == j.right and j.left not in partners:
            partners.append(j.left)
    return partners


def baseline_views(schema_text: str, *, session_id: str = "") -> List[ScreenCandidate]:
    """Propose the `$0` starter dashboard view(s) over the primary entities. Deterministic, no LLM."""
    graph = build_graph(schema_text)
    root = pick_root(graph)
    if root is None:
        return []

    partners = _joined_partners(graph, root)
    name = f"{root} Dashboard"
    # Authoring-contract grammar: a `### view:` section with `- Key: value` list-item lines
    # (grammar.key_lines terminates the block at the first non-`- Key:` line).
    lines = [f"### view: {name}", "- Kind: dashboard", f"- Root: {root}"]
    for partner in partners:
        lines.append(f"- Shows: {root}→{partner}")
    prose = "\n".join(lines) + "\n"

    return [
        ScreenCandidate(
            kind=KIND_VIEW,
            name=name,
            prose=prose,
            entities_referenced=(root, *partners),
            provenance=PROV_BASELINE,
            session_id=session_id,
        )
    ]
