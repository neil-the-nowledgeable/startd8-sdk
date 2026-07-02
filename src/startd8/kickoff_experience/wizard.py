"""Red Carpet wizard-driver + asset-chaining (FR-WD) — a deterministic ``$0`` conductor.

Leads the greenfield/brownfield user over the live ``build_red_carpet_state``: inventories existing
project assets, proposes **pre-populated inputs** from them (each a proposal the human confirms), and
advances through the ranked playbook with a completion meter — using the agentic interview only where no
asset can pre-fill a gap.

**SECURITY (NR-4a / FR-WD-5) — this module MUST NOT import or execute project code.** Asset inventory is
`survey`'s path/name heuristics; schema derivation (which imports Pydantic modules) is proposed as a
**command the human runs**, never an in-wizard import. This module must never reference
``introspect_models`` / ``resolve_models`` / ``build_derivation`` / ``importlib`` — enforced by the
structural anti-import guard test (CRP R1-S1).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional

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
            found=f"`{f.value_path}` seeded (provenance={f.provenance_default})",
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
                found=f"{len(models)} Pydantic model file(s): {shown}",
                needed="a confirmed prisma/schema.prisma",
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
                        needed="a confirmed requirements brief",
                        action_kind="brief",
                        proposal=ProposedAction("brief", {"source": text}, id=_new_id()),
                    ))

    # FR-WD-7 — value inputs: instantiate first (capture cannot create the package/keys), then pre-fill.
    if not _package_present(root):
        out.append(WizardAction(
            "value_inputs",
            found="no kickoff inputs package on disk",
            needed="scaffold the inputs package",
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
    (CRP R1-S3): advance on ``ProposalOutcome.ok``; a **retriable** outcome retains the step (no advance,
    no no-progress increment); a decline/skip increments the no-progress counter. When it hits
    ``no_progress_limit`` on one stage, it offers the interview / friction path. Returns steps completed.
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
                          "run `startd8 kickoff red-carpet --agent` to author it.")
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
