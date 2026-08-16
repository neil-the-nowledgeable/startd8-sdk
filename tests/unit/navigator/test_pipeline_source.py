"""REQ-08 — the prose→product pipeline source, the Verify-as-oracle, and pipeline provenance.

Covers FR-1..FR-8. The byte-identity + field-compat goldens (``node_field_names`` /
``test_no_profile_is_byte_identical``) are asserted elsewhere UNEDITED; here we add the pipeline-domain
guards, the status-vocab well-formedness assertion (FR-8), and the classifier/oracle/provenance behavior.
"""

from __future__ import annotations

import graphlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from startd8.cli import app
from startd8.navigator.models import Node, NodeEvidence, node_field_names
from startd8.navigator.provenance import pipeline_provenance
from startd8.navigator.sources_pipeline import (
    PIPELINE_PROFILE,
    nodes_from_pipeline,
    stages,
    topo_order,
)
from startd8.navigator.verify_oracle import (
    KIND_ASSERTION,
    KIND_COMMAND,
    KIND_MANUAL,
    OracleDescriptor,
    aggregate_exit_code,
    classify,
    evaluate,
)
from startd8.navigator.view_definition import (
    DEFINITION_REGISTRY,
    PIPELINE_DEFINITION,
    validate_definitions,
)

RUNNER = CliRunner()


# ─────────────────────────────── FR-1 / FR-2 — stage projection + edges ───────────────────────────

def test_six_stage_nodes_with_ordinals_and_category():
    nodes = nodes_from_pipeline()
    assert len(nodes) == 6
    assert {n.category for n in nodes} == {"pipeline-stage"}
    ordinals = sorted(int(n.attributes["ordinal"]) for n in nodes)
    assert ordinals == [0, 1, 2, 3, 4, 5]
    # ordinal is a STRING in the Dict[str,str] bag, parses as int in 0..5 (FR-1 Verify).
    for n in nodes:
        assert isinstance(n.attributes["ordinal"], str)
        assert 0 <= int(n.attributes["ordinal"]) <= 5


def test_no_node_field_added_by_pipeline_source():
    """FR-1 / NR-3: the Stage projection adds NO field to Node (category + attributes only).

    The Node field set is the co-churned 0.4.0 golden: REQ-16 (``derivation``) + REQ-17
    (``verify``/``approve``/``was``) are the only additions beyond the original 15.
    """
    assert set(node_field_names()) == {
        "key", "does", "status", "wont", "lives", "ships_when", "confidence", "triggers",
        "children", "child_keys", "category", "orientation", "route_state", "status_facets",
        "attributes",
        "verify", "approve", "was", "derivation",
    }


def test_each_stage_status_in_built_or_spec():
    """FR-1: maturity='stable' closes the outcome to {built, spec} — never thin."""
    for n in nodes_from_pipeline():
        assert n.status in {"built", "spec"}


def test_pipeline_profile_statuses_cover_emitted_statuses():
    """FR-1: PIPELINE_PROFILE.statuses keys cover every status nodes_from_pipeline() emits."""
    emitted = {n.status for n in nodes_from_pipeline()}
    profile_keys = {s.key for s in PIPELINE_PROFILE.statuses}
    assert emitted <= profile_keys


def test_each_stage_lives_to_its_sdk_artifact():
    for n in nodes_from_pipeline():
        assert n.lives, f"{n.key} has no Lives"
        assert n.lives[0].type == "code"
        assert n.lives[0].ref == n.attributes["sdk_artifact"]


def test_stage_depends_on_edges_and_topo_sort():
    """FR-2: contract←functional, {impl,test,doc}←contract; topo-sort succeeds, consistent w/ ordinals."""
    nodes = {n.key: n for n in nodes_from_pipeline()}
    assert "stage:functional" in nodes["stage:contract"].child_keys
    for k in ("stage:impl", "stage:test", "stage:doc"):
        assert "stage:contract" in nodes[k].child_keys
    # every referenced child key is an emitted stage key
    keys = set(nodes)
    for n in nodes.values():
        assert all(ck in keys for ck in n.child_keys)
    order = topo_order()
    assert set(order) == keys
    # order is consistent with ordinals: a stage appears after the stage(s) it consumes.
    pos = {k: i for i, k in enumerate(order)}
    for n in nodes.values():
        for ck in n.child_keys:
            assert pos[ck] < pos[n.key]


