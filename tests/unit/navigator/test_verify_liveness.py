"""REQ-22 — verify-liveness: a requirement can't read verified while its check attests nothing.

The negative-control fixture is NetBSD `O-4` — its `make parity` gate went structurally impossible after a
faithful refactor, yet it passes every structural check. This proves the liveness check catches present-but-
dead (not just absent), reusing verify_oracle (no new engine).
"""

from __future__ import annotations

from startd8.navigator.det_req import parse_fr_lines
from startd8.navigator.govern import (
    check_realization_invariant,
    check_verify_liveness,
    recheck_verify_liveness_on_drift,
)
from startd8.navigator.models import DerivationEdge, Node, NodeEvidence, node_field_names

_LIVES = (NodeEvidence(type="code", ref="git:" + "a" * 40 + ":src/x.py"),)


def _node(key="O-4", verify="session ≡ old_session", gate="", lives=_LIVES, derivation=()):
    return Node(key=key, does="", lives=lives, verify=verify, verify_gate=gate, derivation=derivation)


# ── FR-1 — the optional verify_gate field + parse ──────────────────────────────────────────────────

def test_fr1_gate_field_and_parse():
    assert "verify_gate" in node_field_names() and len(node_field_names()) == 20
    fr = parse_fr_lines("- **FR-1 — X.** does. Name: a thing. Gate: `startd8 navigator build`. "
                        "Verify: it works. Serves: O-1")[0]
    assert fr["gate"] == "`startd8 navigator build`"
    assert parse_fr_lines("- **FR-2 — Y.** z. Name: y. Verify: prose. Serves: O-1")[0]["gate"] == ""


# ── FR-2/FR-3 — dead gate is a loud GAP; live gate flags 0 ─────────────────────────────────────────

def test_fr2_dead_gate_is_a_gap_live_gate_is_clean():
    # NetBSD O-4: a `make parity` gate that no longer resolves to a runnable command → structural death
    dead = _node(gate="make parity")                                   # no runnable allow-listed span
    f = check_verify_liveness([dead], "netbsd.md")
    assert len(f) == 1 and f[0].check == "FR-2" and f[0].ref == "gap:structural"
    assert "DEAD" in f[0].message and f[0].severity == "fail"           # a FACT (gap), loud

    # a live gate (an allow-listed navigator command) flags nothing
    live = _node(gate="`startd8 navigator build --source pipeline --format json`")
    assert check_verify_liveness([live]) == []

    # an un-realized node (no lives) is never checked — liveness unknown (activation gate)
    assert check_verify_liveness([_node(gate="make parity", lives=())]) == []


# ── FR-4 — absence-vs-error: a provenance-reason gate is a precision CANDIDATE, not a territory fail ─

def test_fr4_missing_input_gate_is_a_provenance_candidate():
    gate = "`startd8 navigator build --source requirements --requirements /nope/missing.md --format json`"
    f = check_verify_liveness([_node(gate=gate)])
    assert len(f) == 1 and f[0].ref == "candidate:provenance" and f[0].severity == "advisory"
    assert "provenance" in f[0].message                                # distinct from the structural GAP


# ── FR-5 — re-check liveness on impl-provenance change (the drift move) ────────────────────────────

def test_fr5_recheck_on_impl_provenance_change():
    # a node whose gate is dead, depending on impl "stage:impl" via a derivation edge
    node = _node(gate="make parity", derivation=(DerivationEdge(from_key="stage:impl"),))
    # re-check triggered only for nodes depending on the changed impl
    assert recheck_verify_liveness_on_drift([node], {"stage:impl"}) != []   # its gate is now re-flagged
    assert recheck_verify_liveness_on_drift([node], {"stage:other"}) == []  # not affected → not re-checked


# ── FR-6 — a dead gate routes to a human-gated retrospective Lesson ────────────────────────────────

def test_fr6_dead_gate_routes_to_a_proposed_lesson():
    from startd8.navigator.sources_retrospective import (
        LessonStatus,
        build_lesson_from_liveness_gap,
        derived_from_edges,
        lesson_status,
        revises_edges,
    )

    f = check_verify_liveness([_node(gate="make parity")], "netbsd.md")[0]
    lesson = build_lesson_from_liveness_gap(f)
    assert lesson.category == "lesson" and lesson_status(lesson) == LessonStatus.PROPOSED
    assert derived_from_edges(lesson)[0].from_key == "verify-liveness:O-4"
    assert revises_edges(lesson)[0].from_key == "O-4"                   # proposes revising the requirement


# ── FR-7 — invariant 9 strengthened: present-but-dead verify violates ──────────────────────────────

def test_fr7_invariant9_present_but_dead_verify_violates():
    llm = (DerivationEdge(from_key="up", regime="llm"),)
    # a realized llm node with a PRESENT verify but a DEAD gate → now a violation (was a pass under presence)
    dead = _node(verify="prose claim", gate="make parity", derivation=llm)
    vf = check_realization_invariant([dead])
    assert len(vf) == 1 and "DEAD" in vf[0].message
    # the same node with a LIVE gate → no violation
    live = _node(verify="prose claim", gate="`startd8 navigator build`", derivation=llm)
    assert check_realization_invariant([live]) == []
    # empty verify still violates (the original invariant-9 case)
    assert len(check_realization_invariant([_node(verify="", gate="", derivation=llm)])) == 1


# ── FR-8 — advisory + clean corpus flags 0 (byte-identity is asserted in test_render_profile) ──────

def test_fr8_clean_corpus_flags_zero():
    clean = [_node(key="FR-1", verify="it works", gate=""),          # prose-only verify → not this check
             _node(key="FR-2", gate="`startd8 navigator build --source pipeline --format json`")]  # live gate
    assert check_verify_liveness(clean) == []                        # a clean corpus is silent
