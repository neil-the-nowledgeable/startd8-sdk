"""
Preflight rules for the PYTHON_TEST domain.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from ..domain_preflight_models import CheckStatus, EnvironmentCheck, TaskDomain

from ._base import PreflightRule, RuleContext, RuleContribution
from ._helpers import file_has_pattern, scan_patch_paths
from ._registry import preflight_rule

_TEST = frozenset({TaskDomain.PYTHON_TEST})


@preflight_rule(domains=_TEST, priority=50)
class SourceModuleExistsRule(PreflightRule):
    """Check that the source module under test exists in src/."""

    rule_id = "source_module_exists"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        test_name = Path(ctx.target_file).stem
        if not test_name.startswith("test_"):
            return None

        source_name = test_name[5:]
        src_dir = ctx.project_root / "src"
        if not src_dir.is_dir():
            return None

        for match in src_dir.rglob(f"{source_name}.py"):
            return RuleContribution(checks=[EnvironmentCheck(
                check_name="source_module_exists",
                status=CheckStatus.PASS,
                message=f"Source module found: {match.relative_to(ctx.project_root)}",
            )])

        return RuleContribution(checks=[EnvironmentCheck(
            check_name="source_module_exists",
            status=CheckStatus.WARN,
            message=f"Source module '{source_name}.py' not found in src/",
            detail="May be a new module being created in this batch",
        )])


@preflight_rule(domains=_TEST, priority=55)
class TestDirExistsRule(PreflightRule):
    """Check that the test directory exists."""

    rule_id = "test_dir_exists"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        if ctx.target_dir.exists():
            check = EnvironmentCheck(
                check_name="test_dir_exists",
                status=CheckStatus.PASS,
                message=f"Test directory exists: {ctx.target_dir}",
            )
        else:
            check = EnvironmentCheck(
                check_name="test_dir_exists",
                status=CheckStatus.WARN,
                message=f"Test directory does not exist: {ctx.target_dir}",
            )
        return RuleContribution(checks=[check])


@preflight_rule(domains=_TEST, priority=60)
class ConftestScannableRule(PreflightRule):
    """Check for conftest.py in test directory."""

    rule_id = "conftest_scannable"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        conftest = ctx.target_dir / "conftest.py"
        if conftest.exists():
            check = EnvironmentCheck(
                check_name="conftest_scannable",
                status=CheckStatus.PASS,
                message="conftest.py found in test directory",
            )
        else:
            check = EnvironmentCheck(
                check_name="conftest_scannable",
                status=CheckStatus.SKIP,
                message="No conftest.py in test directory",
            )
        return RuleContribution(checks=[check])


@preflight_rule(domains=_TEST, priority=65)
class PatchPathValidRule(PreflightRule):
    """Detect stale mock.patch targets."""

    rule_id = "patch_path_valid"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        if not ctx.target_path.exists():
            return None

        patch_paths = scan_patch_paths(ctx.target_path)
        contrib = RuleContribution()
        for pp in patch_paths:
            parts = pp.split(".")
            if len(parts) >= 2:
                candidate = ctx.project_root / "src" / Path(*parts[:-1]).with_suffix(".py")
                if not candidate.exists():
                    candidate2 = ctx.project_root / Path(*parts[:-1]).with_suffix(".py")
                    if not candidate2.exists():
                        contrib.checks.append(EnvironmentCheck(
                            check_name="patch_path_valid",
                            status=CheckStatus.WARN,
                            message=f"mock.patch target may be stale: {pp}",
                            detail=f"Could not find module at {candidate}",
                        ))

        # Constraint: existing patch targets
        if patch_paths:
            contrib.constraints.append(
                f"Existing mock.patch targets: {', '.join(patch_paths[:10])} \u2014 "
                f"verify these paths still resolve after code changes"
            )

        return contrib if (contrib.checks or contrib.constraints) else None


@preflight_rule(domains=_TEST, priority=70)
class ThreadAwareTeardownRule(PreflightRule):
    """Detect when source module uses threading."""

    rule_id = "thread_aware_teardown"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        test_name = Path(ctx.target_file).stem
        if not test_name.startswith("test_"):
            return None

        source_name = test_name[5:]
        src_dir = ctx.project_root / "src"
        if not src_dir.is_dir():
            return None

        for match in src_dir.rglob(f"{source_name}.py"):
            if file_has_pattern(match, r"\bthreading\b"):
                check = EnvironmentCheck(
                    check_name="thread_aware_teardown",
                    status=CheckStatus.WARN,
                    message=f"Source module '{source_name}' uses threading",
                    detail="Tests should ensure threads are joined in teardown to avoid flaky failures",
                )
                constraint = (
                    f"Source module '{source_name}' uses threading \u2014 "
                    f"ensure all threads are joined in test teardown"
                )
                return RuleContribution(checks=[check], constraints=[constraint])
            break  # Only check first match

        return None


@preflight_rule(domains=_TEST, priority=100)
class TestConstraintsRule(PreflightRule):
    """Inject prompt constraints and validators for test domain."""

    rule_id = "test_constraints"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        # Scan conftest for fixtures
        fixtures: List[str] = []
        conftest = ctx.target_dir / "conftest.py"
        if conftest.exists():
            try:
                content = conftest.read_text(encoding="utf-8")
                fixtures = re.findall(
                    r"@pytest\.fixture[^)]*\)\s*\ndef\s+(\w+)",
                    content,
                )
            except Exception:
                pass

        fixture_list = ", ".join(fixtures[:20]) or "(none found)"
        return RuleContribution(
            constraints=[
                "Use pytest conventions (functions starting with test_, classes with Test)",
                f"Available fixtures: {fixture_list}",
                "Mock external dependencies -- do not make real API calls",
                "Use == for exact tag/capability matching, not 'in' substring checks",
            ],
            validators=[
                "imports_resolve",
                "test_naming",
                "no_hardcoded_secrets",
                "no_markdown_fences",
                "no_substring_tag_matching",
            ],
        )