def test_topo_order_raises_on_cycle():
    """R8-EB-3: topo_order is fail-loud — a cyclic stage graph raises graphlib.CycleError."""
    a = Node(key="A", does="", child_keys=("B",), category="pipeline-stage")
    b = Node(key="B", does="", child_keys=("A",), category="pipeline-stage")
    with pytest.raises(graphlib.CycleError):
        topo_order([a, b])


def test_nodes_from_pipeline_runs_the_acyclicity_guard():
    """R8-EB-3: nodes_from_pipeline calls topo_order (the guard) — a real build validates acyclicity,
    so topo_order is no longer a test-only dormant. The real graph is acyclic, so the build succeeds."""
    nodes = nodes_from_pipeline()   # would raise graphlib.CycleError if _STAGES held a cycle
    assert len(nodes) == 6


def test_spec_stage_when_artifact_missing(tmp_path):
    """D-A: a fixture repo missing one artifact exercises the SPEC branch via repo=."""
    # Create only the intent artifact; every other stage artifact is absent → spec.
    (tmp_path / "src" / "startd8" / "seeds").mkdir(parents=True)
    nodes = {n.key: n for n in nodes_from_pipeline(repo=tmp_path)}
    assert nodes["stage:intent"].status == "built"     # src/startd8/seeds/ exists
    assert nodes["stage:contract"].status == "spec"    # forward_manifest.py absent
    assert nodes["stage:doc"].status == "spec"         # docs/ absent


# ─────────────────────────────── FR-3 — --source pipeline CLI seam ────────────────────────────────

def test_cli_build_pipeline_json_exits_0_with_six_nodes():
    res = RUNNER.invoke(app, ["navigator", "build", "--source", "pipeline", "--format", "json"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)
    assert data["source"] == "pipeline"
    assert len(data["nodes"]) == 6


def test_existing_sources_unchanged():
    """FR-3: --source requirements|capability-index|node-schema behave unchanged (additive)."""
    fixture = Path(__file__).parent / "fixtures" / "REQ-fixture-minimal.md"
    for args in (
        ["navigator", "build", "--source", "node-schema", "--format", "json"],
        ["navigator", "build", "--source", "capability-index", "--format", "json"],
        ["navigator", "build", "--source", "requirements",
         "--requirements", str(fixture), "--format", "json"],
    ):
        res = RUNNER.invoke(app, args)
        assert res.exit_code == 0, res.output
        assert json.loads(res.stdout)["nodes"]
    # an unknown source still errors, now naming pipeline in the expected set
    bad = RUNNER.invoke(app, ["navigator", "build", "--source", "nope", "--format", "json"])
    assert bad.exit_code == 1
    assert "pipeline" in bad.output


def test_cli_build_pipeline_html_tree_shows_artifact_chain(tmp_path):
    """FR-7: --source pipeline --renderer tree surfaces artifact_chain as a meta row."""
    out = tmp_path / "pipe.html"
    res = RUNNER.invoke(app, [
        "navigator", "build", "--source", "pipeline", "--format", "html",
        "--renderer", "tree", "--out", str(out),
    ])
    assert res.exit_code == 0, res.output
    html = out.read_text(encoding="utf-8")
    assert "artifact_chain" in html or "stage:contract" in html


def test_cli_build_pipeline_graph_renders_dag(tmp_path):
    out = tmp_path / "pipe-graph.html"
    res = RUNNER.invoke(app, [
        "navigator", "build", "--source", "pipeline", "--format", "html",
        "--renderer", "graph", "--out", str(out),
    ])
    assert res.exit_code == 0, res.output
    assert out.is_file()


# ─────────────────────────────── FR-4 — classifier ───────────────────────────────────────────────

def _fixture_doc(tmp_path, verifies):
    doc = tmp_path / "REQ-fx.md"
    lines = ["# Fixture — Requirements", "", "**Format:** det-req/0.1", ""]
    for i, v in enumerate(verifies, start=1):
        lines.append(
            f"- **FR-{i} — Case {i}.** Does thing {i}. Name: case {i}. Verify: {v} Serves: O-1"
        )
    doc.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return doc


def test_classifier_kinds_on_a_fixture(tmp_path):
    doc = _fixture_doc(tmp_path, [
        "`startd8 navigator build --source pipeline --format json` exits 0 with six nodes.",   # command
        "`startd8 navigator build` and `startd8 navigator govern` both pass.",                 # multi -> manual
        "`startd8 navigator build --requirements <doc>` exits 0.",                              # placeholder -> manual
        "node_field_names() is unchanged and six nodes are emitted.",                           # prose -> assertion
    ])
    by = {d.fr_id: d for d in classify(doc)}
    assert by["FR-1"].kind == KIND_COMMAND
    assert by["FR-1"].command_argv is not None
    assert by["FR-1"].command_argv[0] == "startd8"
    assert by["FR-1"].assertion_text  # prose residue retained
    assert by["FR-2"].kind == KIND_MANUAL and by["FR-2"].reason == "multi-command"
    assert by["FR-3"].kind == KIND_MANUAL and by["FR-3"].reason == "unresolved placeholder"
    assert by["FR-4"].kind == KIND_ASSERTION


def test_classifier_joined_command_is_manual(tmp_path):
    doc = _fixture_doc(tmp_path, ["`startd8 navigator build; startd8 navigator govern` both pass."])
    d = classify(doc)[0]
    assert d.kind == KIND_MANUAL and d.reason == "multi-command"


# ─────────────────────────────── FR-5 — evaluate + pass/fail/skip ─────────────────────────────────

def test_verify_default_inert_no_subprocess(tmp_path):
    """FR-5: default emits only skip, no subprocess (verified by all-skip + rc 0)."""
    doc = _fixture_doc(tmp_path, ["`startd8 navigator view-definition` exits 0."])
    res = RUNNER.invoke(app, ["navigator", "verify", "--requirements", str(doc)])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.stdout)
    assert all(v["verdict"] == "skip" for v in payload["verdicts"])
    assert not payload["run_oracle"]


