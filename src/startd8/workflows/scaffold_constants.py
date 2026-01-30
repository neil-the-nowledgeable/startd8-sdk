# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""
Centralized constants for workflow scaffolding.

Following MCP Leg 3 #8: Centralize constants to avoid scattered string literals.
"""

from pathlib import Path
from typing import Dict, List

# =============================================================================
# Template Types
# =============================================================================

TEMPLATE_BASIC = "basic"
TEMPLATE_PIPELINE = "pipeline"
TEMPLATE_MULTI_AGENT = "multi_agent"
TEMPLATE_ASYNC = "async"

VALID_TEMPLATES: List[str] = [
    TEMPLATE_BASIC,
    TEMPLATE_PIPELINE,
    TEMPLATE_MULTI_AGENT,
    TEMPLATE_ASYNC,
]

DEFAULT_TEMPLATE = TEMPLATE_BASIC

# Template descriptions for help text
TEMPLATE_DESCRIPTIONS: Dict[str, str] = {
    TEMPLATE_BASIC: "Simple single-agent workflow",
    TEMPLATE_PIPELINE: "Sequential multi-agent pipeline",
    TEMPLATE_MULTI_AGENT: "Parallel agent coordination",
    TEMPLATE_ASYNC: "Async-first implementation",
}

# =============================================================================
# Default Output Paths
# =============================================================================

# Relative to src/startd8/workflows/
DEFAULT_OUTPUT_DIR = Path("builtin")

# =============================================================================
# Naming Conventions
# =============================================================================

# Class name suffix for generated workflows
WORKFLOW_CLASS_SUFFIX = "Workflow"

# =============================================================================
# Error Messages
# =============================================================================

ERR_INVALID_TEMPLATE = "Invalid template type '{template}'. Valid options: {valid}"
ERR_FILE_EXISTS = "File already exists: {path}. Use --force to overwrite."
ERR_INVALID_NAME = (
    "Invalid workflow name '{name}'. "
    "Use kebab-case (e.g., 'my-workflow') or snake_case (e.g., 'my_workflow')."
)
ERR_JINJA2_NOT_INSTALLED = (
    "Jinja2 is required for workflow scaffolding. "
    "Install with: pip install jinja2"
)
ERR_TEMPLATE_NOT_FOUND = "Template file not found: {template}"
ERR_OUTPUT_DIR_NOT_FOUND = "Output directory does not exist: {path}"

# =============================================================================
# Success Messages
# =============================================================================

MSG_WORKFLOW_CREATED = "Created workflow: {path}"
MSG_WORKFLOW_READY = "Workflow '{name}' is ready to use."

# =============================================================================
# Template Variables (defaults)
# =============================================================================

DEFAULT_VERSION = "1.0.0"
DEFAULT_DESCRIPTION = "A custom workflow implementation."
DEFAULT_CAPABILITIES: List[str] = []
DEFAULT_TAGS: List[str] = ["custom"]
