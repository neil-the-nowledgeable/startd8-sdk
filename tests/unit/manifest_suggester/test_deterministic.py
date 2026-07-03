# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Deterministic ($0) core tests for the Manifest Suggester — baseline, grounding, store."""

from __future__ import annotations

from startd8.manifest_extraction.extractors import extract_views
from startd8.manifest_extraction.grammar import parse_sections
from startd8.manifest_extraction.models import Status
from startd8.manifest_suggester import (
    KIND_VIEW,
    PROV_BASELINE,
    ScreenCandidate,
    ScreenCandidateStore,
    baseline_views,
    build_graph,
    dedupe_missing,
    ground,
    pick_root,
)

# Order<->Product is an explicit M2M via OrderItem; User->Order is a 1:N FK.
SCHEMA = """
model User { id String @id
 name String
 orders Order[]
}
model Order { id String @id
 userId String
 user User @relation(fields: [userId], references: [id])
 items OrderItem[]
}
model Product { id String @id
 name String
 items OrderItem[]
}
model OrderItem {
 orderId String
 productId String
 order Order @relation(fields: [orderId], references: [id])
 product Product @relation(fields: [productId], references: [id])
 @@id([orderId, productId])
}
"""

SIMPLE = "model Widget { id String @id\n name String\n}"


def _not_extracted(records):
    return [r for r in records if r.status == Status.NOT_EXTRACTED]


# ── FR-MS-1 baseline: single root, join-gated, round-trips (R1-F2/R2-F2) ──────


def test_baseline_is_single_root_and_join_gated():
    graph = build_graph(SCHEMA)
    assert pick_root(graph) == "Order"  # most-connected (FK child + M2M member)
    cand = baseline_views(SCHEMA)[0]
    assert cand.kind == KIND_VIEW
    assert cand.provenance == PROV_BASELINE
    # exactly one Root line; a Shows only for the real M2M partner (Product), never the FK-only User
    assert cand.prose.count("Root:") == 1
    assert "Shows: Order→Product" in cand.prose
    assert "User" not in cand.prose  # 1:N FK is NOT a valid Shows target


def test_baseline_round_trips_through_extract_views():
    # the AUTHORITATIVE gate (FR-MS-5): the emitted prose must parse cleanly.
    graph = build_graph(SCHEMA)
    cand = baseline_views(SCHEMA)[0]
    records = []
    view = extract_views("t", parse_sections(cand.prose), graph, records)
    assert view is not None
    assert _not_extracted(records) == []  # nothing rejected


def test_baseline_degrades_to_bare_dashboard_when_no_joins():
    # Ask 5 safe fallback: a lone entity → a bare single-root dashboard, still round-trip-clean.
    graph = build_graph(SIMPLE)
    cand = baseline_views(SIMPLE)[0]
    assert "Shows:" not in cand.prose
    records = []
    assert extract_views("t", parse_sections(cand.prose), graph, records) is not None
    assert _not_extracted(records) == []


def test_baseline_empty_schema_yields_nothing():
    assert baseline_views("") == []


# ── FR-MS-4 grounding guard (necessary, not sufficient) ───────────────────────


def test_ground_accepts_baseline():
    graph = build_graph(SCHEMA)
    assert bool(ground(baseline_views(SCHEMA)[0], graph)) is True


def test_ground_rejects_unknown_entity():
    graph = build_graph(SCHEMA)
    bad = ScreenCandidate(
        kind=KIND_VIEW,
        name="Ghost Dashboard",
        prose="### view: Ghost Dashboard\nKind: dashboard\nRoot: Ghost\n",
        entities_referenced=("Ghost",),
    )
    result = ground(bad, graph)
    assert bool(result) is False
    assert any("does not resolve" in r for r in result.reasons)


def test_ground_rejects_bad_kind():
    graph = build_graph(SCHEMA)
    bad = ScreenCandidate(
        kind=KIND_VIEW,
        name="Order Thing",
        prose="### view: Order Thing\nKind: hologram\nRoot: Order\n",
        entities_referenced=("Order",),
    )
    result = ground(bad, graph)
    assert bool(result) is False
    assert any("outside the published vocabulary" in r for r in result.reasons)


# ── FR-MS-3 dedupe by extractor slug (R1-F5/R1-S7) ────────────────────────────


def test_dedupe_missing_by_slug():
    a = ScreenCandidate(kind=KIND_VIEW, name="Signup Funnel", prose="x")
    b = ScreenCandidate(kind=KIND_VIEW, name="Order Dashboard", prose="y")
    # an existing "signup-funnel" slug drops the case/space variant, keeps the new one
    kept = dedupe_missing([a, b], existing_slugs={"signup-funnel"})
    assert [c.name for c in kept] == ["Order Dashboard"]


def test_dedupe_within_batch():
    a = ScreenCandidate(kind=KIND_VIEW, name="Sales View", prose="x")
    a2 = ScreenCandidate(kind=KIND_VIEW, name="sales-view", prose="x2")
    kept = dedupe_missing([a, a2], existing_slugs=set())
    assert len(kept) == 1  # same slug within the batch → one survives


# ── FR-MS-7 staging reuses the shared toolkit ─────────────────────────────────


def test_store_is_toolkit_based_and_roundtrips(tmp_path):
    from startd8.persona_drafting.staging import JsonSessionStore

    assert issubclass(ScreenCandidateStore, JsonSessionStore)
    store = ScreenCandidateStore(tmp_path, "screens-abc")
    store.save(baseline_views(SCHEMA, session_id="screens-abc"))
    loaded = store.load()
    assert loaded[0].name == "Order Dashboard"
    assert loaded[0].provenance == PROV_BASELINE


def test_store_gc_inherited_from_toolkit(tmp_path):
    for i in range(4):
        ScreenCandidateStore(tmp_path, f"screens-{i}").save(
            [ScreenCandidate(kind=KIND_VIEW, name=f"V{i}", prose="x")]
        )
    assert len(ScreenCandidateStore.session_ids(tmp_path)) == 4
    ScreenCandidateStore.gc(tmp_path, keep=1)
    assert len(ScreenCandidateStore.session_ids(tmp_path)) == 1
