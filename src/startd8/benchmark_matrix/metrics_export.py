# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Export a finished run's scoring data as Prometheus metrics, $0/offline (P5 / FR-18b).

The benchmark's pass/fail/quality/cost is **static** (`cells.json`/`aggregate.json`), but the
dashboards (P1) query Prometheus. This bridges the gap WITHOUT a live ContextCore: it writes a
Prometheus **textfile exposition** (`.prom`) whose metric names + labels match the dashboard PromQL —
``startd8_cost_total`` (by model) and ``task_count_by_status`` (by mapped status, via the same T4
mapping so exclusions stay excluded), plus analyst gauges. Point a Prometheus *textfile collector* (or
the local docker-compose stack) at the file and the SRE run dashboard renders real numbers.

This is the FR-18(b) static-export path; the FR-18(a) live path (ContextCore ingesting the cell task
spans → ``task.count_by_status``) is the alternative when a ContextCore stack is running.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from ..logging_config import get_logger
from .tracking import CELL_STATUS_MAP, map_cell_status

logger = get_logger(__name__)


def _run_id(run_spec: Dict[str, Any]) -> str:
    return (run_spec.get("spec_hash") or "")[:12] or "unknown"


def _metric(name: str, labels: Dict[str, str], value: float) -> str:
    lbl = ",".join(f'{k}="{v}"' for k, v in labels.items())
    return f"{name}{{{lbl}}} {value}"


def export_run_metrics(run_dir: Path) -> str:
    """Build the Prometheus exposition text for a finished run (pure)."""
    run_dir = Path(run_dir)
    run_spec = json.loads((run_dir / "run-spec.json").read_text(encoding="utf-8"))
    cells = json.loads((run_dir / "cells.json").read_text(encoding="utf-8"))
    agg = {}
    agg_path = run_dir / "aggregate.json"
    if agg_path.exists():
        agg = json.loads(agg_path.read_text(encoding="utf-8"))

    run_id = _run_id(run_spec)
    project = f"startd8-benchmark-run-{run_id}"
    lines: List[str] = [f"# Benchmark run {run_spec.get('name', run_id)} ({project})"]

    # --- cost by model (matches startd8_cost_total{project=~...} by (model)) ---
    lines += ["# HELP startd8_cost_total Benchmark LLM cost in USD", "# TYPE startd8_cost_total counter"]
    by_model = (agg.get("by_model") or {})
    # K2 (R4-S4): when both leverage states ran, label cost by `leverage` so dashboards don't blend
    # the off and on arms into one series. `sum by (model)` still collapses correctly; off-only runs
    # stay byte-identical (no leverage label added).
    has_leverage = any(c.get("leverage", "off") != "off" for c in cells)
    if has_leverage:
        cost_by_model_lev: Dict[str, float] = {}
        for c in cells:
            key = (c.get("model", "?"), c.get("leverage", "off"))
            cost_by_model_lev[key] = cost_by_model_lev.get(key, 0.0) + (c.get("cost_usd") or 0.0)
        for (model, lev), cost in sorted(cost_by_model_lev.items()):
            lines.append(_metric("startd8_cost_total",
                                 {"project": project, "model": model, "leverage": lev},
                                 round(cost, 6)))
    else:
        for model, m in by_model.items():
            lines.append(_metric("startd8_cost_total", {"project": project, "model": model},
                                 round(m.get("cost_total_usd") or 0.0, 6)))

    # --- cell counts by mapped task.status (T4 mapping; exclusions stay labelled-and-excluded) ---
    counts: Counter = Counter()
    for c in cells:
        mapped, _excl = map_cell_status(c.get("status", "failed"))
        counts[mapped] += 1
    lines += ["# HELP task_count_by_status Benchmark cell count by ContextCore task.status",
              "# TYPE task_count_by_status gauge"]
    for status in sorted(CELL_STATUS_MAP and {v[0] for v in CELL_STATUS_MAP.values()}):
        lines.append(_metric("task_count_by_status", {"project_id": project, "task_status": status},
                             counts.get(status, 0)))

    # --- analyst gauges: per-model quality median / IQR / pass-rate (for live charts later) ---
    lines += ["# HELP benchmark_quality_median Per-model composite quality (median)",
              "# TYPE benchmark_quality_median gauge"]
    for model, m in by_model.items():
        if m.get("quality_median") is not None:
            lines.append(_metric("benchmark_quality_median", {"project": project, "model": model},
                                 m["quality_median"]))
    lines += ["# HELP benchmark_pass_rate Per-model pass rate", "# TYPE benchmark_pass_rate gauge"]
    for model, m in by_model.items():
        if m.get("pass_rate") is not None:
            lines.append(_metric("benchmark_pass_rate", {"project": project, "model": model},
                                 m["pass_rate"]))
    return "\n".join(lines) + "\n"


def write_run_metrics(run_dir: Path, output_dir: Path) -> Dict[str, Any]:
    """Write the run's Prometheus textfile to ``output_dir/run-metrics.prom``."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    text = export_run_metrics(run_dir)
    path = output_dir / "run-metrics.prom"
    path.write_text(text, encoding="utf-8")
    n = sum(1 for ln in text.splitlines() if ln and not ln.startswith("#"))
    logger.info("Wrote %d metric series → %s", n, path)
    return {"path": str(path), "series": n}
