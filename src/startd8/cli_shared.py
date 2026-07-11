# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Shared CLI primitives: console, logger, framework singleton, agent resolution.

Extracted from cli.py (Pass E) so command-group modules (cli_<group>.py) import
helpers without a cycle back to cli.py.
"""

from typing import Optional
from pathlib import Path
from rich.console import Console

from .framework import AgentFramework
from .agents import BaseAgent
from .logging_config import get_logger
from .utils.agent_resolution import resolve_agent_spec as _resolve_agent_impl

console = Console()
logger = get_logger(__name__)

# Global framework instance
_framework: Optional[AgentFramework] = None


def get_framework(storage_dir: Optional[Path] = None) -> AgentFramework:
    """Get or create framework instance"""
    global _framework
    if _framework is None:
        _framework = AgentFramework(storage_dir)
    return _framework


def _resolve_agent(spec: str, *, name: Optional[str] = None) -> BaseAgent:
    """
    Resolve an agent spec (provider name or model id) into a BaseAgent.

    This is a thin wrapper around the shared utility for backwards compatibility.
    See startd8.utils.agent_resolution.resolve_agent_spec for full documentation.
    """
    return _resolve_agent_impl(spec, name=name)


def render_intro_banner() -> None:
    """FR-UX-16 — the single shared high-level kickoff banner (≤6 lines), shown at the top of every
    human-facing kickoff invocation.

    Sourced from the content contract's tight ``BANNER`` slice (not the fuller TL;DR), so it stays
    scannable and never re-introduces the FR-UX-4 wall. **One** renderer so bare ``kickoff`` and every
    subcommand emit an identical banner (CRP R2-S4). Callers suppress it under ``--json``. Never raises —
    a courtesy banner must not break a command.
    """
    try:
        from .concierge import load_experience_doc

        text = load_experience_doc("intro", section="banner")
    except Exception:
        return
    if not text:
        return
    if console.is_terminal:
        from rich.panel import Panel
        from rich.markdown import Markdown

        console.print(Panel(Markdown(text), border_style="dim", padding=(0, 1)))
    else:
        console.print(text, markup=False, highlight=False)
    console.print()
