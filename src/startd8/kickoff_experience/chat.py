"""M5 — TUI conversational driver, read-only by construction (FR-9 / FR-10 / OQ-8).

Mirrors the concierge chat: the agentic loop drives a kickoff conversation, but can call **only**
read tools. The allow-list is exactly ``{survey, assess, field_states}`` and the posture is enforced
at two independent layers (R1-S5):

  1. *Registration* — the registry is built with exactly those three read tools and
     ``allow_effect_classes=("read",)``.
  2. *Dispatch floor* — every handler routes through :func:`handle_kickoff_read`, which hard-rejects
     any action outside ``KICKOFF_READ_ACTIONS`` before delegating. ``field_states`` routes through
     this floor too (it is not a bypass path), and the write actions
     (``instantiate-kickoff``/``log-friction``/``derive-contract``) can never be reached.

Writes are never agentic: capture (M6) and friction logging happen only at human/CLI/web privilege.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..agents.agentic import AgenticResult, AgenticSession, SessionConfig, ToolRegistry, ToolSpec
from ..agents.base import BaseAgent
from ..concierge.core import handle_concierge_read
from .docs import live_schema_text, load_kickoff_docs
from .ranking import next_action
from .readiness import build_readiness
from .state import build_kickoff_state

# The complete read-only allow-list for the kickoff conversation (OQ-8).
KICKOFF_READ_ACTIONS = ("survey", "assess", "field_states")

POSTURE_BANNER = (
    "🛈 Kickoff assistant — read-only. I can survey the project, assess readiness, and report what "
    "the kickoff grammar understands (extracted / defaulted / missing). I cannot edit files: you "
    "apply captured values via the kickoff UI or the `startd8 kickoff` CLI."
)

KICKOFF_SYSTEM_PROMPT = (
    "You are the StartD8 Kickoff assistant: a READ-ONLY guide that helps a user complete a project "
    "kickoff. You have exactly three tools:\n"
    "  • survey       — brownfield triage of the project\n"
    "  • assess       — kickoff-input readiness (which inputs are authored/estimated/absent)\n"
    "  • field_states — what the kickoff grammar extracted: per-field status (extracted / defaulted "
    "/ missing), the source it came from, and the next recommended action\n"
    "Ground every factual claim in a tool result; never guess. You CANNOT modify files, capture "
    "values, run the cascade, or log friction — and you must never claim to. If the user wants to "
    "save a value, explain that the kickoff UI or the `startd8 kickoff` CLI applies writes at their "
    "privilege, and that you only survey, assess, report state, and advise the next step."
)

_NO_ARGS_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


class KickoffChatError(ValueError):
    """Posture violation: a non-read action reached the kickoff read floor."""


def _field_states_payload(project_root: str | Path) -> dict:
    """The read-only field_states tool result: canonical state + readiness + next action."""
    docs = load_kickoff_docs(project_root)
    state = build_kickoff_state(docs, live_schema_text=live_schema_text(project_root))
    try:
        readiness = build_readiness(project_root)
    except Exception:  # readiness degrades independently; never break field_states on its account
        readiness = None
    payload = {
        "schema_version": 1,
        "action": "field_states",
        "project_root": str(project_root),
        "state": state.to_dict(),
        "next_action": next_action(state, readiness).to_dict(),
    }
    if readiness is not None:
        payload["readiness"] = readiness.to_dict()
    return payload


def handle_kickoff_read(action: str, project_root: str | Path, **_params: object) -> dict:
    """The kickoff read dispatch floor — hard-rejects any non-read action (R1-S5, layer 2).

    ``survey``/``assess`` delegate to the proven concierge read floor; ``field_states`` is handled
    here. There is no path to a write action.
    """
    if action not in KICKOFF_READ_ACTIONS:
        raise KickoffChatError(
            f"kickoff chat is read-only; action {action!r} is refused "
            f"(allowed: {KICKOFF_READ_ACTIONS})"
        )
    if action == "field_states":
        return _field_states_payload(project_root)
    # survey/assess go through the concierge floor (which independently re-rejects non-read actions).
    return handle_concierge_read(action, project_root)


def build_kickoff_registry(project_root: str | Path) -> ToolRegistry:
    """A registry with exactly the three read tools, pinned to *project_root* (R1-S5, layer 1)."""
    root = str(project_root)

    def survey_handler(_args: dict) -> dict:
        return handle_kickoff_read("survey", root)

    def assess_handler(_args: dict) -> dict:
        return handle_kickoff_read("assess", root)

    def field_states_handler(_args: dict) -> dict:
        return handle_kickoff_read("field_states", root)

    return ToolRegistry(
        [
            ToolSpec(
                name="survey",
                description="Survey the project's onboarding state (read-only). No arguments.",
                parameters=_NO_ARGS_SCHEMA,
                handler=survey_handler,
                effect_class="read",
            ),
            ToolSpec(
                name="assess",
                description="Assess kickoff-input readiness (read-only). No arguments.",
                parameters=_NO_ARGS_SCHEMA,
                handler=assess_handler,
                effect_class="read",
            ),
            ToolSpec(
                name="field_states",
                description=(
                    "Report what the kickoff grammar extracted: per-field status, source, and the "
                    "recommended next action (read-only). No arguments."
                ),
                parameters=_NO_ARGS_SCHEMA,
                handler=field_states_handler,
                effect_class="read",
            ),
        ],
        allow_effect_classes=("read",),
    )


@dataclass
class KickoffChat:
    """A read-only kickoff chat session bound to one project."""

    session: AgenticSession
    project_root: str

    def banner(self) -> str:
        return POSTURE_BANNER

    async def ask(self, message: str) -> AgenticResult:
        return await self.session.send(message)

    def cost_line(self, result: AgenticResult) -> str:
        return (
            f"[kickoff · read-only] turns={result.turns} "
            f"tokens={result.total_tokens} cost≈${result.total_cost_usd:.4f}"
        )


def new_kickoff_chat(
    agent: BaseAgent,
    project_root: str | Path,
    *,
    config: Optional[SessionConfig] = None,
) -> KickoffChat:
    """Construct a read-only kickoff chat over *agent*, pinned to *project_root*."""
    registry = build_kickoff_registry(project_root)
    session = AgenticSession(
        agent,
        registry,
        system_prompt=KICKOFF_SYSTEM_PROMPT,
        config=config,
    )
    return KickoffChat(session=session, project_root=str(project_root))
