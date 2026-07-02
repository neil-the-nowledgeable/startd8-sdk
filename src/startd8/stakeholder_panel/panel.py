# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""The live Stakeholder Panel (FR-5/FR-6/FR-8/FR-13/FR-14/FR-16/FR-17/FR-20).

Instantiates one :class:`~startd8.stakeholder_panel.persona.Persona` per roster entry, keeps them
available for on-demand queries, and orchestrates cost tracking (FR-13), OTel spans (FR-14),
transcript persistence (FR-12), a bounded/​budget-gated fan-out (FR-17), and session teardown
(FR-20). The panel is *pinned* to the roster revision it was built from (R2-S3): editing
``stakeholders.yaml`` on disk does not mutate a live panel — a new session must be opened.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional
from uuid import uuid4

from startd8.logging_config import get_logger
from startd8.model_catalog import Models
from startd8.stakeholder_panel.models import (
    Grounding,
    PanelAnswer,
    PersonaBrief,
    Roster,
)
from startd8.stakeholder_panel.persona import Persona, compile_system_prompt
from startd8.stakeholder_panel.telemetry import mark_error, span
from startd8.stakeholder_panel.transcript import TranscriptStore, prune_sessions

__all__ = [
    "StakeholderPanel",
    "PanelError",
    "PanelClosedError",
    "UnknownPersonaError",
    "DEFAULT_MODEL_SPEC",
    "default_agent_factory",
]

logger = get_logger(__name__)

# Personas are cheap bounded Q&A — default to a low-cost model; override via the CLI ``--model``.
DEFAULT_MODEL_SPEC = Models.CLAUDE_HAIKU_LATEST

AgentFactory = Callable[[PersonaBrief], "object"]
BudgetPreflight = Callable[[int], None]


class PanelError(RuntimeError):
    """Base class for panel misuse errors."""


class PanelClosedError(PanelError):
    """A query was issued after :meth:`StakeholderPanel.close` (FR-20)."""


class UnknownPersonaError(PanelError):
    """A ``role_id`` was addressed that is not on the roster (never mis-routed, FR-9c)."""


def default_agent_factory(model_spec: str = DEFAULT_MODEL_SPEC) -> AgentFactory:
    """Build the production agent factory: one real agent per persona, brief baked in (FR-5/FR-15).

    Imported lazily so constructing a panel with an injected factory (tests) needs no provider keys.
    """

    def _factory(brief: PersonaBrief):
        from startd8.utils.agent_resolution import resolve_agent_spec

        return resolve_agent_spec(
            model_spec,
            name=f"persona:{brief.role_id}",
            system_prompt=compile_system_prompt(brief),
        )

    return _factory


def _new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"sess-{stamp}-{uuid4().hex[:8]}"


def _roster_version(personas: List[Persona]) -> str:
    joined = "|".join(sorted(p.brief_hash for p in personas))
    return "sha256:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


