"""
Cross-file import validator — manifest-backed preflight rule (Phase 4, PF-3).

Checks for:
- Circular imports between project files (WARNING severity)
- Missing FQN references in import targets (ERROR severity)

Requires manifest_registry in RuleContext to function.
Gracefully degrades to no-op when registry is unavailable (PF-5).
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


class CrossFileImportValidator(PreflightRule):
    """Validates cross-file import consistency using manifest data.

    Requires manifest_registry to be present in RuleContext.
    Returns None (no contribution) when registry is unavailable.
    """

    domains = PYTHON_DOMAINS
    priority = 200  # Late — requires manifest data

    @property
    def rule_id(self) -> str:
        return "cross_file_import_check"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        if ctx.manifest_registry is None:
            logger.info(
                "manifest.fallback",
                extra={
                    "surface": "cross_file_import_check",
                    "reason": "registry_unavailable",
                },
            )
            return None

        checks: list[EnvironmentCheck] = []

        try:
            dep_graph = ctx.manifest_registry.dependency_graph()
        except Exception as exc:
            logger.debug("cross_file_import_check: dep_graph failed: %s", exc)
            return None

        # Check for circular imports involving the target file
        _EMPTY: frozenset[str] = frozenset()
        target = ctx.target_file
        if target in dep_graph:
            for dep in dep_graph[target]:
                dep_deps = dep_graph.get(dep, _EMPTY)
                if target in dep_deps:
                    checks.append(
                        EnvironmentCheck(
                            check_name="circular_import",
                            status="warn",
                            message=(
                                f"Circular import detected: {target} <-> {dep}"
                            ),
                            detail=(
                                f"Files {target} and {dep} import each other. "
                                f"This may be intentional in Python (lazy imports) "
                                f"but can cause ImportError at runtime."
                            ),
                        )
                    )

        # Check that imports reference existing FQNs
        if ctx.manifest is not None:
            for imp in getattr(ctx.manifest, "imports", []):
                if getattr(imp, "is_relative", False):
                    continue  # Skip relative imports — resolved differently
                for name in getattr(imp, "names", []):
                    fqn = f"{imp.module}.{name}"
                    if not ctx.manifest_registry.fqn_exists(fqn):
                        # Only flag internal imports (not stdlib/external)
                        deps = getattr(ctx.manifest, "dependencies", None)
                        if deps and imp.module in getattr(deps, "internal", []):
                            checks.append(
                                EnvironmentCheck(
                                    check_name="missing_fqn_ref",
                                    status="fail",
                                    message=(
                                        f"Import '{fqn}' not found in project manifests"
                                    ),
                                    detail=(
                                        f"The import from {imp.module} references "
                                        f"'{name}' which does not exist in any "
                                        f"manifest. This is likely a real problem."
                                    ),
                                )
                            )

        if not checks:
            return None

        return RuleContribution(checks=checks)
