# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Machine-checkable Section-G join contract for benchmark tracking (T5.4 / CRP R1-S7 / FR-11/17/18/26).

The Business/Agent observability separation joins on shared attributes asserted across FR-11/17/18/26.
Encoding those joins as data — and verifying each named attribute is actually present on the emitted
span / cost row / insight — turns four scattered prose assertions into one fixture that cannot silently
drift from the emitters.

Each :class:`JoinRow` names a cross-view link, the shared attribute, and a predicate over the relevant
emitted artifact. :func:`verify_join_contract` runs them all and returns per-row results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class JoinRow:
    link: str
    attribute: str
    # predicate(artifact) -> True if the join attribute is present on that artifact
    present: Callable[[Any], bool]


def _labels(task_span: Dict[str, Any]) -> List[str]:
    return (task_span.get("attributes", {}) or {}).get("task.labels", []) or []


def _has_label_prefix(task_span: Dict[str, Any], prefix: str) -> bool:
    return any(str(label).startswith(prefix) for label in _labels(task_span))


# The five Section-G join rows, as predicates over the artifact each one is carried on.
JOIN_CONTRACT: List[JoinRow] = [
    JoinRow(
        "Business-execution ↔ results Loki stream",
        "run_id + cell-identity (service/model/lang/rep)",
        lambda cell_span: _has_label_prefix(cell_span, "run:")
        and _has_label_prefix(cell_span, "service:")
        and _has_label_prefix(cell_span, "model:"),
    ),
    JoinRow(
        "Business-execution ↔ cost",
        "cell_id (cost rollup key)",
        lambda cost_rollup: bool((cost_rollup or {}).get("per_cell")),
    ),
    JoinRow(
        "Business-delivery ↔ cost",
        "milestone:/cell: tag",
        lambda cost_tags: any(
            str(t).startswith(("milestone:", "cell:")) for t in (cost_tags or [])
        ),
    ),
    JoinRow(
        "Agent-insight ↔ cost / tokens",
        "gen_ai.usage.* (input/output tokens on the insight)",
        lambda insight_call: insight_call.get("input_tokens") is not None
        or insight_call.get("output_tokens") is not None,
    ),
    JoinRow(
        "Business ↔ Agent (shared identity)",
        "project.id",
        lambda task_span: bool((task_span.get("attributes", {}) or {}).get("project.id")),
    ),
]


def verify_join_contract(artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Verify each join row against the relevant artifact in ``artifacts``.

    ``artifacts`` keys (any missing key → that row reports ``ok=False, reason="artifact missing"``):
        - ``cell_span``: an emitted execution-cell task-span dict (Business-execution ↔ results/identity)
        - ``cost_rollup``: a cell cost rollup dict (Business-execution ↔ cost)
        - ``cost_tags``: the cost tags applied to a delivery/cell record (Business-delivery ↔ cost)
        - ``insight_call``: the kwargs an insight emission carried (Agent-insight ↔ cost/tokens)
        - ``task_span``: any emitted task-span dict (Business ↔ Agent shared identity)

    Returns one ``{link, attribute, ok, reason}`` per row.
    """
    key_for = {
        JOIN_CONTRACT[0]: "cell_span",
        JOIN_CONTRACT[1]: "cost_rollup",
        JOIN_CONTRACT[2]: "cost_tags",
        JOIN_CONTRACT[3]: "insight_call",
        JOIN_CONTRACT[4]: "task_span",
    }
    results: List[Dict[str, Any]] = []
    for row in JOIN_CONTRACT:
        key = key_for[row]
        artifact: Optional[Any] = artifacts.get(key)
        if artifact is None:
            results.append({"link": row.link, "attribute": row.attribute, "ok": False,
                            "reason": f"artifact '{key}' missing"})
            continue
        try:
            ok = bool(row.present(artifact))
            reason = "" if ok else f"join attribute '{row.attribute}' absent"
        except Exception as exc:  # a malformed artifact is a contract failure, not a crash
            ok, reason = False, f"predicate error: {type(exc).__name__}"
        results.append({"link": row.link, "attribute": row.attribute, "ok": ok, "reason": reason})
    return results
