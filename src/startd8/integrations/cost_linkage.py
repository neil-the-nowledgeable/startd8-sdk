# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Attribute LLM cost to the unit of work for cost-per-milestone / cost-per-cell rollups (T2 / FR-17).

Two attribution paths, both **without a `CostRecord` schema change** (CRP R1-F5: identity rides in
the existing ``tags``, never as a per-cell OTel metric label — that would explode metric cardinality):

1. **In-process** (delivery work, in-process agent calls): :func:`attribute_cost` wraps a block in
   ``CostTracker.tracking_context`` so every cost record incurred inside is tagged ``milestone:<id>``
   / ``cell:<id>`` / ``run:<id>``. Roll up later from ``CostSummary.by_tag`` via
   :func:`milestone_cost_rollup` / :func:`cell_cost_rollup`.

2. **Subprocess** (the benchmark matrix runs each cell in a child process, so the child's
   ``CostTracker`` owns the records and the parent only sees the aggregate): per-cell ``cost_usd`` is
   already persisted in ``cells.json``. :func:`cell_costs_from_cells_json` reads it into the same
   rollup shape — no context-var threading across the process boundary required.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

MILESTONE_TAG = "milestone:"
CELL_TAG = "cell:"
RUN_TAG = "run:"


def cost_tags(
    *, milestone_id: Optional[str] = None, cell_id: Optional[str] = None, run_id: Optional[str] = None
) -> List[str]:
    """Build the canonical work-unit cost tags (only the ones provided)."""
    tags: List[str] = []
    if milestone_id:
        tags.append(f"{MILESTONE_TAG}{milestone_id}")
    if cell_id:
        tags.append(f"{CELL_TAG}{cell_id}")
    if run_id:
        tags.append(f"{RUN_TAG}{run_id}")
    return tags


@contextmanager
def attribute_cost(
    tracker: Any,
    *,
    project: Optional[str] = None,
    milestone_id: Optional[str] = None,
    cell_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Iterator[None]:
    """Tag all **in-process** SDK LLM cost incurred in this block with the work-unit identity (FR-17).

    ``tracker`` is a :class:`startd8.costs.tracker.CostTracker`. Subprocess cost is NOT captured here
    (it lives in the child's tracker) — use :func:`cell_costs_from_cells_json` for benchmark cells.
    """
    tags = cost_tags(milestone_id=milestone_id, cell_id=cell_id, run_id=run_id)
    with tracker.tracking_context(project=project, tags=tags):
        yield


def rollup_by_prefix(summary: Any, prefix: str) -> Dict[str, float]:
    """Extract ``{id: cost}`` from a ``CostSummary.by_tag`` for tags starting with ``prefix``."""
    by_tag: Dict[str, float] = getattr(summary, "by_tag", None) or {}
    return {
        tag[len(prefix):]: cost for tag, cost in by_tag.items() if tag.startswith(prefix)
    }


def milestone_cost_rollup(summary: Any) -> Dict[str, float]:
    """``{milestone_id: total_cost_usd}`` from a CostSummary (delivery / in-process path)."""
    return rollup_by_prefix(summary, MILESTONE_TAG)


def cell_cost_rollup(summary: Any) -> Dict[str, float]:
    """``{cell_id: total_cost_usd}`` from a CostSummary (in-process cell execution path)."""
    return rollup_by_prefix(summary, CELL_TAG)


def cell_costs_from_cells_json(cells_json: Path) -> Dict[str, Any]:
    """Per-cell / per-service / per-model cost rollup from a benchmark run's ``cells.json``.

    The subprocess executor already persists ``cost_usd`` per cell; this mirrors the ``by_tag``
    rollup shape so the parent can attribute cost without crossing the process boundary.
    """
    cells = json.loads(Path(cells_json).read_text(encoding="utf-8"))
    per_cell: Dict[str, float] = {}
    by_service: Dict[str, float] = {}
    by_model: Dict[str, float] = {}
    for c in cells:
        cost = c.get("cost_usd") or 0.0
        cid = c.get("cell_id", "")
        per_cell[cid] = round(per_cell.get(cid, 0.0) + cost, 6)
        if c.get("service"):
            by_service[c["service"]] = round(by_service.get(c["service"], 0.0) + cost, 6)
        if c.get("model"):
            by_model[c["model"]] = round(by_model.get(c["model"], 0.0) + cost, 6)
    return {
        "per_cell": per_cell,
        "by_service": by_service,
        "by_model": by_model,
        "total": round(sum(per_cell.values()), 6),
    }
