"""Shared imports for ImprovedTUI mixins (Pass B).

Mirrors the module-level imports of ``tui_improved.py`` so that methods moved
into mixin modules resolve their bare global references unchanged. Mixin
modules do ``from ._shared import *``. Relative imports are re-leveled to the
``startd8.tui`` package depth (``..x`` reaches ``startd8.x``).
"""

import sys  # noqa: F401
import os  # noqa: F401
import json  # noqa: F401
from typing import Optional, List, Dict, Any, Tuple  # noqa: F401
from pathlib import Path  # noqa: F401

from rich.console import Console  # noqa: F401
from rich.panel import Panel  # noqa: F401
from rich.table import Table  # noqa: F401
from rich.progress import Progress, SpinnerColumn, TextColumn  # noqa: F401
from rich.markdown import Markdown  # noqa: F401
from rich import print as rprint  # noqa: F401

from ..framework import AgentFramework  # noqa: F401
from ..agents import (  # noqa: F401
    MockAgent, ClaudeAgent, GPT4Agent, OpenAICompatibleAgent, ComposerAgent, BaseAgent,
)
from ..orchestration import Pipeline, WorkflowTemplates  # noqa: F401
from ..workflows.builtin import (  # noqa: F401
    DesignPolishWorkflow, CriticalReviewWorkflow, ArchitecturalReviewLogWorkflow,
    ConvergentReviewWorkflow,
)
from ..document_enhancement import DocumentEnhancementChain  # noqa: F401
from ..iterative_workflow import (  # noqa: F401
    IterativeDevWorkflow, IterativeWorkflowResult, save_workflow_result,
)
from ..config import ConfigManager  # noqa: F401
from ..tui_help_system import HelpSystem  # noqa: F401
from ..tui_workflow_help import WorkflowHelper  # noqa: F401
from ..error_analysis import get_last_error_from_logs, format_error_for_analysis  # noqa: F401
from ..paths import default_config_dir, default_data_dir  # noqa: F401
from ..models import (  # noqa: F401
    DocumentEnhancementConfig, AgentConfig as EnhancementAgentConfig, ErrorHandling, AgentResponse,
)
from ..exceptions import AgentError, APIError, ConfigurationError  # noqa: F401
from ..utils.file_operations import save_text_file_with_versioning  # noqa: F401

from .widgets import (  # noqa: F401
    HAS_QUESTIONARY, questionary, Style, console, custom_style, select_with_filter,
)
from .api_key_manager import APIKeyManager  # noqa: F401
from .custom_agent_manager import CustomAgentManager  # noqa: F401
from .tour_guide import TourGuide  # noqa: F401
from .agent_config_tester import AgentConfigTester  # noqa: F401
