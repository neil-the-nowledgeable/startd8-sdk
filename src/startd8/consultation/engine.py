"""Parallel consultation fan-out driver (M2.3–M2.5 / FR-MMC-3, -7, -11).

Reuses the benchmark fan-out shape — ``asyncio.gather(..., return_exceptions=True)`` — over
a consultation roster, threading each model's prior *valid* turns as history so a follow-up
to a single model continues that model's thread and a follow-up to all continues each
thread independently and in parallel.

Continuity mechanism (v1): each model call is a single ``acreate_response`` whose prompt is
a rendered transcript of that model's prior **ok** turns (:meth:`ConsultationSession.valid_history`)
followed by the new user message. Images ride the turn they are supplied on via the M1
``images=`` path (so image-token cost flows through the per-call cost hook, M2.5). Native
per-provider message arrays + prior-image re-send are a documented future enhancement (OQ-10).

Ordering (R2-S10): the engine is the single writer per session object and awaits the whole
gather before persisting, so a model is never threaded with a not-yet-persisted prior turn.
Cross-process collisions are prevented by the exclusive, process-unique session id.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from ..agents.base import BaseAgent
from ..agents.multimodal import ImageInput, model_supports_vision
from ..logging_config import get_logger
from .models import (
    ConsultationSession,
    SessionImageRef,
    Turn,
    TurnError,
    TurnRole,
    TurnStatus,
)
from .store import ConsultationStore, new_session_id

logger = get_logger(__name__)

# Sentinel for "send this follow-up to every roster model".
ALL = "all"


def _classify_error(exc: BaseException) -> TurnError:
    """Capture a provider error as structured data (R2-S8), not a flattened string."""
    code = getattr(exc, "status_code", None)
    if code is None:
        code = getattr(exc, "code", None)
    return TurnError(
        type=type(exc).__name__,
        code=str(code) if code is not None else None,
        message=str(exc)[:1000],
    )


def _tokens(token_usage) -> tuple[Optional[int], Optional[int]]:
    """Extract (input, output) tokens from an AgentResponse.token_usage, tolerating shapes."""
    if token_usage is None:
        return None, None
    if isinstance(token_usage, dict):
        return token_usage.get("input"), token_usage.get("output")
    return getattr(token_usage, "input", None), getattr(token_usage, "output", None)


class ConsultationEngine:
    """Runs the initial fan-out and follow-up turns for a consultation session."""

    def __init__(self, store: ConsultationStore) -> None:
        self.store = store

    # ── public API ───────────────────────────────────────────────────────────
    async def start(
        self,
        prompt: str,
        images: "list[ImageInput] | None",
        roster: "dict[str, BaseAgent]",
    ) -> ConsultationSession:
        """Create a session and fan the initial prompt out to every roster model."""
        images = images or []
        session_id = new_session_id()
        self.store.create_session_dir(session_id)  # exclusive; fail-loud on collision
        session = ConsultationSession(
            id=session_id,
            prompt=prompt,
            images=[SessionImageRef.from_ref(i.to_ref()) for i in images],
            roster=list(roster.keys()),
        )
        await self._fan_out(session, roster, prompt, images, targets=list(roster.keys()))
        return session

    async def follow_up(
        self,
        session: ConsultationSession,
        roster: "dict[str, BaseAgent]",
        prompt: str,
        target: str = ALL,
        images: "list[ImageInput] | None" = None,
    ) -> ConsultationSession:
        """Send a follow-up prompt to ``ALL`` roster models or a single ``target`` model."""
        images = images or []
        if target == ALL:
            targets = list(session.roster)
        else:
            if target not in session.roster:
                raise ValueError(f"{target!r} is not a model in this session's roster")
            targets = [target]
        await self._fan_out(session, roster, prompt, images, targets)
        return session

    async def retry_failed(
        self,
        session: ConsultationSession,
        roster: "dict[str, BaseAgent]",
    ) -> ConsultationSession:
        """Re-invoke **only** the models whose last turn failed (FR-MMC-11).

        Each failed model is retried with the same user prompt it last received; already
        succeeded models are left untouched.
        """
        targets = session.failed_models()
        if not targets:
            return session
        # Group by the prompt each failed model needs replayed (usually identical).
        await asyncio.gather(
            *[
                self._run_one(session, roster[m], m, session.last_user_prompt(m) or session.prompt, [])
                for m in targets
                if m in roster
            ],
            return_exceptions=True,
        )
        self._persist(session)
        return session

    # ── internals ────────────────────────────────────────────────────────────
    async def _fan_out(
        self,
        session: ConsultationSession,
        roster: "dict[str, BaseAgent]",
        prompt: str,
        images: "list[ImageInput]",
        targets: "list[str]",
    ) -> None:
        # return_exceptions=True: one model's failure never aborts the others (FR-MMC-3).
        # _run_one records failures as structured turns, so exceptions should not escape;
        # the flag is defense in depth.
        await asyncio.gather(
            *[self._run_one(session, roster[m], m, prompt, images) for m in targets if m in roster],
            return_exceptions=True,
        )
        self._persist(session)

    async def _run_one(
        self,
        session: ConsultationSession,
        agent: BaseAgent,
        model_id: str,
        prompt: str,
        images: "list[ImageInput]",
    ) -> None:
        turns = session.turns_by_model.setdefault(model_id, [])
        img_refs = [SessionImageRef.from_ref(i.to_ref()) for i in images]

        # Capability gate (FR-MMC-2a): a non-vision model cannot take images — record a
        # skipped turn instead of a mid-run crash.
        if images and not model_supports_vision(model_id):
            turns.append(Turn(role=TurnRole.user, text=prompt, images=img_refs))
            turns.append(
                Turn(
                    role=TurnRole.assistant,
                    status=TurnStatus.skipped_non_vision,
                    error=TurnError(
                        type="capability",
                        message=f"{model_id} is not vision-capable; image turn skipped",
                    ),
                )
            )
            return

        # Build the effective prompt from prior *valid* turns (R1-S8) + this prompt.
        effective_prompt = self._render_history(session, model_id) + prompt
        turns.append(Turn(role=TurnRole.user, text=prompt, images=img_refs))

        try:
            response = await agent.acreate_response(
                prompt_id=f"{session.id}:{model_id}:{len(turns)}",
                prompt=effective_prompt,
                images=images or None,
            )
            in_tok, out_tok = _tokens(getattr(response, "token_usage", None))
            turns.append(
                Turn(
                    role=TurnRole.assistant,
                    text=response.response,
                    status=TurnStatus.ok,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    time_ms=getattr(response, "response_time_ms", None),
                )
            )
        except Exception as exc:  # noqa: BLE001 — one model failing must not sink the panel
            logger.warning(
                "consultation model %s failed: %s", model_id, exc,
                extra={"session_id": session.id, "model_id": model_id},
            )
            turns.append(
                Turn(role=TurnRole.assistant, status=TurnStatus.failed, error=_classify_error(exc))
            )

    @staticmethod
    def _render_history(session: ConsultationSession, model_id: str) -> str:
        """Render prior valid turns as a transcript prefix (empty for the first turn)."""
        history = session.valid_history(model_id)
        if not history:
            return ""
        lines: list[str] = ["<conversation-history>"]
        for turn in history:
            speaker = "User" if turn.role == TurnRole.user else "Assistant"
            lines.append(f"{speaker}: {turn.text}")
        lines.append("</conversation-history>\n\n")
        return "\n".join(lines)

    def _persist(self, session: ConsultationSession) -> None:
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self.store.save(session)
