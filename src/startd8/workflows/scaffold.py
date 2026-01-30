# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""
Workflow scaffolding implementation.

Generates new workflow files from Jinja2 templates.
Following SDK Leg 4 #2: Keep CLI thin, delegate logic here.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .scaffold_constants import (
    DEFAULT_TEMPLATE,
    DEFAULT_VERSION,
    DEFAULT_DESCRIPTION,
    DEFAULT_CAPABILITIES,
    DEFAULT_TAGS,
    DEFAULT_OUTPUT_DIR,
    VALID_TEMPLATES,
    TEMPLATE_DESCRIPTIONS,
    WORKFLOW_CLASS_SUFFIX,
    ERR_INVALID_TEMPLATE,
    ERR_FILE_EXISTS,
    ERR_INVALID_NAME,
    ERR_OUTPUT_DIR_NOT_FOUND,
    MSG_WORKFLOW_CREATED,
)
from .templates import TemplateLoader, TemplateContext, check_jinja2_available


@dataclass
class ScaffoldConfig:
    """Configuration for workflow scaffolding."""

    # Required
    name: str  # Workflow name in kebab-case or snake_case

    # Template selection
    template: str = DEFAULT_TEMPLATE

    # Output configuration
    output_dir: Optional[Path] = None  # Defaults to workflows/builtin/

    # Metadata
    description: str = DEFAULT_DESCRIPTION
    version: str = DEFAULT_VERSION
    capabilities: List[str] = field(default_factory=lambda: list(DEFAULT_CAPABILITIES))
    tags: List[str] = field(default_factory=lambda: list(DEFAULT_TAGS))

    # Behavior
    force: bool = False  # Overwrite existing files


@dataclass
class ScaffoldResult:
    """Result of a scaffold operation."""

    success: bool
    file_path: Optional[Path] = None
    workflow_id: str = ""
    class_name: str = ""
    error: Optional[str] = None

    @classmethod
    def ok(cls, file_path: Path, workflow_id: str, class_name: str) -> "ScaffoldResult":
        """Create a successful result."""
        return cls(
            success=True,
            file_path=file_path,
            workflow_id=workflow_id,
            class_name=class_name,
        )

    @classmethod
    def fail(cls, error: str) -> "ScaffoldResult":
        """Create a failed result."""
        return cls(success=False, error=error)


