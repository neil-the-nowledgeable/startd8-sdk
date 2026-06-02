"""Tests for the Prime Contractor multi-model comparison harness.

Covers: slug derivation, command construction (model pinning, no routing flags),
metric extraction over fixture artifacts, ranking, and a mock end-to-end batch.
Plan: docs/design/PRIME_MODEL_COMPARISON_PLAN.md (S1-S7).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture()
def harness():
    """Import run_prime_model_comparison.py as a module."""
    script = Path(__file__).resolve().parents[3] / "scripts" / "run_prime_model_comparison.py"
    assert script.is_file(), f"Script not found: {script}"
    spec = importlib.util.spec_from_file_location("run_prime_model_comparison", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- slug (S1)

@pytest.mark.parametrize("spec,expected", [
    ("anthropic:claude-opus-4-8", "anthropic-claude-opus-4-8"),
    ("openai:gpt-5.5", "openai-gpt-5.5"),
    ("gemini:gemini-2.5-pro", "gemini-gemini-2.5-pro"),
    ("mock:mock-model", "mock-mock-model"),
])
def test_slug(harness, spec, expected):
    assert harness.slug(spec) == expected


# --------------------------------------------------------------------------- command (S3, FR-7/8)

def test_build_command_pins_model_and_omits_routing(harness, tmp_path):
    cmd = harness.build_command(
        seed=tmp_path / "seed.json",
        workdir=tmp_path / "wd",
        output=tmp_path / "out",
        model="anthropic:claude-opus-4-8",
        cost_budget=5.0,
    )
    # Both generation paths pinned to the same model (FR-7).
    assert cmd[cmd.index("--lead-agent") + 1] == "anthropic:claude-opus-4-8"
    assert cmd[cmd.index("--drafter-agent") + 1] == "anthropic:claude-opus-4-8"
    # Freshness (FR-8) and isolation flags present.
    assert "--force-regenerate" in cmd
    assert "--project-root" in cmd and "--output-dir" in cmd
    # Routing / micro-prime must NOT be enabled (off by default — D1).
    assert "--complexity-routing" not in cmd
    assert "--micro-prime" not in cmd
    # Cost budget forwarded.
    assert cmd[cmd.index("--cost-budget") + 1] == "5.0"


def test_build_command_omits_budget_when_none(harness, tmp_path):
    cmd = harness.build_command(tmp_path / "s", tmp_path / "w", tmp_path / "o", "mock:m", None)
    assert "--cost-budget" not in cmd


# --------------------------------------------------------------------------- extraction (S4, FR-9/10)

def _write_artifacts(output_dir: Path, *, processed, succeeded, failed, success,
                     disk_scores, semantic_counts, total_usd, avg_assembly_delta=0.1,
                     aggregate_score=0.8):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "prime-result.json").write_text(json.dumps({
        "processed": processed, "succeeded": succeeded, "failed": failed, "success": success,
    }))
    features = [
        {"disk_quality_score": d, "semantic_error_count": s, "success": True}
        for d, s in zip(disk_scores, semantic_counts)
    ]
    (output_dir / "prime-postmortem-report.json").write_text(json.dumps({
        "total_features": processed, "successful_features": succeeded, "failed_features": failed,
        "aggregate_score": aggregate_score, "avg_assembly_delta": avg_assembly_delta,
        "features": features, "cost_summary": {"total_usd": total_usd},
    }))


def test_extract_metrics_full(harness, tmp_path):
    _write_artifacts(tmp_path, processed=4, succeeded=3, failed=1, success=True,
                     disk_scores=[1.0, 0.8, 0.6], semantic_counts=[0, 1, 2], total_usd=0.12)
    m = harness.extract_metrics(tmp_path)
    assert m["processed"] == 4 and m["succeeded"] == 3 and m["failed"] == 1
    assert m["completion_rate"] == pytest.approx(0.75)
    assert m["mean_disk_quality_score"] == pytest.approx((1.0 + 0.8 + 0.6) / 3)
    assert m["semantic_error_count"] == 3
    assert m["total_cost"] == pytest.approx(0.12)
    assert m["cost_source"] == "postmortem"
    assert m["cost_per_succeeded_feature"] == pytest.approx(0.12 / 3)
    assert m["artifacts_found"] is True


def test_extract_metrics_missing_artifacts(harness, tmp_path):
    """No crash, all None/zero when a run produced nothing (FR-3/FR-10)."""
    m = harness.extract_metrics(tmp_path)
    assert m["artifacts_found"] is False
    assert m["mean_disk_quality_score"] is None
    assert m["total_cost"] is None
    assert m["cost_per_succeeded_feature"] is None
    assert m["processed"] == 0


# --------------------------------------------------------------------------- ranking (S6, FR-11)

def test_rank_by_disk_quality_then_cost(harness):
    results = [
        {"model": "low", "metrics": {"mean_disk_quality_score": 0.5, "cost_per_succeeded_feature": 0.01}},
        {"model": "high", "metrics": {"mean_disk_quality_score": 0.9, "cost_per_succeeded_feature": 0.05}},
        {"model": "mid", "metrics": {"mean_disk_quality_score": 0.7, "cost_per_succeeded_feature": 0.02}},
    ]
    ranked = harness.rank_models(results)
    assert [r["model"] for r in ranked] == ["high", "mid", "low"]


def test_rank_tiebreak_on_cost(harness):
    results = [
        {"model": "pricey", "metrics": {"mean_disk_quality_score": 0.8, "cost_per_succeeded_feature": 0.10}},
        {"model": "cheap", "metrics": {"mean_disk_quality_score": 0.8, "cost_per_succeeded_feature": 0.02}},
    ]
    assert [r["model"] for r in harness.rank_models(results)][0] == "cheap"


def test_rank_none_disk_sorts_last(harness):
    results = [
        {"model": "noartifacts", "metrics": {"mean_disk_quality_score": None, "cost_per_succeeded_feature": None}},
        {"model": "real", "metrics": {"mean_disk_quality_score": 0.3, "cost_per_succeeded_feature": 0.5}},
    ]
    assert [r["model"] for r in harness.rank_models(results)][0] == "real"


# --------------------------------------------------------------------------- report (S6)

def test_build_markdown_has_columns_and_winner(harness):
    payload = {
        "batch_id": "b1", "generated_at": "2026-06-01T00:00:00Z", "seed": "/s.json",
        "ranked": [
            {"model": "anthropic:claude-opus-4-8",
             "metrics": {"status": "success", "processed": 3, "succeeded": 3, "failed": 0,
                         "completion_rate": 1.0, "mean_disk_quality_score": 0.95,
                         "aggregate_score": 0.9, "avg_assembly_delta": 0.0,
                         "semantic_error_count": 0, "total_cost": 0.2,
                         "cost_per_succeeded_feature": 0.066, "artifacts_found": True}},
            {"model": "openai:gpt-5.5",
             "metrics": {"status": "success", "processed": 3, "succeeded": 2, "failed": 1,
                         "completion_rate": 0.66, "mean_disk_quality_score": 0.7,
                         "aggregate_score": 0.6, "avg_assembly_delta": 0.1,
                         "semantic_error_count": 2, "total_cost": 0.1,
                         "cost_per_succeeded_feature": 0.05, "artifacts_found": True}},
        ],
    }
    md = harness.build_markdown(payload)
    assert "anthropic:claude-opus-4-8" in md and "openai:gpt-5.5" in md
    assert "Recommended: `anthropic:claude-opus-4-8`" in md
    assert "Mean disk quality" in md
    assert "single-run" in md.lower()


# --------------------------------------------------------------------------- mock end-to-end (S2/S3 wiring)

def test_main_dry_run_prints_plan(harness, tmp_path, capsys):
    seed = tmp_path / "seed.json"
    seed.write_text("{}")
    rc = harness.main([
        "--seed", str(seed), "--source-root", str(tmp_path),
        "--model", "mock:a", "--model", "mock:b",
        "--batch-root", str(tmp_path / "batch"), "--dry-run",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "mock:a" in out and "mock:b" in out
    assert "--lead-agent" in out and "--force-regenerate" in out


def test_main_requires_two_models(harness, tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text("{}")
    rc = harness.main(["--seed", str(seed), "--model", "mock:only-one"])
    assert rc == 2


def test_main_rejects_batch_root_equal_source(harness, tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text("{}")
    rc = harness.main([
        "--seed", str(seed), "--source-root", str(tmp_path),
        "--model", "mock:a", "--model", "mock:b", "--batch-root", str(tmp_path),
    ])
    assert rc == 2


# --------------------------------------------------------------------------- H1: nested batch exclusion

def test_ignore_factory_excludes_nested_batch_root(harness, tmp_path):
    source = tmp_path / "proj"
    source.mkdir()
    (source / "src").mkdir()
    batch = source / "out" / "batch1"
    ignore = harness._ignore_factory(source, batch)
    # At the source root, the batch's top component ("out") is excluded...
    top_ignored = ignore(str(source), ["src", "out", "README.md"])
    assert "out" in top_ignored and "src" not in top_ignored
    # ...but not at a sibling/child dir of the same name elsewhere.
    child_ignored = ignore(str(source / "src"), ["out"])
    assert "out" not in child_ignored


def test_ignore_factory_no_batch_outside_source(harness, tmp_path):
    source = tmp_path / "proj"
    source.mkdir()
    batch = tmp_path / "elsewhere"  # not nested
    ignore = harness._ignore_factory(source, batch)
    assert "out" not in ignore(str(source), ["out", "src"])


def test_materialize_copy_excludes_nested_batch(harness, tmp_path):
    source = tmp_path / "proj"
    (source / "src").mkdir(parents=True)
    (source / "src" / "a.py").write_text("x = 1\n")
    (source / "out").mkdir()
    (source / "out" / "stale.txt").write_text("prior run")
    batch = source / "out" / "batch1"
    workdir = batch / "mock-a" / "workdir"
    harness.materialize_sandbox(source, workdir, "copy", batch_root=batch)
    assert (workdir / "src" / "a.py").is_file()
    assert not (workdir / "out").exists()  # nested batch output not copied in


def test_materialize_copy_excludes_stale_run_state(harness, tmp_path):
    """A fresh sandbox must NOT inherit .prime_contractor_state.json / .startd8 (would skip work)."""
    source = tmp_path / "proj"
    (source / "src").mkdir(parents=True)
    (source / "src" / "a.py").write_text("x = 1\n")
    (source / ".prime_contractor_state.json").write_text('{"done": true}')
    (source / ".startd8").mkdir()
    (source / ".startd8" / "state.json").write_text("{}")
    workdir = tmp_path / "batch" / "mock-a" / "workdir"
    harness.materialize_sandbox(source, workdir, "copy", batch_root=tmp_path / "batch")
    assert (workdir / "src" / "a.py").is_file()
    assert not (workdir / ".prime_contractor_state.json").exists()
    assert not (workdir / ".startd8").exists()


# --------------------------------------------------------------------------- M1: timeout

def test_run_command_timeout_marks_failed(harness, tmp_path):
    # A command that sleeps longer than the timeout.
    result = harness.run_command(["python3", "-c", "import time; time.sleep(5)"], tmp_path, timeout=0.5)
    assert result["timed_out"] is True
    assert result["returncode"] == 124
