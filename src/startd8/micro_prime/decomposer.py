"""Moderate Decomposer — pre-escalation decomposition of MODERATE elements (REQ-MP-900).

Analyzes MODERATE elements and, where possible, decomposes them into SIMPLE
sub-elements that can be generated locally. Sub-element results are then
assembled into the complete MODERATE element.

Strategies:
  - ClassDecomposeStrategy (REQ-MP-901): class shell + optional __init__ / class attrs
  - FunctionChainStrategy  (REQ-MP-902): helpers + dispatch body (Phase 3)
"""

from __future__ import annotations

import ast
import builtins as _builtins
import functools
import keyword as _keyword
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
)
from startd8.logging_config import get_logger
from startd8.micro_prime.classifier import classify_element_with_details
from startd8.micro_prime.models import MicroPrimeConfig, TierClassification
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature

logger = get_logger(__name__)

# Bounded set of rejection reasons for metrics (REQ-MP-906, R3-S5).
REJECTION_REASONS = frozenset({
    "no_strategy",
    "metaclass",
    "complex_decorator",
    "api_dependency",
    "orchestrator",
    "too_many_attributes",
    "confidence_below_threshold",
    "max_sub_elements_exceeded",
    "signature_inference_failed",
    "methods_not_separate",
    "not_a_class",
    "disabled",
})

# Decorators / metaclass markers that disqualify class decomposition.
_COMPLEX_CLASS_MARKERS = frozenset({
    "ABCMeta", "__init_subclass__",
})


# ── Data classes ─────────────────────────────────────────────────────


@dataclass
class SubElement:
    """A SIMPLE-tier piece of a decomposed MODERATE element."""

    name: str
    kind: str  # "class_shell", "init", "class_attr", "helper", "dispatch_body"
    prompt_context: str
    depends_on: list[str]
    assembly_order: int
    element_spec: Optional[ForwardElementSpec]  # None for deterministic class_shell
    deterministic: bool = False


@dataclass
class DecompositionPlan:
    """A plan to generate a MODERATE element as a sequence of SIMPLE sub-elements."""

    original_element: ForwardElementSpec
    sub_elements: list[SubElement]
    strategy: str
    assembly_kind: str  # "class_compose", "function_chain", "sequential_body"
    confidence: float  # 0.0–1.0


# ── Confidence computation (REQ-MP-900, R1-S6) ──────────────────────

# Uncertainty signal weights — each reduces confidence by its weight.
_UNCERTAINTY_SIGNALS: dict[str, float] = {
    "missing_init": 0.1,
    "inferred_helper_signature": 0.1,  # per helper
    "parse_only_responsibility": 0.1,
    "class_level_attrs_gt1": 0.1,
}


def _compute_confidence(
    plan: DecompositionPlan,
    uncertainty_signals: list[str],
) -> float:
    """Compute confidence for a decomposition plan.

    Formula: 1.0 - (sum(signal_weights) / max_uncertainty)
    Clamped to [0.0, 1.0]. Returns 1.0 when max_uncertainty == 0.
    """
    max_uncertainty = sum(_UNCERTAINTY_SIGNALS.values())
    if max_uncertainty == 0:
        return 1.0

    total = sum(_UNCERTAINTY_SIGNALS.get(s, 0.0) for s in uncertainty_signals)
    confidence = 1.0 - (total / max_uncertainty)
    return max(0.0, min(1.0, confidence))


# ── Strategy protocol (REQ-MP-907) ──────────────────────────────────


class DecompositionStrategy(Protocol):
    """Protocol for pluggable decomposition strategies."""

    @property
    def name(self) -> str: ...

    def can_handle(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        classification_reason: str,
        classification_signals: Optional[set[str]] = None,
    ) -> bool: ...

    def plan(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        classification_reason: str,
        classification_signals: Optional[set[str]] = None,
    ) -> Optional[DecompositionPlan]: ...

    def assemble(
        self,
        plan: DecompositionPlan,
        sub_results: dict[str, str],
        skeleton: str,
    ) -> Optional[str]: ...


