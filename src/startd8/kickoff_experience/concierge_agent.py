"""Compat shim (GE-M2) — Concierge agent-spec resolution now lives in ``concierge_view``.

GE-M2 folded the concierge-UI quartet into one view+apply module (``concierge_view``). This module
re-exports the agent-resolution surface so the legacy import path
``from startd8.kickoff_experience.concierge_agent import …`` keeps working for one release. Prefer
importing from ``concierge_view`` directly.

Note: monkeypatch tests that stub the internal ladder helpers must patch them on ``concierge_view``
(their real home), not on this shim — patch where the symbol is looked up, not where it is
re-exported.
"""

from __future__ import annotations

from .concierge_view import (  # noqa: F401
    _PROJECT_BUILD_PREFS,
    _global_concierge_agent,
    _project_concierge_agent,
    _usable,
    resolve_concierge_agent_spec,
)

__all__ = ["resolve_concierge_agent_spec"]
