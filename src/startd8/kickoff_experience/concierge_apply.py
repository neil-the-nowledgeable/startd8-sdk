"""Compat shim (GE-M2) — the typed Concierge applier now lives in ``concierge_view``.

GE-M2 folded the concierge-UI quartet into one view+apply module (``concierge_view``). This module
re-exports the applier surface so the legacy import path
``from startd8.kickoff_experience.concierge_apply import …`` keeps working for one release. Prefer
importing from ``concierge_view`` directly.
"""

from __future__ import annotations

from .concierge_view import (  # noqa: F401
    FRICTION_FIELD_MAX,
    ConciergeInputError,
    ConciergeWriteCode,
    ConciergeWriteResult,
    apply_concierge_plan,
    validate_friction,
    validate_posture,
)

__all__ = [
    "FRICTION_FIELD_MAX",
    "ConciergeInputError",
    "ConciergeWriteCode",
    "ConciergeWriteResult",
    "apply_concierge_plan",
    "validate_friction",
    "validate_posture",
]
