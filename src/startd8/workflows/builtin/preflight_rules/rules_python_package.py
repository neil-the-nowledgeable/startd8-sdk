"""
Preflight rules for the PYTHON_PACKAGE_MODULE domain.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..domain_preflight_models import CheckStatus, EnvironmentCheck, TaskDomain

from ._base import PreflightRule, RuleContext, RuleContribution
from ._helpers import (
    file_has_pattern,
    parse_relative_imports,
    scan_optional_dep_guards,
)
from ._registry import preflight_rule

_PKG = frozenset({TaskDomain.PYTHON_PACKAGE_MODULE})


@preflight_rule(domains=_PKG, priority=50)
class InitPyExistsRule(PreflightRule):
    """Check that __init__.py exists in the target directory."""

    rule_id = "init_py_exists"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        init_path = ctx.target_dir / "__init__.py"
        if init_path.exists():
            check = EnvironmentCheck(
                check_name="init_py_exists",
                status=CheckStatus.PASS,
                message="__init__.py exists in target directory",
            )
        else:
            check = EnvironmentCheck(
                check_name="init_py_exists",
                status=CheckStatus.FAIL,
                message="Missing __init__.py in target directory",
                detail=f"Expected at: {init_path}",
            )
        return RuleContribution(checks=[check])


@preflight_rule(domains=_PKG, priority=55)
class ParentPackageImportableRule(PreflightRule):
    """Check that the parent package is importable."""

    rule_id = "parent_package_importable"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        parent_init = ctx.target_dir.parent / "__init__.py"
        if ctx.target_dir.parent == ctx.project_root or parent_init.exists():
            check = EnvironmentCheck(
                check_name="parent_package_importable",
                status=CheckStatus.PASS,
                message="Parent package is importable",
            )
        else:
            check = EnvironmentCheck(
                check_name="parent_package_importable",
                status=CheckStatus.WARN,
                message="Parent package may not be importable (no __init__.py)",
                detail=str(ctx.target_dir.parent),
            )
        return RuleContribution(checks=[check])


@preflight_rule(domains=_PKG, priority=60)
class CircularImportsRule(PreflightRule):
    """Detect potential circular imports between siblings."""

    rule_id = "circular_imports"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        if not ctx.target_dir.is_dir():
            return None

        target_stem = Path(ctx.target_file).stem
        siblings_importing_target = []
        for sibling in ctx.target_dir.iterdir():
            if (
                sibling.suffix == ".py"
                and sibling.stem != target_stem
                and sibling.name != "__init__.py"
            ):
                rel_imports = parse_relative_imports(sibling)
                if target_stem in rel_imports:
                    siblings_importing_target.append(sibling.stem)

        if not (ctx.target_path.exists() and siblings_importing_target):
            return None

        target_imports = parse_relative_imports(ctx.target_path)
        cycles = [s for s in siblings_importing_target if s in target_imports]
        if not cycles:
            return None

        return RuleContribution(checks=[EnvironmentCheck(
            check_name="circular_imports",
            status=CheckStatus.WARN,
            message=f"Potential circular imports with: {', '.join(cycles)}",
            detail="Both files import each other via relative imports",
        )])


@preflight_rule(domains=_PKG, priority=65)
class OptionalDepGuardsPackageRule(PreflightRule):
    """Detect optional imports not in project deps (package module)."""

    rule_id = "optional_dep_guards_package"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        if not ctx.target_path.exists():
            return None

        guards = scan_optional_dep_guards(ctx.target_path)
        unguarded = [
            g for g in guards if g not in ctx.available_deps.all_importable
        ]
        if not unguarded:
            return None

        return RuleContribution(checks=[EnvironmentCheck(
            check_name="optional_dep_guards",
            status=CheckStatus.WARN,
            message=f"Optional imports not in project deps: {', '.join(unguarded)}",
            detail="These imports are guarded by try/except but not declared in pyproject.toml",
        )])


@preflight_rule(domains=_PKG, priority=70)
class PydanticPropertyConfusionRule(PreflightRule):
    """Warn about @property in siblings that could be confused with Pydantic kwargs."""

    rule_id = "pydantic_property_confusion"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        if not ctx.target_dir.is_dir():
            return None

        target_name = Path(ctx.target_file).name
        siblings = [
            f.stem for f in ctx.target_dir.iterdir()
            if f.suffix == ".py"
            and f.name != target_name
            and f.name != "__init__.py"
        ]

        for sib_name in sorted(siblings):
            sib_path = ctx.target_dir / f"{sib_name}.py"
            if file_has_pattern(sib_path, r"@property"):
                return RuleContribution(constraints=[
                    f"Sibling '{sib_name}' uses @property \u2014 do not "
                    f"confuse Pydantic model constructor kwargs with "
                    f"computed properties"
                ])
        return None


@preflight_rule(domains=_PKG, priority=100)
class PackageModuleConstraintsRule(PreflightRule):
    """Inject prompt constraints and validators for package-module domain."""

    rule_id = "package_module_constraints"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        parts = Path(ctx.target_file).parts
        package_name = parts[-2] if len(parts) >= 2 else "unknown"

        # Collect siblings
        siblings: List[str] = []
        if ctx.target_dir.is_dir():
            target_name = Path(ctx.target_file).name
            siblings = sorted([
                f.stem for f in ctx.target_dir.iterdir()
                if f.suffix == ".py"
                and f.name != target_name
                and f.name != "__init__.py"
            ])

        sibling_list = ", ".join(siblings[:20]) or "(none)"
        return RuleContribution(
            constraints=[
                f"This file is part of the {package_name} package",
                f"Use relative imports for siblings: {sibling_list}",
                "Use absolute imports for SDK modules",
            ],
            validators=[
                "relative_imports_valid",
                "deps_available",
                "no_circular_imports",
                "no_markdown_fences",
            ],
        )
