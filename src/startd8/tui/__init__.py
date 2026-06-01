"""TUI helper package.

Pass A refactor of the monolithic ``tui_improved.py``: the self-contained
helper classes and shared widget primitives now live in focused submodules.
``tui_improved`` re-exports these for backward compatibility, so existing
import paths (``from startd8.tui_improved import APIKeyManager``) keep working.
"""

from .widgets import (
    HAS_QUESTIONARY,
    questionary,
    Style,
    console,
    custom_style,
    select_with_filter,
)
from .api_key_manager import APIKeyManager
from .custom_agent_manager import CustomAgentManager
from .tour_guide import TourGuide
from .agent_config_tester import AgentConfigTester

__all__ = [
    "HAS_QUESTIONARY",
    "questionary",
    "Style",
    "console",
    "custom_style",
    "select_with_filter",
    "APIKeyManager",
    "CustomAgentManager",
    "TourGuide",
    "AgentConfigTester",
]
