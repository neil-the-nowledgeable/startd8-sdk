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

        if not checks:
            return None

        return RuleContribution(checks=checks)
