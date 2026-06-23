"""CLI tests for `startd8 compare-models-e2e` (S7, FR-11/12/13/21).

Thin-wrapper tests: the orchestration lives in ``model_comparison_e2e``; here we only assert the
CLI wires flags through, fails fast on a bad preflight, prints the dry-run command plan (cap-delivery
once), threads ``--advance-threshold`` into the gate, and prints the advancing line on a mocked happy
path. All paths are no-network / no-spend (preflight uses ``mock:`` providers; orchestration is
monkeypatched).
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from startd8.cli import app
from startd8 import model_comparison_e2e as e2e

pytestmark = pytest.mark.unit

runner = CliRunner()


def _inputs(tmp_path):
    plan = tmp_path / "plan.md"
    reqs = tmp_path / "requirements.md"
    plan.write_text("# Plan\n", encoding="utf-8")
    reqs.write_text("# Reqs\n", encoding="utf-8")
    return plan, reqs


def _base_args(plan, reqs, tmp_path, *models):
    args = ["compare-models-e2e", "--plan", str(plan), "--requirements", str(reqs)]
    for m in models or ("mock:mock-model", "mock:other-model"):
        args += ["--model", m]
    args += ["--source-root", str(tmp_path / "src"), "--batch-root", str(tmp_path / "out")]
    return args


# (a) dry-run prints the command plan, executes nothing, cap-delivery appears once.
def test_dry_run_prints_plan_executes_nothing(tmp_path, monkeypatch):
    plan, reqs = _inputs(tmp_path)
    (tmp_path / "src").mkdir()

    # Hard-fail if orchestration ever runs.
    def _boom(*a, **k):
        raise AssertionError("orchestrate_e2e must not run in --dry-run")

    monkeypatch.setattr(e2e, "orchestrate_e2e", _boom)

    res = runner.invoke(
        app,
        _base_args(plan, reqs, tmp_path, "mock:mock-model", "mock:other-model") + ["--dry-run"],
    )
    assert res.exit_code == 0, res.output
    # cap-delivery (shared preamble) shown exactly once.
    assert res.output.count("run-cap-delivery.sh") == 1, res.output
    # both models contribute plan-ingestion + prime lines.
    assert "plan-ingestion" in res.output
    assert "prime" in res.output
    assert "manifest_frozen_v1" in res.output


# (b) preflight failure (<2 distinct models) exits non-zero with the error, before any work.
def test_preflight_failure_too_few_models_exits_nonzero(tmp_path, monkeypatch):
    plan, reqs = _inputs(tmp_path)

    def _boom(*a, **k):
        raise AssertionError("must not orchestrate after a failed preflight")

    monkeypatch.setattr(e2e, "orchestrate_e2e", _boom)

    res = runner.invoke(
        app, _base_args(plan, reqs, tmp_path, "mock:only-one")
    )
    assert res.exit_code == 2, res.output
    assert "Preflight failed" in res.output
    assert "need >=2 distinct valid models" in res.output


# (c) mocked happy path: orchestrate/score/write are stubbed; advancing line + paths printed.
def test_happy_path_prints_advancing_and_paths(tmp_path, monkeypatch):
    plan, reqs = _inputs(tmp_path)
    (tmp_path / "src").mkdir()

    captured = {}

    fake_batch = e2e.E2EBatchResult(
        shared=e2e.StageResult(stage=e2e.STAGE_SHARED_PREAMBLE, status=e2e.StageStatus.SUCCESS),
        models=[
            e2e.ModelResult(model="mock:mock-model"),
            e2e.ModelResult(model="mock:other-model"),
        ],
    )

    monkeypatch.setattr(e2e, "preflight", lambda *a, **k: [])

    def fake_orchestrate(models, *a, **k):
        captured["orchestrate_models"] = list(models)
        return fake_batch

    def fake_score(batch, *a, **k):
        # one advances, one does not — so the advancing line is non-empty and selective.
        batch.models[0].capability = {"score": 0.9}
        batch.models[0].cost_fields = {"cost_attributable_usd": 0.12}
        batch.models[0].advanced = True
        batch.models[1].capability = {"score": 0.3}
        batch.models[1].cost_fields = {"cost_attributable_usd": 0.05}
        batch.models[1].advanced = False
        return batch

    def fake_write(batch, batch_root, **k):
        captured["gate"] = k.get("gate")
        captured["comparison_mode"] = k.get("comparison_mode")
        return {
            "manifest": str(batch_root / "batch-run-manifest.json"),
            "report_md": str(batch_root / "comparison-report.md"),
            "report_json": str(batch_root / "comparison-report.json"),
        }

    monkeypatch.setattr(e2e, "orchestrate_e2e", fake_orchestrate)
    monkeypatch.setattr(e2e, "score_batch", fake_score)
    monkeypatch.setattr(e2e, "write_batch_outputs", fake_write)

    res = runner.invoke(
        app, _base_args(plan, reqs, tmp_path, "mock:mock-model", "mock:other-model")
    )
    assert res.exit_code == 0, res.output
    assert "Advancing to next round:" in res.output
    assert "mock:mock-model" in res.output
    assert "batch-run-manifest.json" in res.output
    assert "comparison-report.md" in res.output
    assert captured["comparison_mode"] == "manifest_frozen_v1"


# (d) --advance-threshold is threaded into the AdvancementGate passed to write_batch_outputs.
def test_advance_threshold_threaded_into_gate(tmp_path, monkeypatch):
    plan, reqs = _inputs(tmp_path)
    (tmp_path / "src").mkdir()

    captured = {}
    fake_batch = e2e.E2EBatchResult(
        shared=e2e.StageResult(stage=e2e.STAGE_SHARED_PREAMBLE, status=e2e.StageStatus.SUCCESS),
        models=[e2e.ModelResult(model="mock:a"), e2e.ModelResult(model="mock:b")],
    )

    monkeypatch.setattr(e2e, "preflight", lambda *a, **k: [])
    monkeypatch.setattr(e2e, "orchestrate_e2e", lambda *a, **k: fake_batch)
    monkeypatch.setattr(e2e, "score_batch", lambda b, *a, **k: b)

    def fake_write(batch, batch_root, **k):
        captured["gate"] = k.get("gate")
        return {
            "manifest": "m.json",
            "report_md": "r.md",
            "report_json": "r.json",
        }

    monkeypatch.setattr(e2e, "write_batch_outputs", fake_write)

    res = runner.invoke(
        app,
        _base_args(plan, reqs, tmp_path, "mock:a", "mock:b") + ["--advance-threshold", "0.85"],
    )
    assert res.exit_code == 0, res.output
    gate = captured["gate"]
    assert isinstance(gate, e2e.AdvancementGate)
    assert gate.min_capability == 0.85


# global-budget guard: per-model budget * n_models over the cap aborts before any work.
def test_global_budget_guard_aborts(tmp_path, monkeypatch):
    plan, reqs = _inputs(tmp_path)

    monkeypatch.setattr(e2e, "preflight", lambda *a, **k: [])

    def _boom(*a, **k):
        raise AssertionError("must not orchestrate when global budget is exceeded")

    monkeypatch.setattr(e2e, "orchestrate_e2e", _boom)

    res = runner.invoke(
        app,
        _base_args(plan, reqs, tmp_path, "mock:a", "mock:b")
        + ["--cost-budget", "5", "--global-budget", "4"],
    )
    assert res.exit_code == 2, res.output
    assert "global-budget" in res.output
