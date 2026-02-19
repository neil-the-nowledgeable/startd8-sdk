"""
Preflight rules that contribute post-generation validator functions.

These rules use the ``validator_fns`` field of ``RuleContribution``
so that ``domain_checklist.py`` can discover them via the registry.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from typing import Optional

from ..domain_preflight_models import TaskDomain

from ._base import PYTHON_DOMAINS, PreflightRule, RuleContext, RuleContribution
from ._registry import preflight_rule


# ---------------------------------------------------------------------------
# Validator function implementations
# (signature: (code: str, enrichment) -> List[issue_dict])
# kept as module-level functions for clarity
# ---------------------------------------------------------------------------

# Pre-compiled patterns used by multiple validators (avoid per-call recompile)
_FENCE_PATTERN = re.compile(r"^(```\w*|~~~\w*)$", re.MULTILINE)


def _line_number(code: str, pos: int) -> int:
    """Return the 1-based line number for a character offset in *code*."""
    return code[:pos].count("\n") + 1

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

    # Always include stdlib — the constraint string may only list public names
    # for readability but all stdlib modules are always importable.
    if hasattr(sys, "stdlib_module_names"):
        importable |= sys.stdlib_module_names

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


# ---------------------------------------------------------------------------
# Merge damage detector
# ---------------------------------------------------------------------------

def _validate_merge_damage(code: str, enrichment) -> list:
    """Detect damage introduced by merging generated code into existing files.

    Checks for:
    1. Duplicate top-level function/class definitions (same name defined twice)
    2. Definition ordering violations (default_factory references before definition)
    """
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    # --- Check 1: Duplicate top-level definitions ---
    seen_names: dict = {}  # name -> first line number
    for node in ast.iter_child_nodes(tree):
        name = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
        elif isinstance(node, ast.ClassDef):
            name = node.name

        if name is not None:
            if name in seen_names:
                issues.append({
                    "validator": "merge_damage",
                    "message": (
                        f"Duplicate definition '{name}' "
                        f"(first at line {seen_names[name]}, again at line {node.lineno})"
                    ),
                    "line": node.lineno,
                })
            else:
                seen_names[name] = node.lineno

    # --- Check 2: Definition ordering (default_factory references) ---
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
                                "validator": "merge_damage",
                                "message": (
                                    f"'{ref_name}' used as default_factory but not defined "
                                    f"before class '{node.name}' (possible merge ordering damage)"
                                ),
                                "line": class_node.value.lineno,
                            })
            defined_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined_names.add(target.id)

    return issues


def _validate_relative_imports_valid(code: str, enrichment) -> list:
    """Validate that relative imports reference known sibling modules.

    For package-module domain: checks that relative imports target modules
    listed in the enrichment's ``available_siblings`` (via prompt_constraints).
    Different from ``no_relative_imports`` which flags ALL relative imports.
    """
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    # Extract available siblings from enrichment prompt_constraints
    siblings: set = set()
    for constraint in getattr(enrichment, "prompt_constraints", []):
        if isinstance(constraint, str) and "available_siblings" in constraint.lower():
            # Try to parse sibling names from the constraint text
            parts = constraint.split(":", 1)
            if len(parts) == 2:
                siblings = {n.strip().replace(".py", "") for n in parts[1].split(",") if n.strip()}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
            module_name = node.module or ""
            top_name = module_name.split(".")[0]
            if siblings and top_name and top_name not in siblings:
                issues.append({
                    "validator": "relative_imports_valid",
                    "message": (
                        f"Relative import from {'.' * node.level}{module_name} "
                        f"— module '{top_name}' not in known siblings"
                    ),
                    "line": node.lineno,
                })
    return issues


def _validate_no_circular_imports(code: str, enrichment) -> list:
    """Detect self-imports and obvious circular import patterns.

    Full graph-based circular detection is impractical in a single-file
    validator. Scoped to detecting imports that reference the file's own
    module name (self-import).
    """
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    # Collect top-level definitions, then flag relative imports that pull in
    # a name already defined in this file (likely self-import or circular).
    defined_names: set = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined_names.add(node.name)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.names:
            # Check if the import brings in names that are defined in this file
            for alias in node.names:
                imported_name = alias.name
                if imported_name in defined_names and node.level and node.level > 0:
                    issues.append({
                        "validator": "no_circular_imports",
                        "message": (
                            f"Possible circular import: '{imported_name}' is both "
                            f"defined locally and imported from {'.' * node.level}{node.module}"
                        ),
                        "line": node.lineno,
                    })
    return issues


def _validate_no_markdown_fences(code: str, enrichment) -> list:
    """Detect leftover markdown fence markers in generated code.

    LLMs sometimes leave ```python, ```, or ~~~ fence markers in output.
    """
    issues = []
    for match in _FENCE_PATTERN.finditer(code):
        issues.append({
            "validator": "no_markdown_fences",
            "message": f"Markdown fence marker found: {match.group()!r}",
            "line": _line_number(code, match.start()),
        })
    return issues


def _validate_test_naming(code: str, enrichment) -> list:
    """Check pytest naming conventions for test files.

    Flags:
    - Functions starting with ``test`` but not ``test_`` (e.g. ``testFoo``)
    - Classes containing test methods but not starting with ``Test``
    - Test functions with uppercase letters after ``test_``
    """
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            name = node.name
            # Functions starting with "test" but not "test_"
            if name.startswith("test") and not name.startswith("test_") and name != "test":
                issues.append({
                    "validator": "test_naming",
                    "message": (
                        f"Function '{name}' starts with 'test' but not 'test_' "
                        f"— pytest won't collect it"
                    ),
                    "line": node.lineno,
                })
        elif isinstance(node, ast.ClassDef):
            has_test_methods = any(
                isinstance(m, ast.FunctionDef) and m.name.startswith("test_")
                for m in node.body
            )
            if has_test_methods and not node.name.startswith("Test"):
                issues.append({
                    "validator": "test_naming",
                    "message": (
                        f"Class '{node.name}' contains test methods but doesn't "
                        f"start with 'Test' — pytest won't collect it"
                    ),
                    "line": node.lineno,
                })
    return issues


_SECRET_PATTERN = re.compile(
    r"""(?:api_key|apikey|password|passwd|secret|token|auth_token|access_token)"""
    r"""\s*=\s*['"](?!YOUR_|CHANGE_ME|TODO|xxx|placeholder)[^'"]{4,}['"]""",
    re.IGNORECASE,
)


def _validate_no_hardcoded_secrets(code: str, enrichment) -> list:
    """Detect common hardcoded secret patterns in generated code.

    Looks for assignments like ``api_key = "sk-abc123"`` where the value
    is a non-empty string literal (not a placeholder like ``"YOUR_KEY_HERE"``).
    """
    issues = []
    for match in _SECRET_PATTERN.finditer(code):
        snippet = match.group()
        if len(snippet) > 60:
            snippet = snippet[:57] + "..."
        issues.append({
            "validator": "no_hardcoded_secrets",
            "message": f"Possible hardcoded secret: {snippet}",
            "line": _line_number(code, match.start()),
        })
    return issues


def _validate_no_substring_tag_matching(code: str, enrichment) -> list:
    """Detect ``x in tags`` patterns that should use ``== tag`` for exact match.

    Uses AST to find ``ast.Compare`` nodes with ``In`` operator where the
    right-hand side is a name containing 'tag' or 'capabilit'.
    """
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for op, comparator in zip(node.ops, node.comparators):
            if not isinstance(op, ast.In):
                continue
            # Check if the right-hand side name suggests a tag/capability collection
            rhs_name = ""
            if isinstance(comparator, ast.Name):
                rhs_name = comparator.id
            elif isinstance(comparator, ast.Attribute):
                rhs_name = comparator.attr
            rhs_lower = rhs_name.lower()
            if "tag" in rhs_lower or "capabilit" in rhs_lower:
                issues.append({
                    "validator": "no_substring_tag_matching",
                    "message": (
                        f"Substring match 'x in {rhs_name}' — "
                        f"use '==' for exact tag matching"
                    ),
                    "line": node.lineno,
                })
    return issues


@preflight_rule(domains=PYTHON_DOMAINS, priority=200)
class MergeDamageDetectorRule(PreflightRule):
    """Detect merge damage: duplicates and ordering violations after merge.

    Runs at priority 200 (late) so it executes after merge strategies
    have combined generated code with existing file content.
    """

    rule_id = "merge_damage_detector"
    _validator_fns = {"merge_damage": _validate_merge_damage}

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        return RuleContribution(
            validator_fns={"merge_damage": _validate_merge_damage},
        )


# ---------------------------------------------------------------------------
# run_validator() dispatcher — entry point for subprocess invocation
# ---------------------------------------------------------------------------

# Map every enrichment validator name to its implementation function.
_VALIDATORS = {
    "no_relative_imports": _validate_no_relative_imports,
    "deps_available": _validate_deps_available,
    "definition_ordering": _validate_definition_ordering,
    "merge_damage": _validate_merge_damage,
    "relative_imports_valid": _validate_relative_imports_valid,
    "no_circular_imports": _validate_no_circular_imports,
    "no_markdown_fences": _validate_no_markdown_fences,
    "test_naming": _validate_test_naming,
    "no_hardcoded_secrets": _validate_no_hardcoded_secrets,
    "no_substring_tag_matching": _validate_no_substring_tag_matching,
}


class _StubEnrichment:
    """Minimal enrichment stub for subprocess context.

    The subprocess has no access to the full enrichment object, so
    validators that depend on enrichment data (like ``deps_available``
    needing the "Only import from:" constraint) will gracefully return
    empty issues.
    """

    prompt_constraints: tuple = ()


def run_validator(name: str, file_paths: list) -> None:
    """Entry point for subprocess-invoked post-generation validation.

    Called by ``_resolve_validator_command()`` in ``context_seed_handlers.py``.
    Reads each file, runs the named validator, prints issues as JSON,
    and exits with code 1 if any issues found (code 0 = clean).
    """
    if name not in _VALIDATORS:
        msg = f"Unknown validator: {name!r}. Known: {sorted(_VALIDATORS)}"
        # When invoked as a subprocess, print a clean error to stderr
        # instead of dumping a traceback.
        print(msg, file=sys.stderr)
        raise ValueError(msg)

    validator_fn = _VALIDATORS[name]
    stub = _StubEnrichment()
    all_issues = []

    for fpath in file_paths:
        try:
            with open(fpath, encoding="utf-8") as f:
                code = f.read()
        except OSError as exc:
            all_issues.append({
                "validator": name,
                "message": f"Cannot read file: {exc}",
                "line": 0,
                "file": fpath,
            })
            continue

        issues = validator_fn(code, stub)
        for issue in issues:
            issue["file"] = fpath
        all_issues.extend(issues)

    if all_issues:
        print(json.dumps(all_issues, indent=2))
        sys.exit(1)
    sys.exit(0)
