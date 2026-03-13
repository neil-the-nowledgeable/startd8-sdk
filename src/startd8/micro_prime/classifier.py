"""Element Tier Classification (REQ-MP-500–501, 511).

Classifies manifest elements into tiers for routing decisions:
- TRIVIAL: matches a template (no LLM needed)
- SIMPLE: suitable for local model generation
- MODERATE: requires cloud model
- COMPLEX: requires premium cloud model

Uses a zero-cost heuristic based on manifest signals only (no LLM calls).
"""

from __future__ import annotations

import re as _re
from dataclasses import dataclass
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
from startd8.utils.code_manifest import ElementKind, ParamKind, _STDLIB_MODULES

logger = get_logger(__name__)


@dataclass(frozen=True)
class ClassificationDetails:
    """Classification side-channel details (REQ-MP-511)."""

    file_import_bump: int = 0
    element_api_adjustment: int = 0
    classification_signals: frozenset[str] = frozenset()
    complexity_score: int = 0
    external_dependency_count: int = 0

# ═══════════════════════════════════════════════════════════════════════════
# Classification constants
# ═══════════════════════════════════════════════════════════════════════════

_SIMPLE_NAME_PREFIXES = ("get_", "is_", "has_", "to_", "from_", "as_")
_SIMPLE_NAME_EXACT = {"on_start", "logout", "health_check", "ping"}

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

# External API packages for import-based gating (REQ-MP-501/511)
_DEFAULT_EXTERNAL_API_PACKAGES = {
    # Network / RPC
    "grpc", "grpcio", "httpx", "aiohttp", "requests",
    # Web frameworks
    "flask", "fastapi", "django", "starlette",
    # Template engines
    "jinja2", "mako",
    # Cloud SDKs
    "google.cloud", "google.auth", "google.api_core",
    "boto3", "botocore",
    "azure",
    # Database / ORM
    "sqlalchemy", "alembic", "asyncpg", "psycopg2",
    # Task queues / caching
    "celery", "redis", "kombu",
    # Testing / load
    "locust", "playwright",
}

# Docstring keywords that indicate complex API usage (hard gate to MODERATE)
_COMPLEX_API_HINTS = ("database", "http", "websocket", "grpc", "graphql", "oauth")


def classify_element(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    template_registry: Optional[TemplateRegistry] = None,
    config: Optional[MicroPrimeConfig] = None,
) -> tuple[TierClassification, str]:
    """Classify an element's complexity tier using manifest signals.

    Returns:
        Tuple of (tier, reasoning string).
    """
    tier, reasoning, _details = classify_element_with_details(
        element, file_spec, contracts, template_registry, config,
    )
    return tier, reasoning