def test_run_oracle_runs_readonly_command_and_reports_pass(tmp_path):
    doc = _fixture_doc(tmp_path, ["`startd8 navigator view-definition` exits 0."])
    res = RUNNER.invoke(app, ["navigator", "verify", "--requirements", str(doc), "--run-oracle"])
    assert res.exit_code == 0, res.output
    v = json.loads(res.stdout)["verdicts"][0]
    assert v["verdict"] == "pass"
    assert v["reason"] == "exit 0"


def test_verify_html_projects_verdicts_to_nodes(tmp_path):
    """FR-7 (D-D) / harvest EB-1: verify --format html renders verdicts as oracle-verdict Nodes
    through the existing tree renderer (no new shell). Previously the html arm had no test."""
    doc = _fixture_doc(tmp_path, ["`startd8 navigator view-definition` exits 0."])
    out = tmp_path / "verdicts.html"
    res = RUNNER.invoke(
        app, ["navigator", "verify", "--requirements", str(doc), "--format", "html", "--out", str(out)]
    )
    assert res.exit_code == 0, res.output
    html = out.read_text(encoding="utf-8")
    assert "oracle-verdict" in html and "FR-1" in html


def test_run_oracle_refuses_generate_write_and_self_exec():
    """FR-5: generate (non-nav verb), --out (write flag), and self-exec all -> skip."""
    ds = [
        OracleDescriptor("FR-1", KIND_COMMAND, ("startd8", "generate", "backend"), "x"),
        OracleDescriptor("FR-2", KIND_COMMAND,
                         ("startd8", "navigator", "build", "--source", "pipeline", "--out", "x.html"), "x"),
        OracleDescriptor("FR-3", KIND_COMMAND, ("startd8", "navigator", "verify", "--requirements", "y"), "x"),
    ]
    verdicts = {v.fr_id: v for v in evaluate(ds, run_oracle=True)}
    assert verdicts["FR-1"].verdict == "skip" and verdicts["FR-1"].reason == "non-allowlisted"
    assert verdicts["FR-2"].verdict == "skip" and verdicts["FR-2"].reason == "side-effecting"
    assert verdicts["FR-3"].verdict == "skip" and verdicts["FR-3"].reason == "self-exec"


def test_run_oracle_refuses_equals_form_write_flag():
    """Harvest H1 (security): the ``--out=x`` (equals) form must not evade the write-flag guard.

    click/Typer accept both ``--out x`` and ``--out=x``; matching only the bare token let an authored
    clause smuggle a repo-writing command past the read-only allow-list under ``--run-oracle``.
    """
    ds = [
        OracleDescriptor("FR-1", KIND_COMMAND,
                         ("startd8", "navigator", "build", "--source", "pipeline", "--out=x.html"), "x"),
    ]
    v = evaluate(ds, run_oracle=True)[0]
    assert v.verdict == "skip" and v.reason == "side-effecting"


