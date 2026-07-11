# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""
Project Scaffolder implementation for hybrid manifest tracking.
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from rich.console import Console

from startd8.workflows.templates import check_jinja2_available, TemplateLoader, TemplateContext

from .scaffold_constants import (
    DEFAULT_TEMPLATE,
    TEMPLATE_DIR,
    ERR_TEMPLATE_NOT_FOUND,
    MSG_PROJECT_CREATED,
    MSG_FILE_OVERWRITTEN,
    MSG_FILE_SKIPPED,
    MSG_FILE_FORCED,
    MSG_MANIFEST_UPDATED,
    ERR_INVALID_NAME,
    ERR_INVALID_OUTPUT_DIR,
    SCAFFOLD_MANIFEST_FILE,
)
from .manifest import ProjectScaffoldManifest

console = Console()

def get_file_hash(path: Path) -> str:
    """Calculate SHA-256 hash of a file's contents."""
    if not path.exists():
        return ""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

@dataclass
class ProjectScaffoldConfig:
    """Configuration for project scaffolding."""
    name: str
    template: str = DEFAULT_TEMPLATE
    output_dir: Optional[Path] = None
    force: bool = False
    context_overrides: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectScaffoldResult:
    """Result of a scaffold operation."""
    success: bool
    output_dir: Optional[Path] = None
    files_created: int = 0
    files_updated: int = 0
    files_skipped: int = 0
    error: Optional[str] = None

    @classmethod
    def ok(cls, output_dir: Path, created: int, updated: int, skipped: int) -> "ProjectScaffoldResult":
        return cls(
            success=True,
            output_dir=output_dir,
            files_created=created,
            files_updated=updated,
            files_skipped=skipped,
        )

    @classmethod
    def fail(cls, error: str) -> "ProjectScaffoldResult":
        return cls(success=False, error=error)


