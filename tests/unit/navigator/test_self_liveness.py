"""REQ-27 — self-dogfood the verify gate: adopt it on our OWN corpus, honestly.

The corpus authored "a requirement can't read verified while its check attests nothing" while ~96% of its
own verifies were present-but-dead prose. The honest fix is a three-part split, not a blanket campaign:
classify each verify mechanical-vs-manual (FR-1), adopt a `Gate:` where the verify claims a runnable check
(FR-2), MARK the legitimately-manual ones (FR-3), and stand up an advisory self-gate that reports adoption
and routes the real gap to a human triage (FR-4/FR-5) without ever blocking.

Every check here reuses the built REQ-22/23 machinery (`verify_oracle` + `_gate_liveness` + the REQ-20
Lesson) — no new engine (FR-6).
"""

from __future__ import annotations

from pathlib import Path

from startd8.navigator.det_req import parse_fr_lines, parse_manual
from startd8.navigator.govern import (
    _gate_liveness,
    check_self_dogfood_verify_gates,
    classify_corpus_verifies,
    lessons_from_self_dogfood,
    render_self_dogfood_text,
)
from startd8.navigator.models import Node, node_field_names
from startd8.navigator.sources_requirements import nodes_from_requirements
from startd8.navigator.verify_oracle import classify

CORPUS = Path(__file__).resolve().parents[3] / "docs/design/requirements-visualization"

_FR = "- **FR-{i} — {t}.** does it. Name: a name for it. Lives: code src/startd8/navigator/govern.py. "


def _doc(tmp_path, *bullets, name="REQ-x-fixture.md") -> Path:
    p = tmp_path / name
    p.write_text(
        "# X — Requirements\n\n**Format:** det-req/0.1\n\n"
        "> **Readable handle:** `feature/x-1234abcd`\n"
        "> **Semantic name:** *X does a thing*\n\n"
        "## Functional requirements\n\n" + "\n".join(bullets) + "\n",
        encoding="utf-8",
    )
    return p


def _mechanical(i=1, gate="", manual=""):
    """An FR whose Verify NAMES a runnable span (verify_oracle → `command`)."""
    return (
        _FR.format(i=i, t="A mechanical claim")
        + (f"Gate: {gate}. " if gate else "")
        + (f"Manual: {manual}. " if manual else "")
        + "Verify: `startd8 navigator build --source pipeline --format json` exits 0. Serves: O-1"
    )


def _prose(i=2, manual=""):
    """An FR whose Verify is prose acceptance (verify_oracle → `assertion`)."""
    return (
        _FR.format(i=i, t="A prose claim")
        + (f"Manual: {manual}. " if manual else "")
        + "Verify: a reviewer confirms the shape reads honestly. Serves: O-1"
    )


# ── FR-1 — the mechanical/manual honesty split, via verify_oracle ──────────────────────────────────

def test_fr1_split_buckets_each_verify_and_separates_the_real_gap(tmp_path):
    doc = _doc(tmp_path, _mechanical(1), _prose(2), _prose(3))
    report = classify_corpus_verifies(tmp_path)

    assert [r.kind for r in report.rows] == ["command", "assertion", "assertion"]
    # the ONE misleading "dead" number resolves into a real gap + an honest-manual count
    assert [r.fr for r in report.mechanical_gateless] == ["FR-1"]
    assert len(report.honest_manual) == 2 and report.adoption_rate == 0.0
    assert report.docs == [doc.name]


def test_fr1_reuses_the_one_verify_oracle_classifier(tmp_path):
    """NR-3 — the split IS `verify_oracle.classify`; no second classifier may disagree with it."""
    _doc(tmp_path, _mechanical(1), _prose(2))
    rows = {r.fr: r.kind for r in classify_corpus_verifies(tmp_path).rows}
    oracle = {d.fr_id: d.kind for d in classify(next(tmp_path.glob("REQ-*.md")))}
    assert rows == oracle


# ── FR-2 — adopting a gate moves adoption off zero, and the gate resolves ──────────────────────────

def test_fr2_adopted_gate_closes_the_gap_and_lifts_adoption(tmp_path):
    gate = "`startd8 navigator build --source pipeline --format json`"
    _doc(tmp_path, _mechanical(1, gate=gate), _mechanical(2))
    report = classify_corpus_verifies(tmp_path)

    assert [r.fr for r in report.mechanical_with_gate] == ["FR-1"]
    assert [r.fr for r in report.mechanical_gateless] == ["FR-2"]
    assert report.adoption_rate == 0.5
    # the adopted handle is LIVE under REQ-22's own resolver — adoption that actually attests
    assert report.rows[0].gate_state == "live" and not report.dead_gates


def test_fr2_a_gate_that_does_not_resolve_is_reported_not_silently_counted(tmp_path):
    _doc(tmp_path, _mechanical(1, gate="make parity"))
    report = classify_corpus_verifies(tmp_path)
    assert [r.fr for r in report.dead_gates] == ["FR-1"]
    refs = [f.ref for f in check_self_dogfood_verify_gates(tmp_path)]
    assert "self-dogfood:dead-gate" in refs