def test_run_oracle_missing_input_is_error(tmp_path):
    """FR-5: a referenced input path that is absent → a distinct error verdict (not silent fail)."""
    ds = [OracleDescriptor(
        "FR-1", KIND_COMMAND,
        ("startd8", "navigator", "build", "--source", "requirements",
         "--requirements", str(tmp_path / "nope.md"), "--format", "json"),
        "x")]
    v = evaluate(ds, run_oracle=True)[0]
    assert v.verdict == "error" and "missing input" in v.reason
    assert aggregate_exit_code([v]) != 0


def test_aggregate_exit_code():
    from startd8.navigator.verify_oracle import OracleVerdict
    assert aggregate_exit_code([OracleVerdict("a", "command", "pass"), OracleVerdict("b", "manual", "skip")]) == 0
    assert aggregate_exit_code([OracleVerdict("a", "command", "fail")]) != 0
    assert aggregate_exit_code([OracleVerdict("a", "command", "error")]) != 0


# ─────────────────────────────── FR-6 — pipeline provenance ───────────────────────────────────────

def test_provenance_longest_prefix_ownership():
    """FR-6: an artifact under backend_codegen/ is owned by stage:impl, chain ends at intent."""
    nodes = nodes_from_pipeline()
    rows = pipeline_provenance(nodes, stages(), query="src/startd8/backend_codegen/deep/foo.py")
    assert all(set(r) == {"element", "stage", "origin", "value", "present"} for r in rows)
    stage_keys = [r["stage"] for r in rows]
    assert stage_keys[0] == "stage:intent"          # chain walks upstream→downstream
    assert stage_keys[-1] == "stage:impl"           # ends at the owning stage
    # test_emitter.py is a longer prefix match than backend_codegen/ → owned by stage:test.
    rows2 = pipeline_provenance(nodes, stages(),
                                query="src/startd8/backend_codegen/test_emitter.py")
    assert rows2[-1]["stage"] == "stage:test"


def test_provenance_not_found_row():
    nodes = nodes_from_pipeline()
    rows = pipeline_provenance(nodes, stages(), query="totally/unowned/path.py")
    assert len(rows) == 1
    assert rows[0]["present"] is False
    assert rows[0]["stage"] is None


# ── R8-EB-4: FR-id query resolution ──────────────────────────────────────────────────────────────

def _fr_node(key, ref, etype="code"):
    return Node(key=key, does="", lives=(NodeEvidence(type=etype, ref=ref, note=""),),
                category="functional-requirements")


def test_provenance_fr_id_resolves_to_chain():
    """R8-EB-4: an FR-id query resolves via requirement_nodes to the FR's code file, then traces."""
    nodes = nodes_from_pipeline()
    reqs = [_fr_node("FR-9", "src/startd8/backend_codegen/thing.py")]
    rows = pipeline_provenance(nodes, stages(), query="FR-9", requirement_nodes=reqs)
    assert [r["stage"] for r in rows][-1] == "stage:impl"       # backend_codegen/ → impl
    intent = rows[0]
    assert intent["stage"] == "stage:intent" and "FR-9" in intent["origin"]   # requirement named at origin


def test_provenance_fr_id_without_corpus_is_not_found():
    """R8-EB-4: an FR-id with no requirement_nodes → an honest not-found row (never an invented path)."""
    rows = pipeline_provenance(nodes_from_pipeline(), stages(), query="FR-3")
    assert len(rows) == 1 and rows[0]["present"] is False
    assert "no requirement corpus" in rows[0]["origin"]


def test_provenance_unknown_fr_id_is_not_found():
    rows = pipeline_provenance(nodes_from_pipeline(), stages(), query="FR-404",
                               requirement_nodes=[_fr_node("FR-9", "src/x.py")])
    assert rows[0]["present"] is False and "not in the provided requirement corpus" in rows[0]["origin"]


def test_provenance_fr_id_with_no_code_ref_is_not_found():
    rows = pipeline_provenance(nodes_from_pipeline(), stages(), query="FR-9",
                               requirement_nodes=[_fr_node("FR-9", "docs/x.md", etype="doc")])
    # a doc-only Lives still yields a path (fallback), but a bare FR with no lives → not-found:
    bare = Node(key="FR-9", does="", category="functional-requirements")
    rows2 = pipeline_provenance(nodes_from_pipeline(), stages(), query="FR-9", requirement_nodes=[bare])
    assert rows2[0]["present"] is False and "no code" in rows2[0]["origin"]
    assert isinstance(rows, list)


