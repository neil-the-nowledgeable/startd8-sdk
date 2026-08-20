"""REQ-28 — runtime o11y grounding: the territory's two signals routed into the loop.

Feature o11y (`parity` / `compare_live`) → the deepest liveness cell; AI o11y (cost telemetry) → the
measured realization regime + the planned-vs-realized regression, through REQ-19's seam. Every test is
fixture-driven: no Prometheus, no docker, no live scrape (the adapters are the only coupling point, and
they are fed REAL `ParityResult` / `LiveComparisonReport` objects to prove the reuse is not a mock shape).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from startd8.navigator.govern import check_liveness_layer, govern_corpus
from startd8.navigator.models import (
    DerivationEdge,
    Node,
    NodeEvidence,
    RealizationRegime,
    node_field_names,
)
from startd8.navigator.realization import node_regime
from startd8.navigator.runtime_grounding import (
    REF_MEASURED_REGRESSION,
    REF_RUNTIME_DEAD,
    REF_RUNTIME_UNOBSERVED,
    CostObservation,
    RuntimeEmission,
    check_measured_determinism_regression,
    check_runtime_verify_liveness,
    cost_telemetry_to_provenance,
    ground_corpus_in_runtime,
    lessons_from_runtime_grounding,
    load_cost_telemetry,
    merge_runtime_emissions,
    propose_instrumentation_for_gap,
    runtime_emission_from_live_comparison,
    runtime_emission_from_parity,
    runtime_findings_to_sarif,
)

_NAV = Path(__file__).parents[3] / "src" / "startd8" / "navigator"
_RUNTIME_GROUNDING = _NAV / "runtime_grounding.py"


def _objective(key: str, signal: str, *, target: str = "the goal") -> Node:
    """An objective node with a bound live signal (REQ-23's `target_signal`) — the runtime cell's subject."""
    return Node(
        key=key,
        does="an outcome",
        category="objective",
        orientation="outcome",
        lives=(NodeEvidence(type="doc", ref=f"REQ-x.md#{key}"),),
        attributes={"kind": "objective", "target": target, "target_signal": signal},
    )


def _planned_deterministic(key: str, path: str) -> Node:
    """A node whose PLAN declares `deterministic` ($0) and whose `lives` is the join key for telemetry."""
    return Node(
        key=key,
        does="a generated artifact",
        category="functional-requirements",
        lives=(NodeEvidence(type="code", ref=path),),
        derivation=(DerivationEdge(from_key="intent", regime=RealizationRegime.DETERMINISTIC),),
    )


# ── FR-1 — a declared feature with no live emission is a runtime verify-liveness GAP ────────────────


def test_fr1_declared_feature_with_no_live_emission_is_a_gap():
    from startd8.observability.parity import ParityResult

    emission = runtime_emission_from_parity(ParityResult(declared_not_emitted=["startd8.cost.total"]))
    dead = check_runtime_verify_liveness([_objective("O-1", "`startd8_cost_total`")], emission, "REQ-x.md")
    assert len(dead) == 1
    assert dead[0].ref == REF_RUNTIME_DEAD and dead[0].severity == "fail" and dead[0].fr == "O-1"
    # the exported (underscore) and canonical (dotted) forms are the SAME signal — parity's own convention
    assert check_runtime_verify_liveness([_objective("O-1", "`startd8.cost.total`")], emission)[0].fr == "O-1"


def test_fr1_a_feature_that_emits_yields_no_finding():
    from startd8.observability.parity import ParityResult

    emission = runtime_emission_from_parity(ParityResult(declared_not_emitted=["other.metric"]))
    assert check_runtime_verify_liveness([_objective("O-1", "`startd8_cost_total`")], emission) == []
    # a node that binds NO signal is the static target-unmeasured cell's business, not the runtime cell's
    assert check_runtime_verify_liveness([_objective("O-2", "")], emission) == []


def test_fr1_compare_live_fail_verdict_is_a_dead_sli():
    from startd8.observability.compare_live import LiveComparisonReport

    report = LiveComparisonReport(
        status="fail",
        reason="dead metric",
        tier_a={},
        standup={},
        tier_b={},
        fail_verdicts=[{"verdict": "fail", "metric": "startd8_cost_total", "expr": "sum(x)"}],
    )
    emission = runtime_emission_from_live_comparison(report)
    found = check_runtime_verify_liveness([_objective("O-1", "`startd8_cost_total`")], emission)
    assert [f.ref for f in found] == [REF_RUNTIME_DEAD]
    assert "compare_live" in found[0].message  # the finding names the observation that grounds it


def test_fr1_promql_signal_matches_the_metric_it_queries():
    emission = RuntimeEmission(dead=frozenset({"http_server_request_duration"}), source="fixture")
    node = _objective("O-1", "`histogram_quantile(0.95, http_server_request_duration)`")
    assert [f.ref for f in check_runtime_verify_liveness([node], emission)] == [REF_RUNTIME_DEAD]


def test_fr1_runtime_cell_joins_the_one_liveness_layer():
    """The runtime cell reports under the SAME `liveness` layer as the static cells (REQ-23 FR-5)."""
    emission = RuntimeEmission(dead=frozenset({"m_x"}), source="fixture")
    layer = check_liveness_layer([], [_objective("O-1", "`m_x`")], "REQ-x.md", runtime_emission=emission)
    assert [f.ref for f in layer] == [REF_RUNTIME_DEAD]
    assert all(str(f.ref).startswith("liveness:") for f in layer)


def test_fr1_findings_render_through_the_shared_sarif_sink():
    emission = RuntimeEmission(
        dead=frozenset({"m_dead"}), unobserved=frozenset({"m_absent"}), source="fixture"
    )
    findings = check_runtime_verify_liveness(
        [_objective("O-1", "`m_dead`"), _objective("O-2", "`m_absent`")], emission, "REQ-x.md"
    )
    doc = runtime_findings_to_sarif(findings, corpus="requirements-visualization")
    assert doc["version"] == "2.1.0" and doc["$schema"]
    results = {r["ruleId"]: r["level"] for r in doc["runs"][0]["results"]}
    assert results == {REF_RUNTIME_DEAD: "error", REF_RUNTIME_UNOBSERVED: "note"}
    assert doc["runs"][0]["invocations"][0]["properties"]["corpus"] == "requirements-visualization"
    # nothing was skipped — the navigator Finding shape adapts cleanly onto the shared renderer
    assert "skipped" not in doc["runs"][0]["invocations"][0].get("properties", {})


# ── FR-2 — the measured realization regime, grounded in AI cost telemetry via the REQ-19 seam ───────


def test_fr2_observed_llm_cost_measures_llm():
    prov = cost_telemetry_to_provenance([CostObservation(file="app/x.py", cost=0.42, model="sonnet")])
    node = Node(key="FR-1", does="", lives=(NodeEvidence(type="code", ref="app/x.py"),))
    assert node_regime(node, prov) == RealizationRegime.LLM


def test_fr2_observed_zero_cost_measures_deterministic():
    """An EXPLICIT $0 observation is a real measurement (generated, nothing spent) → deterministic."""
    prov = cost_telemetry_to_provenance([CostObservation(file="app/x.py", cost=0.0)])
    node = Node(key="FR-1", does="", lives=(NodeEvidence(type="code", ref="app/x.py"),))
    assert node_regime(node, prov) == RealizationRegime.DETERMINISTIC


def test_fr2_absent_cost_degrades_and_never_asserts_a_false_deterministic():
    """The FR-4 guard at the realization seam: an ABSENT cost is not a $0 — it grounds nothing."""
    prov = cost_telemetry_to_provenance([CostObservation(file="app/x.py", cost=None)])
    node = Node(key="FR-1", does="", lives=(NodeEvidence(type="code", ref="app/x.py"),))
    assert node_regime(node, prov) == RealizationRegime.UNKNOWN  # not `deterministic`
    # and a node with no telemetry at all keeps its DECLARED regime (the seam degrades, never overrides)
    declared_llm = Node(
        key="FR-2",
        does="",
        lives=(NodeEvidence(type="code", ref="app/untelemetered.py"),),
        derivation=(DerivationEdge(from_key="intent", regime=RealizationRegime.LLM),),
    )
    assert node_regime(declared_llm, prov) == RealizationRegime.LLM


def test_fr2_low_confidence_measurement_degrades_to_declared():
    """REQ-19's confidence gate governs — a weak join never overrides the plan (the honesty firewall)."""
    prov = cost_telemetry_to_provenance(
        [CostObservation(file="app/x.py", cost=1.5, confidence=0.2)]
    )
    node = _planned_deterministic("FR-1", "app/x.py")
    assert node_regime(node, prov) == RealizationRegime.DETERMINISTIC  # declared stands


def test_fr2_telemetry_joins_a_git_evidence_ref():
    """Reuses REQ-19's `git:<sha>:<path>` join — the same key the realization source already normalizes."""
    prov = cost_telemetry_to_provenance([CostObservation(file="src/x.py", cost=0.1)])
    node = Node(key="FR-1", does="", lives=(NodeEvidence(type="code", ref="git:" + "a" * 40 + ":src/x.py"),))
    assert node_regime(node, prov) == RealizationRegime.LLM


def test_fr2_load_cost_telemetry_keeps_a_missing_cost_absent(tmp_path):
    p = tmp_path / "cost.json"
    p.write_text(
        json.dumps(
            {
                "observations": [
                    {"file": "a.py", "cost": 0.5, "model": "sonnet"},
                    {"file": "b.py"},  # the field is ABSENT — must not become 0.0
                    {"file": "c.py", "cost": None},
                    {"file": "", "cost": 9.9},  # unusable row → dropped, never a phantom file
                ]
            }
        ),
        encoding="utf-8",
    )
    obs = {o.file: o for o in load_cost_telemetry(p)}
    assert set(obs) == {"a.py", "b.py", "c.py"}
    assert obs["a.py"].regime == RealizationRegime.LLM
    assert obs["b.py"].cost is None and obs["b.py"].regime is None
    assert obs["c.py"].regime is None
    assert load_cost_telemetry(tmp_path / "missing.json") == []  # absent telemetry → nothing to ground


# ── FR-3 — planned-vs-realized, grounded in live telemetry ─────────────────────────────────────────


def test_fr3_planned_deterministic_with_observed_cost_is_a_measured_regression():
    nodes = [_planned_deterministic("FR-1", "app/x.py")]
    found = check_measured_determinism_regression(
        nodes, [CostObservation(file="app/x.py", cost=1.20, model="sonnet")], "REQ-x.md"
    )
    assert len(found) == 1 and found[0].ref == REF_MEASURED_REGRESSION
    assert found[0].severity == "fail" and found[0].fr == "FR-1"


def test_fr3_agreement_yields_no_regression():
    nodes = [_planned_deterministic("FR-1", "app/x.py")]
    assert check_measured_determinism_regression(nodes, [CostObservation(file="app/x.py", cost=0.0)]) == []


def test_fr3_absent_telemetry_yields_no_findings():
    nodes = [_planned_deterministic("FR-1", "app/x.py")]
    assert check_measured_determinism_regression(nodes, None) == []
    assert check_measured_determinism_regression(nodes, []) == []


def test_fr3_reuses_req19_regression_check_verbatim():
    """NR-2: the comparison itself is REQ-19's — this only grounds the measured side + re-tags the ref."""
    from startd8.navigator.govern import check_determinism_regression

    nodes = [_planned_deterministic("FR-1", "app/x.py")]
    prov = cost_telemetry_to_provenance([CostObservation(file="app/x.py", cost=1.0)])
    base = check_determinism_regression(nodes, prov, "REQ-x.md")
    wrapped = check_measured_determinism_regression(nodes, provenance=prov, doc="REQ-x.md")
    assert [f.message for f in base] == [f.message for f in wrapped]
    assert [f.ref for f in wrapped] == [REF_MEASURED_REGRESSION]


# ── FR-4 — absence-vs-error (the Harbor FIELDSTATE guard) ──────────────────────────────────────────


def test_fr4_an_unobservable_run_is_never_a_fail():
    from startd8.observability.compare_live import LiveComparisonReport

    report = LiveComparisonReport(
        status="unknown", reason="standup unavailable", tier_a={}, standup={}, tier_b=None
    )
    emission = runtime_emission_from_live_comparison(report)
    assert emission.observed is False
    found = check_runtime_verify_liveness([_objective("O-1", "`m_x`")], emission)
    assert [f.severity for f in found] == ["advisory"]
    assert [f.ref for f in found] == [REF_RUNTIME_UNOBSERVED]
    assert "NOT a real zero" in found[0].message


def test_fr4_a_pending_probe_is_absent_not_failing():
    """`pending_probe` is severity 0 by declared upstream invariant — it can never become a GAP here."""
    emission = runtime_emission_from_live_comparison(
        {"status": "pass", "pending_verdicts": [{"verdict": "pending_probe", "metric": "probe_fresh"}]}
    )
    found = check_runtime_verify_liveness([_objective("O-1", "`probe_fresh`")], emission)
    assert [f.ref for f in found] == [REF_RUNTIME_UNOBSERVED] and found[0].severity == "advisory"


def test_fr4_absent_and_real_fail_carry_distinct_refs_and_severities():
    emission = RuntimeEmission(dead=frozenset({"m_dead"}), unobserved=frozenset({"m_absent"}))
    found = {
        f.fr: f
        for f in check_runtime_verify_liveness(
            [_objective("O-1", "`m_dead`"), _objective("O-2", "`m_absent`")], emission
        )
    }
    assert found["O-1"].ref != found["O-2"].ref
    assert (found["O-1"].severity, found["O-2"].severity) == ("fail", "advisory")


def test_fr4_a_best_effort_parity_miss_is_advisory_not_a_gap():
    """parity's span sub-check is explicitly best-effort — a soft miss must not ship as a hard fact."""
    from startd8.observability.parity import ParityResult

    emission = runtime_emission_from_parity(ParityResult(spans_without_site=["navigator.build"]))
    found = check_runtime_verify_liveness([_objective("O-1", "`navigator.build`")], emission)
    assert [f.severity for f in found] == ["advisory"]


def test_fr4_merge_never_promotes_an_absence_to_a_failure():
    a = RuntimeEmission(dead=frozenset({"m_x"}), source="parity")
    b = RuntimeEmission(unobserved=frozenset({"m_x", "m_y"}), observed=False, source="compare_live")
    merged = merge_runtime_emissions(a, b)
    assert merged.dead == frozenset({"m_x"}) and merged.unobserved == frozenset({"m_y"})
    assert merged.observed is False and "parity" in merged.source
    assert merge_runtime_emissions(None, None) is None  # absent stays absent


# ── FR-5 — propose, don't dispose (the generative fix + the Lessons) ───────────────────────────────


def test_fr5_a_gap_proposes_a_req_stub_without_a_patch_when_ungrounded():
    finding = check_runtime_verify_liveness(
        [_objective("O-1", "`m_dead`")], RuntimeEmission(dead=frozenset({"m_dead"})), "REQ-x.md"
    )[0]
    prop = propose_instrumentation_for_gap(finding)
    assert prop.applied is False and prop.patch is None
    assert prop.req_stub["subject"] == "O-1" and prop.req_stub["disposition"] == "proposed"
    assert prop.req_stub["ref"] == REF_RUNTIME_DEAD and prop.req_stub["verify"]


def test_fr5_a_grounded_gap_proposes_a_real_instrumentation_patch():
    """Reuses the Harbor-proven `instrumentation_gen` renderer — the patch is PROPOSED, never applied."""
    from startd8.scaffold_codegen.instrumentation_gen import harbor_core_reference_gap

    finding = check_runtime_verify_liveness(
        [_objective("O-1", "`http_server_request_duration`")],
        RuntimeEmission(dead=frozenset({"http_server_request_duration"})),
        "REQ-x.md",
    )[0]
    prop = propose_instrumentation_for_gap(
        finding,
        gap=harbor_core_reference_gap(),
        source_ctx={"trace_provider": "src/lib/trace/trace.go", "http_options": "src/lib/trace/helper.go"},
    )
    assert prop.applied is False
    assert prop.patch and prop.patch["language"] == "go" and prop.patch["edits"]
    assert "apply it yourself" in prop.note
    assert prop.req_stub  # both human routes are offered, never one silently chosen


def test_fr5_instrumentation_gens_honest_boundary_is_reported_not_swallowed():
    from startd8.scaffold_codegen.instrumentation_gen import InstrumentationGap

    finding = check_runtime_verify_liveness(
        [_objective("O-1", "`istio_requests_total`")],
        RuntimeEmission(dead=frozenset({"istio_requests_total"})),
    )[0]
    gap = InstrumentationGap(
        subject="istio",
        service="data-plane",
        language="cpp-envoy",
        missing_families=["http.server.request.duration"],
        mechanism="runtime-composed envoy data-plane",
    )
    prop = propose_instrumentation_for_gap(finding, gap=gap)
    assert prop.patch is None and prop.applied is False
    assert "declined" in prop.note and "runtime-composed" in prop.note


def test_fr5_a_gap_routes_to_a_proposed_human_gated_lesson():
    from startd8.navigator.sources_retrospective import lesson_status, revises_edges

    findings = check_runtime_verify_liveness(
        [_objective("O-1", "`m_dead`"), _objective("O-2", "`m_absent`")],
        RuntimeEmission(dead=frozenset({"m_dead"}), unobserved=frozenset({"m_absent"})),
        "REQ-x.md",
    )
    lessons = lessons_from_runtime_grounding(findings, confidence=0.9)
    assert len(lessons) == 1  # only the FACT routes; the unobserved advisory does not
    lesson = lessons[0]
    assert lesson.key == "lesson:O-1" and lesson_status(lesson) == "proposed"
    assert [e.from_key for e in revises_edges(lesson)] == ["O-1"]
    assert "runtime" in lesson.does.lower() and lesson.confidence == 0.9


def test_fr5_a_measured_regression_routes_to_a_regression_lesson():
    from startd8.navigator.sources_retrospective import lesson_status

    findings = check_measured_determinism_regression(
        [_planned_deterministic("FR-1", "app/x.py")], [CostObservation(file="app/x.py", cost=2.0)]
    )
    lessons = lessons_from_runtime_grounding(findings)
    assert [lesson_status(x) for x in lessons] == ["proposed"]
    assert lessons[0].key == "lesson:FR-1"


def test_fr5_no_code_path_applies_anything_to_the_subject_tree():
    """NR-1, by construction: the module has NO writer at all — no write/mkdir/copy/run call sites."""
    tree = ast.parse(_RUNTIME_GROUNDING.read_text(encoding="utf-8"))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    forbidden = {
        "write_text", "write_bytes", "writelines", "write", "open", "mkdir", "unlink",
        "rename", "replace_file", "copy", "copytree", "rmtree", "run", "check_call",
        "check_output", "Popen", "system", "apply_revise", "auto_apply_revise",
    }
    assert not (called & forbidden), f"runtime_grounding gained an apply path: {sorted(called & forbidden)}"
    imported = _module_imports("runtime_grounding.py")
    assert not [m for m in imported if "subprocess" in m or "shutil" in m]


# ── FR-6 — reuse-only, additive, advisory, byte-identical ──────────────────────────────────────────


def _module_imports(name: str) -> list:
    out = []
    for node in ast.walk(ast.parse((_NAV / name).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append(("." * (node.level or 0)) + (node.module or ""))
    return out


def test_fr6_wiring_reuses_the_existing_pieces_and_builds_no_new_engine():
    imported = _module_imports("runtime_grounding.py")
    assert any("coverage_map.findings_sarif" in m for m in imported)  # the ONE SARIF sink
    assert any("scaffold_codegen.instrumentation_gen" in m for m in imported)  # the generative fix
    assert any("realization_contract" in m for m in imported)  # REQ-19's typed seam
    assert any("sources_retrospective" in m for m in imported)  # REQ-20's Lesson builders
    # and the o11y contracts are consumed through their REAL public types (adapters, not re-authored)
    from startd8.observability.compare_live import LiveComparisonReport  # noqa: F401
    from startd8.observability.parity import ParityResult  # noqa: F401


def test_fr6_navigator_construction_firewall_holds():
    """The runtime module may reach `scaffold_codegen` (the propose adapter) but never the construction
    subsystems the navigator core is firewalled from."""
    forbidden = ("backend_codegen", "contractors", "micro_prime")
    assert not [m for m in _module_imports("runtime_grounding.py") if any(f in m for f in forbidden)]
    for core in ("govern.py", "realization.py", "sources_retrospective.py"):
        assert not [m for m in _module_imports(core) if any(f in m for f in forbidden)], core


def test_fr6_no_new_node_field():
    assert len(node_field_names()) == 20  # REQ-28 is additive: a Lesson projection, no schema growth


def test_fr6_absent_runtime_input_is_byte_identical():
    nodes = [_objective("O-1", "`m_x`")]
    assert check_liveness_layer([], nodes, "REQ-x.md") == check_liveness_layer(
        [], nodes, "REQ-x.md", runtime_emission=None
    )
    assert ground_corpus_in_runtime(nodes) == []
    assert runtime_findings_to_sarif([])["runs"][0]["results"] == []


def test_fr6_the_fixed_govern_battery_gains_no_runtime_check(tmp_path):
    """Charter NR-6: the 5-check battery is unchanged — no runtime cell, no runtime dependency."""
    doc = tmp_path / "REQ-01-thing.md"
    doc.write_text(
        "# Thing — Requirements\n\n**Format:** det-req/0.1\n\n"
        "> **Readable handle:** `feature/thing-1234abcd`\n"
        "> **Semantic name:** *Do the thing*\n\n"
        "## Objectives\n\n- **O-1:** A goal — target: X. Signal: `m_dead`.\n\n"
        "## Functional requirements\n\n"
        "- **FR-1 — Do it.** Name: Do the thing. Verify: it works. Serves: O-1\n",
        encoding="utf-8",
    )
    report = govern_corpus(tmp_path)
    assert set(report.checks_summary()) <= {"FR-1", "FR-2", "FR-3", "FR-4", "FR-5"}
    assert not [f for f in report.findings if "runtime" in str(f.ref)]


def _corpus(tmp_path, signal: str = "`m_dead`") -> Path:
    doc = tmp_path / "REQ-01-thing.md"
    doc.write_text(
        "# Thing — Requirements\n\n**Format:** det-req/0.1\n\n"
        "> **Readable handle:** `feature/thing-1234abcd`\n"
        "> **Semantic name:** *Do the thing*\n\n"
        f"## Objectives\n\n- **O-1:** A goal — target: X. Signal: {signal}.\n\n"
        "## Functional requirements\n\n"
        "- **FR-1 — Do it.** Name: Do the thing. Verify: it works. Serves: O-1\n",
        encoding="utf-8",
    )
    return doc


def test_fr6_cli_runtime_o11y_is_opt_in_and_never_blocks(tmp_path):
    """The `navigator runtime-o11y` surface: advisory exit 0 even WITH a gap, and a no-op without input."""
    from typer.testing import CliRunner

    from startd8.cli import app

    _corpus(tmp_path)
    live = tmp_path / "compare-live.json"
    live.write_text(
        json.dumps({"status": "fail", "fail_verdicts": [{"verdict": "fail", "metric": "m_dead"}]}),
        encoding="utf-8",
    )
    runner = CliRunner()

    bare = runner.invoke(app, ["navigator", "runtime-o11y", "--dir", str(tmp_path)])
    assert bare.exit_code == 0 and "no runtime observation supplied" in bare.stdout

    sarif = tmp_path / "out.sarif"
    lessons = tmp_path / "lessons.json"
    res = runner.invoke(
        app,
        [
            "navigator", "runtime-o11y", "--dir", str(tmp_path),
            "--compare-live-json", str(live), "--propose",
            "--sarif-out", str(sarif), "--lessons-out", str(lessons), "--format", "json",
        ],
    )
    assert res.exit_code == 0  # a runtime gap ROUTES to a human; it never fails the build (NR-3)
    payload = json.loads(res.stdout)
    assert [f["ref"] for f in payload["findings"]] == [REF_RUNTIME_DEAD]
    assert payload["lessons"] and payload["proposals"][0]["applied"] is False
    assert json.loads(sarif.read_text())["runs"][0]["results"][0]["ruleId"] == REF_RUNTIME_DEAD
    assert json.loads(lessons.read_text())["lessons"]


def test_fr2_cli_govern_grounds_the_measured_regime_in_cost_telemetry(tmp_path):
    """FR-2/FR-3 through the doc'd surface (`Lives: govern.py`): `govern --cost-telemetry` feeds REQ-19's
    seam from AI o11y instead of a static provenance file — opt-in, and never both sources at once."""
    from typer.testing import CliRunner

    from startd8.cli import app

    _corpus(tmp_path)
    telemetry = tmp_path / "cost.json"
    telemetry.write_text(json.dumps([{"file": "src/x.py", "cost": 1.25}]), encoding="utf-8")
    runner = CliRunner()

    ok = runner.invoke(
        app, ["navigator", "govern", "--dir", str(tmp_path), "--cost-telemetry", str(telemetry),
              "--format", "json"]
    )
    assert ok.exit_code in (0, 1)  # a govern verdict, not a crash: the telemetry grounded the seam
    both = runner.invoke(
        app, ["navigator", "govern", "--dir", str(tmp_path), "--cost-telemetry", str(telemetry),
              "--realization-provenance", str(telemetry)]
    )
    assert both.exit_code == 2 and "not both" in both.stdout
    bad = tmp_path / "bad.json"
    bad.write_text('{"observations": {"not": "a list"}}', encoding="utf-8")
    assert runner.invoke(
        app, ["navigator", "govern", "--dir", str(tmp_path), "--cost-telemetry", str(bad)]
    ).exit_code == 2


def test_fr6_cli_missing_dir_is_an_operational_error(tmp_path):
    from typer.testing import CliRunner

    from startd8.cli import app

    res = CliRunner().invoke(app, ["navigator", "runtime-o11y", "--dir", str(tmp_path / "nope")])
    assert res.exit_code == 2


def test_fr6_the_runtime_pass_is_advisory_end_to_end():
    """A gap + an unobserved signal + a measured regression in one pass — reported, never blocking."""
    nodes = [_objective("O-1", "`m_dead`"), _planned_deterministic("FR-1", "app/x.py")]
    findings = ground_corpus_in_runtime(
        nodes,
        emission=RuntimeEmission(dead=frozenset({"m_dead"}), source="fixture"),
        observations=[CostObservation(file="app/x.py", cost=3.0)],
        doc="REQ-x.md",
    )
    assert {f.ref for f in findings} == {REF_RUNTIME_DEAD, REF_MEASURED_REGRESSION}
    # the report is data, not a verdict: nothing here returns an exit code or raises
    assert all(f.severity in ("fail", "advisory") for f in findings)
    assert len(lessons_from_runtime_grounding(findings)) == 2
