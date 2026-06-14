"""T5.4 — Section-G join contract (R1-S7) + FR-23/FR-24 negative-requirement tests (R1-S1/R2-F2/F3)."""

import json
from pathlib import Path

from startd8.benchmark_matrix.tracking import reconstruct_run_tracking
from startd8.integrations.cost_linkage import cell_costs_from_cells_json, cost_tags
from startd8.integrations.join_contract import JOIN_CONTRACT, verify_join_contract

_SRC = Path(__file__).resolve().parents[2] / "src" / "startd8"
TRACKING_MODULES = [
    _SRC / "integrations" / "milestone_tracking.py",
    _SRC / "integrations" / "cost_linkage.py",
    _SRC / "integrations" / "insight_emission.py",
    _SRC / "integrations" / "join_contract.py",
    _SRC / "integrations" / "tracking_redaction.py",
    _SRC / "benchmark_matrix" / "tracking.py",
]


def _write_run(tmp_path):
    cells = [
        {"cell_id": "h:cart:opus:r0", "service": "cart", "model": "opus", "language": "go",
         "repetition": 0, "status": "ok", "cost_usd": 0.10},
        {"cell_id": "h:email:opus:r0", "service": "email", "model": "opus", "language": "py",
         "repetition": 0, "status": "failed", "cost_usd": 0.05, "error": "x"},
    ]
    run = tmp_path / "run"
    run.mkdir()
    (run / "run-spec.json").write_text(json.dumps({"name": "r", "spec_hash": "h" * 32}))
    (run / "cells.json").write_text(json.dumps(cells))
    return run


# --- T5.4: the join contract holds on real emitted artifacts ---

def test_join_contract_holds_on_real_artifacts(tmp_path):
    run = _write_run(tmp_path)
    reconstruct_run_tracking(run, mode="cell")
    cell_span = json.loads(
        (run / "contextcore-tracking" / "contextcore-tasks" / "h:cart:opus:r0.json").read_text()
    )
    artifacts = {
        "cell_span": cell_span,
        "cost_rollup": cell_costs_from_cells_json(run / "cells.json"),
        "cost_tags": cost_tags(milestone_id="M3", cell_id="h:cart:opus:r0"),
        "insight_call": {"input_tokens": 1200, "output_tokens": 340},
        "task_span": cell_span,
    }
    results = verify_join_contract(artifacts)
    assert len(results) == len(JOIN_CONTRACT) == 5
    failed = [r for r in results if not r["ok"]]
    assert not failed, failed


def test_join_contract_detects_missing_join_attribute():
    bad_span = {"attributes": {"task.labels": ["service:cart"], "project.id": "x"}}  # no run: label
    results = verify_join_contract({"cell_span": bad_span, "task_span": bad_span})
    loki_row = next(r for r in results if "results Loki" in r["link"])
    assert loki_row["ok"] is False
    cost_row = next(r for r in results if r["link"] == "Business-execution ↔ cost")
    assert cost_row["ok"] is False and "missing" in cost_row["reason"]  # artifact absent


# --- FR-23 (R2-F3): reuse, not reimplementation ---

def test_fr23_tracking_does_not_reimplement_canonical_machinery():
    forbidden = ["def _build_state_file", "class InsightEmitter", "def record_cost("]
    for mod in TRACKING_MODULES:
        src = mod.read_text()
        for f in forbidden:
            assert f not in src, f"{mod.name} reimplements canonical machinery: {f}"
    # and it DOES call the canonical emitter
    assert "emit_task_tracking_artifacts" in (_SRC / "integrations" / "milestone_tracking.py").read_text()
    assert "emit_task_tracking_artifacts" in (_SRC / "benchmark_matrix" / "tracking.py").read_text()


# --- FR-24 (R2-F2): SDK emits spans + zero-point events, no derived rate/velocity/burndown gauges ---

def test_fr24_no_sdk_derived_gauge_metrics():
    forbidden = [
        "create_gauge", "create_observable_gauge", "create_up_down_counter",
        "create_histogram", ".create_counter(", "meter.create",
    ]
    for mod in TRACKING_MODULES:
        src = mod.read_text()
        for f in forbidden:
            assert f not in src, f"{mod.name} creates an OTel metric ({f}) — gauges are ContextCore-owned (FR-24)"
