"""
Common preflight rules applicable across multiple domains.
"""

from __future__ import annotations

from typing import Optional

from ..domain_preflight_models import CheckStatus, EnvironmentCheck

from ._base import (
    ALL_DOMAINS,
    PYTHON_DOMAINS,
    PreflightRule,
    RuleContext,
    RuleContribution,
)
from ._helpers import LOGGER_RESERVED_FIELDS, file_has_pattern
from ._registry import preflight_rule


@preflight_rule(domains=ALL_DOMAINS, priority=10)
class ParentDirExistsRule(PreflightRule):
    """Check that the parent directory of the target file exists."""

    rule_id = "parent_dir_exists"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        if ctx.target_dir.exists():
            check = EnvironmentCheck(
                check_name="parent_dir_exists",
                status=CheckStatus.PASS,
                message=f"Parent directory exists: {ctx.target_dir}",
            )
        else:
            check = EnvironmentCheck(
                check_name="parent_dir_exists",
                status=CheckStatus.WARN,
                message=f"Parent directory does not exist: {ctx.target_dir}",
                detail="Directory will need to be created before code generation",
            )
        return RuleContribution(checks=[check])


@preflight_rule(domains=PYTHON_DOMAINS, priority=200)
class LoggerReservedFieldsRule(PreflightRule):
    """Detect logging usage and inject reserved-field constraint."""

    rule_id = "logger_reserved_fields"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        if not ctx.target_path.exists():
            return None
        if not file_has_pattern(ctx.target_path, r"\blogger\b"):
            return None

        sample_fields = ", ".join(sorted(list(LOGGER_RESERVED_FIELDS))[:8])
        check = EnvironmentCheck(
            check_name="logger_reserved_fields",
            status=CheckStatus.PASS,
            message="File uses logging \u2014 reserved field constraint will be injected",
            detail=f"Reserved fields: {', '.join(sorted(list(LOGGER_RESERVED_FIELDS)[:10]))}...",
        )
        constraint = (
            f"Do not use LogRecord reserved field names as extra= keys: "
            f"{sample_fields}, ..."
        )
        return RuleContribution(checks=[check], constraints=[constraint])
