# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""
Template loading utilities for workflow scaffolding.

Following SDK Leg 12 #2: Optional imports with graceful fallback for Jinja2.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..scaffold_constants import (
    ERR_JINJA2_NOT_INSTALLED,
    ERR_TEMPLATE_NOT_FOUND,
    VALID_TEMPLATES,
)

# Optional Jinja2 import (requires jinja2 package)
try:
    from jinja2 import Environment, FileSystemLoader, Template
    JINJA2_AVAILABLE = True
except ImportError:
    Environment = None  # type: ignore
    FileSystemLoader = None  # type: ignore
    Template = None  # type: ignore
    JINJA2_AVAILABLE = False


# Template directory (same directory as this file)
TEMPLATES_DIR = Path(__file__).parent


@dataclass
class TemplateContext:
    """Context variables for template rendering."""

    # Naming
    workflow_id: str          # kebab-case: "my-workflow"
    module_name: str          # snake_case: "my_workflow"
    class_name: str           # PascalCase: "MyWorkflowWorkflow"

    # Metadata
    name: str                 # Display name: "My Workflow"
    description: str
    version: str

    # Configuration
    capabilities: list
    tags: list

    # Optional extras
    author: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Jinja2 template."""
        return {
            "workflow_id": self.workflow_id,
            "module_name": self.module_name,
            "class_name": self.class_name,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": self.capabilities,
            "tags": self.tags,
            "author": self.author,
        }


class TemplateLoader:
    """
    Load and render Jinja2 templates for workflow scaffolding.

    Raises ImportError if Jinja2 is not installed.
    """

    def __init__(self, templates_dir: Optional[Path] = None):
        """
        Initialize template loader.

        Args:
            templates_dir: Directory containing .jinja templates.
                          Defaults to the templates/ directory.

        Raises:
            ImportError: If Jinja2 is not installed.
        """
        if not JINJA2_AVAILABLE:
            raise ImportError(ERR_JINJA2_NOT_INSTALLED)

        self.templates_dir = templates_dir or TEMPLATES_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def get_template(self, template_type: str) -> "Template":
        """
        Get a template by type.

        Args:
            template_type: One of VALID_TEMPLATES (basic, pipeline, etc.)

        Returns:
            Jinja2 Template object

        Raises:
            FileNotFoundError: If template file doesn't exist.
        """
        template_file = f"{template_type}.py.jinja"
        template_path = self.templates_dir / template_file

        if not template_path.exists():
            raise FileNotFoundError(
                ERR_TEMPLATE_NOT_FOUND.format(template=template_file)
            )

        return self._env.get_template(template_file)

    def render(self, template_type: str, context: TemplateContext) -> str:
        """
        Render a template with the given context.

        Args:
            template_type: Template type (basic, pipeline, etc.)
            context: TemplateContext with variables

        Returns:
            Rendered Python code as string
        """
        template = self.get_template(template_type)
        return template.render(**context.to_dict())

    def list_templates(self) -> list:
        """List available template types."""
        available = []
        for template_type in VALID_TEMPLATES:
            template_path = self.templates_dir / f"{template_type}.py.jinja"
            if template_path.exists():
                available.append(template_type)
        return available


def check_jinja2_available() -> bool:
    """Check if Jinja2 is available for import."""
    return JINJA2_AVAILABLE
