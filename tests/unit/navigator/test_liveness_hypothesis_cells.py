"""REQ-25 — the liveness layer's HYPOTHESIS cells (fact-rungs ship, judgment-rungs park-by-default).

The discipline: each hypothesis cell = a deterministic FACT-rung (ships as a GAP/trigger, reusing an
existing checker — NR-2) + a semantic JUDGMENT-rung (parked-by-default behind a precision gate — NR-3/4;
a false GAP is a durable-red-carrying-no-truth). This proves the fact-rungs fire and the judgment-rungs
stay inert (execute nothing) until precision-cleared AND their judge is verify-live.
"""

from __future__ import annotations

from startd8.navigator.govern import (
    PRECISION_THRESHOLD,
    JudgmentRung,
    check_liveness_layer,
    check_mitigation_inert,
    check_non_goal_violated,
    check_touches_provenance_changed,
    is_unparked,
    judgment_rung_for,
    lessons_from_liveness_layer,
    run_judgment_rung,
)
from startd8.navigator.models import Node, NodeEvidence

_INJECTION = 'def q(cur, name):\n    cur.execute(f"SELECT * FROM users WHERE name = {name}")\n'
_SAFE = 'def q(cur, name):\n    cur.execute("SELECT * FROM users WHERE name = ?", (name,))\n'
_LIVE_GATE = "`startd8 navigator build --source pipeline --format json`"


def _node(key, *, lives_path=None, mitigation="", wont=(), gate=""):
    lives = (NodeEvidence(type="code", ref=str(lives_path)),) if lives_path else ()
    attrs = {"security_mitigation": mitigation} if mitigation else {}
    return Node(key=key, does="", category="functional-requirements", lives=lives, wont=tuple(wont),
                verify_gate=gate, attributes=attrs)


# ── FR-1 — mitigation-inert fact-rung (reuse the security verifier) ─────────────────────────────────

def test_fr1_declared_mitigation_the_verifier_reports_absent_is_a_gap(tmp_path):
    vuln = tmp_path / "q.py"
    vuln.write_text(_INJECTION, encoding="utf-8")
    f = check_mitigation_inert([_node("FR-1", lives_path=vuln, mitigation="injection")], doc="REQ-x.md")
    assert len(f) == 1 and f[0].ref == "liveness:mitigation-inert" and f[0].severity == "fail"


def test_fr1_present_mitigation_yields_none(tmp_path):
    safe = tmp_path / "q.py"
    safe.write_text(_SAFE, encoding="utf-8")
    assert check_mitigation_inert([_node("FR-1", lives_path=safe, mitigation="injection")]) == []


def test_fr1_no_declared_mitigation_or_no_code_is_skipped(tmp_path):
    safe = tmp_path / "q.py"
    safe.write_text(_INJECTION, encoding="utf-8")
    assert check_mitigation_inert([_node("FR-1", lives_path=safe, mitigation="")]) == []   # no claim
    assert check_mitigation_inert([_node("FR-1", mitigation="injection")]) == []           # no realized code


# ── FR-2 — non-goal-violated fact-rung (reuse import/AST checks) ────────────────────────────────────

def test_fr2_violated_import_ban_is_a_gap(tmp_path):
    code = tmp_path / "m.py"
    code.write_text("from startd8 import backend_codegen\nx = 1\n", encoding="utf-8")
    f = check_non_goal_violated([_node("FR-2", lives_path=code, wont=("no-import:backend_codegen",))], doc="d")
    assert len(f) == 1 and f[0].ref == "liveness:non-goal-violated" and f[0].severity == "fail"


def test_fr2_respected_non_goal_yields_none(tmp_path):
    code = tmp_path / "m.py"
    code.write_text("import os\nx = 1\n", encoding="utf-8")
    assert check_non_goal_violated([_node("FR-2", lives_path=code, wont=("no-import:backend_codegen",))]) == []


# ── FR-3 — touches-dead re-judge trigger (reuse REQ-19 provenance-change) ───────────────────────────

def test_fr3_touches_file_with_changed_provenance_triggers(tmp_path):
    n = Node(key="FR-3", does="", lives=(NodeEvidence(type="code", ref="src/x.py"),))
    trig = check_touches_provenance_changed([n], {"src/x.py"}, "d")
    assert len(trig) == 1 and trig[0].ref == "liveness:touches-provenance-changed"
    assert check_touches_provenance_changed([n], set()) == []               # nothing changed → none


