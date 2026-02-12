"""
Preflight rules for the PYTHON_SINGLE_MODULE domain.
"""

from __future__ import annotations

from typing import Optional

from ..domain_preflight_models import CheckStatus, EnvironmentCheck, TaskDomain

from ._base import PreflightRule, RuleContext, RuleContribution
from ._helpers import scan_optional_dep_guards
from ._registry import preflight_rule

_SINGLE = frozenset({TaskDomain.PYTHON_SINGLE_MODULE})


@preflight_rule(domains=_SINGLE, priority=50)
class NotInPackageRule(PreflightRule):
    """Verify target is NOT inside a package (__init__.py check)."""

    rule_id = "not_in_package"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        init_path = ctx.target_dir / "__init__.py"
        if init_path.exists():
            check = EnvironmentCheck(
                check_name="not_in_package",
                status=CheckStatus.WARN,
                message="Target dir has __init__.py \u2014 may need package-module treatment",
                detail=str(init_path),
            )
        else:
            check = EnvironmentCheck(
                check_name="not_in_package",
                status=CheckStatus.PASS,
                message="Target is not inside a Python package (no __init__.py)",
            )
        return RuleContribution(checks=[check])


@preflight_rule(domains=_SINGLE, priority=60)
class OptionalDepGuardsSingleRule(PreflightRule):
    """Detect optional imports not declared in pyproject.toml (single module)."""

    rule_id = "optional_dep_guards_single"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        if not ctx.target_path.exists():
            return None

        guards = scan_optional_dep_guards(ctx.target_path)
        unguarded = [
            g for g in guards if g not in ctx.available_deps.all_importable
        ]

        contrib = RuleContribution()
        if unguarded:
            contrib.checks.append(EnvironmentCheck(
                check_name="optional_dep_guards",
                status=CheckStatus.WARN,
                message=f"Optional imports not in project deps: {', '.join(unguarded)}",
                detail="These imports are guarded by try/except but not declared in pyproject.toml",
            ))

        # Constraint: preserve existing guards
        if guards:
            contrib.constraints.append(
                f"Existing optional dependency guards (try/except ImportError): "
                f"{', '.join(guards)} \u2014 preserve these patterns"
            )

        return contrib if (contrib.checks or contrib.constraints) else None


@preflight_rule(domains=_SINGLE, priority=100)
class SingleModuleConstraintsRule(PreflightRule):
    """Inject prompt constraints and validators for single-module domain."""

    rule_id = "single_module_constraints"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        all_importable = ctx.available_deps.all_importable
        # For the LLM prompt hint, show only public module names (skip _-prefixed
        # internal modules) to keep the constraint readable while covering the
        # names the generated code is likely to use.
        public = sorted(n for n in all_importable if not n.startswith("_"))
        return RuleContribution(
            constraints=[
                "Output a single Python module -- not a package",
                "Do not use relative imports (from .module import ...)",
                f"Only import from: {', '.join(public)}",
                "Define utility functions before classes that reference them",
            ],
            validators=[
                "no_relative_imports",
                "deps_available",
                "definition_ordering",
                "no_markdown_fences",
                "merge_damage",
            ],
        )
