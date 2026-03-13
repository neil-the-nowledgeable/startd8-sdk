"""Contract violation repair step (Phase 3.1).

Fixes forward manifest contract violations detected during assembly or splice:

1. Signature mismatches — parameter count, names, return annotation
2. Missing base classes — adds missing base classes to class definitions
3. Wrong return type annotations — corrects return type in function signature
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ContractViolationDiagnostic, ElementContext, RepairContext, RepairStepResult

logger = get_logger(__name__)


class ContractViolationFixStep:
    """Fix forward manifest contract violations in generated code."""

    name: str = "contract_violation_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        modified_code = code
        fixes: list[str] = []

        # Extract contract violation diagnostics from context
        violations = [
            d for d in context.diagnostics
            if isinstance(d, ContractViolationDiagnostic)
        ]

        if not violations:
            return RepairStepResult(
                step_name=self.name,
                modified=False,
                code=code,
                metrics={"fixes": []},
            )

        for v in violations:
            if v.violation_type == "missing_base_class":
                modified_code, fix = _fix_missing_base_class(
                    modified_code, v.element_name, v.expected,
                )
                if fix:
                    fixes.append(fix)

            elif v.violation_type == "wrong_return_type":
                modified_code, fix = _fix_return_annotation(
                    modified_code, v.element_name, v.expected,
                )
                if fix:
                    fixes.append(fix)

            elif v.violation_type == "missing_parameter":
                modified_code, fix = _fix_missing_parameter(
                    modified_code, v.element_name, v.expected,
                )
                if fix:
                    fixes.append(fix)

        modified = modified_code != code
        if modified:
            logger.info(
                "contract_violation_fix applied %d fix(es) to %s: %s",
                len(fixes), file_path.name, "; ".join(fixes),
            )

        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code=modified_code,
            metrics={"fixes": fixes, "violations_seen": len(violations)},
        )


def _fix_missing_base_class(
    code: str, class_name: str, expected_base: str,
) -> tuple[str, str]:
    """Add a missing base class to a class definition.

    Handles both ``class Foo:`` and ``class Foo(ExistingBase):`` forms.
    """
    if not class_name or not expected_base:
        return code, ""

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, ""

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue

        # Check if base already present
        existing_bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                existing_bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                existing_bases.append(ast.dump(base))

        if expected_base in existing_bases:
            return code, ""

        # Find and modify the class line
        lines = code.splitlines(keepends=True)
        line_idx = node.lineno - 1
        if line_idx >= len(lines):
            return code, ""

        line = lines[line_idx]
        # Pattern: class Name: or class Name(bases):
        no_bases = re.match(
            r"(\s*class\s+" + re.escape(class_name) + r"\s*)(\s*:)",
            line,
        )
        if no_bases:
            lines[line_idx] = no_bases.group(1) + f"({expected_base}):\n"
            return "".join(lines), f"added base class {expected_base} to {class_name}"

        with_bases = re.match(
            r"(\s*class\s+" + re.escape(class_name) + r"\s*\()([^)]*)\)",
            line,
        )
        if with_bases:
            existing = with_bases.group(2).strip()
            if existing:
                new_bases = f"{existing}, {expected_base}"
            else:
                new_bases = expected_base
            lines[line_idx] = with_bases.group(1) + new_bases + "):\n"
            return "".join(lines), f"added base class {expected_base} to {class_name}"

    return code, ""


def _fix_return_annotation(
    code: str, func_name: str, expected_return: str,
) -> tuple[str, str]:
    """Fix or add return type annotation on a function."""
    if not func_name or not expected_return:
        return code, ""

    lines = code.splitlines(keepends=True)
    # Find the def line
    pattern = re.compile(
        r"(\s*(?:async\s+)?def\s+" + re.escape(func_name) + r"\s*\([^)]*\))"
        r"(\s*(?:->\s*\S+)?)(\s*:)"
    )
    for i, line in enumerate(lines):
        m = pattern.match(line)
        if m:
            lines[i] = m.group(1) + f" -> {expected_return}" + m.group(3) + "\n"
            return "".join(lines), f"fixed return type of {func_name} → {expected_return}"

    return code, ""


def _fix_missing_parameter(
    code: str, func_name: str, expected_param: str,
) -> tuple[str, str]:
    """Add a missing parameter to a function signature."""
    if not func_name or not expected_param:
        return code, ""

    lines = code.splitlines(keepends=True)
    pattern = re.compile(
        r"(\s*(?:async\s+)?def\s+" + re.escape(func_name) + r"\s*\()([^)]*)\)"
    )
    for i, line in enumerate(lines):
        m = pattern.match(line)
        if m:
            existing_params = m.group(2).strip()
            # Check if param already exists
            if expected_param.split(":")[0].strip() in existing_params:
                return code, ""
            if existing_params:
                new_params = f"{existing_params}, {expected_param}"
            else:
                new_params = expected_param
            rest = line[m.end():]
            lines[i] = m.group(1) + new_params + ")" + rest
            return "".join(lines), f"added parameter {expected_param} to {func_name}"

    return code, ""