# ── FR-4/FR-6 — judgment-rungs park by default; un-park needs precision AND a verify-live judge ──────

def test_fr4_parked_by_default_executes_nothing():
    rung = JudgmentRung(cell="mitigation-inert")                            # no precision baseline
    assert is_unparked(rung) is False
    assert run_judgment_rung(rung, candidates=[{"key": "FR-1", "evidence": "bytes"}]) == []


def test_fr4_below_threshold_stays_parked():
    rung = JudgmentRung(cell="x", precision=PRECISION_THRESHOLD - 0.1, judge_verify_live=True)
    assert is_unparked(rung) is False


def test_fr6_judge_must_be_verify_live_to_unpark():
    live_judge = Node(key="judge", does="", verify_gate=_LIVE_GATE)
    dead_judge = Node(key="judge", does="", verify_gate="make parity")      # not a runnable command
    assert judgment_rung_for("x", precision=0.95, judge=live_judge).judge_verify_live is True
    assert judgment_rung_for("x", precision=0.95, judge=dead_judge).judge_verify_live is False
    assert is_unparked(judgment_rung_for("x", precision=0.95, judge=live_judge)) is True
    assert is_unparked(judgment_rung_for("x", precision=0.95, judge=dead_judge)) is False  # dead judge → parked


# ── FR-5 — an un-parked judgment-rung is a CANDIDATE, never a GAP ───────────────────────────────────

def test_fr5_unparked_rung_emits_a_candidate_never_a_gap():
    live_judge = Node(key="judge", does="", verify_gate=_LIVE_GATE)
    rung = judgment_rung_for("mitigation-inert", precision=0.95, judge=live_judge)
    out = run_judgment_rung(rung, candidates=[{"key": "FR-1", "evidence": "the cited bytes"}], doc="d")
    assert len(out) == 1
    assert out[0].severity == "advisory"                                    # a candidate, NOT a fail/GAP
    assert out[0].ref == "candidate:mitigation-inert" and "the cited bytes" in out[0].message


# ── FR-7 — registered in the liveness layer; a confirmed dead claim routes to a Lesson ──────────────

def test_fr7_fact_rungs_register_in_the_liveness_layer(tmp_path):
    vuln = tmp_path / "q.py"
    vuln.write_text(_INJECTION, encoding="utf-8")
    code = tmp_path / "m.py"
    code.write_text("from startd8 import backend_codegen\n", encoding="utf-8")
    frs = [_node("FR-1", lives_path=vuln, mitigation="injection"),
           _node("FR-2", lives_path=code, wont=("no-import:backend_codegen",))]
    layer = check_liveness_layer(frs, (), "REQ-x.md")
    cells = {f.ref for f in layer}
    assert "liveness:mitigation-inert" in cells and "liveness:non-goal-violated" in cells


def test_fr7_gaps_route_to_proposed_lessons_candidates_do_not(tmp_path):
    from startd8.navigator.sources_retrospective import lesson_status

    vuln = tmp_path / "q.py"
    vuln.write_text(_INJECTION, encoding="utf-8")
    layer = check_liveness_layer([_node("FR-1", lives_path=vuln, mitigation="injection")], (), "REQ-x.md")
    lessons = lessons_from_liveness_layer(layer)
    assert lessons and all(lesson_status(les) == "proposed" for les in lessons)   # human-gated (REQ-20)
    # a candidate (advisory) is NOT routed — only facts become proposed revisions
    live_judge = Node(key="j", does="", verify_gate=_LIVE_GATE)
    cand = run_judgment_rung(judgment_rung_for("x", precision=0.95, judge=live_judge),
                             candidates=[{"key": "FR-9", "evidence": "e"}], doc="d")
    assert lessons_from_liveness_layer(cand) == []


# ── FR-8 — additive, byte-identical, parked rungs inert ─────────────────────────────────────────────

def test_fr8_clean_corpus_adds_nothing_and_parked_rungs_execute_nothing():
    clean = [_node("FR-1")]                                                 # no mitigation / no-import / no gate
    # the new cells add nothing on a clean node; parked judgment-rungs execute nothing
    parked = JudgmentRung(cell="mitigation-inert")
    layer = check_liveness_layer(clean, (), "d", judgment_rungs=[parked])
    assert layer == []
