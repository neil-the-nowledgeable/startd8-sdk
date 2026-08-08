"""REQ-03 Loop Rundown — the dry-run spine-walk emitter over a LoopManifest.

A **Rundown** walks a dev-os LoopManifest's ``pieces ∪ gates`` and emits one ``dry_run_trace`` verdict per
node (contextcore ``DryRunVerdict.to_dict()`` shape, parity-guarded) — a describe-only pass with ZERO side
effects. These tests assert the shape/vocab contract, the control-flow ``would_act`` mapping, honest GAP
detection on a dangling edge, and the side-effect ban (byte-identical queue — the same guard as
``test_dry_run_gate.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from startd8.workflows.loop_queue.dry_run_spine import spine_verdicts, spine_verdicts_from_path
from startd8.workflows.loop_queue.models import (
    DRY_RUN_GAP_WHAT_CHANGE,
    DRY_RUN_WOULD_ACT_VALUES,
    LoopQueueConfig,
)
from startd8.workflows.loop_queue.queue import WorkflowLoopQueue

# The canonical dev-os conformance manifest (the SIL-REX spine).
_THANOS_MANIFEST = Path(
    "/Users/neilyashinsky/Documents/dev/dev-os/loops/examples/thanos-sil-rex.loop.yaml"
)

_VERDICT_FIELDS = {
    "stage_id",
    "received",
    "would_act",
    "what_change",
    "inputs",
    "outputs",
    "downstream_handoff",
    "why",
}


def _mini_manifest(tmp_path: Path, *, dangling: bool = False) -> Path:
    """A tiny 2-piece + 1-gate spine; optionally with a dangling edge endpoint (→ a GAP)."""
    doc = {
        "schema_version": "1.0.0",
        "pilot_id": "t",
        "pieces": [
            {"id": "measure", "kind": "cadence", "role": "measure"},
            {"id": "opt", "kind": "cadence", "role": "orchestrator", "config": {"optional": True}},
        ],
        "gates": [{"id": "admit", "kind": "bound_eligible"}],
        "edges": [
            {"from": "measure", "to": "admit", "contract": "bound-then-admit"},
        ],
    }
    if dangling:
        doc["edges"].append({"from": "admit", "to": "ghost-node", "contract": "handoff"})
    p = tmp_path / "mini.loop.yaml"
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return p


# --------------------------------------------------------------------------- shape / vocab


def test_every_verdict_matches_the_dryrunverdict_shape(tmp_path):
    verdicts = spine_verdicts_from_path(_mini_manifest(tmp_path))
    assert verdicts, "expected at least one verdict"
    for v in verdicts:
        assert set(v.keys()) == _VERDICT_FIELDS
        assert v["would_act"] in DRY_RUN_WOULD_ACT_VALUES
        assert isinstance(v["inputs"], list) and isinstance(v["outputs"], list)
        assert v["downstream_handoff"] is None


def test_one_verdict_per_node_in_declaration_order(tmp_path):
    verdicts = spine_verdicts_from_path(_mini_manifest(tmp_path))
    ids = [v["stage_id"] for v in verdicts]
    # pieces (declaration order) then gates — matches render_node_graph's nodes = pieces ∪ gates
    assert ids == ["measure", "opt", "admit"]


def test_label_sources_from_role(tmp_path):
    verdicts = spine_verdicts_from_path(_mini_manifest(tmp_path))
    measure = next(v for v in verdicts if v["stage_id"] == "measure")
    assert measure["what_change"].startswith("measure")  # role, not id-only


# --------------------------------------------------------------------------- control-flow mapping


def test_spine_piece_would_act_yes(tmp_path):
    verdicts = spine_verdicts_from_path(_mini_manifest(tmp_path))
    measure = next(v for v in verdicts if v["stage_id"] == "measure")
    assert measure["would_act"] == "yes"
    assert measure["received"] is True


def test_optional_piece_is_not_mine(tmp_path):
    verdicts = spine_verdicts_from_path(_mini_manifest(tmp_path))
    opt = next(v for v in verdicts if v["stage_id"] == "opt")
    assert opt["would_act"] == "not-mine"


def test_gate_would_act_yes(tmp_path):
    verdicts = spine_verdicts_from_path(_mini_manifest(tmp_path))
    admit = next(v for v in verdicts if v["stage_id"] == "admit")
    assert admit["would_act"] == "yes"


def test_edges_populate_inputs_and_outputs(tmp_path):
    verdicts = spine_verdicts_from_path(_mini_manifest(tmp_path))
    measure = next(v for v in verdicts if v["stage_id"] == "measure")
    admit = next(v for v in verdicts if v["stage_id"] == "admit")
    assert measure["outputs"] == ["admit:bound-then-admit"]
    assert admit["inputs"] == ["measure:bound-then-admit"]


# --------------------------------------------------------------------------- honest GAP


def test_dangling_edge_endpoint_is_a_gap(tmp_path):
    verdicts = spine_verdicts_from_path(_mini_manifest(tmp_path, dangling=True))
    gap = next(v for v in verdicts if v["stage_id"] == "ghost-node")
    # exactly DryRunVerdict.gap(): received=False, would_act="no", the guarded sentinel what_change
    assert gap["received"] is False
    assert gap["would_act"] == "no"
    assert gap["what_change"] == DRY_RUN_GAP_WHAT_CHANGE


def test_no_gap_when_all_edges_resolve(tmp_path):
    verdicts = spine_verdicts_from_path(_mini_manifest(tmp_path, dangling=False))
    assert not any(v["received"] is False for v in verdicts)


# --------------------------------------------------------------------------- real conformance manifest


@pytest.mark.skipif(not _THANOS_MANIFEST.exists(), reason="dev-os conformance manifest not present")
def test_thanos_spine_is_dense_and_covers_all_nodes():
    doc = yaml.safe_load(_THANOS_MANIFEST.read_text(encoding="utf-8"))
    n_nodes = len(doc.get("pieces") or []) + len(doc.get("gates") or [])
    verdicts = spine_verdicts(doc)
    # one verdict per declared node (dense — 0 GAP for a well-formed spine), plus 0 dangling on thanos
    assert len([v for v in verdicts if v["received"]]) == n_nodes
    assert not any(v["received"] is False for v in verdicts)  # all thanos edges resolve
    # the one optional piece degrades to not-mine
    assert any(v["would_act"] == "not-mine" for v in verdicts)


# --------------------------------------------------------------------------- side-effect ban (FR-2)


def _snapshot(d: Path) -> dict:
    if not d.exists():
        return {}
    return {p.name: p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def test_dry_run_spine_writes_no_queue_state(tmp_path):
    """FR-2: the Rundown is describe-only — byte-identical queue, nothing persisted."""
    q = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "wlq"))
    before = _snapshot(q.storage.queue_root)
    job = q.dry_run_spine(_mini_manifest(tmp_path))
    after = _snapshot(q.storage.queue_root)
    assert before == after  # zero job-state files written
    assert job.dry_run is True
    assert job.config["manifest_ref"].endswith("mini.loop.yaml")
    assert [v["stage_id"] for v in job.dry_run_trace] == ["measure", "opt", "admit"]


def test_dry_run_spine_fails_loud_on_missing_manifest(tmp_path):
    q = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "wlq"))
    with pytest.raises(FileNotFoundError):
        q.dry_run_spine(tmp_path / "nope.loop.yaml")


def test_malformed_yaml_raises_valueerror_not_yamlerror(tmp_path):
    """E1: bad YAML normalizes to ValueError so the CLI's except (FileNotFoundError, ValueError) catches it."""
    bad = tmp_path / "bad.loop.yaml"
    bad.write_text("pieces: [unclosed\n", encoding="utf-8")
    with pytest.raises(ValueError):
        spine_verdicts_from_path(bad)


# --------------------------------------------------------------------------- operator surface (wloop CLI)


def test_wloop_rundown_cli_emits_trace_to_stdout(tmp_path):
    """Value-path: the ``wloop rundown`` operator surface wires the emitter (not built-but-unwired)."""
    import json as _json

    from typer.testing import CliRunner

    from startd8.cli_wloop import wloop_app

    manifest = _mini_manifest(tmp_path)
    res = CliRunner().invoke(
        wloop_app, ["rundown", "--manifest", str(manifest), "--root", str(tmp_path / "wlq")]
    )
    assert res.exit_code == 0, res.output
    trace = _json.loads(res.output)
    assert [v["stage_id"] for v in trace] == ["measure", "opt", "admit"]


def test_wloop_rundown_cli_bad_manifest_exits_2(tmp_path):
    from typer.testing import CliRunner

    from startd8.cli_wloop import wloop_app

    res = CliRunner().invoke(
        wloop_app, ["rundown", "--manifest", str(tmp_path / "nope.yaml"), "--root", str(tmp_path / "wlq")]
    )
    assert res.exit_code == 2
