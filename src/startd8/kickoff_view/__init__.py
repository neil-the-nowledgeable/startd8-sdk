"""Kickoff-panel viewer (observability UX) — a read-only viewer over the facilitated-panel
transcript at ``.startd8/kickoff-panel/<session_id>.json``.

Follow the facilitated process round-by-round and role-by-role for validation-by-observation
and inspiration — **observe and navigate only**. Explicit non-goals (mirrors the facilitation
design §8): no scoring / acceptance / quality grading, no idea-capture or write-back, no
editing/re-running the panel, no ratification affordances. See
``docs/design/project-start/KICKOFF_PANEL_OBSERVABILITY_UX_REQUIREMENTS.md``.

Mirrors the ``startd8.consultation`` five-surface pattern:
``models`` → ``store`` → ``view`` → ``_webview_template`` → ``facade``.
"""

from .models import (
    KickoffTranscript,
    PanelEntry,
    PanelPrep,
    PanelRound,
    PanelSynthesis,
    model_family,
)
from .store import KickoffPanelStore
from .view import render_html, render_text
from .facade import KickoffViewService
from .watcher import TranscriptWatcher

__all__ = [
    "KickoffTranscript",
    "PanelEntry",
    "PanelRound",
    "PanelPrep",
    "PanelSynthesis",
    "model_family",
    "KickoffPanelStore",
    "render_html",
    "render_text",
    "KickoffViewService",
    "TranscriptWatcher",
]