class ProjectScaffolder:
    """Generates project directory structures with manifest tracking."""

    def __init__(self):
        self._loader: Optional[TemplateLoader] = None

    @property
    def loader(self) -> TemplateLoader:
        """Lazy-load the jinja2 template loader."""
        if self._loader is None:
            self._loader = TemplateLoader(str(TEMPLATE_DIR))
        return self._loader

    def _validate_name(self, name: str) -> None:
        """Validate project name format."""
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', name):
            raise ValueError(ERR_INVALID_NAME.format(name=name))

    def _resolve_template_path(self, template_name: str) -> Path:
        """Resolve a template name to an absolute directory path."""
        target = TEMPLATE_DIR / template_name
        if not target.is_dir():
            raise FileNotFoundError(ERR_TEMPLATE_NOT_FOUND.format(
                template=template_name,
                templates_dir=TEMPLATE_DIR
            ))
        return target

    def _render_path(self, path_str: str, context: Dict[str, Any]) -> str:
        """Render a file or directory path string using basic substitutions."""
        # Simple string replacement for path templating since we can't easily 
        # use jinja to evaluate just the path string without compiling it.
        # We handle typical substitutions directly:
        result = path_str
        for k, v in context.items():
            if isinstance(v, str):
                result = result.replace(f"{{{{{k}}}}}", v)
        return result

    def scaffold(self, config: ProjectScaffoldConfig) -> ProjectScaffoldResult:
        """Scaffold a project template with manifest-based update safe-guards."""
        if not check_jinja2_available():
            return ProjectScaffoldResult.fail("Jinja2 represents a required dependency for the ProjectScaffolder.")

        try:
            self._validate_name(config.name)
            template_path = self._resolve_template_path(config.template)
        except (ValueError, FileNotFoundError) as e:
            return ProjectScaffoldResult.fail(str(e))

        output_dir = config.output_dir or Path.cwd() / config.name
        
        # Check folder sanity
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / SCAFFOLD_MANIFEST_FILE
        if any(output_dir.iterdir()) and not manifest_path.exists():
            # Directory not empty, and no manifest exists
            return ProjectScaffoldResult.fail(ERR_INVALID_OUTPUT_DIR)

        # Load or create manifest
        manifest = ProjectScaffoldManifest.load(output_dir)
        if manifest is None:
            manifest = ProjectScaffoldManifest(template=config.template)

        # Construct context
        module_name = config.name.replace("-", "_").lower()
        context_data = {
            "project_name": config.name,
            "module_name": module_name,
            **config.context_overrides
        }
        
        # Update manifest context 
        manifest.context.update(context_data)
        
        # Prepare jinja env context variables
        jinja_ctx = manifest.context

        files_created = 0
        files_updated = 0
        files_skipped = 0

        # Walk the template directory
        for item in template_path.rglob("*"):
            if not item.is_file():
                continue

            # Calculate relative path from template root
            rel_path = item.relative_to(template_path)
            
            # Resolve templated path names (e.g. src/{{module_name}}/__init__.py)
            resolved_rel_path = Path(self._render_path(str(rel_path), manifest.context))
            is_jinja = resolved_rel_path.suffix == ".jinja"
            
            if is_jinja:
                resolved_rel_path = resolved_rel_path.with_suffix("")
                
            dest_path = output_dir / resolved_rel_path
            rel_dest_str = str(resolved_rel_path)
            
            # Render or copy content
            try:
                if is_jinja:
                    # Use environment to load from file (TemplateLoader expects relative to TEMPLATE_DIR)
                    rel_to_templates = item.relative_to(TEMPLATE_DIR)
                    # We bypass loader.render because it requires TemplateContext, and use raw jinja template
                    template = self.loader._env.get_template(str(rel_to_templates))
                    content = template.render(**jinja_ctx)
                    content_bytes = content.encode("utf-8")
                else:
                    content_bytes = item.read_bytes()
            except Exception as e:
                return ProjectScaffoldResult.fail(f"Failed to render {rel_path}: {e}")

            # Compute new hash
            new_hash = hashlib.sha256(content_bytes).hexdigest()

            # Handle safe overwriting
            if dest_path.exists():
                current_hash = get_file_hash(dest_path)
                original_hash = manifest.file_hashes.get(rel_dest_str)

                if config.force:
                    # Forced overwrite
                    dest_path.write_bytes(content_bytes)
                    manifest.file_hashes[rel_dest_str] = new_hash
                    files_updated += 1
                    console.print(MSG_FILE_FORCED.format(path=rel_dest_str), style="yellow")
                    continue
                elif original_hash and current_hash != original_hash:
                    # File was modified by LLM/user since last scaffold
                    files_skipped += 1
                    console.print(MSG_FILE_SKIPPED.format(path=rel_dest_str), style="yellow")
                    continue
                elif current_hash == new_hash:
                    # No changes needed
                    continue
                else:
                    # File exists, hash matches original (unmodified), template updated
                    dest_path.write_bytes(content_bytes)
                    manifest.file_hashes[rel_dest_str] = new_hash
                    files_updated += 1
                    console.print(MSG_FILE_OVERWRITTEN.format(path=rel_dest_str), style="green")
            else:
                # File is new
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_bytes(content_bytes)
                manifest.file_hashes[rel_dest_str] = new_hash
                files_created += 1

        # Save state
        manifest.save(output_dir)
        console.print(MSG_MANIFEST_UPDATED.format(path=output_dir / SCAFFOLD_MANIFEST_FILE), style="blue")
        console.print(MSG_PROJECT_CREATED.format(name=config.name), style="green bold")

        return ProjectScaffoldResult.ok(
            output_dir=output_dir,
            created=files_created,
            updated=files_updated,
            skipped=files_skipped
        )

def scaffold_project(name: str, template: str = DEFAULT_TEMPLATE, output_dir: Optional[Path] = None, force: bool = False) -> ProjectScaffoldResult:
    """Convenience functional interface."""
    scaffolder = ProjectScaffolder()
    config = ProjectScaffoldConfig(name=name, template=template, output_dir=output_dir, force=force)
    return scaffolder.scaffold(config)
