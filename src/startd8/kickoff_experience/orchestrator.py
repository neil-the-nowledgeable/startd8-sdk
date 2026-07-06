# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Kickoff conductor (GE-M2) — the ONE "what's next" projection over the advisor's playbook.

GE-M2 consolidated the three overlapping projections over the same ``red_carpet_advisor`` /
``build_red_carpet_state`` output into this single conductor module:

* **the ordered plan** (FR-KO-1, ``build_kickoff_plan``) — a read-only, cost-labeled walkthrough of
  ``build_red_carpet_state().next_steps`` (the advisor's ranked playbook). The Guide-phase entry.
* **the completion meter** (FR-WD-2, ``build_completion``) — a ``$0`` filled/total meter over the
  user-fillable surface.

The interactive red-carpet wizard (``run_red_carpet_driver`` + ``wizard_prepopulate``) was **retired**
(see ``docs/design/kickoff/ADR_RETIRE_RED_CARPET_WIZARD.md``); its value-input leg is superseded by the
kernel ``kickoff confirm`` walk and its schema/manifest advisory by ``kickoff guided``.

None of these recompute a plan, spend, write, or auto-run a step (P1/NR-KO-1): they PROJECT the
already-computed advisor output. No new engine (FR-GE-6). The legacy module names
(``orchestrator`` is canonical; ``wizard`` / ``red_carpet_completion``) remain importable as thin
compat shims re-exporting from here for one release.

**SECURITY (NR-4a / FR-WD-5) — this module MUST NOT import or execute project code.** Asset
inventory is ``survey``'s path/name heuristics; schema derivation (which imports Pydantic modules) is
proposed as a **command the human runs**, never an in-module import. This module must never reference
``introspect_models`` / ``resolve_models`` / ``build_derivation`` / ``importlib`` — enforced by the
structural anti-import guard test (CRP R1-S1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple

from startd8.kickoff_experience.red_carpet import build_red_carpet_state
from startd8.kickoff_experience.red_carpet_advisor import (
    CMD_GENERATE_BACKEND,
    CMD_GENERATE_CONTRACT_PROMOTE,
    CMD_GENERATE_SCAFFOLD,
    CMD_GENERATE_VIEWS,
    CMD_POLISH_APPLY,
    CMD_RED_CARPET_AGENT,
    CMD_SCREENS_SUGGEST,
    CMD_SCREENS_SUGGEST_ROLES,
    CMD_WIREFRAME,
)

__all__ = [
    # ordered plan
    "PlanStep",
    "KickoffPlan",
    "cost_tag",
    "build_kickoff_plan",
    # completion meter
    "StageCompletion",
    "Completion",
    "build_completion",
]

# ================================================================================================
# The ordered plan (FR-KO-1)
# ================================================================================================

# Cost class per command (the tag shown beside each step). "$0" = deterministic, no LLM; "paid" = an
# LLM pass; "$0+paid" = a $0 baseline with an optional paid `--roles` pass.
_COST: dict = {
    CMD_GENERATE_CONTRACT_PROMOTE: "$0",
    CMD_WIREFRAME: "$0",
    CMD_GENERATE_SCAFFOLD: "$0",
    CMD_GENERATE_BACKEND: "$0",
    CMD_GENERATE_VIEWS: "$0",
    CMD_POLISH_APPLY: "$0",
    CMD_SCREENS_SUGGEST_ROLES: "paid",  # the persona pass always spends (no $0 baseline)
    CMD_SCREENS_SUGGEST: "$0+paid",  # baseline is $0; `--roles` spends
    CMD_RED_CARPET_AGENT: "$0+paid",  # $0 conductor; the optional `--agent <spec>` interview spends
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
        # "path" is deliberately shape-neutral — the guided conductor serves both greenfield and
        # brownfield projects, so the header must not hardcode "greenfield".
        lines: List[str] = ["Kickoff plan — the guided path", ""]
        # Blocker reframe: "unmet gates" (the presence-based complete-app set) are *optional*
        # manifests when the generators are already ready — the app is buildable without them.
        gates = ", ".join(self.unmet_gates) if self.unmet_gates else "(none)"
        buildable = self.readiness_score == 1.0
        if self.cascade_offerable:
            lines.append("you are here: the $0 cascade is COMPLETE — all manifests authored")
        elif buildable:
            lines.append(
                f"you are here: BUILDABLE now (generators ready); optional manifests not yet "
                f"authored: {gates}"
            )
        else:
            lines.append(
                f"you are here: next stage = {self.next_stage or 'done'}; not yet authored: {gates}"
            )
        if self.readiness_score is not None:
            # Clarify the axis: this is the fraction of $0-cascade GENERATORS (scaffold/backend/views)
            # that are ready — NOT overall build-readiness. It can read 1.0 while manifest gates
            # (app/pages) above are still unmet; the two are distinct axes (avoids the "1.0 but
            # unmet gates" contradiction a bare "readiness score" invites).
            lines.append(f"cascade generators ready: {self.readiness_score} (scaffold/backend/views)")
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


# ================================================================================================
# The completion meter (FR-WD-2, folded from `red_carpet_completion.py`)
# ================================================================================================
#
# Distinct from the coarse ``readiness_score`` (a ready-*stage* fraction): this counts real units the
# user fills. Denominator = **user-fillable units only** (CRP R1-F1): the cascade gates
# (``schema``/``app``/``pages``/``views``) ∪ the writable value-input fields
# (``default_config().writable_fields()``). The always-pending ``content`` and derived ``run`` stages
# are **excluded**, so a fully-filled project reads **100%**.
#
# Weighting (CRP R1-F2): **stage-equal, then field-equal within a stage** — each stage contributes an
# equal share of the overall %; within a stage its units split evenly.
#
# Filled semantics (CRP R1-F7): a value-input field is "filled" only if **present AND its domain is
# not invalid** — a present-but-invalid value never masks a blocked build. ``defaulted`` values
# (provenance ``estimate``/``config-default``) are counted **distinctly** (``n_defaulted``), not as
# done.
#
# Pure / read-only / no-LLM. Never imports project code (NR-4a).

_MANIFEST_GATES: Tuple[str, ...] = ("app", "pages", "views")
_DEFAULTED_PROVENANCE = ("estimate", "config-default")


@dataclass(frozen=True)
class StageCompletion:
    stage: str
    filled: int
    total: int

    @property
    def fraction(self) -> float:
        return (self.filled / self.total) if self.total else 0.0

    def to_dict(self) -> dict:
        return {"stage": self.stage, "filled": self.filled, "total": self.total,
                "pct": round(100 * self.fraction)}


@dataclass(frozen=True)
class Completion:
    """The user-fillable completion meter — per-stage + overall %, with a distinct defaulted count."""

    stages: Tuple[StageCompletion, ...]
    overall_pct: int          # 0..100, stage-equal mean of the fillable stages
    n_defaulted: int          # present value-input fields whose provenance is a default/estimate

    def to_dict(self) -> dict:
        return {
            "overall_pct": self.overall_pct,
            "n_defaulted": self.n_defaulted,
            "stages": [s.to_dict() for s in self.stages],
        }


def _field_present(root: Path, file: str, dotted_key: str) -> bool:
    """True iff the value-input field's dotted key exists (non-null) in its on-disk YAML. Read-only;
    a parse failure → False (the domain-invalid check zeroes it out anyway)."""
    import yaml

    p = root / "docs" / "kickoff" / "inputs" / file
    if not p.is_file():
        return False
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    cur: Any = data
    for part in dotted_key.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return False
        cur = cur[part]
    return cur is not None


def build_completion(
    project_root: str | Path,
    state: Any,
    assess: Optional[Mapping[str, Any]] = None,
) -> Completion:
    """Compute the user-fillable completion meter (FR-WD-2). ``state`` supplies the cascade gates via
    ``unmet_gates``; ``assess`` supplies per-domain validity (an invalid domain → its fields unfilled)."""
    root = Path(project_root)
    unmet = set(getattr(state, "unmet_gates", ()) or ())

    # data_model — one unit: the schema gate.
    dm = StageCompletion("data_model", 0 if "schema" in unmet else 1, 1)

    # manifests — three units: app / pages / views.
    mf_filled = sum(1 for g in _MANIFEST_GATES if g not in unmet)
    mf = StageCompletion("manifests", mf_filled, len(_MANIFEST_GATES))

    # value_inputs — the writable fields; filled = present AND domain not invalid.
    from .manifest import default_config

    domains_status = ((assess or {}).get("kickoff_inputs") or {}).get("domains") or {}
    fields = [f for f in default_config().writable_fields() if f.write_target is not None]
    filled = 0
    n_defaulted = 0
    for f in fields:
        wt = f.write_target
        domain = wt.file[:-5] if wt.file.endswith(".yaml") else wt.file
        domain_invalid = (domains_status.get(domain) or {}).get("status") == "invalid"
        if not domain_invalid and _field_present(root, wt.file, wt.key):
            filled += 1
            if f.provenance_default in _DEFAULTED_PROVENANCE:
                n_defaulted += 1
    vi = StageCompletion("value_inputs", filled, len(fields))

    stages = (dm, mf, vi)
    fracs = [s.fraction for s in stages if s.total]
    overall = round(100 * (sum(fracs) / len(fracs))) if fracs else 0
    return Completion(stages=stages, overall_pct=overall, n_defaulted=n_defaulted)