class WorkflowScaffolder:
    """
    Generate new workflow files from templates.

    Example:
        scaffolder = WorkflowScaffolder()
        result = scaffolder.scaffold(ScaffoldConfig(
            name="my-workflow",
            template="pipeline",
            description="My custom pipeline",
        ))
        if result.success:
            print(f"Created: {result.file_path}")
    """

    def __init__(self):
        """Initialize the scaffolder."""
        self._loader: Optional[TemplateLoader] = None

    @property
    def loader(self) -> TemplateLoader:
        """Lazy-load template loader (raises ImportError if Jinja2 missing)."""
        if self._loader is None:
            self._loader = TemplateLoader()
        return self._loader

    def scaffold(self, config: ScaffoldConfig) -> ScaffoldResult:
        """
        Generate a new workflow file from a template.

        Args:
            config: ScaffoldConfig with name, template, and options

        Returns:
            ScaffoldResult with success status and file path
        """
        # Validate template
        if config.template not in VALID_TEMPLATES:
            return ScaffoldResult.fail(
                ERR_INVALID_TEMPLATE.format(
                    template=config.template,
                    valid=", ".join(VALID_TEMPLATES),
                )
            )

        # Convert name to standard formats
        try:
            workflow_id = self._to_kebab_case(config.name)
            module_name = self._to_snake_case(config.name)
            class_name = self._to_pascal_case(config.name) + WORKFLOW_CLASS_SUFFIX
            display_name = self._to_display_name(config.name)
        except ValueError as e:
            return ScaffoldResult.fail(str(e))

        # Determine output path
        if config.output_dir:
            output_dir = config.output_dir
        else:
            # Default: src/startd8/workflows/builtin/
            output_dir = Path(__file__).parent / DEFAULT_OUTPUT_DIR

        if not output_dir.exists():
            return ScaffoldResult.fail(
                ERR_OUTPUT_DIR_NOT_FOUND.format(path=output_dir)
            )

        output_file = output_dir / f"{module_name}_workflow.py"

        # Check if file exists
        if output_file.exists() and not config.force:
            return ScaffoldResult.fail(
                ERR_FILE_EXISTS.format(path=output_file)
            )

        # Build template context
        context = TemplateContext(
            workflow_id=workflow_id,
            module_name=module_name,
            class_name=class_name,
            name=display_name,
            description=config.description,
            version=config.version,
            capabilities=config.capabilities,
            tags=config.tags,
        )

        # Render template
        try:
            content = self.loader.render(config.template, context)
        except FileNotFoundError as e:
            return ScaffoldResult.fail(str(e))
        except Exception as e:
            return ScaffoldResult.fail(f"Template rendering failed: {e}")

        # Write file
        try:
            output_file.write_text(content)
        except OSError as e:
            return ScaffoldResult.fail(f"Failed to write file: {e}")

        return ScaffoldResult.ok(
            file_path=output_file,
            workflow_id=workflow_id,
            class_name=class_name,
        )

    def list_templates(self) -> List[dict]:
        """
        List available templates with descriptions.

        Returns:
            List of dicts with 'name' and 'description' keys
        """
        templates = []
        for name in VALID_TEMPLATES:
            templates.append({
                "name": name,
                "description": TEMPLATE_DESCRIPTIONS.get(name, ""),
            })
        return templates

    # =========================================================================
    # Name conversion utilities
    # =========================================================================

    def _validate_name(self, name: str) -> None:
        """Validate workflow name format."""
        # Allow kebab-case, snake_case, or mixed
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', name):
            raise ValueError(ERR_INVALID_NAME.format(name=name))

    def _to_kebab_case(self, name: str) -> str:
        """Convert name to kebab-case (workflow-id format)."""
        self._validate_name(name)
        # Replace underscores with hyphens, lowercase
        return name.replace("_", "-").lower()

    def _to_snake_case(self, name: str) -> str:
        """Convert name to snake_case (module_name format)."""
        self._validate_name(name)
        # Replace hyphens with underscores, lowercase
        return name.replace("-", "_").lower()

    def _to_pascal_case(self, name: str) -> str:
        """Convert name to PascalCase (ClassName format)."""
        self._validate_name(name)
        # Split on hyphens and underscores, capitalize each part
        parts = re.split(r'[-_]', name)
        return "".join(part.capitalize() for part in parts)

    def _to_display_name(self, name: str) -> str:
        """Convert name to display name (Title Case with spaces)."""
        self._validate_name(name)
        # Split on hyphens and underscores, title case each part
        parts = re.split(r'[-_]', name)
        return " ".join(part.capitalize() for part in parts)


def scaffold_workflow(
    name: str,
    template: str = DEFAULT_TEMPLATE,
    output_dir: Optional[Path] = None,
    description: str = DEFAULT_DESCRIPTION,
    force: bool = False,
) -> ScaffoldResult:
    """
    Convenience function to scaffold a workflow.

    Args:
        name: Workflow name (kebab-case or snake_case)
        template: Template type (basic, pipeline, multi_agent, async)
        output_dir: Output directory (defaults to workflows/builtin/)
        description: Workflow description
        force: Overwrite existing files

    Returns:
        ScaffoldResult with success status and file path
    """
    scaffolder = WorkflowScaffolder()
    config = ScaffoldConfig(
        name=name,
        template=template,
        output_dir=output_dir,
        description=description,
        force=force,
    )
    return scaffolder.scaffold(config)