# ── Signature rendering helper ────────────────────────────────────────


def _render_signature_str(sig: Signature) -> str:
    """Render a Signature to a parameter string, e.g. ``(self, name: str)``."""
    parts: list[str] = []
    saw_positional_only = False
    saw_keyword_only = False

    for param in sig.params:
        rendered = param.name
        if param.annotation:
            rendered += f": {param.annotation}"
        if param.default is not None:
            rendered += f" = {param.default}"

        if param.kind == ParamKind.POSITIONAL_ONLY:
            saw_positional_only = True
            parts.append(rendered)
        elif param.kind == ParamKind.VAR_POSITIONAL:
            if saw_positional_only:
                parts.append("/")
                saw_positional_only = False
            parts.append(f"*{rendered}")
            saw_keyword_only = True
        elif param.kind == ParamKind.KEYWORD_ONLY:
            if saw_positional_only:
                parts.append("/")
                saw_positional_only = False
            if not saw_keyword_only:
                parts.append("*")
                saw_keyword_only = True
            parts.append(rendered)
        elif param.kind == ParamKind.VAR_KEYWORD:
            if saw_positional_only:
                parts.append("/")
                saw_positional_only = False
            parts.append(f"**{rendered}")
        else:
            # POSITIONAL or KEYWORD
            if saw_positional_only:
                parts.append("/")
                saw_positional_only = False
            parts.append(rendered)

    if saw_positional_only:
        parts.append("/")

    return f"({', '.join(parts)})"


# ── Class Decomposition Strategy (REQ-MP-901) ───────────────────────


