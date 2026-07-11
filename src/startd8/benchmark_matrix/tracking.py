# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Post-hoc execution-cell tracking for a benchmark run (T4 / Section B / FR-7/8/9/10).

A **pure reader** over a finished run's ``run-spec.json`` + ``cells.json`` — it touches NO run-loop
code, which is the spine of the FR-25 non-blocking guarantee (OQ-7: post-hoc is the default; live is
a separate opt-in). It projects the run into a ContextCore hierarchy via the existing
``task_tracking_emitter`` (epic = run, story = service, task = cell), attaches per-cell cost
(reusing :mod:`startd8.integrations.cost_linkage`), and optionally emits notable-cell insights
(reusing :mod:`startd8.integrations.insight_emission`).

As-built 6-status mapping (CRP R1-S2/R2-F1 — ``integrity_fail`` / ``infra_fail`` are *exclusions*,
not model failures, carried via an ``exclusion_reason`` label and excluded from any model pass/fail):

==================  =============  ==========================
``CellResult``      ``task.status``  label
==================  =============  ==========================
``ok``              ``done``        —
``failed``          ``cancelled``   —
``timeout``         ``cancelled``   —
``integrity_fail``  ``cancelled``   ``exclusion_reason:integrity``
``infra_fail``      ``blocked``     ``exclusion_reason:infra``
``budget_skip``     ``blocked``     —
==================  =============  ==========================

Granularity (OQ-2): **per-cell** task spans for a small (flagship/full-app) run; **service stories
with cell counts** for the large matrix — auto-selected by cell volume, or forced via ``mode``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..integrations.cost_linkage import cell_costs_from_cells_json
from ..integrations.insight_emission import emit_notable_cell_insights
from ..logging_config import get_logger
from ..workflows.builtin.plan_ingestion_models import (
    ComplexityScore,
    ContractorRoute,
    ParsedFeature,
    ParsedPlan,
    TaskTrackingConfig,
)
from ..workflows.builtin.task_tracking_emitter import emit_task_tracking_artifacts

logger = get_logger(__name__)

# native cell status -> (task.status, exclusion_reason | None)
CELL_STATUS_MAP: Dict[str, Tuple[str, Optional[str]]] = {
    "ok": ("done", None),
    "failed": ("cancelled", None),
    "timeout": ("cancelled", None),
    "integrity_fail": ("cancelled", "integrity"),
    "infra_fail": ("blocked", "infra"),
    "budget_skip": ("blocked", None),
}

# Above this many cells, default to count-mode (service stories + counts) rather than a task per cell.
CELL_TASK_THRESHOLD = 120


def map_cell_status(native: str) -> Tuple[str, Optional[str]]:
    """Map a native ``CellResult.status`` to ``(task.status, exclusion_reason)``."""
    return CELL_STATUS_MAP.get(native, ("cancelled", None))


def _run_id(run_spec: Dict[str, Any]) -> str:
    return (run_spec.get("spec_hash") or "")[:12] or "unknown"


def _cell_labels(run_id: str, c: Dict[str, Any], native: str, exclusion: Optional[str]) -> List[str]:
    labels = [
        "cell",
        f"run:{run_id}",
        f"service:{c.get('service', '')}",
        f"model:{c.get('model', '')}",
        f"lang:{c.get('language', '')}",
        f"rep:{c.get('repetition', 0)}",
        f"status:{native}",
        f"cost_usd:{c.get('cost_usd') or 0}",
    ]
    if exclusion:
        labels.append(f"exclusion_reason:{exclusion}")
    if c.get("sandbox_violation"):
        labels.append("sandbox_violation")
    return labels


