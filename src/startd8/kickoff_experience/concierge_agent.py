"""Resolve which agent (provider/model) the agentic Concierge uses (FR-PC-*).

Precedence (FR-PC-4) — first present, non-placeholder, resolvable-as-a-string layer wins:

    1. the explicit ``--agent`` flag            → source "flag"
    2. per-project ``docs/kickoff/inputs/build-preferences.yaml`` ``concierge_agent`` → "project"
    3. global ``~/.startd8/config.json`` ``preferences.concierge_agent``              → "global"
    4. the catalog default ``Models.CLAUDE_SONNET_LATEST``                            → "default"

This returns the chosen **spec string + source label only** — it does NOT validate the spec or build
an agent (FR-PC-5 / OQ-6). Validation stays at the existing boundary (the CLI's
``resolve_agent_spec`` try/except and the web ``make_chat_factory`` degrade path), so a bad configured
spec degrades exactly like a bad ``--agent``. A malformed/unreadable project file is skipped, never
fatal (FR-PC-9); angle-bracket template placeholders are treated as unset (FR-PC-10).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

# Project config path is pinned (FR-PC-8): this file only, never an examples/ or templates/ copy.
_PROJECT_BUILD_PREFS = ("docs", "kickoff", "inputs", "build-preferences.yaml")


def _usable(spec: Optional[str]) -> Optional[str]:
    """A config value is usable iff it's a non-empty string that is not a `<…>` placeholder (FR-PC-10)."""
    if not spec:
        return None
    s = spec.strip()
    if not s or (s.startswith("<") and s.endswith(">")):
        return None
    return s


def _project_concierge_agent(project_root: str | Path) -> Optional[str]:
    """Read `concierge_agent` from the project's build-preferences.yaml; skip on any error (FR-PC-9)."""
    path = Path(project_root).expanduser().joinpath(*_PROJECT_BUILD_PREFS)
    if not path.is_file():
        return None
    try:
        from ..kickoff_inputs import parse_build_preferences

        return _usable(parse_build_preferences(path.read_text(encoding="utf-8")).concierge_agent)
    except Exception:
        # Malformed sheet / IO error → skip this layer (degrade to the next), never crash.
        return None


def _global_concierge_agent() -> Optional[str]:
    try:
        from ..config import get_config_manager

        return _usable(get_config_manager().get_preference("concierge_agent"))
    except Exception:
        return None


def resolve_concierge_agent_spec(
    project_root: str | Path,
    flag: Optional[str] = None,
) -> Tuple[str, str]:
    """Return ``(spec, source)`` for the agentic Concierge per the FR-PC-4 precedence."""
    from ..model_catalog import Models

    flag_spec = _usable(flag)
    if flag_spec:
        return flag_spec, "flag"
    project_spec = _project_concierge_agent(project_root)
    if project_spec:
        return project_spec, "project"
    global_spec = _global_concierge_agent()
    if global_spec:
        return global_spec, "global"
    return Models.CLAUDE_SONNET_LATEST, "default"   # catalog reference, not a literal (FR-PC-6)