class ClassDecomposeStrategy:
    """Decomposes MODERATE class elements into shell + optional attrs/init."""

    def __init__(self, config: Optional[MicroPrimeConfig] = None, template_registry: Optional[Any] = None) -> None:
        self._config = config or MicroPrimeConfig()
        self._template_registry = template_registry

    @property
    def name(self) -> str:
        return "class_decompose"

    def can_handle(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        classification_reason: str,
        classification_signals: Optional[set[str]] = None,
    ) -> bool:
        """Fast check: can this strategy decompose this element?"""
        if not self._config.class_decompose_enabled:
            return False

        if element.kind != ElementKind.CLASS:
            return False

        # Check metaclass/complex decorators
        if self._has_complex_markers(element):
            return False

        # Methods must already be separate elements in file_spec
        if not self._methods_are_separate(element, file_spec):
            return False

        # At most 3 class-level attributes
        attr_count = self._count_class_attrs(element, file_spec)
        if attr_count > 3:
            return False

        return True

    def plan(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        classification_reason: str,
        classification_signals: Optional[set[str]] = None,
    ) -> Optional[DecompositionPlan]:
        """Produce a decomposition plan for a class element."""
        sub_elements: list[SubElement] = []
        uncertainty_signals: list[str] = []
        order = 0
        max_sub = self._config.max_sub_elements

        def _append(sub: SubElement) -> bool:
            """Append sub-element, enforcing max_sub_elements early."""
            sub_elements.append(sub)
            if len(sub_elements) > max_sub:
                logger.debug(
                    "Plan for %s rejected: %d sub-elements > max %d",
                    element.name, len(sub_elements), max_sub,
                )
                return False
            return True

        # 1. Class shell — always deterministic
        if not _append(SubElement(
            name="class_shell",
            kind="class_shell",
            prompt_context="",
            depends_on=[],
            assembly_order=order,
            element_spec=None,  # Deterministic — extracted from skeleton
            deterministic=True,
        )):
            return None
        order += 1

        # 2. Class-level attributes (constants/variables with parent_class == element.name)
        class_attrs = self._get_class_attrs(element, file_spec)
        if class_attrs:
            if len(class_attrs) > 1:
                uncertainty_signals.append("class_level_attrs_gt1")
            attr_names = ", ".join(a.name for a in class_attrs)
            # Use a VARIABLE spec without parent_class to avoid the classifier's
            # class-membership bonus (+2) that can push this to MODERATE tier.
            # Assembly inserts the generated lines at class scope.
            if not _append(SubElement(
                name="_class_attributes",
                kind="class_attr",
                prompt_context=(
                    f"Class-level attributes for {element.name}: {attr_names}. "
                    "Output only assignment statements; do not use self."
                ),
                depends_on=["class_shell"],
                assembly_order=order,
                element_spec=ForwardElementSpec(
                    kind=ElementKind.VARIABLE,
                    name="_class_attributes",
                    signature=None,
                    docstring_hint=f"Class-level attributes for {element.name}.",
                ),
            )):
                return None
            order += 1

        # 3. __init__ — include if present in manifest, otherwise signal uncertainty.
        init_spec = next(
            (
                e for e in file_spec.elements
                if e.name == "__init__" and e.parent_class == element.name
            ),
            None,
        )
        if init_spec is not None:
            if not _append(SubElement(
                name="__init__",
                kind="init",
                prompt_context=f"Initialize {element.name}.",
                depends_on=["class_shell"],
                assembly_order=order,
                element_spec=init_spec,
            )):
                return None
            order += 1
        else:
            uncertainty_signals.append("missing_init")

        # If class has no __init__ in manifest and no class-level state,
        # shell-only plan suffices.

        # Build plan
        dummy_plan = DecompositionPlan(
            original_element=element,
            sub_elements=sub_elements,
            strategy=self.name,
            assembly_kind="class_compose",
            confidence=0.0,  # Set below
        )
        dummy_plan.confidence = _compute_confidence(dummy_plan, uncertainty_signals)

        # REQ-MP-1005: If all non-deterministic sub-elements are TRIVIAL (template-matched),
        # mark them deterministic and skip LLM entirely.
        templates = getattr(self, "_template_registry", None)
        if templates is not None:
            all_trivial = True
            for sub in dummy_plan.sub_elements:
                if sub.deterministic:
                    continue
                if sub.element_spec is None:
                    all_trivial = False
                    break
                if not templates.is_trivial(sub.element_spec):
                    all_trivial = False
                    break
            if all_trivial:
                for sub in dummy_plan.sub_elements:
                    if not sub.deterministic:
                        sub.deterministic = True
                logger.info(
                    "All sub-elements TRIVIAL for %s — marking deterministic",
                    element.name,
                )

        return dummy_plan

    def assemble(
        self,
        plan: DecompositionPlan,
        sub_results: dict[str, str],
        skeleton: str,
    ) -> Optional[str]:
        """Assemble a class from its decomposed sub-elements.

        For a shell-only class (no attrs/init), returns "pass" which the
        splicer uses to replace the class-scope `raise NotImplementedError`.
        """
        # Validate that the shell sub-element was generated
        shell_code = sub_results.get("class_shell")
        if shell_code is None:
            return None

        parts: list[str] = []
        sub_map = {s.name: s for s in plan.sub_elements}

        # Class attributes
        attr_code = sub_results.get("_class_attributes")
        if attr_code:
            parts.append(textwrap.dedent(attr_code).strip("\n"))

        # __init__ body
        init_code = sub_results.get("__init__")
        if init_code:
            init_spec = sub_map.get("__init__")
            if init_spec is None or init_spec.element_spec is None:
                logger.warning(
                    "Missing __init__ element_spec for %s",
                    plan.original_element.name,
                )
                return None
            spec = init_spec.element_spec
            if spec.signature is None:
                logger.warning(
                    "Missing __init__ signature for %s",
                    plan.original_element.name,
                )
                return None
            prefix = "async def" if spec.kind in (
                ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD,
            ) else "def"
            sig = _render_signature_str(spec.signature)
            ret = ""
            if spec.signature.return_annotation:
                ret = f" -> {spec.signature.return_annotation}"
            method_lines = [f"{prefix} {spec.name}{sig}{ret}:"]
            if spec.docstring_hint:
                method_lines.append(f'    """{spec.docstring_hint}"""')
            body_lines = textwrap.dedent(init_code).splitlines()
            if not body_lines:
                body_lines = ["pass"]
            method_lines.extend(
                [f"    {line}" if line.strip() else "" for line in body_lines]
            )
            parts.append("\n".join(method_lines))

        if parts:
            assembled = "\n\n".join(parts)
        else:
            # Shell only — return "pass" as the body token
            assembled = shell_code  # "pass"

        # Validate assembled code can exist inside a class
        try:
            # Wrap in a class stub to validate as class body
            test_code = f"class _Test:\n"
            for line in assembled.splitlines():
                test_code += f"    {line}\n"
            ast.parse(test_code)
        except SyntaxError:
            logger.warning(
                "Assembly validation failed for %s",
                plan.original_element.name,
            )
            return None

        return assembled

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _has_complex_markers(element: ForwardElementSpec) -> bool:
        """Check for metaclass or complex decorator markers."""
        decorators = element.decorators or []
        for dec in decorators:
            if any(marker in dec for marker in _COMPLEX_CLASS_MARKERS):
                return True
            # dataclass with complex field factories
            if "dataclass" in dec and ("field(" in dec or "factory" in dec):
                return True
        # Check bases for ABCMeta
        for base in (element.bases or []):
            if "ABCMeta" in base or "metaclass=" in base:
                return True
        return False

    @staticmethod
    def _methods_are_separate(
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
    ) -> bool:
        """Check that the class's methods are separate elements in file_spec."""
        # Find child elements of this class
        child_methods = [
            e for e in file_spec.elements
            if e.parent_class == element.name
            and e.kind in (
                ElementKind.METHOD, ElementKind.ASYNC_METHOD,
                ElementKind.FUNCTION, ElementKind.ASYNC_FUNCTION,
                ElementKind.PROPERTY,
            )
        ]
        # A decomposable class must have at least one method as a separate element
        return len(child_methods) > 0

    @staticmethod
    def _count_class_attrs(
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
    ) -> int:
        """Count class-level attributes from manifest elements."""
        return sum(
            1 for e in file_spec.elements
            if e.parent_class == element.name
            and e.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE)
        )

    @staticmethod
    def _get_class_attrs(
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
    ) -> list[ForwardElementSpec]:
        """Get class-level attribute elements from manifest."""
        return [
            e for e in file_spec.elements
            if e.parent_class == element.name
            and e.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE)
        ]


