"""REQ-06 corpus governance — the 5-check battery + CLI + the FR-8 precision gate.

Covers:
  (a) FR-8 HEADLINE: `govern_corpus(docs/design/requirements-visualization)` yields ZERO
      fail-severity findings across REQ-01..09 (the shipped acceptance condition).
  (b) per-FR unit tests over a small fixture corpus: a clean 2-doc corpus passes; a no-name-block
      doc fails FR-1; a hard-wrapped-FR doc fails FR-2; a doc citing a missing local REQ fails FR-3;
      a doc whose own deliverable path is cited does NOT fail (the exclusion); an FR missing Verify:
      flags FR-4; the CLI exits 0 / 1 / 2.
  (c) the equivalence guard lives in test_spec_delivery_loop.py (sdl.gate_spec still resolves after
      the lift) — this file additionally asserts govern.gate_spec IS the loop's gate_spec (one home).
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from startd8.cli import app
from startd8.navigator.govern import (
    GovernReport,
    gate_spec,
    govern_corpus,
    render_govern_json,
    render_govern_text,
)

RUNNER = CliRunner()

_CORPUS = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "design"
    / "requirements-visualization"
)
_CLEAN_FIXTURE = Path(__file__).parent / "fixtures" / "govern_clean"


# --- a helper to write a minimal well-formed REQ doc, then perturb one field per test ------------


def _write_req(
    dir_: Path,
    name: str,
    *,
    key: str,
    handle: bool = True,
    semname: bool = True,
    canonical: bool = True,
    cites: str = "",
    touches: str = "`src/startd8/x.py`",
    verify: str = "Verify: `x` exits 0.",
    extra_body: str = "",
) -> Path:
    lines = [f"# {name} — Requirements", "", "**Format:** det-req/0.1", ""]
    if handle:
        lines.append(f"> **Readable handle:** `feature/{name.lower()}`")
    if semname:
        lines.append(f"> **Semantic name:** *A fixture doc named {name}. {cites}*")
    if canonical:
        lines.append(
            f"> **Canonical ref:** `cc:intent:govern-fixture:feature:{key.lower()}`"
        )
    lines += ["", "## Objectives", "", "- O-1: Be a fixture — target: pass", ""]
    lines += ["## Functional requirements", ""]
    lines.append(
        f"- **FR-1 — Do the thing.** It does the thing. {cites} "
        f"Name: {name} does the thing. Touches: {touches}. {verify} Serves: O-1"
    )
    if extra_body:
        lines.append(extra_body)
    lines += ["", "## Non-goals", "", "- NR-1: Nothing."]
    p = dir_ / name if name.endswith(".md") else dir_ / f"{key}-{name.lower()}.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ------------------------------------------------------------------------------------------------ #
# (a) FR-8 headline — zero fail-severity on the current corpus (REQ-01..09)
# ------------------------------------------------------------------------------------------------ #


def test_fr8_precision_gate_current_corpus_has_zero_fail_findings():
    """FR-8: the shipped acceptance condition — the REQ-0n numeric corpus (REQ-01..09) raises NO
    fail-severity finding (zero FALSE positives). Non-numeric REQ docs in the same dir (e.g. the
    stage-0-blocked `REQ-seat-requirement-*` spec, a different initiative) may be legitimate
    TRUE-positive findings — the precision claim is about the conformant numeric corpus, not about
    silencing a real non-conformant outlier."""
    report = govern_corpus(_CORPUS)
    numbered = [f for f in report.fail_findings if f.doc.startswith("REQ-0")]
    assert (
        numbered == []
    ), "REQ-01..09 must govern clean (fail-severity=0); got: " + "; ".join(
        f"{f.doc}:{f.check}:{f.message[:50]}" for f in numbered
    )
    # every remaining fail-severity finding is on a NON-numeric REQ doc (a true positive), not REQ-0n
    assert all(not f.doc.startswith("REQ-0") for f in report.fail_findings)


def test_clean_fixture_corpus_passes():
    """A hand-authored clean 2-doc fixture corpus governs cleanly (no fail-severity)."""
    report = govern_corpus(_CLEAN_FIXTURE)
    assert report.clean is True
    assert report.exit_code == 0
    assert {"REQ-01-alpha.md", "REQ-02-beta.md"}.issubset(set(report.docs))


def test_govern_survives_unreadable_corpus_doc(tmp_path):
    """HTH-P2: an unreadable corpus doc must not abort the battery (orphan-scan OSError guard)."""
    import os

    if os.geteuid() == 0:  # pragma: no cover - root ignores chmod perms
        return
    _write_req(tmp_path, "alpha", key="REQ-01")
    bad = _write_req(tmp_path, "beta", key="REQ-02")
    os.chmod(bad, 0o000)
    try:
        report = govern_corpus(tmp_path)  # must NOT raise despite the unreadable doc
    finally:
        os.chmod(bad, 0o644)  # restore so tmp cleanup can remove it
    assert report is not None  # battery completed


# ------------------------------------------------------------------------------------------------ #
# (b) per-FR unit tests
# ------------------------------------------------------------------------------------------------ #


def test_fr1_no_name_block_fails(tmp_path):
    """FR-1: a doc missing the Readable-handle/Semantic-name block fails (a real fail, not advisory)."""
    _write_req(tmp_path, "Alpha", key="REQ-01")
    _write_req(tmp_path, "Beta", key="REQ-02", handle=False, semname=False)
    report = govern_corpus(tmp_path)
    fr1_fails = [
        f
        for f in report.fail_findings
        if f.check == "FR-1" and f.doc.startswith("REQ-02")
    ]
    assert fr1_fails, "a doc with no name block must raise an FR-1 fail"
    assert report.clean is False
    assert report.exit_code == 1


def test_fr1_missing_canonical_is_advisory_not_fail(tmp_path):
    """FR-1: the ADDED canonical-ref check degrades to advisory (never fails a pre-convention doc)."""
    _write_req(tmp_path, "Alpha", key="REQ-01")
    _write_req(tmp_path, "Beta", key="REQ-02", canonical=False)
    report = govern_corpus(tmp_path)
    assert report.clean is True  # canonical-ref absence never fails the build
    adv = [
        f
        for f in report.advisory_findings
        if f.check == "FR-1" and "Canonical ref" in f.message
    ]
    assert adv, "a doc missing only Canonical ref should raise an FR-1 advisory"


def test_fr2_hardwrapped_fr_fails(tmp_path):
    """FR-2: a hard-wrapped FR bullet (fields on a 2nd physical line) → marker-vs-parse mismatch fail."""
    _write_req(tmp_path, "Alpha", key="REQ-01")
    (tmp_path / "REQ-02-wrapped.md").write_text(
        "# Wrapped — Requirements\n\n"
        "> **Readable handle:** `feature/w`\n> **Semantic name:** *w*\n"
        "> **Canonical ref:** `cc:intent:x:feature:req-02`\n\n"
        "## Objectives\n\n- O-1: x — target: y\n\n"
        "## Functional requirements\n\n"
        # a hard-wrapped FR whose TITLE spans two physical lines: the `- **FR-` marker is present but
        # the per-line bullet regex (needs `.**` on the same line) can't parse it → marker>parse.
        "- **FR-1 — A title that got hard\n"
        "  wrapped mid-sentence.** body. Name: w. Verify: `y`. Serves: O-1\n",
        encoding="utf-8",
    )
    report = govern_corpus(tmp_path)
    fr2 = [
        f
        for f in report.fail_findings
        if f.check == "FR-2" and f.doc.startswith("REQ-02")
    ]
    assert fr2, "a hard-wrapped FR must raise an FR-2 fail"
    assert report.exit_code == 1


def test_fr3_missing_local_req_ref_fails(tmp_path):
    """FR-3: a local-scheme REQ-0N citation with no matching doc is a dangling-cross-ref fail."""
    # corpus has REQ-01 only; REQ-01 cites REQ-08 which does not exist → fail
    _write_req(tmp_path, "Alpha", key="REQ-01", cites="See REQ-08 for the sibling.")
    report = govern_corpus(tmp_path)
    fr3 = [f for f in report.fail_findings if f.check == "FR-3" and f.ref == "REQ-08"]
    assert fr3, "a citation to a missing local REQ-0N must raise an FR-3 fail"
    assert report.exit_code == 1


def test_fr3_out_of_scheme_ref_does_not_fail(tmp_path):
    """FR-3: a cross-project ref (REQ-10 / REQ-99, not REQ-0N form) is NOT fail-severity.

    This is exactly why the real corpus is clean: REQ-02 cites 'dev-os REQ-10' and REQ-06 cites
    REQ-99 in prose — out-of-scheme refs must never fail (FR-8 precision).
    """
    _write_req(
        tmp_path,
        "Alpha",
        key="REQ-01",
        cites="See dev-os REQ-10 and the example REQ-99.",
    )
    report = govern_corpus(tmp_path)
    bad = [
        f
        for f in report.fail_findings
        if f.check == "FR-3" and f.ref in ("REQ-10", "REQ-99")
    ]
    assert bad == [], "out-of-scheme REQ-10/REQ-99 must not be fail-severity"


def test_fr3_own_deliverable_path_not_flagged(tmp_path):
    """FR-3: a doc citing its OWN to-be-built deliverable path is NOT failed (the exclusion rule)."""
    # cite a not-yet-existing path AS the FR's own Touches: → excluded (own deliverable)
    _write_req(
        tmp_path,
        "Alpha",
        key="REQ-01",
        touches="`src/startd8/navigator/notyet_deliverable.py`",
    )
    report = govern_corpus(tmp_path)
    flagged = [
        f
        for f in report.findings
        if f.check == "FR-3" and "notyet_deliverable" in f.message
    ]
    assert (
        flagged == []
    ), "a doc's own declared deliverable path must not be flagged as dangling"


def test_fr4_fr_missing_verify_fails(tmp_path):
    """FR-4: an FR with no Verify: is a coverage fail (every FR needs an acceptance test)."""
    _write_req(tmp_path, "Alpha", key="REQ-01")
    _write_req(tmp_path, "Beta", key="REQ-02", verify="")  # no Verify:
    report = govern_corpus(tmp_path)
    fr4 = [
        f
        for f in report.fail_findings
        if f.check == "FR-4"
        and "no `Verify:`" in f.message
        and f.doc.startswith("REQ-02")
    ]
    assert fr4, "an FR missing Verify: must raise an FR-4 fail"
    assert report.exit_code == 1


# ------------------------------------------------------------------------------------------------ #
# report shape + renderers
# ------------------------------------------------------------------------------------------------ #


def test_report_json_round_trips_and_scores(tmp_path):
    """The JSON report carries the verdict, per-check roll-up, govern_score, and findings."""
    import json

    _write_req(tmp_path, "Alpha", key="REQ-01")
    _write_req(tmp_path, "Beta", key="REQ-02", handle=False, semname=False)
    report = govern_corpus(tmp_path)
    data = json.loads(render_govern_json(report))
    assert data["clean"] is False
    assert data["exit_code"] == 1
    assert set(data["checks"].keys()) == {"FR-1", "FR-2", "FR-3", "FR-4", "FR-5"}
    assert 0.0 <= data["govern_score"] <= 1.0


def test_text_report_names_checks_and_verdict():
    report = govern_corpus(_CLEAN_FIXTURE)
    text = render_govern_text(report)
    assert "corpus governance" in text
    for fr in ("FR-1", "FR-2", "FR-3", "FR-4", "FR-5"):
        assert fr in text
    assert "exit 0" in text


# ------------------------------------------------------------------------------------------------ #
# (c) CLI exit codes: 0 clean / 1 drift / 2 operational error
# ------------------------------------------------------------------------------------------------ #


def test_cli_govern_clean_exits_0():
    result = RUNNER.invoke(app, ["navigator", "govern", "--dir", str(_CLEAN_FIXTURE)])
    assert result.exit_code == 0, result.output


def test_cli_govern_drift_exits_1(tmp_path):
    _write_req(tmp_path, "Alpha", key="REQ-01")
    _write_req(tmp_path, "Beta", key="REQ-02", handle=False, semname=False)
    result = RUNNER.invoke(app, ["navigator", "govern", "--dir", str(tmp_path)])
    assert result.exit_code == 1, result.output


def test_cli_govern_missing_dir_exits_2(tmp_path):
    result = RUNNER.invoke(
        app, ["navigator", "govern", "--dir", str(tmp_path / "nope")]
    )
    assert result.exit_code == 2, result.output


def test_cli_govern_json_format(tmp_path):
    _write_req(tmp_path, "Alpha", key="REQ-01")
    _write_req(tmp_path, "Beta", key="REQ-02")
    result = RUNNER.invoke(
        app, ["navigator", "govern", "--dir", str(tmp_path), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert '"checks"' in result.output


def test_cli_govern_bad_format_exits_2():
    result = RUNNER.invoke(
        app, ["navigator", "govern", "--dir", str(_CLEAN_FIXTURE), "--format", "yaml"]
    )
    assert result.exit_code == 2, result.output


# ------------------------------------------------------------------------------------------------ #
# equivalence / one-home guard: govern.gate_spec IS the loop's gate_spec (lifted, not forked)
# ------------------------------------------------------------------------------------------------ #


def test_gate_spec_is_the_lifted_one_home():
    """The stage-0 gate now lives in govern; the loop script re-exports the SAME object (Kagami)."""
    import sys

    scripts = Path(__file__).resolve().parents[3] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import navigator_spec_delivery_loop as sdl

    assert sdl.gate_spec is gate_spec
    assert sdl._HANDLE.pattern
    assert sdl._SEMNAME.pattern
    assert sdl._FR_MARKER.pattern


def test_govern_report_is_a_dataclass_report():
    """GovernReport exposes the fail/advisory partition + exit code the CLI/tests consume."""
    report = GovernReport(corpus="x", docs=["REQ-01-x.md"])
    assert report.clean is True
    assert report.exit_code == 0
    assert report.fail_findings == []


# ── REQ-18 FR-5 — invariant 9 (llm-regime edge obligates a non-empty verify, activation-gated) ─────


def test_invariant_9_fires_only_for_realized_llm_target_with_empty_verify():
    from startd8.navigator.govern import check_realization_invariant
    from startd8.navigator.models import DerivationEdge, Node, NodeEvidence

    llm_edge = (DerivationEdge(from_key="up", regime="llm"),)
    lives = (NodeEvidence(type="code", ref="git:" + "a" * 40 + ":src/x.py"),)

    # realized (lives) + llm edge + empty verify → ONE named invariant-9 finding
    violating = Node(key="FR-1", does="", lives=lives, verify="", derivation=llm_edge)
    f = check_realization_invariant([violating], "REQ-x.md")
    assert len(f) == 1 and f[0].check == "FR-5" and f[0].fr == "FR-1"
    assert "invariant 9" in f[0].message and "llm-regime" in f[0].message

    # same node but empty lives (unbuilt/spec) → NO finding (activation gate)
    assert (
        check_realization_invariant(
            [Node(key="FR-1", does="", verify="", derivation=llm_edge)]
        )
        == []
    )

    # llm edge + lives + NON-empty verify → satisfied, no finding
    assert (
        check_realization_invariant(
            [Node(key="FR-1", does="", lives=lives, verify="x", derivation=llm_edge)]
        )
        == []
    )

    # deterministic edge + lives + empty verify → no obligation, no finding
    det = Node(
        key="FR-1",
        does="",
        lives=lives,
        verify="",
        derivation=(DerivationEdge(from_key="up", regime="deterministic"),),
    )
    assert check_realization_invariant([det]) == []


# ── REQ-19 FR-6 — planned-vs-realized determinism-regression govern finding ────────────────────────


def test_fr6_determinism_regression_finding():
    from startd8.navigator.govern import check_determinism_regression
    from startd8.navigator.models import DerivationEdge, Node, NodeEvidence
    from startd8.navigator.realization import MeasuredProvenanceSource
    from startd8.navigator.realization_contract import parse_record

    # a node PLANNED deterministic (declared edge) whose file MEASURES llm → regression
    node = Node(
        key="FR-1",
        does="",
        lives=(NodeEvidence(type="code", ref="src/x.py"),),
        derivation=(DerivationEdge(from_key="up", regime="deterministic"),),
    )
    measured_llm = MeasuredProvenanceSource(
        {
            "src/x.py": parse_record(
                {"file": "src/x.py", "regime": "llm", "source_confidence": 0.95}
            )
        }
    )
    f = check_determinism_regression([node], measured_llm, "REQ-x.md")
    assert (
        len(f) == 1
        and f[0].check == "FR-6"
        and "regression" in f[0].message
        and f[0].fr == "FR-1"
    )

    # plan agrees with measurement (both deterministic) → no finding
    measured_det = MeasuredProvenanceSource(
        {
            "src/x.py": parse_record(
                {
                    "file": "src/x.py",
                    "regime": "deterministic",
                    "source_confidence": 0.95,
                }
            )
        }
    )
    assert check_determinism_regression([node], measured_det) == []
    # no provenance → planned==measured (both declared) → no finding
    assert check_determinism_regression([node], None) == []


# ── REQ-20 FR-2 — ungrounded Lesson flagged by govern ──────────────────────────────────────────────


def test_fr2_ungrounded_lesson_flagged():
    from startd8.navigator.govern import Finding, check_lesson_grounding
    from startd8.navigator.models import Node
    from startd8.navigator.sources_retrospective import build_lesson_from_regression

    ungrounded = Node(
        key="lesson:x", does="", category="lesson"
    )  # no derived-from, no lives
    f = check_lesson_grounding([ungrounded], "REQ-x.md")
    assert len(f) == 1 and f[0].check == "FR-2" and "ungrounded" in f[0].message
    # a grounded Lesson (built from a regression) yields none
    grounded = build_lesson_from_regression(
        Finding("FR-6", "fail", "d", "node 'FR-1' ... regression.", fr="FR-1")
    )
    assert check_lesson_grounding([grounded]) == []
    # a non-lesson node is never flagged
    assert (
        check_lesson_grounding(
            [Node(key="FR-1", does="", category="functional-requirements")]
        )
        == []
    )


def test_generated_projection_is_exempt_from_govern(tmp_path):
    """A det-doc-kit $0 GENERATED projection (a `.projected.md` / GENERATED-marked doc) matches the
    REQ-*.md glob but is NOT an authored REQ — govern must not hold it to authoring conventions.
    """
    from startd8.navigator.govern import _is_generated_projection

    proj = tmp_path / "REQ-99-thing.projected.md"
    proj.write_text("<!-- GENERATED det-plan/0.1 -->\n# projected\n", encoding="utf-8")
    authored = tmp_path / "REQ-99-thing.md"
    authored.write_text("# A Thing — Requirements\n", encoding="utf-8")
    assert _is_generated_projection(proj) is True
    assert _is_generated_projection(authored) is False
    # a projection dropped in a corpus dir contributes no fail-finding (govern skips it).
    (tmp_path / "REQ-01-x.projected.md").write_text(
        "<!-- GENERATED det-plan/0.1 -->\n# x\n", encoding="utf-8"
    )
    report = govern_corpus(tmp_path)
    assert not any("projected" in f.doc for f in report.fail_findings)
