"""Compat shim (GE-M2) — the TUI Concierge driver now lives in ``concierge_view``.

GE-M2 folded the concierge-UI quartet into one view+apply module (``concierge_view``). This module
re-exports the TUI driver surface so the legacy import path
``from startd8.kickoff_experience.tui_concierge import …`` keeps working for one release. Prefer
importing from ``concierge_view`` directly.
"""

from __future__ import annotations

from .concierge_view import (  # noqa: F401
    CONFIRM_UNAVAILABLE,
    ConciergeRunResult,
    ConfirmFn,
    PrintFn,
    PromptFn,
    _questionary_confirm,
    _questionary_prompt,
    run_concierge,
)

__all__ = [
    "CONFIRM_UNAVAILABLE",
    "ConciergeRunResult",
    "ConfirmFn",
    "PrintFn",
    "PromptFn",
    "run_concierge",
]
