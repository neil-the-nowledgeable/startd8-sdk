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
from .store import ConsultationStore, new_session_id
from .engine import ConsultationEngine

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
]
