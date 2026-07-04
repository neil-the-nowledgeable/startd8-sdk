"""Compat shim (GE-M2) — the completion meter now lives in the ``orchestrator`` conductor.

GE-M2 consolidated the three "what's next" projections (``orchestrator`` + ``wizard`` +
``red_carpet_completion``) into one conductor module (``orchestrator``). This module re-exports the
completion-meter surface so the legacy import path
``from startd8.kickoff_experience.red_carpet_completion import …`` keeps working for one release.
Prefer importing from ``orchestrator`` directly.
"""

from __future__ import annotations

from .orchestrator import (  # noqa: F401
    _DEFAULTED_PROVENANCE,
    _MANIFEST_GATES,
    Completion,
    StageCompletion,
    _field_present,
    build_completion,
)

__all__ = ["StageCompletion", "Completion", "build_completion"]