def classify_element_with_details(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    template_registry: Optional[TemplateRegistry] = None,
    config: Optional[MicroPrimeConfig] = None,
) -> tuple[TierClassification, str, ClassificationDetails]:
    """Classify an element and return side-channel details (REQ-MP-511).

    Flow:
      1. Early exits: TRIVIAL (template), PROPERTY, CONSTANT, ORCHESTRATOR
      2. Hard gates: binding-heavy external APIs, docstring API hints
      3. Scoring: params, return type, name, bindings, imports, decorators,
         async, class, docstring length, file size
      4. Threshold: score <= -1 → SIMPLE, <= 2 → MODERATE, else → COMPLEX
    """
    cfg = config or MicroPrimeConfig()
    signals: set[str] = set()
    details = ClassificationDetails()

    # ── TRIVIAL gate: template match (REQ-MP-500a) ──
    if template_registry and template_registry.is_trivial(
        element, file_spec=file_spec, contracts=contracts,
    ):
        return TierClassification.TRIVIAL, "matches template registry", details

    # ── Property: almost always simple ──
    if element.kind == ElementKind.PROPERTY:
        return TierClassification.SIMPLE, "property accessor", details

    # ── Constants: simple unless they're app/server instances ──
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        if element.name.lower() in _APP_INSTANCE_NAMES:
            signals.add("app_server_instance")
            details = ClassificationDetails(classification_signals=frozenset(signals))
            return TierClassification.MODERATE, f"app/server instance ({element.name})", details
        return TierClassification.SIMPLE, "constant/variable declaration", details

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
        signals.add("orchestrator")
        real_params = _get_real_params(element)
        if len(real_params) <= 1:
            details = ClassificationDetails(classification_signals=frozenset(signals))
            return (
                TierClassification.MODERATE,
                f"{orch_reason}; {len(real_params)} params (side-effect heavy)",
                details,
            )

    # ── Hard gates (checked before scoring to avoid wasted work) ──

    external_pkgs = _get_external_api_packages(cfg)
    import_index = _build_import_index(file_spec, external_pkgs)

    # Binding constraints referencing external APIs → MODERATE
    binding_hits = _binding_mentions_external(contracts, external_pkgs)
    if binding_hits >= 3:
        signals.add("external_api")
        details = ClassificationDetails(
            element_api_adjustment=binding_hits,
            classification_signals=frozenset(signals),
        )
        return (
            TierClassification.MODERATE,
            f"binding references external APIs ({binding_hits})",
            details,
        )

    # Docstring references complex API category → MODERATE
    if element.docstring_hint:
        doc_lower = element.docstring_hint.lower()
        for hint in _COMPLEX_API_HINTS:
            if hint in doc_lower:
                signals.add("external_api")
                details = ClassificationDetails(classification_signals=frozenset(signals))
                return (
                    TierClassification.MODERATE,
                    f"docstring references complex API: {hint}",
                    details,
                )

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

    # Import analysis: scope to imports the element actually references
    file_import_count = import_index.file_external_count
    element_import_count, has_refs = _element_relevant_import_count(
        element, import_index,
    )
    effective_import_count = element_import_count if has_refs else file_import_count
    if effective_import_count > 0:
        signals.add("external_imports")
        capped_bump = _cap_import_score(effective_import_count)
        complexity_score += capped_bump
        reasons.append(f"external APIs: {effective_import_count} packages")

    # Complex decorators
    if set(element.decorators or []) & _COMPLEX_DECORATORS:
        signals.add("complex_decorators")
        complexity_score += 2
        reasons.append(f"complex decorators: {element.decorators}")

    # Async
    if element.kind in (ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD):
        complexity_score += 1
        reasons.append("async")

    # Class definition
    if element.kind == ElementKind.CLASS:
        signals.add("class_definition")
        complexity_score += 2
        reasons.append("class definition")

    # Docstring hint intent length — strip Args/Returns/Raises boilerplate
    if element.docstring_hint:
        intent_len = _docstring_intent_length(element.docstring_hint)
        if intent_len > 200:
            complexity_score += 1
            reasons.append(f"long docstring intent ({intent_len} chars)")

    # Small-file bias: elements in files with few total elements are
    # likely simpler than the same signature in a large module.
    total_elements = len(file_spec.elements) if file_spec.elements else 0
    if total_elements <= 4:
        complexity_score -= 1
        reasons.append(f"small file ({total_elements} elements)")

    # ── Classify ──
    reasoning = "; ".join(reasons) if reasons else "default"

    details = ClassificationDetails(
        file_import_bump=file_import_count,
        element_api_adjustment=binding_hits,
        classification_signals=frozenset(signals),
        complexity_score=complexity_score,
        external_dependency_count=effective_import_count,
    )

    if complexity_score <= -1:
        return TierClassification.SIMPLE, reasoning, details
    elif complexity_score <= 2:
        return TierClassification.MODERATE, reasoning, details
    else:
        return TierClassification.COMPLEX, reasoning, details


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

_DOCSTRING_SECTION_RE = _re.compile(
    r"^\s*(Args|Arguments|Parameters|Returns?|Raises?|Yields?|Examples?|Notes?|See Also|Attributes)\s*:",
    _re.MULTILINE,
)


def _docstring_intent_length(docstring: str) -> int:
    """Return the character length of the intent portion of a docstring.

    Strips conventional sections (Args, Returns, Raises, etc.) so that
    verbose parameter documentation doesn't inflate the complexity signal.
    """
    match = _DOCSTRING_SECTION_RE.search(docstring)
    if match:
        return len(docstring[: match.start()].rstrip())
    return len(docstring.rstrip())


def _get_real_params(element: ForwardElementSpec) -> list:
    """Get parameters excluding self/cls."""
    if not element.signature:
        return []
    return [p for p in element.signature.params if p.name not in ("self", "cls")]


# ── Import analysis ──────────────────────────────────────────────────────


@dataclass
class _ImportIndex:
    """Pre-computed import analysis for a file spec.

    Built once per classification call and shared across all import-related
    checks, eliminating the duplicated import-matching loops.
    """
    file_external_count: int
    name_to_pkg: dict[str, str]


