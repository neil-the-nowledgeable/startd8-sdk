# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""A single live persona: a brief compiled into a system prompt, wrapping one agent (FR-5/FR-6/FR-7).

The persona is a thin wrapper over ``agent.agenerate(prompt, system_prompt=…)`` (FR-15) — no
``AgenticSession``. It threads its own bounded conversation history (FR-6/FR-20), answers strictly
in-character with a machine-readable grounding signal (FR-7), and **never raises**: an agent
failure/timeout degrades to an ``unavailable`` answer (FR-16), never a fabricated fact.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Tuple

from startd8.agents.base import BaseAgent
from startd8.logging_config import get_logger
from startd8.stakeholder_panel.grounding_guard import check_grounding
from startd8.stakeholder_panel.models import Grounding, PanelAnswer, PersonaBrief
from startd8.stakeholder_panel.provenance import brief_hash

__all__ = ["Persona", "compile_system_prompt", "parse_grounding"]

logger = get_logger(__name__)

_GROUNDING_MARKER = "GROUNDING:"
# Bound threaded history so a long session cannot grow the prompt (and cost) without limit (FR-20).
_DEFAULT_HISTORY_TURNS = 6


def _bullets(items: List[str]) -> str:
    return "\n".join(f"  - {i}" for i in items) if items else "  - (none stated)"


def compile_system_prompt(brief: PersonaBrief) -> str:
    """Compile a persona brief into the system prompt that bounds it (FR-7)."""
    return (
        "You are role-playing a single project stakeholder during a software project kickoff. "
        "Stay in character and answer as this person would.\n\n"
        f"WHO YOU ARE: {brief.display_name} (role id: {brief.role_id})\n"
        f"YOUR GOALS:\n{_bullets(brief.goals)}\n"
        f"YOUR CONSTRAINTS:\n{_bullets(brief.constraints)}\n"
        f"POSITIONS YOU HAVE ALREADY TAKEN:\n{_bullets(brief.known_positions)}\n"
        f"OUT OF SCOPE FOR YOU:\n{_bullets(brief.out_of_scope)}\n\n"
        "RULES:\n"
        "- The brief above is your ENTIRE knowledge. Answer only from it.\n"
        "- If asked something the brief does not cover, DEFER: say it is outside your remit and "
        "that the team should decide. Do NOT invent facts, numbers, or decisions.\n"
        "- Speak in the first person, concisely (2-4 sentences).\n"
        "- End EVERY reply with a final line, exactly:\n"
        "  GROUNDING: <grounded|uncertain|deferred>\n"
        "  where grounded = the brief directly supports your answer; uncertain = you inferred or "
        "hedged; deferred = the question is outside your brief."
    )


def parse_grounding(raw: str) -> Tuple[str, Grounding]:
    """Split a model reply into (visible answer, grounding). Missing marker ⇒ ``uncertain``."""
    lines = raw.splitlines()
    grounding = Grounding.UNCERTAIN
    kept: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith(_GROUNDING_MARKER):
            grounding = Grounding.coerce(stripped[len(_GROUNDING_MARKER) :])
            continue
        kept.append(line)
    return "\n".join(kept).strip(), grounding


class Persona:
    """One stakeholder, kept available for bounded multi-turn Q&A."""

    def __init__(
        self,
        brief: PersonaBrief,
        agent: BaseAgent,
        *,
        history_turns: int = _DEFAULT_HISTORY_TURNS,
    ) -> None:
        self.brief = brief
        self.agent = agent
        self.role_id = brief.role_id
        self.system_prompt = compile_system_prompt(brief)
        # Pinned at construction (R2-S3): the exact brief revision this live persona answers from.
        self.brief_hash = brief_hash(brief)
        self._history_turns = max(0, history_turns)
        self._history: List[Tuple[str, str]] = []
        # Serialize concurrent asks to THIS persona so the threaded history is race-free (FR-20).
        self._lock = asyncio.Lock()

    def _prompt_with_history(self, question: str) -> str:
        parts: List[str] = []
        for q, a in self._history:
            parts.append(f"USER: {q}\nYOU: {a}")
        parts.append(f"USER: {question}\nYOU:")
        return "\n\n".join(parts)

    def _remember(self, question: str, answer: str) -> None:
        if self._history_turns == 0:
            return  # stateless persona: keep no history (never grow the prompt/cost)
        self._history.append((question, answer))
        if len(self._history) > self._history_turns:
            # Drop oldest turns beyond the cap (simple bound; summarization is a later refinement).
            self._history = self._history[-self._history_turns :]

    async def ask(self, question: str, *, value_path: str = "") -> PanelAnswer:
        """Answer *question* in character. Never raises — a failure degrades to ``unavailable``."""
        async with self._lock:
            prompt = self._prompt_with_history(question)
            now = datetime.now(timezone.utc).isoformat()
            try:
                text, _time_ms, usage = await self.agent.agenerate(
                    prompt, system_prompt=self.system_prompt
                )
            except Exception as exc:  # noqa: BLE001 - degrade, never propagate (FR-16)
                logger.warning(
                    "persona %s unavailable: %s", self.role_id, exc, exc_info=False
                )
                return PanelAnswer(
                    role_id=self.role_id,
                    question=question,
                    text="(stakeholder unavailable)",
                    grounding=Grounding.UNAVAILABLE,
                    value_path=value_path,
                    brief_hash=self.brief_hash,
                    model=getattr(self.agent, "model", ""),
                    created_at=now,
                )

            visible, reported = parse_grounding(text)
            # FR-7 (M3): independent guard — downgrade a self-reported "grounded" that asserts
            # specifics the brief does not support, and attach the advisory flags.
            grounding, flags = check_grounding(self.brief, visible, reported)
            self._remember(question, visible)
            return PanelAnswer(
                role_id=self.role_id,
                question=question,
                text=visible,
                grounding=grounding,
                value_path=value_path,
                brief_hash=self.brief_hash,
                model=getattr(self.agent, "model", "")
                or getattr(usage, "model_name", "")
                or "",
                input_tokens=int(getattr(usage, "input", 0) or 0),
                output_tokens=int(getattr(usage, "output", 0) or 0),
                created_at=now,
                flags=flags,
            )
