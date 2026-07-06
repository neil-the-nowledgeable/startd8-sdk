# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Kickoff conductor (GE-M2) — the ONE "what's next" projection over the advisor's playbook.

GE-M2 consolidated the three overlapping projections over the same ``red_carpet_advisor`` /
``build_red_carpet_state`` output into this single conductor module:

* **the ordered plan** (FR-KO-1, ``build_kickoff_plan``) — a read-only, cost-labeled walkthrough of
  ``build_red_carpet_state().next_steps`` (the advisor's ranked playbook). The Guide-phase entry.
* **the completion meter** (FR-WD-2, ``build_completion``) — a ``$0`` filled/total meter over the
  user-fillable surface.
* **the interactive wizard** (FR-WD, ``run_red_carpet_driver`` + ``wizard_prepopulate`` /
  ``wizard_inventory`` / ``WizardAction``) — a deterministic ``$0`` conductor that proposes
  pre-populated inputs and advances through the playbook.

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
from typing import Any, Callable, List, Mapping, Optional, Tuple

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
    # interactive wizard
    "WizardAction",
    "wizard_inventory",
    "wizard_prepopulate",
    "run_red_carpet_driver",
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


# ================================================================================================
# The interactive wizard (FR-WD, folded from `wizard.py`)
# ================================================================================================
#
# Leads the greenfield/brownfield user over the live ``build_red_carpet_state``: inventories existing
# project assets, proposes **pre-populated inputs** from them (each a proposal the human confirms),
# and advances through the ranked playbook with a completion meter — using the agentic interview only
# where no asset can pre-fill a gap.

_BRIEF_REL = "docs/kickoff/REQUIREMENTS.md"
_DERIVE_COMMAND = "startd8 concierge derive-contract --modules <your.models> --apply  # then confirm `schema`"


@dataclass(frozen=True)
class WizardAction:
    """One step's found / needed / action triple (FR-WD-3). ``action_kind`` is a ``PROPOSAL_KINDS``
    member (proposal set) or ``"command"`` (a named CLI command) — never free prose (CRP R1-F8)."""

    stage: str
    found: str
    needed: str
    action_kind: str
    proposal: Optional[Any] = None   # a ProposedAction when action_kind is a proposal kind
    command: Optional[str] = None    # the CLI command when action_kind == "command"

    def to_dict(self) -> dict:
        d = {"stage": self.stage, "found": self.found, "needed": self.needed,
             "action_kind": self.action_kind}
        if self.command:
            d["command"] = self.command
        if self.proposal is not None:
            d["proposal_kind"] = self.proposal.kind
        return d


def wizard_inventory(project_root: str | Path) -> dict:
    """FR-WD-4 — read-only asset inventory via ``survey`` (never imports project code). Excludes the
    brief's own output from PRD candidates so a re-drive doesn't re-detect it (CRP R1-F6)."""
    from ..concierge.core import build_survey

    surv = build_survey(project_root)
    reqs = [d for d in (surv.get("requirement_docs") or []) if str(d.get("path")) != _BRIEF_REL]
    return {
        "model_files": list(surv.get("model_files") or []),
        "requirement_docs": reqs,
        "fixture_candidates": list(surv.get("fixture_candidates") or []),
    }


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def _package_present(root: Path) -> bool:
    return (root / "docs" / "kickoff" / "inputs").is_dir()


def _instantiate_proposal() -> Any:
    from .proposals import ProposedAction, _new_id

    return ProposedAction("instantiate", {"posture": "prototype"}, id=_new_id())


def _prefill_actions(root: Path, domains_status: dict) -> List[WizardAction]:
    """FR-WD-7 — pre-fill absent value-input fields via `capture`, ONLY for template-seeded keys on an
    instantiated package. `build_capture_plan` validates the key exists (it replaces, cannot create);
    a non-seeded key raises → we skip it (no failing proposal). Never imports project code."""
    from .manifest import default_config
    from .proposals import ProposedAction, _new_id

    out: List[WizardAction] = []
    cfg = default_config()
    try:
        from .capture import build_capture_plan
    except Exception:
        return out
    for f in cfg.writable_fields():
        if f.write_target is None:
            continue
        # only offer a pre-fill where the field is a default worth confirming (estimate/config-default)
        if f.provenance_default not in ("estimate", "config-default"):
            continue
        default_val = "REVIEW"   # placeholder value the human edits; capture validates round-trip
        try:
            plan = build_capture_plan(root, f.value_path, default_val, config=cfg)
        except Exception:
            continue   # unseeded key / missing file / round-trip fail → skip (FR-WD-7 precondition)
        out.append(WizardAction(
            "value_inputs",
            found=f"{f.label} — currently a default",   # KICKOFF_UX FR-UX-10: plain, no value_path/provenance jargon
            needed="a confirmed value",
            action_kind="capture",
            proposal=ProposedAction("capture", {"value_path": f.value_path, "value": default_val},
                                    id=_new_id(), base_sha=plan.base_sha),
        ))
    return out


def wizard_prepopulate(project_root: str | Path, inventory: dict, state: Any,
                       assess: Optional[dict] = None) -> List[WizardAction]:
    """FR-WD-5/6/7 — pure preview; **NO writes, NO project imports.** Returns per-gap WizardActions."""
    root = Path(project_root)
    unmet = set(getattr(state, "unmet_gates", ()) or ())
    out: List[WizardAction] = []

    # FR-WD-5 — schema: PROPOSE THE DERIVE COMMAND (never import project code) when models exist.
    if "schema" in unmet:
        models = inventory.get("model_files") or []
        if models:
            shown = ", ".join(models[:4]) + ("…" if len(models) > 4 else "")
            out.append(WizardAction(
                "data_model",
                found=f"{len(models)} existing data file(s): {shown}",   # KICKOFF_UX FR-UX-10 — plain
                needed="Your data",
                action_kind="command",
                command=_DERIVE_COMMAND,
            ))
        else:
            # FR-WD-6 — brief from an existing PRD (safe read; the brief output is already excluded).
            reqs = inventory.get("requirement_docs") or []
            if reqs:
                prd = str(reqs[0].get("path"))
                text = _read_text(root / prd)
                if text.strip():
                    from .proposals import ProposedAction, _new_id

                    out.append(WizardAction(
                        "data_model",
                        found=f"a requirements doc: {prd}",
                        needed="Your data",                 # KICKOFF_UX FR-UX-10 — plain
                        action_kind="brief",
                        proposal=ProposedAction("brief", {"source": text}, id=_new_id()),
                    ))

    # FR-WD-7 — value inputs: instantiate first (capture cannot create the package/keys), then pre-fill.
    if not _package_present(root):
        out.append(WizardAction(
            "value_inputs",
            found="no settings yet",                    # KICKOFF_UX FR-UX-10 — plain
            needed="Your settings",
            action_kind="instantiate",
            proposal=_instantiate_proposal(),
        ))
    else:
        domains_status = ((assess or {}).get("kickoff_inputs") or {}).get("domains") or {}
        out.extend(_prefill_actions(root, domains_status))
    return out


# Inputs the driver treats as "end the session".
_QUIT_WORDS = frozenset({"", "exit", "quit", ":q", "q"})


def run_red_carpet_driver(
    *,
    banner: str,
    build_state: "Callable[[], Any]",
    prepopulate: "Callable[[Any], List[WizardAction]]",
    read_input: "Callable[[str], Optional[str]]",
    emit_line: "Callable[[str], None]",
    on_proposal: "Callable[[Any], Any]",
    render_state: "Callable[[Any], None]" = lambda s: None,
    interview: "Optional[Callable[[str], None]]" = None,
    no_progress_limit: int = 3,
    max_steps: int = 100,
) -> int:
    """The deterministic `$0` driver loop (FR-WD-1) — **pure of IO** for testability.

    Each step: build the live state → render it → compute the current gap's pre-populated action(s) →
    present the found/needed/action → confirm via ``on_proposal`` (human privilege). Advance mapping
    (CRP R1-S3): advance on ``ProposalOutcome.ok``; a **retriable** outcome retains the step (no
    advance, no no-progress increment); a decline/skip increments the no-progress counter. When it
    hits ``no_progress_limit`` on one stage, it offers the interview / friction path. Returns steps
    completed.
    """
    emit_line(banner)
    steps = 0
    stalls: dict = {}
    while steps < max_steps:
        state = build_state()
        render_state(state)
        if getattr(state, "next_stage", None) is None:
            emit_line("✅ the input surface is complete — the $0 cascade is offerable.")
            break
        actions = [a for a in prepopulate(state) if a.stage == state.next_stage] or prepopulate(state)
        if not actions:
            # no asset can pre-fill this gap → hand to the interview (FR-WD-8) or stop.
            if interview is not None:
                interview(state.next_stage)
            else:
                emit_line(f"no pre-populated action for `{state.next_stage}` — "
                          f"run `{CMD_RED_CARPET_AGENT}` to author it.")
                break
            steps += 1
            continue
        action = actions[0]
        emit_line(f"[{action.stage}] found: {action.found}")
        emit_line(f"           needed: {action.needed}")
        if action.action_kind == "command":
            emit_line(f"           run: {action.command}")
            # a command is the human's to run; we cannot confirm it — advance the presentation.
            reply = read_input("[enter to continue, or q to quit] ")
            if reply is None or reply.strip().lower() in _QUIT_WORDS:
                break
            steps += 1
            continue
        outcome = on_proposal(action.proposal)   # host confirm → apply (or decline)
        code = getattr(outcome, "code", None)
        if outcome is not None and getattr(outcome, "ok", False):
            emit_line(f"  ✓ {code}: {getattr(outcome, 'detail', '')}")
            stalls[action.stage] = 0
        elif outcome is not None and getattr(outcome, "retriable", False):
            emit_line(f"  … {code} (retriable) — leaving this step in place")
            # retain the step; do NOT count toward no-progress (CRP R1-S3)
        else:
            stalls[action.stage] = stalls.get(action.stage, 0) + 1
            emit_line("  (skipped)")
            if stalls[action.stage] >= no_progress_limit:
                emit_line(f"  stuck on `{action.stage}` — you can log friction "
                          "(`startd8 kickoff concierge`) or work it manually.")
                stalls[action.stage] = 0
        steps += 1
    return steps
