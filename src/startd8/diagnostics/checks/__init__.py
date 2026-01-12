"""
Diagnostic checks registry.

This module provides a central registry for all diagnostic checks.
Checks can be registered and discovered at runtime.
"""

from typing import Callable, Dict, List, Optional

from ..models import CheckCategory, CheckDefinition, HealthCheck

# Global registry of checks
_CHECKS: Dict[str, CheckDefinition] = {}


def register_check(
    name: str,
    category: CheckCategory,
    requires_framework: bool = False,
    requires_api_call: bool = False,
    description: Optional[str] = None,
) -> Callable:
    """Decorator to register a diagnostic check.

    Usage:
        @register_check("api_key_check", CheckCategory.AGENTS)
        def check_api_keys() -> HealthCheck:
            ...
    """
    def decorator(func: Callable[..., HealthCheck]) -> Callable[..., HealthCheck]:
        _CHECKS[name] = CheckDefinition(
            name=name,
            category=category,
            check_func=func,
            requires_framework=requires_framework,
            requires_api_call=requires_api_call,
            description=description,
        )
        return func
    return decorator


def get_all_checks() -> List[CheckDefinition]:
    """Get all registered checks."""
    return list(_CHECKS.values())


def get_checks_by_category(category: CheckCategory) -> List[CheckDefinition]:
    """Get checks for a specific category."""
    return [check for check in _CHECKS.values() if check.category == category]


def get_quick_checks() -> List[CheckDefinition]:
    """Get checks that don't require API calls (fast checks)."""
    return [check for check in _CHECKS.values() if not check.requires_api_call]


def get_check(name: str) -> Optional[CheckDefinition]:
    """Get a specific check by name."""
    return _CHECKS.get(name)


# Import check modules to register checks
from . import agent_checks
from . import cost_checks
from . import storage_checks
from . import framework_checks

__all__ = [
    "register_check",
    "get_all_checks",
    "get_checks_by_category",
    "get_quick_checks",
    "get_check",
    "CheckDefinition",
]
