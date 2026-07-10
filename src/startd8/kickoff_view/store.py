"""Read-only store over ``.startd8/kickoff-panel/`` (FR-UX-1 / FR-UX-2).

Mirrors :class:`startd8.consultation.store.ConsultationStore` for *reads only* — the viewer
never writes a transcript (Mottainai, FR-UX-2). The sole writer is
``KickoffFacilitator._persist`` (atomic ``tmp`` + ``os.replace``), so a mid-round read sees
either the previous or the next complete document, never a torn one (FR-UX-19).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import KickoffTranscript

TRANSCRIPT_SUBDIR = ".startd8/kickoff-panel"


def _safe_session_component(session_id: str) -> str:
    """Reject a session_id that could escape the kickoff-panel dir (path-traversal guard).

    Mirrors ``TranscriptStore._safe_session_component`` — added because #8 threads a ``source_session_id``
    read from the durable VIPP inbox into ``load()``; an attacker-influenced value like ``../../etc/x``
    must not resolve outside the project (the apply route degrades the resulting ValueError to n/a).
    """
    if not session_id or "/" in session_id or "\\" in session_id or session_id in (".", ".."):
        raise ValueError(f"unsafe session_id: {session_id!r}")
    return session_id


class KickoffPanelStore:
    """List and load facilitation transcripts under a project's ``.startd8/kickoff-panel/``."""

    def __init__(self, project_root: "str | Path" = ".") -> None:
        self.project_root = Path(project_root).expanduser()
        self.root = self.project_root / TRANSCRIPT_SUBDIR

    def _path(self, session_id: str) -> Path:
        return self.root / f"{_safe_session_component(session_id)}.json"

    def list_sessions(self) -> list[str]:
        """Session ids present on disk, **newest-first by mtime** (FR-UX-1)."""
        if not self.root.is_dir():
            return []
        files = [p for p in self.root.glob("*.json") if p.is_file()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [p.stem for p in files]

    def latest_session_id(self) -> Optional[str]:
        """The newest session id, or ``None`` when the directory is empty/absent."""
        sessions = self.list_sessions()
        return sessions[0] if sessions else None

    def load(self, session_id: str) -> KickoffTranscript:
        """Load and validate a transcript by id. Raises ``FileNotFoundError`` if absent."""
        path = self._path(session_id)
        if not path.is_file():
            raise FileNotFoundError(f"no kickoff-panel transcript: {session_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return KickoffTranscript.model_validate(data)

    def load_latest(self) -> Optional[KickoffTranscript]:
        """Load the newest transcript, or ``None`` when none exist (read-only, $0)."""
        sid = self.latest_session_id()
        return self.load(sid) if sid else None

    def mtime(self, session_id: str) -> float:
        """File mtime — the cheap change signal a future ``--watch`` poll-and-diffs (FR-UX-17)."""
        return self._path(session_id).stat().st_mtime