# ── Function Chain Strategy (REQ-MP-902) ─────────────────────────────


def _is_method(element: ForwardElementSpec) -> bool:
    return element.kind in (ElementKind.METHOD, ElementKind.ASYNC_METHOD)


def _is_async(element: ForwardElementSpec) -> bool:
    return element.kind in (ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD)


# Reason substrings that indicate API/orchestrator classification (fallback
# until ClassificationSignal enum is available — see REQ-MP-902 note).
# Values are lowercase — compared against reason_lower at match site.
_API_ORCHESTRATOR_REASON_MARKERS = frozenset({
    "external API",
    "external imports",
    "orchestrator",
    "app/server instance",
})

# Python keywords and builtins that must not be used as helper names.
_PYTHON_RESERVED = frozenset(
    list(_keyword.kwlist)
    + list(getattr(_keyword, "softkwlist", []))
    + dir(_builtins)
)

# Responsibility clause separators (deterministic, no LLM).


@functools.lru_cache(maxsize=1)
def _compile_clause_re() -> "re.Pattern[str]":
    return re.compile(
        r"""
        ;\s*                   # semicolons
        | ^\s*[-*•]\s+         # bullet markers at line start
        | ^\s*\d+[.)]\s+      # enumerated prefixes (1. or 1))
        """,
        re.MULTILINE | re.VERBOSE,
    )


