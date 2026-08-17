"""REQ-23 — the liveness layer's fact-first cells (target-unmeasured + served-by-a-dead-FR).

Both are FACTS (structural death → GAP, no precision tuning) that can't cry wolf, rolled into the single
`liveness` govern layer beside REQ-22's verify-liveness.
"""

from __future__ import annotations

from startd8.navigator.govern import (
    check_liveness_layer,
    check_served_by_dead_fr,
    check_target_unmeasured,
)
from startd8.navigator.models import Node, NodeEvidence
from startd8.navigator.sources_requirements import outcome_nodes_from_requirements

_LIVES = (NodeEvidence(type="code", ref="git:" + "a" * 40 + ":src/x.py"),)


def _fr(key, serves, gate="", lives=_LIVES):
    return Node(key=key, does="", category="functional-requirements", lives=lives, verify="claim",
                verify_gate=gate, attributes={"serves": serves})


def _objectives_doc(tmp_path, body):
    doc = tmp_path / "REQ-x.md"
    doc.write_text("# X — Requirements\n\n**Format:** det-req/0.1\n\n## Objectives\n\n" + body + "\n",
                   encoding="utf-8")
    return doc


# ── FR-1 — outcome projection with target + optional signal ────────────────────────────────────────

def test_fr1_outcome_nodes_carry_target_and_signal(tmp_path):
    doc = _objectives_doc(tmp_path,
                          "- **O-1:** Measured coverage — target: 90% of nodes measured. Signal: `cov_ratio`.\n"
                          "- **O-2:** A goal — target: every node bound.")
    outs = {n.key: n for n in outcome_nodes_from_requirements(doc)}
    assert outs["O-1"].category == "objective" and outs["O-1"].attributes["target_signal"] == "`cov_ratio`"
    assert outs["O-2"].attributes["target"] and outs["O-2"].attributes["target_signal"] == ""  # unmeasured


# ── FR-2 — target-unmeasured is a GAP (fact) ───────────────────────────────────────────────────────

def test_fr2_target_without_signal_is_a_gap(tmp_path):
    doc = _objectives_doc(tmp_path,
                          "- **O-1:** Bound — target: X. Signal: `metric_x`.\n"
                          "- **O-2:** Unbound — target: Y.")
    f = check_target_unmeasured(outcome_nodes_from_requirements(doc), "REQ-x.md")
    assert len(f) == 1 and f[0].fr == "O-2" and f[0].ref == "liveness:target-unmeasured"
    assert f[0].severity == "fail"                                   # a FACT (gap), not a candidate


# ── FR-3 — served-by-a-dead-FR (verify-liveness rolled up the serves edge) ─────────────────────────

def test_fr3_outcome_served_only_by_dead_frs_is_a_gap():
    # O-1 served by two FRs, both with dead gates → GAP; O-2 served by one dead + one LIVE → clean
    frs = [
        _fr("FR-1", "O-1", gate="make parity"),                      # dead
        _fr("FR-2", "O-1", gate="make check"),                       # dead
        _fr("FR-3", "O-2", gate="make parity"),                      # dead
        _fr("FR-4", "O-2", gate="`startd8 navigator build --source pipeline --format json`"),  # LIVE
    ]
    f = {x.fr: x for x in check_served_by_dead_fr(frs)}
    assert "O-1" in f and f["O-1"].ref == "liveness:served-by-a-dead-fr"
    assert "O-2" not in f                                            # one live serving FR clears it


def test_fr3_ignores_unrealized_and_prose_only():
    # a prose-only FR (no gate) is UNAUTOMATED, not dead → doesn't flag its outcome
    assert check_served_by_dead_fr([_fr("FR-1", "O-1", gate="")]) == []
    # an un-realized (no lives) FR is not counted
    assert check_served_by_dead_fr([_fr("FR-1", "O-1", gate="make parity", lives=())]) == []


# ── FR-4 — a dead cell routes to a human-gated retrospective Lesson ────────────────────────────────

def test_fr4_gap_routes_to_a_proposed_lesson():
    from startd8.navigator.sources_retrospective import build_lesson_from_liveness_gap, lesson_status

    f = check_served_by_dead_fr([_fr("FR-1", "O-1", gate="make parity")])[0]
    lesson = build_lesson_from_liveness_gap(f)
    assert lesson_status(lesson) == "proposed" and lesson.key == "lesson:O-1"


# ── FR-5 — one liveness layer (all three cells, tagged) ────────────────────────────────────────────

def test_fr5_liveness_layer_reports_all_three_cells(tmp_path):
    doc = _objectives_doc(tmp_path, "- **O-9:** Unbound — target: Z.")
    outcomes = outcome_nodes_from_requirements(doc)
    frs = [
        _fr("FR-1", "O-1", gate="make parity"),                      # dead → verify-liveness + served-by-dead
        _fr("FR-2", "O-1", gate="make check"),                       # dead
    ]
    layer = check_liveness_layer(frs, outcomes, "REQ-x.md")
    cells = {f.ref for f in layer}
    assert "liveness:verify-liveness" in cells                       # REQ-22 cell
    assert "liveness:target-unmeasured" in cells                     # REQ-23 cell 1 (O-9)
    assert "liveness:served-by-a-dead-fr" in cells                   # REQ-23 cell 2 (O-1)
    assert all(str(f.ref).startswith("liveness:") for f in layer)    # ONE layer, not a scatter


# ── FR-6 — clean corpus flags 0 (byte-identity in test_render_profile) ─────────────────────────────

def test_fr6_clean_corpus_is_silent(tmp_path):
    doc = _objectives_doc(tmp_path, "- **O-1:** Bound — target: X. Signal: `metric_x`.")
    clean_frs = [_fr("FR-1", "O-1", gate="`startd8 navigator build --source pipeline --format json`")]
    assert check_liveness_layer(clean_frs, outcome_nodes_from_requirements(doc)) == []