def test_fr2_the_corpus_has_actually_adopted_gates_that_are_not_dead():
    """The dogfood itself: our OWN corpus carries ≥9 parseable, non-dead `Gate:` handles (was 0/180)."""
    report = classify_corpus_verifies(CORPUS)
    gated = report.gated
    assert len(gated) >= 9, [r.fr for r in gated]
    assert all(r.gate_state in ("live", "unrunnable-provenance") for r in gated), [
        (r.doc, r.fr, r.gate_state) for r in gated if r.gate_state not in ("live", "unrunnable-provenance")
    ]
    # every adopted gate resolves through REQ-22's resolver, not a second one
    assert all(_gate_liveness(n)[0] != "dead-structural"
               for n in (Node(key=r.fr, does="", verify_gate=r.gate) for r in gated))
    assert report.adoption_rate > 0.0
    assert not report.dead_gates, [(r.doc, r.fr, r.gate) for r in report.dead_gates]


# ── FR-3 — the explicit manual marker (no new Node field) ──────────────────────────────────────────

def test_fr3_manual_marker_parses_and_does_not_pollute_verify_or_lives():
    fr = parse_fr_lines(
        "- **FR-1 — X.** does. Name: a thing. Lives: code src/startd8/navigator/govern.py. "
        "Manual: human acceptance — a reviewer reads it. Verify: it reads honestly. Serves: O-1"
    )[0]
    assert fr["manual"] == "human acceptance — a reviewer reads it"
    assert fr["verify"] == "it reads honestly"                       # marker did not leak into the verify
    assert fr["lives"] == [{"type": "code", "ref": "src/startd8/navigator/govern.py"}]
    # unmarked FRs are unchanged (additive)
    assert parse_fr_lines("- **FR-2 — Y.** z. Name: y. Verify: prose. Serves: O-1")[0]["manual"] == ""
    assert parse_manual("no marker here")[1] == ""


def test_fr3_marked_manual_leaves_the_gap_count_and_an_unmarked_mechanical_does_not(tmp_path):
    _doc(tmp_path,
         _mechanical(1, manual="human acceptance — the runnable half is the unit suite"),
         _mechanical(2))
    report = classify_corpus_verifies(tmp_path)

    marked = {r.fr: r for r in report.rows}
    assert marked["FR-1"].marked_manual and not marked["FR-1"].mechanical   # excluded from the gap
    assert marked["FR-1"].honest_manual and marked["FR-1"].kind == "command"
    assert [r.fr for r in report.mechanical_gateless] == ["FR-2"]           # the unmarked one is NOT
    # the override is honoured but never silent — a command-shaped verify claimed manual is reported
    assert "self-dogfood:manual-override" in [f.ref for f in check_self_dogfood_verify_gates(tmp_path)]


def test_fr3_marker_rides_attributes_not_a_new_node_field(tmp_path):
    """No Node field #21 — the marker projects through the typed-attributes channel (REQ-08 Stage)."""
    doc = _doc(tmp_path, _prose(1, manual="human acceptance — a reviewer reads it"), _prose(2))
    nodes = {n.key: n for n in nodes_from_requirements(doc)}
    assert nodes["FR-1"].attributes["verify_kind"] == "manual"
    assert "human acceptance" in nodes["FR-1"].attributes["verify_manual_why"]
    assert "verify_kind" not in nodes["FR-2"].attributes          # unmarked → byte-identical projection
    assert len(node_field_names()) == 20 and "verify_kind" not in node_field_names()


def test_fr3_the_corpus_marks_its_ironic_prose_verifies():
    """The dogfood: REQ-22 — which authored the cure while 8/8 prose — now says so explicitly."""
    rows = [r for r in classify_corpus_verifies(CORPUS).rows if r.doc.startswith("REQ-22-")]
    assert rows and all(r.marked_manual and r.honest_manual for r in rows), [
        (r.fr, r.marked_manual) for r in rows
    ]


def test_fr3_a_prose_mention_of_gate_or_manual_is_not_a_marker():
    """The false-mechanical guard: a label is invented from prose only if the parse is case-blind.
    `REQ-04` FR-6 ("the top acceptance gate: if it fails, …") used to parse as a present-but-DEAD gate."""
    fr = parse_fr_lines(
        "- **FR-1 — X.** This is the top acceptance gate: if it fails, the refactor is rejected. "
        "Optional manual: compare a re-run. Name: a thing. Verify: it reads honestly. Serves: O-1"
    )[0]
    assert fr["gate"] == "" and fr["manual"] == ""


# ── FR-4 — the standing advisory self-gate ─────────────────────────────────────────────────────────

def test_fr4_self_gate_reports_adoption_and_the_gap_and_never_blocks(tmp_path):
    _doc(tmp_path, _mechanical(1), _prose(2, manual="human acceptance — a reviewer reads it"))
    findings = check_self_dogfood_verify_gates(tmp_path)

    headline = [f for f in findings if f.ref == "self-dogfood:adoption"]
    assert len(headline) == 1 and "adoption" in headline[0].message
    gaps = [f for f in findings if f.ref == "self-dogfood:mechanical-gateless"]
    assert [f.fr for f in gaps] == ["FR-1"] and "adopt a `Gate:`" in gaps[0].message
    # NR-2 — advisory ONLY: nothing the self-gate emits can fail a pipeline
    assert {f.severity for f in findings} == {"advisory"}


