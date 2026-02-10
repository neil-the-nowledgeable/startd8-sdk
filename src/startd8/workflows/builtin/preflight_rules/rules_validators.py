"""
Preflight rules that contribute post-generation validator functions.

These rules use the ``validator_fns`` field of ``RuleContribution``
so that ``domain_checklist.py`` can discover them via the registry.
"""

from __future__ import annotations

import ast
from typing import Optional

from ..domain_preflight_models import TaskDomain

from ._base import PreflightRule, RuleContext, RuleContribution
from ._registry import preflight_rule


# ---------------------------------------------------------------------------
# Validator function implementations
# (signature: (code: str, enrichment) -> List[issue_dict])
# kept as module-level functions for clarity
# ---------------------------------------------------------------------------

def _validate_no_relative_imports(code: str, enrichment) -> list:
    """Flag relative imports in single-module domain."""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
            issues.append({
                "validator": "no_relative_imports",
                "message": f"Relative import found: from {'.' * node.level}{node.module or ''} import ...",
                "line": node.lineno,
            })
    return issues


def _validate_deps_available(code: str, enrichment) -> list:
    """Check that imported top-level packages are in available deps."""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    importable = None
    for constraint in getattr(enrichment, "prompt_constraints", []):
        if constraint.startswith("Only import from:"):
            names_str = constraint.split(":", 1)[1].strip()
            importable = {n.strip() for n in names_str.split(",") if n.strip()}
            break

    if importable is None:
        return issues

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in importable:
                    issues.append({
                        "validator": "deps_available",
                        "message": f"Import '{alias.name}' \u2014 top-level '{top}' not in available deps",
                        "line": node.lineno,
                    })
        elif isinstance(node, ast.ImportFrom) and node.module and (not node.level or node.level == 0):
            top = node.module.split(".")[0]
            if top not in importable:
                issues.append({
                    "validator": "deps_available",
                    "message": f"Import from '{node.module}' \u2014 top-level '{top}' not in available deps",
                    "line": node.lineno,
                })
    return issues


def _validate_definition_ordering(code: str, enrichment) -> list:
    """Ensure names used in Field(default_factory=X) are defined before the class."""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    defined_names: set = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined_names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            for class_node in ast.walk(node):
                if isinstance(class_node, ast.keyword) and class_node.arg == "default_factory":
                    if isinstance(class_node.value, ast.Name):
                        ref_name = class_node.value.id
                        if ref_name not in defined_names:
                            issues.append({
                                "validator": "definition_ordering",
                                "message": f"'{ref_name}' used as default_factory but not defined before class '{node.name}'",
                                "line": class_node.value.lineno,
                            })
            defined_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined_names.add(target.id)

    return issues


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

_SINGLE = frozenset({TaskDomain.PYTHON_SINGLE_MODULE})


@preflight_rule(domains=_SINGLE, priority=150)
class NoRelativeImportsValidatorRule(PreflightRule):
    """Contribute the ``no_relative_imports`` validator function."""

    rule_id = "no_relative_imports_validator"
    _validator_fns = {"no_relative_imports": _validate_no_relative_imports}

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        return RuleContribution(
            validator_fns={"no_relative_imports": _validate_no_relative_imports},
        )


@preflight_rule(domains=_SINGLE, priority=150)
class DepsAvailableValidatorRule(PreflightRule):
    """Contribute the ``deps_available`` validator function."""

    rule_id = "deps_available_validator"
    _validator_fns = {"deps_available": _validate_deps_available}

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        return RuleContribution(
            validator_fns={"deps_available": _validate_deps_available},
        )


@preflight_rule(domains=_SINGLE, priority=150)
class DefinitionOrderingValidatorRule(PreflightRule):
    """Contribute the ``definition_ordering`` validator function."""

    rule_id = "definition_ordering_validator"
    _validator_fns = {"definition_ordering": _validate_definition_ordering}

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        return RuleContribution(
            validator_fns={"definition_ordering": _validate_definition_ordering},
        )
