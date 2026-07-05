"""Synchronous facade for CLI/TUI over the kickoff-panel viewer (read-only).

Mirrors :class:`startd8.consultation.facade.ConsultationService`, but there is nothing async
and nothing mutating here — the viewer only *reads* a transcript the orchestrator wrote. Kept
as a single object so any future TUI surface and the CLI share one bridge (no fork).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .models import KickoffTranscript
from .store import KickoffPanelStore
from .view import render_html, render_text
from .watcher import TranscriptWatcher


class KickoffViewService:
    """Load / list / render kickoff-panel transcripts for a project."""

    def __init__(self, project_root: "str | Path" = ".") -> None:
        self.store = KickoffPanelStore(project_root)

    def list_sessions(self) -> list[str]:
        return self.store.list_sessions()

    def latest_session_id(self) -> Optional[str]:
        return self.store.latest_session_id()

    def load(self, session_id: str) -> KickoffTranscript:
        return self.store.load(session_id)

    def load_latest(self) -> Optional[KickoffTranscript]:
        return self.store.load_latest()

    def render_html(
        self, session_id: str, *, live_reload_secs: "Optional[int]" = None
    ) -> str:
        return render_html(
            self.store.load(session_id), live_reload_secs=live_reload_secs
        )

    def render_text(self, session_id: str, *, by_role: bool = False) -> str:
        return render_text(self.store.load(session_id), by_role=by_role)

    def watcher(self, session_id: str, *, interval: float = 1.0) -> TranscriptWatcher:
        """A :class:`TranscriptWatcher` for live-follow (FR-UX-17)."""
        return TranscriptWatcher(self.store, session_id, interval=interval)