def test_fr4_runs_over_our_own_corpus_and_stays_advisory():
    findings = check_self_dogfood_verify_gates(CORPUS)
    assert findings and {f.severity for f in findings} == {"advisory"}
    text = render_self_dogfood_text(classify_corpus_verifies(CORPUS))
    assert "verify.gate adoption" in text and "never blocks" in text


def test_fr4_is_reachable_from_the_spec_delivery_loop(tmp_path, capsys):
    """FR-4 — the self-gate is integrable into the Spec Delivery Loop (`--self-dogfood`), not just built."""
    import importlib.util

    script = Path(__file__).resolve().parents[3] / "scripts/navigator_spec_delivery_loop.py"
    spec = importlib.util.spec_from_file_location("sdl_self_dogfood", script)
    sdl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sdl)

    _doc(tmp_path, _mechanical(1), _prose(2, manual="human acceptance — a reviewer reads it"))
    assert sdl.run_self_dogfood(tmp_path) == 0            # advisory: the loop's exit code is untouched
    out = capsys.readouterr().out
    assert "verify.gate adoption" in out and "proposed triage lesson" in out
    assert "--self-dogfood" in script.read_text(encoding="utf-8")


def test_fr4_does_not_join_the_fixed_five_check_govern_battery():
    """REQ-06 NR-6 — the charter is five checks; the self-gate is opt-in, never a sixth."""
    from startd8.navigator.govern import GovernReport

    assert sorted(GovernReport("x").checks_summary()) == ["FR-1", "FR-2", "FR-3", "FR-4", "FR-5"]


# ── FR-5 — a mechanical-but-gateless FR routes to a human triage lesson ────────────────────────────

def test_fr5_gateless_mechanical_fr_routes_to_a_proposed_triage_lesson(tmp_path):
    from startd8.navigator.sources_retrospective import (
        LessonStatus,
        derived_from_edges,
        is_grounded,
        lesson_status,
        revise_is_active,
        revises_edges,
    )

    _doc(tmp_path, _mechanical(1), _prose(2))
    findings = check_self_dogfood_verify_gates(tmp_path)
    lessons = lessons_from_self_dogfood(findings)

    assert len(lessons) == 1
    lesson = lessons[0]
    assert lesson.category == "lesson" and lesson_status(lesson) == LessonStatus.PROPOSED
    assert is_grounded(lesson)                                     # grounded in its outcome (REQ-20 FR-2)
    assert derived_from_edges(lesson)[0].from_key == "self-dogfood:FR-1"
    assert revises_edges(lesson)[0].from_key == "FR-1"
    assert not revise_is_active(lesson)                            # propose, don't dispose — never applied
    assert "adopt a `Gate:`" in lesson.attributes["proposes"]
    assert "`Manual:`" in lesson.attributes["proposes"]             # the OTHER honest option


def test_fr5_reports_and_headlines_are_not_routed_as_proposals(tmp_path):
    """Only the real gap becomes a proposal — the adoption headline and the notes are reports."""
    _doc(tmp_path, _mechanical(1, gate="make parity"), _prose(2))
    findings = check_self_dogfood_verify_gates(tmp_path)
    assert {f.ref for f in findings} >= {"self-dogfood:adoption", "self-dogfood:dead-gate"}
    assert lessons_from_self_dogfood(findings) == []   # no mechanical-gateless FR → no proposal


def test_fr5_never_a_silent_green_for_a_command_without_a_gate(tmp_path):
    _doc(tmp_path, _mechanical(1))
    findings = check_self_dogfood_verify_gates(tmp_path)
    assert any(f.ref == "self-dogfood:mechanical-gateless" and f.fr == "FR-1" for f in findings)
    assert len(lessons_from_self_dogfood(findings)) == 1


# ── FR-6 — reuse, additive, byte-identical ────────────────────────────────────────────────────────

def test_fr6_self_gate_reuses_the_built_liveness_layer_and_adds_no_engine():
    """The gate resolver IS REQ-22's `_gate_liveness`; the classifier IS `verify_oracle`."""
    import inspect

    from startd8.navigator import govern

    src = inspect.getsource(govern.classify_corpus_verifies)
    assert "_gate_liveness" in src and "verify_oracle" in src
    assert not any(w in src for w in ("subprocess", "Popen", "os.system"))  # no execution, structural only


def test_fr6_an_unmarked_ungated_corpus_projects_exactly_as_before(tmp_path):
    """Additive: a doc with neither `Gate:` nor `Manual:` yields the same Node projection as before."""
    doc = _doc(tmp_path, _prose(1), _prose(2))
    for n in nodes_from_requirements(doc):
        assert n.verify_gate == ""
        assert "verify_kind" not in n.attributes and "verify_manual_why" not in n.attributes
