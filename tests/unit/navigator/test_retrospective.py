"""REQ-20 — Lesson node + human-gated `revises` feedback edge (the retrospective bookend, increment 1).

The load-bearing guarantee (FR-4/FR-7): a Lesson PROPOSES; the human DISPOSES. The `revises` edge is inert
until `accepted`, and no code path applies a revise autonomously — propose, don't dispose.
"""

from __future__ import annotations

from startd8.navigator.govern import Finding
from startd8.navigator.models import EdgeRelation, node_field_names
from startd8.navigator.sources_retrospective import (
    LESSON_CATEGORY,
    LessonStatus,
    accept_lesson,
    build_lesson_from_regression,
    derived_from_edges,
    is_grounded,
    lesson_status,
    reject_lesson,
    revise_is_active,
    revises_edges,
)


def _regression(fr="FR-1"):
    return Finding("FR-6", "fail", "REQ-x.md",
                   f"node {fr!r} was PLANNED deterministic but MEASURED llm — a determinism regression.",
                   fr=fr)


# ── FR-1 — Lesson is a Node projection, no Node field change ────────────────────────────────────────

def test_lesson_is_a_node_projection_no_field_change():
    lesson = build_lesson_from_regression(_regression())
    assert lesson.category == LESSON_CATEGORY
    # the golden: no new Node field (Lesson = category + attributes; revises = a relation value)
    assert set(node_field_names()) == {
        "key", "does", "status", "wont", "lives", "ships_when", "confidence", "triggers",
        "children", "child_keys", "category", "orientation", "route_state", "status_facets",
        "attributes", "verify", "approve", "was", "derivation",
    }


# ── FR-5 / FR-3 / FR-2 — regression → grounded proposed Lesson with derived-from + revises ──────────

def test_build_lesson_from_regression_grounds_and_revises():
    lesson = build_lesson_from_regression(_regression("FR-7"))
    # FR-2 grounding: derived-from the outcome + lives citing it
    df = derived_from_edges(lesson)
    assert len(df) == 1 and df[0].from_key == "regression:FR-7"
    assert lesson.lives and is_grounded(lesson)
    # FR-3 revises: a backward relation value pointing at the offending contract node
    rv = revises_edges(lesson)
    assert len(rv) == 1 and rv[0].relation == EdgeRelation.REVISES and rv[0].from_key == "FR-7"
    # revises is distinct from derived-from (not mis-traversed)
    assert rv[0].from_key != df[0].from_key
    # FR-4: defaults proposed
    assert lesson_status(lesson) == LessonStatus.PROPOSED


def test_ungrounded_lesson_is_not_grounded():
    from startd8.navigator.models import Node
    assert not is_grounded(Node(key="lesson:x", does="", category="lesson"))   # no derived-from, no lives


# ── FR-4 / FR-7 — propose, don't dispose (the human gate) ──────────────────────────────────────────

def test_revise_inert_until_accepted():
    lesson = build_lesson_from_regression(_regression())
    assert revise_is_active(lesson) is False                       # proposed → inert
    accepted = accept_lesson(lesson)
    assert lesson_status(accepted) == LessonStatus.ACCEPTED and revise_is_active(accepted) is True
    # original is unchanged (frozen) — accept returns a new node
    assert lesson_status(lesson) == LessonStatus.PROPOSED


def test_rejected_lesson_retained_with_rationale_and_inert():
    lesson = build_lesson_from_regression(_regression())
    rejected = reject_lesson(lesson, "the llm realization was intentional here")
    assert lesson_status(rejected) == LessonStatus.REJECTED
    assert rejected.attributes["rationale"] == "the llm realization was intentional here"  # retained, not deleted
    assert revise_is_active(rejected) is False                     # rejected → still inert


def test_fr7_no_autonomous_apply_path_exists():
    """FR-7 negative test: the module exposes NO function that APPLIES a revise / mutates an upstream node
    — the revise is a proposal held in the IR. The only gate (`revise_is_active`) merely REPORTS accept."""
    import startd8.navigator.sources_retrospective as retro
    apply_names = [n for n in dir(retro) if "apply" in n.lower() or "mutate" in n.lower()]
    assert apply_names == [], f"REQ-20 must expose no autonomous apply-revise path; found {apply_names}"
    # and the gate is False for every non-accepted status (nothing could apply while proposed/rejected)
    lesson = build_lesson_from_regression(_regression())
    assert not revise_is_active(lesson) and not revise_is_active(reject_lesson(lesson, "no"))


# ── FR-6 — render the loop (Mieruka): backward edges, revises distinguished ─────────────────────────

def test_fr6_lesson_backward_edges_render_revises_distinguished(tmp_path):
    """FR-6: a graph render of a Lesson shows its derived-from + revises edges, with revises visibly
    distinguished (its own colour/dash), through the EXISTING graph renderer (no new shell)."""
    from startd8.navigator.models import Node, NodeEvidence
    from startd8.navigator.render_graph import render_navigator_graph_html

    lesson = build_lesson_from_regression(_regression("FR-7"))
    contract = Node(key="FR-7", does="the offending contract", category="functional-requirements")
    outcome = Node(key="regression:FR-7", does="the determinism regression outcome", category="outcome",
                   lives=(NodeEvidence(type="link", ref="x"),))
    out = tmp_path / "loop.html"
    render_navigator_graph_html([lesson, contract, outcome], out, semantic_only=True)
    html = out.read_text()
    assert "revises" in html and "derived-from" in html            # both backward edges labelled
    assert "#bc8cff" in html and "#39c5cf" in html                 # revises (violet) ≠ derived-from (cyan)


# ── FR-7 — additive, byte-identical (the wireframe app path is untouched) ───────────────────────────

def test_fr7_wireframe_render_byte_identical():
    """FR-7: the Lesson/edge work is graph-renderer-only; the wireframe app path stays byte-identical."""
    from startd8.wireframe import (
        ContentCoverageStats,
        WireframeItem,
        WireframePlan,
        WireframeSection,
    )
    from startd8.wireframe_view.view import render_html

    item = WireframeItem(label="FR-1 — x", status="spec", detail="", paths=())
    sec = WireframeSection(key="identity", title="Identity", status="spec", items=(item,))
    plan = WireframePlan(project_root=".", sections=(sec,), input_provenance={}, merge_warnings=(),
                         shape={"nodes": 1}, readiness={}, status_counts={"spec": 1},
                         content_coverage=ContentCoverageStats())
    assert render_html(plan) == render_html(plan, profile=None)