def test_cli_provenance_fr_id(tmp_path):
    """R8-EB-4 wired: navigator provenance --query FR-1 --requirements <doc> traces via the FR's Lives."""
    doc = tmp_path / "reqs.md"
    doc.write_text(
        "# Demo — Requirements\n\n"
        "- **FR-1 — Demo.** Does a thing. Name: demo thing. "
        "Lives: code src/startd8/backend_codegen/thing.py. Verify: it works. Serves: O-1\n",
        encoding="utf-8",
    )
    res = RUNNER.invoke(app, ["navigator", "provenance", "--query", "FR-1", "--requirements", str(doc)])
    assert res.exit_code == 0, res.output
    chain = json.loads(res.stdout)["chain"]
    assert chain[-1]["stage"] == "stage:impl"


def test_cli_provenance_fr_id_without_requirements_errors_with_flag_name(tmp_path):
    """HTH harvest: an FR-id query without --requirements errors naming the CLI flag (not the lib param)."""
    res = RUNNER.invoke(app, ["navigator", "provenance", "--query", "FR-1"])
    assert res.exit_code != 0
    assert "--requirements" in res.output and "requirement_nodes" not in res.output


def test_cli_provenance_unowned_path_exits_nonzero():
    res = RUNNER.invoke(app, ["navigator", "provenance", "--query", "totally/unowned.py"])
    assert res.exit_code != 0
    assert json.loads(res.stdout)["chain"][0]["present"] is False


def test_cli_provenance_html_renders_chain_as_nodes(tmp_path):
    """FR-9 / R8-EB-6: --format html projects chain rows to pipeline-provenance Nodes via the tree renderer."""
    out = tmp_path / "prov.html"
    res = RUNNER.invoke(
        app, ["navigator", "provenance", "--query", "src/startd8/backend_codegen/x.py",
              "--format", "html", "--out", str(out)]
    )
    assert res.exit_code == 0, res.output
    html = out.read_text(encoding="utf-8")
    assert "pipeline-provenance" in html and "stage:impl" in html


def test_cli_provenance_html_requires_out():
    res = RUNNER.invoke(app, ["navigator", "provenance", "--query", "a/b.py", "--format", "html"])
    assert res.exit_code != 0 and "--out is required" in res.output


def test_cli_provenance_html_not_found_still_exits_nonzero(tmp_path):
    """FR-9 exit-code contract, html quadrant (harvest gate): a not-found trace still exits 1 under
    --format html (and writes the file) so CI distinguishes traced from unowned in either format."""
    out = tmp_path / "nf.html"
    res = RUNNER.invoke(
        app, ["navigator", "provenance", "--query", "totally/unowned.py", "--format", "html", "--out", str(out)]
    )
    assert res.exit_code == 1
    assert out.exists() and "pipeline-provenance" in out.read_text(encoding="utf-8")


def test_cli_provenance_rejects_unknown_format():
    res = RUNNER.invoke(app, ["navigator", "provenance", "--query", "a/b.py", "--format", "yaml"])
    assert res.exit_code != 0 and "unknown --format" in res.output


def test_provenance_spec_stage_still_emits_row(tmp_path):
    """R1-S10: a chain through a SPEC (un-built) stage still emits that stage's row."""
    (tmp_path / "src" / "startd8" / "seeds").mkdir(parents=True)
    (tmp_path / "src" / "startd8" / "backend_codegen").mkdir(parents=True)
    nodes = nodes_from_pipeline(repo=tmp_path)  # contract/functional artifacts absent → spec
    rows = pipeline_provenance(nodes, stages(), query="src/startd8/backend_codegen/foo.py")
    by = {r["stage"]: r for r in rows}
    assert "stage:contract" in by
    assert by["stage:contract"]["present"] is False     # SPEC stage still surfaces with the gap
    assert by["stage:impl"]["present"] is True           # its artifact dir exists in the fixture repo


def test_provenance_lives_in_provenance_module():
    """FR-6: pipeline_provenance is a sibling of chrome_provenance in the same module."""
    import startd8.navigator.provenance as prov
    assert hasattr(prov, "pipeline_provenance")
    assert hasattr(prov, "chrome_provenance")


# ─────────────────────────────── FR-8 — guards ───────────────────────────────────────────────────

def test_validate_definitions_clean_with_pipeline_domain():
    assert "pipeline" in DEFINITION_REGISTRY
    assert validate_definitions(DEFINITION_REGISTRY) == []


