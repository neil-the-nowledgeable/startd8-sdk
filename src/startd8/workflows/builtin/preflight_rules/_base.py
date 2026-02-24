"""
Base types for the preflight rule registry.

Defines the PreflightRule ABC, RuleContext, RuleContribution dataclasses,
and domain-set constants used by all built-in and third-party rules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, List, Optional

from ..domain_preflight_models import (
    AvailableDeps,
    EnvironmentCheck,
    TaskDomain,
)


# ---------------------------------------------------------------------------
# Domain set constants
# ---------------------------------------------------------------------------

ALL_DOMAINS: FrozenSet[TaskDomain] = frozenset(TaskDomain)

PYTHON_DOMAINS: FrozenSet[TaskDomain] = frozenset({
    TaskDomain.PYTHON_SINGLE_MODULE,
    TaskDomain.PYTHON_PACKAGE_MODULE,
    TaskDomain.PYTHON_TEST,
})

CONFIG_DOMAINS: FrozenSet[TaskDomain] = frozenset({
    TaskDomain.CONFIG_TOML,
    TaskDomain.CONFIG_YAML,
    TaskDomain.CONFIG_JSON,
})


# ---------------------------------------------------------------------------
# Rule context and contribution
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuleContext:
    """Immutable context passed to every rule's ``evaluate()`` method."""

    target_file: str
    target_path: Path          # project_root / target_file (pre-computed)
    target_dir: Path           # target_path.parent
    project_root: Path
    domain: TaskDomain
    available_deps: AvailableDeps
    # Phase 4: per-file FileManifest (None when manifest unavailable)
    manifest: Any = None
    # Phase 4: project-wide ManifestRegistry for cross-file rules (PF-3)
    manifest_registry: Any = None


@dataclass
class RuleContribution:
    """What a single rule contributes to the enrichment."""

    checks: List[EnvironmentCheck] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    validators: List[str] = field(default_factory=list)
    validator_fns: Dict[str, Callable] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract rule
# ---------------------------------------------------------------------------

class PreflightRule(ABC):
    """Base class for all preflight rules.

    Subclasses declare which domains they apply to, an optional priority,
    and implement ``evaluate()`` to return a ``RuleContribution`` (or ``None``
    to contribute nothing).
    """

    domains: FrozenSet[TaskDomain] = ALL_DOMAINS
    priority: int = 100  # Lower = runs first (10=early, 100=default, 200=late)

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique identifier for this rule (e.g. 'parent_dir_exists')."""
        ...

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        """Evaluate the rule against the given context.

        Returns a RuleContribution with any checks, constraints, validators,
        or None to contribute nothing.
        """
        return None