def _parse_responsibilities(text: Optional[str]) -> list[str]:
    """Parse a docstring or design section into distinct responsibility clauses.

    Deterministic parsing: splits on ``;``, bullet markers, or numbered
    prefixes. Ignores clauses shorter than 4 words. ``"and"`` is NOT a
    separator — it commonly appears within single responsibilities.
    """
    if not text:
        return []
    pattern = _compile_clause_re()
    clauses = pattern.split(text)
    result: list[str] = []
    for clause in clauses:
        cleaned = clause.strip().rstrip(".")
        if len(cleaned.split()) >= 4:
            result.append(cleaned)
    return result


def _slugify_helper_name(clause: str) -> str:
    """Derive a helper function name from a responsibility clause.

    Produces a snake_case slug prefixed with ``_``. Falls back to empty
    string if the result is invalid (caller handles fallback).
    """
    # Extract key verbs/nouns — take first 6 words, lowercase, strip non-alnum
    words = re.sub(r"[^a-zA-Z0-9\s]", "", clause).lower().split()[:6]
    slug = "_".join(words)
    if not slug or slug in _PYTHON_RESERVED or len(slug) > 48:
        return ""
    return f"_{slug}"


def _uniquify_name(
    name: str,
    existing: set[str],
) -> str:
    """Ensure ``name`` doesn't collide with ``existing`` names."""
    if name not in existing:
        return name
    for suffix in range(2, 100):
        candidate = f"{name}_{suffix}"
        if candidate not in existing:
            return candidate
    return f"{name}_99"  # pragma: no cover


def _render_helper_def(helper: SubElement, helper_code: str) -> Optional[str]:
    """Render a helper SubElement + its generated code into a full function def."""
    if not (helper.element_spec and helper.element_spec.signature):
        return None
    prefix = "async def" if _is_async(helper.element_spec) else "def"
    sig = _render_signature_str(helper.element_spec.signature)
    ret = ""
    if helper.element_spec.signature.return_annotation:
        ret = f" -> {helper.element_spec.signature.return_annotation}"
    header = f"{prefix} {helper.name}{sig}{ret}:"
    body = textwrap.dedent(helper_code).strip()
    if not body:
        body = "pass"
    indented = textwrap.indent(body, "    ")
    if helper.element_spec.docstring_hint:
        return (
            f"{header}\n"
            f'    """{helper.element_spec.docstring_hint}"""\n'
            f"{indented}"
        )
    return f"{header}\n{indented}"