def test_pipeline_status_vocab_is_wellformed():
    """FR-8 (R1-F3): a DEDICATED status-vocab assertion (validate_definitions does NOT cover this).

    Each declared status has a non-empty label/meaning/color and an int severity.
    """
    assert PIPELINE_PROFILE.statuses, "pipeline profile has no statuses"
    for s in PIPELINE_PROFILE.statuses:
        assert s.label and s.label.strip(), f"{s.key} has empty label"
        assert s.meaning and s.meaning.strip(), f"{s.key} has empty meaning"
        assert s.color and s.color.strip(), f"{s.key} has empty color"
        assert isinstance(s.severity, int), f"{s.key} severity is not an int"


def test_pipeline_domain_keyed_by_nodestatus_ids():
    """FR-1/R1-F2: the vocab is keyed by NodeStatus ids (built/spec), not prose labels."""
    keys = set(PIPELINE_DEFINITION.vocabulary["statuses"])
    assert keys == {"built", "spec"}


def test_no_new_module_imports_wireframe_view_for_pipeline_path():
    """FR-8: the pipeline/oracle path introduces no new wireframe_view import (no new shell)."""
    for mod in ("sources_pipeline", "verify_oracle"):
        src = (Path(__file__).parents[3] / "src" / "startd8" / "navigator" / f"{mod}.py").read_text()
        assert "wireframe_view" not in src


# ── REQ-16 FR-1 — the typed derivation edge (distinct from containment; regime reserved/unset) ─────

def test_stage_exposes_derivation_edge_distinct_from_children():
    """REQ-16 FR-1: a stage with an upstream input exposes it as a typed DerivationEdge object, distinct
    from containment `children`. REQ-18 FR-1 populates its `regime` slot with the declared `deterministic`
    (the pipeline is the `$0` compiler); a BARE DerivationEdge still defaults `regime=None` (the reserved slot)."""
    from startd8.navigator.models import DerivationEdge

    nodes = {n.key: n for n in nodes_from_pipeline()}
    contract = nodes["stage:contract"]
    assert contract.children == ()                       # containment is untouched (NR-5)
    assert contract.derivation and all(isinstance(e, DerivationEdge) for e in contract.derivation)
    edge = contract.derivation[0]
    assert edge.from_key == "stage:functional"           # the typed derivation input
    assert edge.relation == "derived-from"
    assert edge.regime == "deterministic"                # REQ-18 FR-1: declared regime on the pipeline edge
    assert DerivationEdge(from_key="x").regime is None    # REQ-16 NR-6: the slot itself still defaults unset
    # intent is the root — no upstream derivation
    assert nodes["stage:intent"].derivation == ()


def test_derivation_edges_mirror_the_depends_on_keys():
    """REQ-16 FR-1: the typed derivation edges cover the same upstream set as child_keys (both retained;
    child_keys still drives topo_order, the typed edge drives provenance)."""
    for n in nodes_from_pipeline():
        assert tuple(e.from_key for e in n.derivation) == tuple(n.child_keys)


def test_pipeline_provenance_chain_is_sourced_from_the_typed_edge():
    """REQ-16 FR-1: pipeline_provenance returns a chain sourced from the derivation edge (not the
    longest-prefix heuristic) — proven by mutating a node's typed edge and seeing the chain follow it."""
    import dataclasses

    from startd8.navigator.models import DerivationEdge

    nodes = nodes_from_pipeline()
    # Baseline: impl derives from contract → chain is intent→functional→contract→impl.
    rows = pipeline_provenance(nodes, stages(), query="src/startd8/backend_codegen/foo.py")
    assert [r["stage"] for r in rows][-1] == "stage:impl"
    assert "stage:contract" in [r["stage"] for r in rows]
    # Re-point impl's DERIVATION edge straight at intent (bypassing contract/functional). If the walk
    # read child_keys (unchanged) the chain would still include contract; sourcing from the typed edge,
    # the chain collapses to intent→impl — the discriminating proof the edge drives the walk.
    rewired = tuple(
        dataclasses.replace(n, derivation=(DerivationEdge(from_key="stage:intent"),))
        if n.key == "stage:impl" else n
        for n in nodes
    )
    rows2 = pipeline_provenance(rewired, stages(), query="src/startd8/backend_codegen/foo.py")
    chain2 = [r["stage"] for r in rows2]
    assert chain2 == ["stage:intent", "stage:impl"]      # followed the typed edge, not child_keys
    assert "stage:contract" not in chain2
