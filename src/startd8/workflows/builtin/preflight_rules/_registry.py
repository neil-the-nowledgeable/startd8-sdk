"""
PreflightRuleRegistry — thread-safe singleton for preflight rules.

Follows the ProviderRegistry pattern (``src/startd8/providers/registry.py``)
with decorator-based registration (``EventBus.on`` pattern).
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable, ClassVar, Dict, FrozenSet, List, Optional, Type

from ..domain_preflight_models import TaskDomain

from ._base import (
    PreflightRule,
    RuleContext,
    RuleContribution,
)

logger = logging.getLogger(__name__)


class PreflightRuleRegistry:
    """Central registry for preflight rules.

    Thread-safe singleton. Rules are registered either programmatically
    via ``register()``, by the ``@preflight_rule`` decorator, or
    automatically via entry-point discovery (group ``startd8.preflight_rules``).
    """

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _rules: ClassVar[Dict[str, PreflightRule]] = {}
    _discovered: ClassVar[bool] = False

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #

    @classmethod
    def register(cls, rule: PreflightRule) -> None:
        """Register a rule instance.

        Raises ``TypeError`` if *rule* is not a ``PreflightRule``.
        Logs a warning (but does not error) on duplicate ``rule_id``.
        """
        if not isinstance(rule, PreflightRule):
            raise TypeError(
                f"{rule!r} is not a PreflightRule subclass instance"
            )

        rule_id = rule.rule_id
        with cls._lock:
            if rule_id in cls._rules:
                logger.warning("Overwriting existing preflight rule: %s", rule_id)
            cls._rules[rule_id] = rule
            logger.debug("Registered preflight rule: %s (priority=%d)", rule_id, rule.priority)

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    @classmethod
    def discover(cls, force: bool = False) -> None:
        """Discover rules via entry-point group ``startd8.preflight_rules``.

        Also imports built-in rules so they self-register via the decorator.
        """
        with cls._lock:
            if cls._discovered and not force:
                return

        cls._import_builtin_rules()
        cls._discover_entry_points()

        with cls._lock:
            cls._discovered = True

    @classmethod
    def _import_builtin_rules(cls) -> None:
        """Explicitly instantiate and register all built-in rules.

        Decorators fire on first import only. After ``clear()``, Python's
        module cache means re-importing won't re-fire decorators, so we
        explicitly create instances here (mirroring ProviderRegistry).
        """
        from .rules_common import (
            ParentDirExistsRule, LoggerReservedFieldsRule,
            ServiceMetadataPreflightRule,
        )
        from .rules_python_single import (
            NotInPackageRule, OptionalDepGuardsSingleRule,
            SingleModuleConstraintsRule,
        )
        from .rules_python_package import (
            InitPyExistsRule, ParentPackageImportableRule, CircularImportsRule,
            OptionalDepGuardsPackageRule, PydanticPropertyConfusionRule,
            PackageModuleConstraintsRule,
        )
        from .rules_python_test import (
            SourceModuleExistsRule, TestDirExistsRule, ConftestScannableRule,
            PatchPathValidRule, ThreadAwareTeardownRule, TestConstraintsRule,
        )
        from .rules_config import (
            ConfigFileValidRule, EntryPointReinstallRule, ConfigConstraintsRule,
        )
        from .rules_validators import (
            NoRelativeImportsValidatorRule, DepsAvailableValidatorRule,
            DefinitionOrderingValidatorRule, MergeDamageDetectorRule,
        )
        from .call_graph_validator import CallGraphValidator

        builtin_classes = [
            ParentDirExistsRule, LoggerReservedFieldsRule, ServiceMetadataPreflightRule,
            NotInPackageRule, OptionalDepGuardsSingleRule,
            SingleModuleConstraintsRule,
            InitPyExistsRule, ParentPackageImportableRule, CircularImportsRule,
            OptionalDepGuardsPackageRule, PydanticPropertyConfusionRule,
            PackageModuleConstraintsRule,
            SourceModuleExistsRule, TestDirExistsRule, ConftestScannableRule,
            PatchPathValidRule, ThreadAwareTeardownRule, TestConstraintsRule,
            ConfigFileValidRule, EntryPointReinstallRule, ConfigConstraintsRule,
            NoRelativeImportsValidatorRule, DepsAvailableValidatorRule,
            DefinitionOrderingValidatorRule, MergeDamageDetectorRule,
            CallGraphValidator,
        ]
        for rule_cls in builtin_classes:
            cls.register(rule_cls())

    @classmethod
    def _discover_entry_points(cls) -> None:
        """Load rules from the ``startd8.preflight_rules`` entry-point group."""
        try:
            if sys.version_info >= (3, 10):
                from importlib.metadata import entry_points
                try:
                    eps = entry_points(group="startd8.preflight_rules")
                except TypeError:
                    eps = entry_points().get("startd8.preflight_rules", [])
            else:
                try:
                    from importlib_metadata import entry_points  # type: ignore[no-redef]
                    eps = entry_points().get("startd8.preflight_rules", [])
                except ImportError:
                    eps = []

            for ep in eps:
                try:
                    rule_class = ep.load()
                    rule = rule_class()
                    cls.register(rule)
                except Exception as exc:
                    logger.warning(
                        "Failed to load preflight rule %s: %s", ep.name, exc
                    )
        except Exception as exc:
            logger.debug("Entry-point discovery for preflight rules failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Evaluation
    # ------------------------------------------------------------------ #

    @classmethod
    def evaluate_all(cls, ctx: RuleContext) -> RuleContribution:
        """Evaluate all rules applicable to *ctx.domain*.

        Rules are filtered by domain, sorted by priority (ascending),
        and their contributions merged into one ``RuleContribution``.
        """
        cls.discover()

        with cls._lock:
            rules = list(cls._rules.values())

        applicable = [r for r in rules if ctx.domain in r.domains]
        applicable.sort(key=lambda r: r.priority)

        merged = RuleContribution()
        for rule in applicable:
            try:
                contrib = rule.evaluate(ctx)
            except Exception as exc:
                logger.warning(
                    "Preflight rule %s raised: %s", rule.rule_id, exc,
                )
                continue

            if contrib is None:
                continue

            merged.checks.extend(contrib.checks)
            merged.constraints.extend(contrib.constraints)
            merged.validators.extend(contrib.validators)
            merged.validator_fns.update(contrib.validator_fns)

        return merged

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #

    @classmethod
    def get_rule(cls, rule_id: str) -> Optional[PreflightRule]:
        """Return a registered rule by id, or ``None``."""
        cls.discover()
        with cls._lock:
            return cls._rules.get(rule_id)

    @classmethod
    def list_rules(cls) -> List[str]:
        """Return all registered rule ids."""
        cls.discover()
        with cls._lock:
            return list(cls._rules.keys())

    @classmethod
    def get_validator_fn(cls, name: str) -> Optional[Callable]:
        """Return a validator function contributed by any rule, or ``None``.

        Searches across all registered rules' last ``evaluate_all`` results
        is impractical, so instead we scan the rule classes for
        ``validator_fns`` contributed during a dry-run with a dummy context.
        This is mainly used by ``domain_checklist.py`` for fallback.
        """
        cls.discover()
        with cls._lock:
            rules = list(cls._rules.values())
        for rule in rules:
            # Check if the rule class has a class-level validator_fns mapping
            fns = getattr(rule, "_validator_fns", {})
            if name in fns:
                return fns[name]
        return None

    # ------------------------------------------------------------------ #
    # Testing support
    # ------------------------------------------------------------------ #

    @classmethod
    def clear(cls) -> None:
        """Remove all registered rules (useful for testing)."""
        with cls._lock:
            cls._rules.clear()
            cls._discovered = False
            logger.debug("Cleared preflight rule registry")


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def preflight_rule(
    domains: Optional[FrozenSet[TaskDomain]] = None,
    priority: Optional[int] = None,
) -> Callable[[Type[PreflightRule]], Type[PreflightRule]]:
    """Class decorator that instantiates a ``PreflightRule`` and registers it.

    Usage::

        @preflight_rule(domains=frozenset({TaskDomain.PYTHON_TEST}))
        class MyRule(PreflightRule):
            rule_id = "my_rule"
            def evaluate(self, ctx): ...
    """
    def decorator(cls: Type[PreflightRule]) -> Type[PreflightRule]:
        if domains is not None:
            cls.domains = domains
        if priority is not None:
            cls.priority = priority
        instance = cls()
        PreflightRuleRegistry.register(instance)
        return cls
    return decorator
