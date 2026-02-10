"""
Preflight rules for the CONFIG_TOML, CONFIG_YAML, CONFIG_JSON domains.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..domain_preflight_models import CheckStatus, EnvironmentCheck, TaskDomain

from ._base import CONFIG_DOMAINS, PreflightRule, RuleContext, RuleContribution
from ._registry import preflight_rule


@preflight_rule(domains=CONFIG_DOMAINS, priority=50)
class ConfigFileValidRule(PreflightRule):
    """Validate that existing config file is parseable."""

    rule_id = "config_file_valid"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        contrib = RuleContribution()

        if ctx.target_path.exists():
            contrib.checks.append(EnvironmentCheck(
                check_name="config_file_exists",
                status=CheckStatus.PASS,
                message=f"Config file exists: {ctx.target_file}",
            ))
            # Validate format
            try:
                content = ctx.target_path.read_text(encoding="utf-8")
                if ctx.domain == TaskDomain.CONFIG_JSON:
                    json.loads(content)
                elif ctx.domain == TaskDomain.CONFIG_TOML:
                    try:
                        import tomllib
                    except ImportError:
                        try:
                            import tomli as tomllib  # type: ignore[no-redef]
                        except ImportError:
                            tomllib = None  # type: ignore[assignment]
                    if tomllib is not None:
                        with open(ctx.target_path, "rb") as f:
                            tomllib.load(f)
                elif ctx.domain == TaskDomain.CONFIG_YAML:
                    import yaml
                    yaml.safe_load(content)
                contrib.checks.append(EnvironmentCheck(
                    check_name="config_format_valid",
                    status=CheckStatus.PASS,
                    message="Existing config file is valid",
                ))
            except Exception as exc:
                contrib.checks.append(EnvironmentCheck(
                    check_name="config_format_valid",
                    status=CheckStatus.WARN,
                    message=f"Existing config file has format issues: {exc}",
                ))
        else:
            contrib.checks.append(EnvironmentCheck(
                check_name="config_file_exists",
                status=CheckStatus.SKIP,
                message="Config file does not exist yet (will be created)",
            ))

        return contrib


@preflight_rule(domains=frozenset({TaskDomain.CONFIG_TOML}), priority=60)
class EntryPointReinstallRule(PreflightRule):
    """Warn that pyproject.toml entry-point changes require reinstall."""

    rule_id = "entry_point_reinstall"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        if Path(ctx.target_file).name != "pyproject.toml":
            return None

        check = EnvironmentCheck(
            check_name="entry_point_reinstall",
            status=CheckStatus.WARN,
            message=(
                "Changes to entry points in pyproject.toml require "
                "`pip install -e .` to take effect"
            ),
            detail="Entry points are resolved at install time, not runtime",
        )
        constraint = (
            "Changes to [project.entry-points] or [project.scripts] "
            "require `pip install -e .` to take effect"
        )
        return RuleContribution(checks=[check], constraints=[constraint])


@preflight_rule(domains=CONFIG_DOMAINS, priority=100)
class ConfigConstraintsRule(PreflightRule):
    """Inject prompt constraints and validators for config domains."""

    rule_id = "config_constraints"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        constraints = ["Preserve existing sections"]
        if ctx.target_path.exists():
            constraints.append("Current content provided as context")

        return RuleContribution(
            constraints=constraints,
            validators=[
                "valid_format",
                "existing_keys_preserved",
            ],
        )
