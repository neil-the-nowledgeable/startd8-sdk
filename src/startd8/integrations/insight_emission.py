# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Emit benchmark agent insights via AgentInsightBridge (T3 / Section C / FR-12/13/14).

Two emitters, both duck-typed over an :class:`startd8.integrations.contextcore.AgentInsightBridge`
(so they degrade gracefully when ContextCore is absent — the bridge no-ops and returns False):

- :func:`emit_insight_spec` — build-time **decisions / risks / lessons / questions** from a declared
  spec (e.g. ``insights.yaml``): the CRP architectural-review decisions (Temporal NO-GO, Cursor cut,
  fail-closed budget …), the FR-44/45 CRITICAL risks, and the run lessons. Carries evidence refs and
  ``supersedes`` for cross-model review memory (FR-15/16).
- :func:`emit_notable_cell_insights` — run-time insights for a benchmark run's ``cells.json``,
  **notable-events-only** (OQ-6): terminal model failures → ``blocker``; sandbox violations → ``risk``.
  ``ok`` / ``infra_fail`` / ``budget_skip`` / ``integrity_fail`` are NOT model events and are skipped
  (a key run produces ~hundreds of cells; only the notable few become insights).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

# Cell statuses that represent a genuine, notable MODEL failure (vs. infra/budget/integrity exclusions).
_NOTABLE_FAILURES = {"failed", "timeout"}


def emit_insight_spec(bridge: Any, spec: Dict[str, Any]) -> Dict[str, int]:
    """Emit declared build-time insights through the bridge. Returns per-type emitted counts."""
    counts = {"decisions": 0, "risks": 0, "lessons": 0, "questions": 0}

    for d in spec.get("decisions", []):
        if bridge.emit_decision(
            d["summary"], d.get("confidence", 0.9),
            rationale=d.get("rationale"), evidence=d.get("evidence"),
            audience=d.get("audience"), supersedes=d.get("supersedes"),
        ):
            counts["decisions"] += 1

    for r in spec.get("risks", []):
        if bridge.emit_risk(
            r["summary"], r.get("confidence", 0.8),
            rationale=r.get("rationale"), evidence=r.get("evidence"), supersedes=r.get("supersedes"),
        ):
            counts["risks"] += 1

    for les in spec.get("lessons", []):
        if bridge.emit_lesson(
            les["summary"], category=les.get("category", "general"),
            applies_to=les.get("applies_to"), evidence=les.get("evidence"),
        ):
            counts["lessons"] += 1

    for q in spec.get("questions", []):
        if bridge.emit_question(
            q.get("question") or q["summary"],
            blocking=q.get("blocking", False), evidence=q.get("evidence"),
        ):
            counts["questions"] += 1

    logger.info("Emitted insight spec: %s", counts)
    return counts


def emit_notable_cell_insights(
    bridge: Any, cells: Any, *, run_id: Optional[str] = None
) -> int:
    """Emit run-time insights for notable cells only (OQ-6). ``cells`` is a list or a cells.json path.

    Returns the number of insights emitted (should be ≪ cell count on a healthy run).
    """
    if isinstance(cells, (str, Path)):
        cells = json.loads(Path(cells).read_text(encoding="utf-8"))

    emitted = 0
    rationale = f"run={run_id}" if run_id else None
    for c in cells:
        cell_id = c.get("cell_id", "")
        evidence: List[Dict[str, str]] = [{"type": "file", "ref": cell_id}]
        if c.get("sandbox_violation"):
            if bridge.emit_risk(
                f"Sandbox violation in cell {cell_id}: {c['sandbox_violation']}",
                0.9, rationale=rationale, evidence=evidence,
            ):
                emitted += 1
        elif c.get("status") in _NOTABLE_FAILURES:
            err = (c.get("error") or "")[:200]
            if bridge.emit_blocker(
                f"Cell {cell_id} {c.get('status')}",
                1.0, rationale=(err or rationale), evidence=evidence,
            ):
                emitted += 1
        # ok / infra_fail / budget_skip / integrity_fail → not notable model events; skipped.

    logger.info("Emitted %d notable-cell insights (run=%s)", emitted, run_id)
    return emitted