class FunctionChainStrategy:
    """Decomposes MODERATE functions into dispatch body + helper sub-functions (REQ-MP-902)."""

    def __init__(self, config: Optional[MicroPrimeConfig] = None) -> None:
        self._config = config or MicroPrimeConfig()

    @property
    def name(self) -> str:
        return "function_chain"

    def can_handle(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        classification_reason: str,
        classification_signals: Optional[set[str]] = None,
    ) -> bool:
        if not self._config.function_chain_enabled:
            return False

        # Must be a function or method
        if not (_is_method(element) or element.kind in (
            ElementKind.FUNCTION, ElementKind.ASYNC_FUNCTION,
        )):
            return False

        # Exclude API/orchestrator classifications
        if classification_signals is not None:
            disqualifying = {"external_api", "external_imports",
                             "orchestrator", "app_server_instance"}
            if classification_signals & disqualifying:
                return False
        else:
            # Fallback: reason-string matching
            reason_lower = classification_reason.lower()
            if any(marker in reason_lower for marker in _API_ORCHESTRATOR_REASON_MARKERS):
                logger.debug(
                    "FunctionChain: %s excluded via reason-string fallback: %s",
                    element.name, classification_reason,
                )
                return False

        # Must have 2+ responsibilities in docstring
        clauses = _parse_responsibilities(element.docstring_hint or "")
        if len(clauses) < 2:
            return False

        # Must not exceed max helpers
        if len(clauses) > self._config.max_helpers_per_function:
            return False

        return True

    def plan(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        classification_reason: str,
        classification_signals: Optional[set[str]] = None,
    ) -> Optional[DecompositionPlan]:
        # Intentionally re-validates clauses for direct-call safety (without can_handle).
        clauses = _parse_responsibilities(element.docstring_hint or "")
        if len(clauses) < 2 or len(clauses) > self._config.max_helpers_per_function:
            return None

        # Collect existing names for uniquification
        existing_names: set[str] = {e.name for e in file_spec.elements}
        method = _is_method(element)
        async_ = _is_async(element)

        sub_elements: list[SubElement] = []
        uncertainty_signals: list[str] = []
        helper_names: list[str] = []
        order = 0

        # Build helper sub-elements for each responsibility
        for i, clause in enumerate(clauses):
            slug = _slugify_helper_name(clause)
            if not slug:
                slug = f"_helper_{i + 1}"
                uncertainty_signals.append("inferred_helper_signature")
            helper_name = _uniquify_name(slug, existing_names)
            existing_names.add(helper_name)
            helper_names.append(helper_name)

            # Build a synthetic element spec for the helper
            helper_params: list[Param] = []
            if method:
                helper_params.append(Param(name="self", kind=ParamKind.POSITIONAL_ONLY))
            # Forward the original function's non-self params
            if element.signature:
                for p in element.signature.params:
                    if p.name in ("self", "cls"):
                        continue
                    helper_params.append(p)

            helper_kind = (
                ElementKind.ASYNC_METHOD if async_ and method
                else ElementKind.METHOD if method
                else ElementKind.ASYNC_FUNCTION if async_
                else ElementKind.FUNCTION
            )

            helper_spec = ForwardElementSpec(
                kind=helper_kind,
                name=helper_name,
                signature=Signature(
                    params=helper_params,
                    return_annotation=None,
                ),
                parent_class=element.parent_class if method else None,
                docstring_hint=clause,
            )

            sub_elements.append(SubElement(
                name=helper_name,
                kind="helper",
                prompt_context=f"Implement: {clause}",
                depends_on=[],
                assembly_order=order,
                element_spec=helper_spec,
            ))
            order += 1

        # Dispatch body — calls helpers in sequence
        helper_stubs = ", ".join(helper_names)
        dispatch_context = (
            f"Implement the body of {element.name} by calling these helpers "
            f"in order: {helper_stubs}. "
            f"Each helper handles one responsibility. "
            f"Do NOT implement the helpers — just call them."
        )

        sub_elements.append(SubElement(
            name=f"{element.name}_dispatch",
            kind="dispatch_body",
            prompt_context=dispatch_context,
            depends_on=helper_names,
            assembly_order=order,
            element_spec=element,  # Reuse original spec for the dispatch body
        ))

        plan = DecompositionPlan(
            original_element=element,
            sub_elements=sub_elements,
            strategy=self.name,
            assembly_kind="function_chain",
            confidence=0.0,
        )
        plan.confidence = _compute_confidence(plan, uncertainty_signals)
        return plan

    def assemble(
        self,
        plan: DecompositionPlan,
        sub_results: dict[str, str],
        skeleton: str,
    ) -> Optional[str]:
        """Assemble helpers + dispatch body into complete code.

        For module-level functions: helper defs are concatenated, then the
        dispatch body replaces the original function's NotImplementedError.
        For methods: helpers are private methods on the same class; only the
        dispatch body is returned (helpers are separate elements handled by
        the splicer via their element_spec.parent_class).
        """
        # Collect helper definitions and the dispatch body
        helpers: list[SubElement] = [
            s for s in plan.sub_elements if s.kind == "helper"
        ]
        dispatch_sub = next(
            (s for s in plan.sub_elements if s.kind == "dispatch_body"),
            None,
        )
        if dispatch_sub is None:
            return None

        dispatch_code = sub_results.get(dispatch_sub.name)
        if dispatch_code is None:
            return None

        if _is_method(plan.original_element):
            # For methods, helpers become separate class methods — the splicer
            # handles them individually. Only return the dispatch body.
            return dispatch_code

        # For module-level functions, concatenate helper defs + dispatch body.
        parts: list[str] = []
        for helper in sorted(helpers, key=lambda h: h.assembly_order):
            helper_code = sub_results.get(helper.name)
            if helper_code is None:
                return None
            rendered = _render_helper_def(helper, helper_code)
            if rendered is not None:
                parts.append(rendered)

        # Append the dispatch body (just the body, not a full def)
        parts.append(textwrap.dedent(dispatch_code).strip())

        assembled = "\n\n\n".join(parts)

        # Validate
        try:
            ast.parse(assembled)
        except SyntaxError:
            logger.warning(
                "Function chain assembly validation failed for %s",
                plan.original_element.name,
                exc_info=True,
            )
            return None

        return assembled


