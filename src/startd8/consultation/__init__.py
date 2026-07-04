"""Multi-Model Consultation (M2) — session model, storage, and parallel fan-out.

Send one prompt (+ up to 2 images) to N models in parallel, persist each model's answer
as a :class:`ConsultationSession` for human comparison, and follow up with all-or-one
routing while each model's thread is retained. Inspired by (not part of) the Summer2026
benchmark. See ``docs/design/multi-model-consult/``.
"""

from .models import (
    ConsultationSession,
    SessionImageRef,
    Turn,
    TurnError,
    TurnRole,
    TurnStatus,
)
from .store import ConsultationStore, SessionBusyError, new_session_id
from .engine import ALL, ConsultationEngine
from .facade import ConsultationService
from .roster import DEFAULT_COUNCIL, build_roster
from .selection import resolve_images, select_from_dir, load_paths
from .view import comparison_table, comparison_text, render_html
from .cost import session_cost, turn_cost_usd
from .presets import PresetStore
from .continuity import build_messages, reload_image

__all__ = [
    "ConsultationSession",
    "SessionImageRef",
    "Turn",
    "TurnError",
    "TurnRole",
    "TurnStatus",
    "ConsultationStore",
    "new_session_id",
    "ConsultationEngine",
    "ALL",
    "ConsultationService",
    "DEFAULT_COUNCIL",
    "build_roster",
    "resolve_images",
    "select_from_dir",
    "load_paths",
    "comparison_table",
    "comparison_text",
    "render_html",
    "session_cost",
    "turn_cost_usd",
    "PresetStore",
    "SessionBusyError",
    "build_messages",
    "reload_image",
]