class StakeholderPanel:
    """A session-scoped panel of live personas."""

    def __init__(
        self,
        roster: Roster,
        *,
        project_root: Path | str = ".",
        session_id: Optional[str] = None,
        agent_factory: Optional[AgentFactory] = None,
        model_spec: str = DEFAULT_MODEL_SPEC,
        cost_tracker: Optional[object] = None,
        cost_project: str = "stakeholder-panel",
        persist: bool = True,
        history_turns: int = 6,
        prune_keep: int = 50,
        budget_preflight: Optional[BudgetPreflight] = None,
    ) -> None:
        factory = agent_factory or default_agent_factory(model_spec)
        self.session_id = session_id or _new_session_id()
        self.project_root = Path(project_root).expanduser()
        self._model_spec = model_spec
        self._cost_tracker = cost_tracker
        self._cost_project = cost_project
        self._budget_preflight = budget_preflight
        self._closed = False

        self._personas: List[Persona] = [
            Persona(brief, factory(brief), history_turns=history_turns)
            for brief in roster.personas
        ]
        self._by_id = {p.role_id: p for p in self._personas}
        self.roster_version = _roster_version(self._personas)

        self._transcript: Optional[TranscriptStore] = None
        if persist:
            prune_sessions(self.project_root, keep=prune_keep)
            self._transcript = TranscriptStore(self.project_root, self.session_id)

        with span(
            "panel.instantiate",
            **{
                "panel.session_id": self.session_id,
                "panel.persona_count": len(self._personas),
                "panel.roster_version": self.roster_version,
            },
        ):
            logger.info(
                "panel session %s: %d personas (roster %s)",
                self.session_id,
                len(self._personas),
                self.roster_version,
            )

    # ── introspection ────────────────────────────────────────────────────────
    @property
    def role_ids(self) -> List[str]:
        return [p.role_id for p in self._personas]

    def _check_open(self) -> None:
        if self._closed:
            raise PanelClosedError(f"panel session {self.session_id} is closed")

    # ── queries ──────────────────────────────────────────────────────────────
    async def ask(
        self, role_id: str, question: str, *, value_path: str = ""
    ) -> PanelAnswer:
        """Ask one named persona. Raises :class:`UnknownPersonaError` for an off-roster role_id."""
        self._check_open()
        persona = self._by_id.get(role_id)
        if persona is None:
            raise UnknownPersonaError(
                f"no persona {role_id!r} on roster (have: {', '.join(self.role_ids) or 'none'})"
            )

        with span(
            "panel.ask",
            **{
                "panel.role_id": role_id,
                "panel.session_id": self.session_id,
                "gen_ai.request.model": self._model_spec,
                "panel.value_path": value_path or None,
            },
        ) as active_span:
            answer = await persona.ask(question, value_path=value_path)
            if not answer.available:
                mark_error(active_span, "persona unavailable")

            cost = self._record_cost(answer)
            answer = dataclasses.replace(
                answer,
                session_id=self.session_id,
                roster_version=self.roster_version,
                cost_usd=cost,
            )
            _stamp_span(active_span, answer)

        if self._transcript is not None and answer.available:
            self._transcript.append(answer)
        return answer

    async def ask_all(
        self, question: str, *, cap: Optional[int] = None, value_path: str = ""
    ) -> List[PanelAnswer]:
        """Ask every persona, bounded by a cap + optional budget preflight (FR-17).

        The first *cap* personas answer (paid); any remainder are returned as ``deferred`` stubs
        marked "cap reached" and never spend. ``cap=None`` means "all personas".
        """
        self._check_open()
        personas = list(self._personas)
        effective_cap = len(personas) if cap is None else max(0, cap)
        to_ask = personas[:effective_cap]
        deferred = personas[effective_cap:]

        if self._budget_preflight is not None:
            # Raises (e.g. BudgetExceededError) to abort BEFORE any spend (FR-17).
            self._budget_preflight(len(to_ask))

        answered = await asyncio.gather(
            *(self.ask(p.role_id, question, value_path=value_path) for p in to_ask)
        )
        stubs = [_deferred_stub(p, question, value_path, self) for p in deferred]
        return list(answered) + stubs

    # ── lifecycle ────────────────────────────────────────────────────────────
    def close(self) -> None:
        """Release the panel (FR-20). Idempotent; further queries raise ``PanelClosedError``."""
        if self._closed:
            return
        self._closed = True
        self._personas = []
        self._by_id = {}

    def __enter__(self) -> "StakeholderPanel":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ── internals ────────────────────────────────────────────────────────────
    def _record_cost(self, answer: PanelAnswer) -> float:
        """Record one query's cost with role_id+session_id attribution (FR-13). Never throws."""
        if self._cost_tracker is None or not answer.available:
            return 0.0
        try:
            record = self._cost_tracker.record_cost(
                agent_name=f"panel:{answer.role_id}",
                model=answer.model or self._model_spec,
                input_tokens=answer.input_tokens,
                output_tokens=answer.output_tokens,
                project=self._cost_project,
                tags=[f"role:{answer.role_id}", f"session:{self.session_id}"],
                metadata={"role_id": answer.role_id, "session_id": self.session_id},
            )
            return float(getattr(record, "total_cost", 0.0) or 0.0)
        except (
            Exception
        ) as exc:  # noqa: BLE001 - cost tracking must never break a query
            logger.warning("panel cost record failed for %s: %s", answer.role_id, exc)
            return 0.0


def _stamp_span(active_span: object, answer: PanelAnswer) -> None:
    """Attach non-text answer metrics to the query span (R1-F5: no raw Q&A/brief text)."""
    from startd8.agents.agentic_otel import set_attributes

    set_attributes(
        active_span,
        **{
            "panel.grounding": answer.grounding.value,
            "gen_ai.usage.input_tokens": answer.input_tokens,
            "gen_ai.usage.output_tokens": answer.output_tokens,
            "panel.cost_usd": answer.cost_usd,
        },
    )


def _deferred_stub(
    persona: Persona, question: str, value_path: str, panel: "StakeholderPanel"
) -> PanelAnswer:
    return PanelAnswer(
        role_id=persona.role_id,
        question=question,
        text="(deferred — panel query cap reached)",
        grounding=Grounding.DEFERRED,
        value_path=value_path,
        brief_hash=persona.brief_hash,
        roster_version=panel.roster_version,
        session_id=panel.session_id,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