def reconstruct_run_tracking(
    run_dir: Path,
    *,
    mode: str = "auto",
    output_dir: Optional[Path] = None,
    install: bool = False,
    insight_bridge: Any = None,
) -> Dict[str, Any]:
    """Reconstruct ContextCore execution-cell tracking from a finished run directory.

    Args:
        run_dir: A ``.startd8/benchmark-runs/<hash>/`` dir with ``run-spec.json`` + ``cells.json``.
        mode: ``"cell"`` | ``"count"`` | ``"auto"`` (by cell volume) — OQ-2 granularity.
        output_dir: Where to write artifacts (defaults to ``run_dir/contextcore-tracking``).
        install: Also install state files to ``~/.contextcore/state/``.
        insight_bridge: Optional AgentInsightBridge → also emit notable-cell insights (T3/FR-14).

    Returns:
        Summary dict: project_id, run_id, granularity, counts, cost rollup, notable-insight count.
    """
    run_dir = Path(run_dir)
    run_spec = json.loads((run_dir / "run-spec.json").read_text(encoding="utf-8"))
    cells = json.loads((run_dir / "cells.json").read_text(encoding="utf-8"))

    run_id = _run_id(run_spec)
    run_name = run_spec.get("name", run_id)
    project_id = f"startd8-benchmark-run-{run_id}"
    epic_id = f"{project_id}-epic"
    cell_mode = mode == "cell" or (mode == "auto" and len(cells) <= CELL_TASK_THRESHOLD)

    by_service: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in cells:
        by_service[c.get("service", "unknown")].append(c)

    # Run is finished → epic + every service story is terminal (done).
    initial_statuses: Dict[str, str] = {epic_id: "done"}
    features: List[ParsedFeature] = []
    tasks: List[Dict[str, Any]] = []

    for service in sorted(by_service):
        scells = by_service[service]
        story_id = f"{service}-story"
        ok = sum(1 for c in scells if c.get("status") == "ok")
        labels = ["service", f"run:{run_id}", f"cells:{len(scells)}", f"ok:{ok}"]
        features.append(
            ParsedFeature(
                feature_id=service, name=service, description=f"{service} ({len(scells)} cells)",
                target_files=[], dependencies=[], estimated_loc=0, labels=labels,
            )
        )
        initial_statuses[story_id] = "done"

        if cell_mode:
            for c in scells:
                native = c.get("status", "failed")
                mapped, exclusion = map_cell_status(native)
                tid = c.get("cell_id") or f"{service}:{c.get('model')}:r{c.get('repetition', 0)}"
                tasks.append(
                    {
                        "task_id": tid,
                        "title": f"{c.get('model', '')} r{c.get('repetition', 0)}",
                        "story_points": 1,
                        "priority": "medium",
                        "labels": _cell_labels(run_id, c, native, exclusion),
                        "depends_on": [],
                        "config": {"task_description": tid, "context": {"feature_id": service}},
                    }
                )
                initial_statuses[tid] = mapped

    plan = ParsedPlan(
        title=f"Benchmark run {run_name} ({run_id})",
        goals=[f"Execution tracking for run {run_id}"],
        features=features,
        dependency_graph={},
        mentioned_files=[],
    )
    complexity = ComplexityScore(
        composite=len(cells), feature_count=len(features), cross_file_deps=0, api_surface=0,
        test_complexity=0, integration_depth=0, domain_novelty=0, ambiguity=0,
        reasoning="Benchmark execution-cell tracking (not a code-complexity assessment).",
        route=ContractorRoute.ARTISAN,
    )
    config = TaskTrackingConfig(
        project_id=project_id, project_name=f"Benchmark run {run_name}",
        sprint_id="summer-2026", install_to_contextcore=install, emit_ndjson_events=True,
    )
    out_dir = output_dir or (run_dir / "contextcore-tracking")
    result = emit_task_tracking_artifacts(
        plan, complexity, tasks, config, out_dir, initial_statuses=initial_statuses
    )

    cost_rollup = cell_costs_from_cells_json(run_dir / "cells.json")
    notable = 0
    if insight_bridge is not None:
        notable = emit_notable_cell_insights(insight_bridge, cells, run_id=run_id)

    summary = {
        "project_id": project_id,
        "run_id": run_id,
        "granularity": "cell" if cell_mode else "count",
        "counts": {"services": len(features), "cells": len(cells), "cell_tasks": len(tasks)},
        "cost_total_usd": cost_rollup["total"],
        "cost_by_model": cost_rollup["by_model"],
        "notable_insights": notable,
        "tasks_dir": result.get("tasks_dir"),
    }
    logger.info("Reconstructed run tracking: %s", {k: summary[k] for k in ("run_id", "granularity", "counts")})
    return summary
