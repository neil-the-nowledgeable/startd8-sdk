"""Concierge conversational front-end (FR-12) — onboarding as a dialogue, read-only by construction.

The first consumer of the agentic loop (`AgenticSession`). It lets a user *ask* about a project's
SDK-onboarding readiness in natural language; the assistant answers by calling the Concierge's two
**read-only** tools (`survey`, `assess`) and never anything else.

**Posture is structurally inviolable (FR-13), enforced at two independent layers:**
  1. *Registration* — the registry is built with exactly the two read tools and the loop's default
     ``allow_effect_classes={"read"}`` policy (write/destructive are denied by FR-19 anyway).
  2. *Dispatch floor* — every handler routes through ``handle_concierge_read``, which hard-rejects
     any non-``READ_ACTIONS`` action before delegating. Even a mis-registered write tool cannot reach
     a write branch.

**Cost disclosure (FR-14):** the Concierge *tools* stay ``$0``/deterministic, but the *conversation*
spends LLM tokens. The surface exposes a posture banner and a per-session cost line so the
capability's historical "``$0``, no LLM" property is not silently broken — posture is preserved
(explaining ≠ operating); the cost is made visible.

The project root is **pinned at session construction**: tool handlers ignore any model-supplied path
and always operate on the one project, so the loop cannot be steered to survey arbitrary directories.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..agents.agentic import AgenticResult, AgenticSession, SessionConfig, ToolRegistry, ToolSpec
from ..agents.base import BaseAgent
from .core import handle_concierge_read

POSTURE_BANNER = (
    "🛈 Concierge — assist, not operate. Read-only: I can survey and assess this project "
    "to advise on SDK onboarding; I cannot modify files, run the cascade, or record gates."
)

CONCIERGE_SYSTEM_PROMPT = (
    "You are the StartD8 Concierge: a READ-ONLY onboarding assistant that helps a user understand "
    "how ready their project is to be built with the StartD8 SDK. You have exactly two tools:\n"
    "  • survey  — brownfield triage (product boundary, existing PRDs/models/fixtures, path "
    "couplings, PII risks)\n"
    "  • assess  — kickoff-input readiness (which inputs are authored/estimated/placeholder/absent)\n"
    "Ground every factual claim about the project in a tool result; do not guess. You CANNOT modify "
    "files, run the generation cascade, instantiate kickoff artifacts, log friction, or perform any "
    "write — and you must never claim to. If the user asks for a write action, explain that the "
    "`startd8 concierge` CLI performs writes and that you only survey, assess, and advise."
)

_NO_ARGS_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def build_concierge_registry(project_root: str | Path) -> ToolRegistry:
    """A registry with exactly the two read tools, pinned to *project_root* (FR-13 layer 1)."""
    root = str(project_root)

    def survey_handler(_args: dict) -> dict:
        return handle_concierge_read("survey", root)

    def assess_handler(_args: dict) -> dict:
        return handle_concierge_read("assess", root)

    return ToolRegistry(
        [
            ToolSpec(
                name="survey",
                description="Survey the project's onboarding state (read-only). Takes no arguments.",
                parameters=_NO_ARGS_SCHEMA,
                handler=survey_handler,
                effect_class="read",
            ),
            ToolSpec(
                name="assess",
                description="Assess kickoff-input readiness (read-only). Takes no arguments.",
                parameters=_NO_ARGS_SCHEMA,
                handler=assess_handler,
                effect_class="read",
            ),
        ],
        allow_effect_classes=("read",),
    )


@dataclass
class ConciergeChat:
    """A read-only onboarding chat session bound to one project."""

    session: AgenticSession
    project_root: str

    def banner(self) -> str:
        """FR-14 posture banner — show once at session start."""
        return POSTURE_BANNER

    async def ask(self, message: str) -> AgenticResult:
        """Ask an onboarding question; the assistant may call survey/assess to answer."""
        return await self.session.send(message)

    def cost_line(self, result: AgenticResult) -> str:
        """FR-14 per-session cost line — render after each turn so spend is never silent."""
        return (
            f"[concierge · read-only] turns={result.turns} "
            f"tokens={result.total_tokens} cost≈${result.total_cost_usd:.4f}"
        )


def new_concierge_chat(
    agent: BaseAgent,
    project_root: str | Path,
    *,
    config: Optional[SessionConfig] = None,
) -> ConciergeChat:
    """Construct a read-only Concierge chat over *agent*, pinned to *project_root*.

    Raises ``UnsupportedToolUseError`` if the agent does not implement the tool-use primitive.
    """
    registry = build_concierge_registry(project_root)
    session = AgenticSession(
        agent,
        registry,
        system_prompt=CONCIERGE_SYSTEM_PROMPT,
        config=config,
    )
    return ConciergeChat(session=session, project_root=str(project_root))
