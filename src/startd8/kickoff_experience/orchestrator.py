# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Kickoff orchestrator (FR-KO-1) — a read-only guided map over the advisor's ranked playbook.

Turns the disconnected greenfield path into **one legible, cost-labeled, ordered walkthrough**. It
renders the already-computed ``build_red_carpet_state().next_steps`` (the advisor's ranked playbook) —
it does **not** recompute a plan, spend, write, or auto-run a step (P1/NR-KO-1). Each step carries a
**cost tag** derived from its command so a user sees at a glance which steps are ``$0`` deterministic,
which are ``paid`` (a role pass or interview), and which are a human ``gate``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from startd8.kickoff_experience.red_carpet import build_red_carpet_state
from startd8.kickoff_experience.red_carpet_advisor import (
    CMD_GENERATE_BACKEND,
    CMD_GENERATE_CONTRACT_PROMOTE,
    CMD_RED_CARPET_AGENT,
    CMD_SCREENS_SUGGEST,
    CMD_WIREFRAME,
)

__all__ = ["PlanStep", "KickoffPlan", "cost_tag", "build_kickoff_plan"]

# Cost class per command (the tag shown beside each step). "$0" = deterministic, no LLM; "paid" = an
# LLM pass; "$0+paid" = a $0 baseline with an optional paid `--roles` pass.
_COST: dict = {
    CMD_GENERATE_CONTRACT_PROMOTE: "$0",
    CMD_WIREFRAME: "$0",
    CMD_GENERATE_BACKEND: "$0",
    CMD_SCREENS_SUGGEST: "$0+paid",  # baseline is $0; `--roles` spends
    CMD_RED_CARPET_AGENT: "paid",  # the LLM interview
}


def cost_tag(command: Optional[str]) -> str:
    """The cost class for a playbook *command* (``$0`` / ``paid`` / ``$0+paid`` / ``step``)."""
    if not command:
        return "gate"  # a command-less step is a human action / gate
    # match the leading `startd8 <verb …>` even if the playbook carries trailing args
    for known, tag in _COST.items():
        if command.startswith(known):
            return tag
    return "step"


@dataclass
class PlanStep:
    rank: int
    stage: str
    title: str
    detail: str
    command: Optional[str]
    cost: str

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "stage": self.stage,
            "title": self.title,
            "detail": self.detail,
            "command": self.command,
            "cost": self.cost,
        }


@dataclass
class KickoffPlan:
    next_stage: Optional[str]
    cascade_offerable: bool
    unmet_gates: List[str]
    readiness_score: Optional[float]
    steps: List[PlanStep] = field(default_factory=list)

    @property
    def next_step(self) -> Optional[PlanStep]:
        return self.steps[0] if self.steps else None

    def to_dict(self) -> dict:
        return {
            "next_stage": self.next_stage,
            "cascade_offerable": self.cascade_offerable,
            "unmet_gates": self.unmet_gates,
            "readiness_score": self.readiness_score,
            "steps": [s.to_dict() for s in self.steps],
        }

    def render(self) -> str:
        lines: List[str] = ["Kickoff plan — the guided greenfield path", ""]
        if self.cascade_offerable:
            lines.append("you are here: the $0 cascade is BUILD-READY (all gates met)")
        else:
            gates = ", ".join(self.unmet_gates) if self.unmet_gates else "(none)"
            lines.append(
                f"you are here: next stage = {self.next_stage or 'done'}; unmet gates = {gates}"
            )
        if self.readiness_score is not None:
            lines.append(f"readiness score: {self.readiness_score}")
        lines.append("")
        if not self.steps:
            lines.append(
                "no next steps — nothing to do (or the advisor could not read the project)."
            )
            return "\n".join(lines)
        for s in self.steps:
            lines.append(f"  {s.rank}. [{s.cost}] {s.title}  ({s.stage})")
            if s.detail:
                lines.append(f"     {s.detail}")
            if s.command:
                lines.append(f"     $ {s.command}")
        lines.append("")
        lines.append(
            "(read-only map — it spends/writes nothing; run each command yourself at its gate)"
        )
        return "\n".join(lines)


def build_kickoff_plan(project_root: Path | str) -> KickoffPlan:
    """Render the advisor's ranked playbook as a cost-labeled kickoff plan (read-only, ``$0``)."""
    state = build_red_carpet_state(project_root)
    steps = [
        PlanStep(
            rank=getattr(s, "rank", i + 1),
            stage=getattr(s, "stage", ""),
            title=getattr(s, "title", ""),
            detail=getattr(s, "detail", ""),
            command=getattr(s, "command", None),
            cost=cost_tag(getattr(s, "command", None)),
        )
        for i, s in enumerate(state.next_steps or ())
    ]
    return KickoffPlan(
        next_stage=state.next_stage,
        cascade_offerable=state.cascade_offerable,
        unmet_gates=list(state.unmet_gates or ()),
        readiness_score=state.readiness_score,
        steps=steps,
    )
