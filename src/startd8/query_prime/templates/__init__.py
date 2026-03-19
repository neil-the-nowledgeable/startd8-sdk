"""Query template registry for TRIVIAL query generation.

Provides deterministic code templates for health checks and basic CRUD,
bypassing LLM generation entirely for simple patterns.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from ..models import DatabaseType, OperationType, QueryWorkItem

# Registry: (database, language, operation) -> generator function
_TEMPLATE_REGISTRY: Dict[
    Tuple[str, str, str],
    Callable[[QueryWorkItem], str],
] = {}


def register_template(
    database: DatabaseType,
    language: str,
    operation: OperationType,
    generator: Callable[[QueryWorkItem], str],
) -> None:
    """Register a template generator function."""
    key = (database.value, language, operation.value)
    _TEMPLATE_REGISTRY[key] = generator


def is_trivial(work_item: QueryWorkItem) -> bool:
    """Check if a work item can be handled by a template."""
    key = (
        work_item.database.value,
        work_item.target_language,
        work_item.operation_type.value,
    )
    return key in _TEMPLATE_REGISTRY


def generate(work_item: QueryWorkItem) -> Optional[str]:
    """Generate code from a template if available.

    Returns:
        Generated code string, or None if no template matches.
    """
    key = (
        work_item.database.value,
        work_item.target_language,
        work_item.operation_type.value,
    )
    generator = _TEMPLATE_REGISTRY.get(key)
    if generator is None:
        return None
    return generator(work_item)


# Import template modules to trigger registration
from . import crud, health_check  # noqa: E402, F401
