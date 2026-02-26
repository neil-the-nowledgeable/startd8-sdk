"""
Call graph validator — manifest-backed preflight rule (Phase 6, CG-PF-1,2,3).

Checks for:
- CG-PF-1: Missing call targets (target_fqn references nonexistent FQN) → WARNING
- CG-PF-2: Call graph cycles → WARNING with cycle path
- CG-PF-3: Dynamic dispatch presence → INFO advisory

Requires manifest_registry in RuleContext to function.
Gracefully degrades to no-op when registry is unavailable.
"""

from __future__ import annotations

from typing import Optional

from startd8.logging_config import get_logger

from ._base import (
    PYTHON_DOMAINS,
    PreflightRule,
    RuleContext,
    RuleContribution,
)
from ..domain_preflight_models import EnvironmentCheck

logger = get_logger(__name__)


class CallGraphValidator(PreflightRule):
    """Validates call graph consistency using manifest data.

    Requires manifest_registry to be present in RuleContext.
    Returns None (no contribution) when registry is unavailable.
    """

    domains = PYTHON_DOMAINS
    priority = 210  # After CrossFileImportValidator (200)

    @property
    def rule_id(self) -> str:
        return "call_graph_validator"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        if ctx.manifest_registry is None:
            logger.info(
                "manifest.fallback",
                extra={
                    "surface": "call_graph_validator",
                    "reason": "registry_unavailable",
                },
            )
            return None

        checks: list[EnvironmentCheck] = []

        # CG-PF-1: Verify call targets exist
        if ctx.manifest is not None:
            try:
                from startd8.utils.manifest_registry import _flatten_elements

                elements = _flatten_elements(ctx.manifest.elements)
                for elem in elements:
                    if elem.call_graph is None:
                        continue
                    for call in elem.call_graph.calls:
                        if call.target_fqn is not None and not ctx.manifest_registry.fqn_exists(call.target_fqn):
                            checks.append(
                                EnvironmentCheck(
                                    check_name="missing_call_target",
                                    status="warn",
                                    message=(
                                        f"Call target '{call.target_fqn}' from "
                                        f"'{elem.fqn}' not found in project manifests"
                                    ),
                                    detail=(
                                        f"Element {elem.fqn} calls {call.target_fqn} "
                                        f"which does not exist in any manifest. "
                                        f"This may indicate a missing dependency or "
                                        f"external library call."
                                    ),
                                )
                            )
            except Exception as exc:
                logger.debug("call_graph_validator: CG-PF-1 failed: %s", exc)

        # CG-PF-2: Cycle detection
        try:
            cycles = ctx.manifest_registry.call_graph_cycles(max_depth=10)
            for cycle in cycles[:5]:  # Limit to 5 cycles to avoid noise
                cycle_str = " → ".join(cycle)
                checks.append(
                    EnvironmentCheck(
                        check_name="call_graph_cycle",
                        status="warn",
                        message=f"Call graph cycle detected: {cycle_str}",
                        detail=(
                            f"Circular call chain found: {cycle_str}. "
                            f"This may indicate tight coupling or recursive "
                            f"dependencies that could complicate refactoring."
                        ),
                    )
                )
        except Exception as exc:
            logger.debug("call_graph_validator: CG-PF-2 failed: %s", exc)

        # CG-PF-3: Dynamic dispatch advisory
        if ctx.manifest is not None:
            try:
                from startd8.utils.manifest_registry import _flatten_elements

                elements = _flatten_elements(ctx.manifest.elements)
                for elem in elements:
                    if elem.call_graph is not None and elem.call_graph.has_dynamic_dispatch:
                        checks.append(
                            EnvironmentCheck(
                                check_name="dynamic_dispatch",
                                status="info",
                                message=(
                                    f"Dynamic dispatch detected in '{elem.fqn}'"
                                ),
                                detail=(
                                    f"Element {elem.fqn} uses dynamic dispatch "
                                    f"(e.g., getattr, __call__, operator overloading). "
                                    f"Static call graph may be incomplete for this function."
                                ),
                            )
                        )
            except Exception as exc:
                logger.debug("call_graph_validator: CG-PF-3 failed: %s", exc)

        # Phase 5 PF-1: Validate __all__ against manifest elements
        checks.extend(self._validate_module_all(ctx))

        if not checks:
            return None

        return RuleContribution(checks=checks)

    def _validate_module_all(self, ctx: RuleContext) -> list[EnvironmentCheck]:
        """Phase 5 PF-1: Validate that module __all__ exports exist in the manifest.

        When enable_introspect is True and module_all_for() returns a non-None
        list, flags any export name that is not found as an element in the manifest.

        Gracefully degrades to an empty list when:
        - registry is unavailable
        - enable_introspect is False on the config
        - manifest or path is unavailable
        """
        checks: list[EnvironmentCheck] = []
        if ctx.manifest_registry is None:
            return checks
        if ctx.manifest is None:
            return checks

        # Only run when introspect is enabled
        config = getattr(ctx, "config", None)
        enable_introspect = getattr(config, "enable_introspect", False) if config else False
        if not enable_introspect:
            return checks

        relative_path = getattr(ctx, "relative_path", None)
        if not relative_path:
            return checks

        try:
            mod_all = ctx.manifest_registry.module_all_for(relative_path)
            if mod_all is None:
                return checks  # No __all__ — nothing to validate

            from startd8.utils.manifest_registry import _flatten_elements
            element_names = {
                elem.fqn.split(".")[-1] if elem.fqn and "." in elem.fqn else elem.fqn
                for elem in _flatten_elements(ctx.manifest.elements)
                if elem.fqn
            }

            for export_name in mod_all:
                if export_name not in element_names:
                    checks.append(
                        EnvironmentCheck(
                            check_name="module_all_missing_element",
                            status="warn",
                            message=(
                                f"Module exports '{export_name}' in __all__ but no "
                                f"element '{export_name}' found in {relative_path}"
                            ),
                            detail=(
                                f"'{export_name}' is listed in __all__ but does not "
                                f"correspond to any known element in the manifest. "
                                f"This may indicate a missing import, renamed element, "
                                f"or stale __all__ list."
                            ),
                        )
                    )
        except Exception as exc:
            logger.debug("call_graph_validator: PF-1 module_all validation failed: %s", exc)

        return checks
