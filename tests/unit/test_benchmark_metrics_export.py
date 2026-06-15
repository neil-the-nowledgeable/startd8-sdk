"""Tests for the Prometheus textfile exporter (P5 / FR-18b)."""

import json
from pathlib import Path

from startd8.benchmark_matrix.metrics_export import export_run_metrics, write_run_metrics


def _write_run(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "run-spec.json").write_text(json.dumps({"name": "r1", "spec_hash": "49252392edaa0000"}))
    # 2 ok (→done), 1 infra_fail (→blocked, excluded), 1 failed (→cancelled)
    (run / "cells.json").write_text(json.dumps([
        {"cell_id": "h:a:opus:r0", "service": "a", "model": "opus", "status": "ok", "cost_usd": 0.1},
        {"cell_id": "h:b:opus:r0", "service": "b", "model": "opus", "status": "ok", "cost_usd": 0.2},
        {"cell_id": "h:a:gpt:r0", "service": "a", "model": "gpt", "status": "infra_fail", "cost_usd": 0.0},
        {"cell_id": "h:b:gem:r0", "service": "b", "model": "gem", "status": "failed", "cost_usd": 0.05},
    ]))
    (run / "aggregate.json").write_text(json.dumps({
        "by_model": {
            "opus": {"cost_total_usd": 0.30, "quality_median": 1.0, "pass_rate": 1.0},
            "gem": {"cost_total_usd": 0.05, "quality_median": 0.9, "pass_rate": 1.0},
            "gpt": {"cost_total_usd": 0.0, "quality_median": None, "pass_rate": None},
        },
    }))
    return run


def test_exposition_has_dashboard_metric_names(tmp_path):
    text = export_run_metrics(_write_run(tmp_path))
    proj = 'startd8-benchmark-run-49252392edaa'
    # cost metric the SRE dashboard queries
    assert f'startd8_cost_total{{project="{proj}",model="opus"}} 0.3' in text
    # task_count_by_status the dashboard queries — ok→done(2), infra→blocked(1), failed→cancelled(1)
    assert f'task_count_by_status{{project_id="{proj}",task_status="done"}} 2' in text
    assert f'task_count_by_status{{project_id="{proj}",task_status="blocked"}} 1' in text
    assert f'task_count_by_status{{project_id="{proj}",task_status="cancelled"}} 1' in text
    # analyst gauge (gpt has no quality → omitted)
    assert 'benchmark_quality_median{' in text and 'model="gpt"' not in text.split("benchmark_quality_median")[1].split("# HELP")[0]


def test_valid_exposition_lines(tmp_path):
    text = export_run_metrics(_write_run(tmp_path))
    for ln in text.splitlines():
        if ln and not ln.startswith("#"):
            # "name{labels} value"
            assert "{" in ln and "} " in ln
            float(ln.rsplit(" ", 1)[1])  # value parses


def test_write_run_metrics(tmp_path):
    out = write_run_metrics(_write_run(tmp_path), tmp_path / "out")
    assert Path(out["path"]).name == "run-metrics.prom"
    assert out["series"] >= 5
