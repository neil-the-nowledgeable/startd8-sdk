"""Semantic import path repair step (REQ-SR-200).

Fixes ``import_resolution`` errors where generated code uses package-style
imports (``from emailservice.email_server import X``) in projects with flat
module layout (no ``__init__.py``).

Two rewrite patterns:
- ``from <pkg>.<module> import <names>`` → ``from <module> import <names>``
- ``from <pkg> import <module>`` → ``import <module>``

Only applied when:
1. The first segment of the import path is a sibling directory on disk
2. That directory has flat layout (no ``__init__.py``)
3. The rewrite is not ambiguous (target module doesn't exist in both
   the importing file's directory and the target directory)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, RepairContext, RepairStepResult, SemanticDiagnostic

logger = get_logger(__name__)


def _detect_layout(service_dir: Path) -> str:
    """Detect flat vs package layout for a service directory."""
    if (service_dir / "__init__.py").exists():
        return "package"
    return "flat"


class SemanticImportFixStep:
    """Fix local namespace-as-package imports for flat-layout projects."""

    name: str = "semantic_import_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        diagnostics = [
            d for d in context.diagnostics
            if isinstance(d, SemanticDiagnostic)
            and d.semantic_category == "import_resolution"
        ]
        if not diagnostics:
            return RepairStepResult(step_name=self.name, modified=False, code=code)

        project_root = context.project_root or file_path.parent
        lines = code.splitlines(keepends=True)
        fixes: list[str] = []

        for diag in diagnostics:
            symbol = diag.symbol  # e.g., "emailservice.email_server" or "emailservice"
            parts = symbol.split(".")

            service_dir_name = parts[0]
            service_dir = project_root / service_dir_name

            # Only repair if it's a known sibling directory with flat layout
            if not service_dir.is_dir():
                continue
            if _detect_layout(service_dir) != "flat":
                continue

            target_line_idx = diag.line - 1
            if target_line_idx < 0 or target_line_idx >= len(lines):
                continue

            line = lines[target_line_idx]

            # Case 1: from <pkg>.<module> import <names>  (multi-segment symbol)
            if len(parts) >= 2:
                module_path = ".".join(parts[1:])  # "email_server" or "logger"

                # Guard: skip ambiguous cross-service imports
                importing_dir = file_path.parent
                module_base = module_path.split(".")[0]
                if (
                    importing_dir / f"{module_base}.py"
                ).exists() and service_dir.resolve() != importing_dir.resolve():
                    logger.warning(
                        "Ambiguous cross-service import: %s exists in both %s and %s — skipping repair",
                        module_base, importing_dir.name, service_dir_name,
                    )
                    continue

                pattern_from = re.compile(
                    r"^(\s*from\s+)" + re.escape(symbol) + r"(\s+import\s+.+)$"
                )
                m = pattern_from.match(line)
                if m:
                    new_line = f"{m.group(1)}{module_path}{m.group(2)}"
                    if not new_line.endswith("\n") and line.endswith("\n"):
                        new_line += "\n"
                    lines[target_line_idx] = new_line
                    fixes.append(f"from {symbol} → from {module_path}")
                    continue

            # Case 2: from <pkg> import <module>  (single-segment symbol = package name)
            pattern_bare = re.compile(
                r"^(\s*)from\s+" + re.escape(service_dir_name)
                + r"\s+import\s+(\w+)(.*)$"
            )
            m = pattern_bare.match(line)
            if m:
                indent = m.group(1)
                imported_name = m.group(2)
                rest = m.group(3)
                new_line = f"{indent}import {imported_name}{rest}"
                if not new_line.endswith("\n") and line.endswith("\n"):
                    new_line += "\n"
                lines[target_line_idx] = new_line
                fixes.append(f"from {service_dir_name} import {imported_name} → import {imported_name}")
                continue

        modified = len(fixes) > 0
        if modified:
            logger.info(
                "semantic_import_fix applied %d fix(es) to %s: %s",
                len(fixes), file_path.name, "; ".join(fixes),
            )

        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code="".join(lines),
            metrics={"fixes": fixes},
        )
