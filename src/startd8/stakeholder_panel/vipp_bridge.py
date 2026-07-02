# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""The opt-in VIPP pass: consult the panel about a report's OMIT questions (FR-9/FR-16/FR-17/FR-18).

Invoked *around* VIPP's deterministic ``$0`` core (never inside ``evaluate_envelope``), mirroring
``compose.enhance_narrative``. It reads the OMIT-default dispositions' routing context (``unresolved``,
FR-9b), routes each to a persona (FR-9c), asks the panel, and returns **synthetic advisory dicts** —
which the caller attaches to the report in a *separate* section. It never mutates a verdict (FR-9)
and never lets a synthetic claim into ``dispositions`` (FR-18).

Duck-typed on both ``report`` (``.dispositions`` → ``.proposal_id`` / ``.unresolved``) and ``panel``
(``.briefs`` / ``.ask``), so ``stakeholder_panel`` takes **no dependency on ``vipp``**.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger
from startd8.stakeholder_panel.models import Grounding
from startd8.stakeholder_panel.routing import route

__all__ = ["Consultation", "consult_panel"]

logger = get_logger(__name__)


@dataclass
class Consultation:
    """Result of a panel pass: advisory dicts + rolled-up cost/llm usage (never verdict changes)."""

    advisories: List[Dict[str, Any]] = field(default_factory=list)
    cost_usd: float = 0.0
    llm_used: bool = False


def _brief_goals(panel: Any, role_id: str) -> List[str]:
    for brief in panel.briefs:
        if brief.role_id == role_id:
            return list(brief.goals)
    return []


def consult_panel(
    report: Any, panel: Any, *, cap: Optional[int] = None
) -> Consultation:
    """Route every OMIT question in *report* to the panel and collect synthetic advisories.

    ``cap`` bounds the number of *paid* asks across the whole pass (FR-17); routed questions beyond
    it are returned as ``deferred``. No-match questions stay OMIT (FR-9c); a persona failure yields
    ``unavailable`` and never aborts the pass (FR-16).
    """
    # Flatten OMIT questions (with routing) in deterministic disposition/question order.
    routed: List[Dict[str, Any]] = []
    for disp in getattr(report, "dispositions", []) or []:
        for u in getattr(disp, "unresolved", []) or []:
            symbol, claim = u.get("symbol", ""), u.get("claim", "")
            routed.append(
                {
                    "proposal_id": getattr(disp, "proposal_id", ""),
                    "symbol": symbol,
                    "claim": claim,
                    "role_id": route(panel.briefs, symbol, claim),
                }
            )

    if not routed:
        return Consultation()

    async def _run() -> List[Dict[str, Any]]:
        advisories: List[Dict[str, Any]] = []
        asked = 0
        for item in routed:
            pid, symbol, claim, role_id = (
                item["proposal_id"],
                item["symbol"],
                item["claim"],
                item["role_id"],
            )
            base = {"proposal_id": pid, "symbol": symbol, "claim": claim}
            if role_id is None:  # FR-9c: no persona matched → stays OMIT
                advisories.append({**base, "status": "no-stakeholder"})
                continue
            if cap is not None and asked >= cap:  # FR-17: cap reached → defer, no spend
                advisories.append({**base, "status": "deferred", "role_id": role_id})
                continue
            asked += 1
            question = (
                f"During kickoff we could not confirm this from the project docs: {claim} "
                f"(symbol: {symbol}). From your role, is that intended, and what should it be?"
            )
            answer = await panel.ask(
                role_id, question, value_path=symbol
            )  # never raises (FR-16)
            if answer.grounding is Grounding.UNAVAILABLE:
                advisories.append({**base, "status": "unavailable", "role_id": role_id})
                continue
            advisories.append(
                {
                    **base,
                    "status": "answered",
                    "role_id": role_id,
                    "answer": answer.text,
                    "grounding": answer.grounding.value,
                    "brief_goals": _brief_goals(panel, role_id),
                    "cost_usd": answer.cost_usd,
                    "flags": list(answer.flags),  # FR-7 (M3) advisory grounding flags
                }
            )
        return advisories

    advisories = asyncio.run(_run())
    cost = sum(float(a.get("cost_usd", 0.0) or 0.0) for a in advisories)
    llm_used = any(a.get("status") == "answered" for a in advisories)
    logger.info(
        "panel consultation: %d OMIT questions, %d answered",
        len(routed),
        sum(1 for a in advisories if a.get("status") == "answered"),
    )
    return Consultation(advisories=advisories, cost_usd=cost, llm_used=llm_used)
