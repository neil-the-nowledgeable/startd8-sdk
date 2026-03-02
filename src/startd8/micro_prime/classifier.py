"""Element Tier Classification (REQ-MP-500–501, 511).

Classifies manifest elements into tiers for routing decisions:
- TRIVIAL: matches a template (no LLM needed)
- SIMPLE: suitable for local model generation
- MODERATE: requires cloud model
- COMPLEX: requires premium cloud model

Uses a zero-cost heuristic based on manifest signals only (no LLM calls).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from startd8.complexity import ComplexityTier

from startd8.forward_manifest import (
    ContractConfidence,
    ForwardElementSpec,
    ForwardFileSpec,
    InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.micro_prime.models import MicroPrimeConfig, TierClassification
from startd8.micro_prime.templates import TemplateRegistry
from startd8.utils.code_manifest import ElementKind, ParamKind

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Classification constants (from experiment script)
# ═══════════════════════════════════════════════════════════════════════════

_SIMPLE_NAME_PREFIXES = ("get_", "is_", "has_", "to_", "from_", "as_")

_SIMPLE_RETURN_TYPES = {
    "str", "int", "float", "bool", "None", "list", "dict",
    "Optional[str]", "Optional[int]", "Optional[float]", "Optional[bool]",
}

_COMPLEX_DECORATORS = {"abstractmethod", "overload", "contextmanager"}

_ORCHESTRATOR_NAMES = {
    "start", "serve", "main", "run", "run_server", "bootstrap",
    "setup", "launch", "initialize", "entrypoint",
}

_ORCHESTRATOR_SUFFIXES = ("_handler", "_pipeline", "_workflow", "_server")

_ORCHESTRATOR_DOC_KEYWORDS = (
    "server", "bootstrap", "pipeline", "orchestrat", "initialize",
    "start", "launch", "setup", "wire", "configure all",
)

_APP_INSTANCE_NAMES = {"app", "application", "server", "api"}


def classify_element(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    template_registry: Optional[TemplateRegistry] = None,
    config: Optional[MicroPrimeConfig] = None,
) -> tuple[TierClassification, str]:
    """Classify an element's complexity tier using manifest signals.

    Args:
        element: The element to classify.
        file_spec: The file spec for import context.
        contracts: Binding constraints for this element.
        template_registry: Optional template registry for TRIVIAL detection.
        config: Optional config for threshold overrides.

    Returns:
        Tuple of (tier, reasoning string).
    """
    cfg = config or MicroPrimeConfig()

    # ── TRIVIAL gate: template match (REQ-MP-500a) ──
    if template_registry and template_registry.is_trivial(element):
        return TierClassification.TRIVIAL, "matches template registry"

    # ── Property: almost always simple ──
    if element.kind == ElementKind.PROPERTY:
        return TierClassification.SIMPLE, "property accessor"

    # ── Constants: simple unless they're app/server instances ──
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        if element.name.lower() in _APP_INSTANCE_NAMES:
            return TierClassification.MODERATE, f"app/server instance ({element.name})"
        return TierClassification.SIMPLE, "constant/variable declaration"

    # ── Orchestrator / bootstrap early detection ──
    is_orchestrator = False
    orch_reason = ""

    if element.name.lower() in _ORCHESTRATOR_NAMES:
        is_orchestrator = True
        orch_reason = f"orchestrator name ({element.name})"
    elif any(element.name.lower().endswith(s) for s in _ORCHESTRATOR_SUFFIXES):
        is_orchestrator = True
        orch_reason = f"orchestrator suffix ({element.name})"
    elif (
        not element.parent_class
        and element.docstring_hint
        and any(kw in element.docstring_hint.lower() for kw in _ORCHESTRATOR_DOC_KEYWORDS)
    ):
        is_orchestrator = True
        orch_reason = "orchestrator docstring hint"

    if is_orchestrator:
        real_params = _get_real_params(element)
        if len(real_params) <= 1:
            return (
                TierClassification.MODERATE,
                f"{orch_reason}; {len(real_params)} params (side-effect heavy)",
            )

    # ── Per-element API dependency analysis (REQ-MP-511) ──
    api_tier = _check_api_dependencies(element, file_spec, cfg)
    if api_tier is not None:
        return api_tier

    # ── Scoring system ──
    reasons: list[str] = []
    if is_orchestrator:
        reasons.append(orch_reason)

    complexity_score = 0

    # Binding constraints
    binding_count = sum(
        1 for c in contracts
        if c.confidence in (ContractConfidence.EXPLICIT, ContractConfidence.INFERRED)
    )

    # Param count
    param_count = 0
    has_kwargs = False
    simple_return = False

    if element.signature:
        real_params = _get_real_params(element)
        param_count = len(real_params)
        has_kwargs = any(
            p.kind in (ParamKind.VAR_POSITIONAL, ParamKind.VAR_KEYWORD)
            for p in real_params
        )
        if element.signature.return_annotation:
            simple_return = element.signature.return_annotation in _SIMPLE_RETURN_TYPES

    if param_count <= 2:
        complexity_score -= 1
        reasons.append(f"{param_count} params")
    elif param_count >= 5:
        complexity_score += 2
        reasons.append(f"{param_count} params (many)")

    if has_kwargs:
        complexity_score += 1
        reasons.append("variadic params")

    if simple_return and element.signature:
        complexity_score -= 1
        reasons.append(f"simple return ({element.signature.return_annotation})")

    # Simple name prefix
    if any(element.name.startswith(p) for p in _SIMPLE_NAME_PREFIXES):
        complexity_score -= 1
        reasons.append("simple name prefix")

    # Binding constraints
    if binding_count == 0:
        complexity_score -= 1
        reasons.append("no binding constraints")
    elif binding_count >= 3:
        complexity_score += 2
        reasons.append(f"{binding_count} binding constraints")

    # Complex decorators
    if set(element.decorators or []) & _COMPLEX_DECORATORS:
        complexity_score += 2
        reasons.append(f"complex decorators: {element.decorators}")

    # Async
    if element.kind in (ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD):
        complexity_score += 1
        reasons.append("async")

    # Class definition
    if element.kind == ElementKind.CLASS:
        complexity_score += 2
        reasons.append("class definition")

    # Docstring hint length
    if element.docstring_hint and len(element.docstring_hint) > 100:
        complexity_score += 1
        reasons.append("long docstring hint (complex intent)")

    # ── Classify ──
    reasoning = "; ".join(reasons) if reasons else "default"

    if complexity_score <= -1:
        return TierClassification.SIMPLE, reasoning
    elif complexity_score <= 2:
        return TierClassification.MODERATE, reasoning
    else:
        return TierClassification.COMPLEX, reasoning


def _get_real_params(element: ForwardElementSpec) -> list:
    """Get parameters excluding self/cls."""
    if not element.signature:
        return []
    return [p for p in element.signature.params if p.name not in ("self", "cls")]


def _check_api_dependencies(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    config: MicroPrimeConfig,
) -> Optional[tuple[TierClassification, str]]:
    """Two-pass API dependency analysis (REQ-MP-511).

    Pass 1: File-level import gate — count unique external imports.
    Pass 2: Per-element binding constraint check.

    Returns tier override or None to continue scoring.
    """
    # Pass 1: Count unique external imports in the file
    external_imports = set()
    for imp in file_spec.imports:
        if imp.kind == "from":
            external_imports.add(imp.module)
        else:
            external_imports.add(imp.module)

    # Exclude stdlib and common built-in modules
    import sys
    stdlib = getattr(sys, "stdlib_module_names", set()) or set()
    external_only = {
        mod for mod in external_imports
        if mod.split(".")[0] not in stdlib
    }

    if len(external_only) > config.max_simple_imports:
        return (
            TierClassification.MODERATE,
            f"file has {len(external_only)} external imports (>{config.max_simple_imports})",
        )

    # Pass 2: Per-element name/docstring hints for complex API usage
    if element.docstring_hint:
        doc_lower = element.docstring_hint.lower()
        complex_api_hints = ("database", "http", "websocket", "grpc", "graphql", "oauth")
        for hint in complex_api_hints:
            if hint in doc_lower:
                return (
                    TierClassification.MODERATE,
                    f"docstring references complex API: {hint}",
                )

    return None


# ═══════════════════════════════════════════════════════════════════════════
# Shared complexity bridge (REQ-MP-808)
# ═══════════════════════════════════════════════════════════════════════════


def _to_shared_tier(tier: TierClassification) -> "ComplexityTier":
    """Map Micro Prime ``TierClassification`` → shared ``ComplexityTier``."""
    from startd8.complexity import ComplexityTier

    _map = {
        TierClassification.TRIVIAL: ComplexityTier.TRIVIAL,
        TierClassification.SIMPLE: ComplexityTier.SIMPLE,
        TierClassification.MODERATE: ComplexityTier.MODERATE,
        TierClassification.COMPLEX: ComplexityTier.COMPLEX,
    }
    result = _map.get(tier)
    if result is None:
        logger.warning("Unknown TierClassification %r, defaulting to MODERATE", tier)
        return ComplexityTier.MODERATE
    return result


def classify_element_shared(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    template_registry: Optional[TemplateRegistry] = None,
    config: Optional[MicroPrimeConfig] = None,
) -> "tuple[ComplexityTier, str]":
    """Classify an element returning the shared ``ComplexityTier``.

    Wrapper around ``classify_element`` that maps the result to the
    unified ``ComplexityTier`` enum from ``startd8.complexity``.

    Args:
        Same as ``classify_element``.

    Returns:
        Tuple of (``ComplexityTier``, reasoning string).
    """
    tier, reason = classify_element(
        element, file_spec, contracts, template_registry, config,
    )
    return _to_shared_tier(tier), reason
