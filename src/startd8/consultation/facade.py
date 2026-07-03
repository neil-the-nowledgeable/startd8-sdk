"""Synchronous facade over the async consultation engine (M3/M3.5).

The TUI's questionary loop and the ``startd8 consult`` CLI are both synchronous; this bridges
them to the async :class:`ConsultationEngine` via ``asyncio.run`` (mirrors the
``tui/agentic_chat.py`` reply bridge). Both surfaces call the **same** service — the no-fork
guarantee (FR-MMC-13) is that TUI and CLI share this object, not just similar code.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from ..agents.base import BaseAgent
from ..agents.multimodal import ImageInput
from .engine import ALL, ConsultationEngine
from .models import ConsultationSession
from .store import ConsultationStore


class ConsultationService:
    """Sync wrapper coupling a :class:`ConsultationStore` and :class:`ConsultationEngine`."""

    def __init__(self, base_dir: "str | Path" = ".startd8") -> None:
        self.store = ConsultationStore(base_dir)
        self.engine = ConsultationEngine(self.store)

    def start(
        self,
        prompt: str,
        images: "Optional[list[ImageInput]]",
        roster: "dict[str, BaseAgent]",
    ) -> ConsultationSession:
        return asyncio.run(self.engine.start(prompt, images, roster))

    def follow_up(
        self,
        session: ConsultationSession,
        roster: "dict[str, BaseAgent]",
        prompt: str,
        target: str = ALL,
        images: "Optional[list[ImageInput]]" = None,
    ) -> ConsultationSession:
        return asyncio.run(self.engine.follow_up(session, roster, prompt, target, images))

    def retry_failed(
        self,
        session: ConsultationSession,
        roster: "dict[str, BaseAgent]",
    ) -> ConsultationSession:
        return asyncio.run(self.engine.retry_failed(session, roster))

    def load(self, session_id: str) -> ConsultationSession:
        return self.store.load(session_id)

    def list_sessions(self) -> list[str]:
        return self.store.list_sessions()
