"""
Preflight Rule Registry — declarative domain checks for DomainPreflightWorkflow.

Public API:

    PreflightRule        — ABC for all rules
    RuleContext           — immutable context passed to evaluate()
    RuleContribution      — what a rule contributes (checks, constraints, validators)
    PreflightRuleRegistry — singleton registry with evaluate_all()
    preflight_rule        — class decorator for auto-registration

Domain-set constants:

    ALL_DOMAINS, PYTHON_DOMAINS, CONFIG_DOMAINS
"""

from ._base import (
    ALL_DOMAINS,
    CONFIG_DOMAINS,
    PYTHON_DOMAINS,
    PreflightRule,
    RuleContext,
    RuleContribution,
)
from ._registry import (
    PreflightRuleRegistry,
    preflight_rule,
)

__all__ = [
    "ALL_DOMAINS",
    "CONFIG_DOMAINS",
    "PYTHON_DOMAINS",
    "PreflightRule",
    "PreflightRuleRegistry",
    "RuleContext",
    "RuleContribution",
    "preflight_rule",
]