# ── Moderate Decomposer (REQ-MP-900) ────────────────────────────────


class ModerateDecomposer:
    """Analyzes MODERATE elements and produces decomposition plans."""

    def __init__(
        self,
        strategies: Optional[list[Any]] = None,
        config: Optional[MicroPrimeConfig] = None,
        template_registry: Optional[Any] = None,
    ) -> None:
        self._config = config or MicroPrimeConfig()
        self._template_registry = template_registry
        self._strategies: list[Any] = strategies or [
            ClassDecomposeStrategy(config=self._config, template_registry=template_registry),
            FunctionChainStrategy(config=self._config),
        ]

    def can_decompose(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        classification_reason: str,
        classification_signals: Optional[set[str]] = None,
    ) -> bool:
        """Lightweight viability check for dry-run reports only.

        Delegates to strategy.can_handle() without building a full plan.
        Must not be called in the generation path — use decompose() instead.
        """
        if not self._config.decomposition_enabled:
            return False
        return any(
            s.can_handle(
                element, file_spec, manifest, classification_reason,
                classification_signals,
            )
            for s in self._strategies
        )

    def decompose(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        classification_reason: str,
        classification_signals: Optional[set[str]] = None,
    ) -> Optional[DecompositionPlan]:
        """Produce a decomposition plan, or None if no strategy applies.

        This is the single entry point for the generation path — it checks
        strategy applicability, builds the plan, and applies confidence/size
        filters in one pass.
        """
        if not self._config.decomposition_enabled:
            return None

        for s in self._strategies:
            if s.can_handle(
                element, file_spec, manifest, classification_reason,
                classification_signals,
            ):
                plan = s.plan(
                    element, file_spec, manifest, classification_reason,
                    classification_signals,
                )
                if plan is None:
                    continue
                # Ensure all non-deterministic sub-elements are SIMPLE/TRIVIAL
                sub_ok = True
                for sub in plan.sub_elements:
                    if sub.deterministic:
                        continue
                    if sub.element_spec is None:
                        sub_ok = False
                        break
                    tier, _reason, _details = classify_element_with_details(
                        sub.element_spec, file_spec, [], None, self._config,
                    )
                    if tier not in (
                        TierClassification.SIMPLE,
                        TierClassification.TRIVIAL,
                    ):
                        logger.debug(
                            "Plan for %s rejected: sub-element %s classified %s",
                            element.name, sub.name, tier.value,
                        )
                        sub_ok = False
                        break
                if not sub_ok:
                    continue
                if len(plan.sub_elements) > self._config.max_sub_elements:
                    logger.debug(
                        "Plan for %s rejected: %d sub-elements > max %d",
                        element.name, len(plan.sub_elements),
                        self._config.max_sub_elements,
                    )
                    continue
                if plan.confidence < self._config.decomposition_confidence_threshold:
                    logger.debug(
                        "Plan for %s rejected: confidence %.2f < threshold %.2f",
                        element.name, plan.confidence,
                        self._config.decomposition_confidence_threshold,
                    )
                    continue
                return plan

        return None

    def assemble(
        self,
        plan: DecompositionPlan,
        sub_results: dict[str, str],
        skeleton: str,
    ) -> Optional[str]:
        """Compose sub-element results into the complete element code."""
        for s in self._strategies:
            if s.name == plan.strategy:
                return s.assemble(plan, sub_results, skeleton)
        return None
