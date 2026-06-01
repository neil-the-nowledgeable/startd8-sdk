# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

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