def _build_import_index(
    file_spec: ForwardFileSpec,
    external_packages: set[str],
) -> _ImportIndex:
    """Build an import index mapping imported names to external packages."""
    external_pkgs_found: set[str] = set()
    name_to_pkg: dict[str, str] = {}

    for imp in file_spec.imports:
        module = imp.module
        root = module.split(".")[0]
        if root in _STDLIB_MODULES:
            continue
        matched_pkg = None
        for pkg in external_packages:
            if module == pkg or module.startswith(pkg + "."):
                matched_pkg = pkg
                break
            if root == pkg:
                matched_pkg = pkg
                break
        if matched_pkg is None:
            matched_pkg = root
        external_pkgs_found.add(matched_pkg)
        name_to_pkg[module] = matched_pkg
        name_to_pkg[root] = matched_pkg
        for name in imp.names:
            name_to_pkg[name] = matched_pkg

    return _ImportIndex(
        file_external_count=len(external_pkgs_found),
        name_to_pkg=name_to_pkg,
    )


def _element_relevant_import_count(
    element: ForwardElementSpec,
    import_index: _ImportIndex,
) -> tuple[int, bool]:
    """Count external imports the element actually references.

    Collects type names from the element's annotations (parameter types,
    return type), base classes, and decorators, then counts how many of the
    file's external imports provide those names.

    Returns:
        Tuple of (count, has_structural_refs).  ``has_structural_refs`` is True
        when the element has any annotations, bases, or decorators that could
        be checked — even if none matched external imports.  When False, callers
        should fall back to file-level count.
    """
    referenced_names: set[str] = set()
    has_structural_refs = False

    if element.signature:
        for p in element.signature.params:
            if p.annotation:
                has_structural_refs = True
                referenced_names.update(_extract_type_tokens(p.annotation))
        if element.signature.return_annotation:
            has_structural_refs = True
            referenced_names.update(
                _extract_type_tokens(element.signature.return_annotation),
            )

    for base in element.bases or []:
        has_structural_refs = True
        referenced_names.update(_extract_type_tokens(base))

    for dec in element.decorators or []:
        has_structural_refs = True
        referenced_names.update(_extract_type_tokens(dec))

    if not referenced_names:
        return 0, has_structural_refs

    hit_pkgs: set[str] = set()
    for name in referenced_names:
        pkg = import_index.name_to_pkg.get(name)
        if pkg:
            hit_pkgs.add(pkg)

    return len(hit_pkgs), has_structural_refs


_TYPE_TOKEN_RE = _re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")


def _extract_type_tokens(annotation: str) -> set[str]:
    """Extract identifier tokens from a type annotation string.

    For ``"Optional[grpc.Server]"`` returns ``{"Optional", "grpc", "Server", "grpc.Server"}``.
    """
    tokens: set[str] = set()
    for match in _TYPE_TOKEN_RE.finditer(annotation):
        full = match.group()
        tokens.add(full)
        parts = full.split(".")
        for i in range(len(parts)):
            tokens.add(".".join(parts[: i + 1]))
    return tokens


def _cap_import_score(raw_count: int) -> int:
    """Cap import-based score contribution to prevent domination.

    Returns:
        1 for 1-3 imports, 2 for 4-6, 3 for 7+.
    """
    if raw_count <= 0:
        return 0
    if raw_count <= 3:
        return 1
    if raw_count <= 6:
        return 2
    return 3


def _get_external_api_packages(config: MicroPrimeConfig) -> set[str]:
    """Return the external API package set from config or defaults."""
    if config.external_api_packages:
        return {p.strip() for p in config.external_api_packages if p and p.strip()}
    return set(_DEFAULT_EXTERNAL_API_PACKAGES)


def _binding_mentions_external(
    contracts: list[InterfaceContract],
    external_packages: set[str],
) -> int:
    """Count bindings that mention external API packages."""
    hits = 0
    for c in contracts:
        text = " ".join(filter(None, [c.binding_text, c.description, c.import_path]))
        lower = text.lower()
        for pkg in external_packages:
            if pkg.lower() in lower:
                hits += 1
                break
    return hits


# ── Backward compatibility ───────────────────────────────────────────────
# These functions were used by callers outside the classifier.  Preserved
# as thin wrappers around the new _ImportIndex-based implementation.


def _import_complexity_bump(
    file_spec: ForwardFileSpec,
    external_packages: set[str],
) -> int:
    """Count distinct external API packages in file imports (REQ-MP-501)."""
    index = _build_import_index(file_spec, external_packages)
    return index.file_external_count


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
    """
    tier, reason = classify_element(
        element, file_spec, contracts, template_registry, config,
    )
    return _to_shared_tier(tier), reason
