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
from startd8.utils.code_manifest import ElementKind, Param, Signature
from startd8.utils.file_assembler import DeterministicFileAssembler

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


# ── Class Decomposition Strategy (REQ-MP-901) ───────────────────────


class ClassDecomposeStrategy:
    """Decomposes MODERATE class elements into shell + optional attrs/init."""

    def __init__(self, config: Optional[MicroPrimeConfig] = None) -> None:
        self._config = config or MicroPrimeConfig()

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
        if not self.can_handle(
            element, file_spec, manifest, classification_reason,
            classification_signals,
        ):
            return None

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
            # NOTE: ForwardElementSpec disallows parent_class on CONSTANT kinds.
            # Use a METHOD spec with a minimal signature so validation passes.
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
                    kind=ElementKind.METHOD,
                    name="_class_attributes",
                    parent_class=element.name,
                    signature=Signature(
                        params=[Param(name="self")],
                        return_annotation="None",
                    ),
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
        # Start with the shell result
        shell_code = sub_results.get("class_shell")
        if shell_code is None:
            return None

        parts: list[str] = []
        sub_map = {s.name: s for s in plan.sub_elements}
        assembler = DeterministicFileAssembler()

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
            sig = assembler._render_signature(spec.signature)
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


# ── Moderate Decomposer (REQ-MP-900) ────────────────────────────────


class ModerateDecomposer:
    """Analyzes MODERATE elements and produces decomposition plans."""

    def __init__(
        self,
        strategies: Optional[list[Any]] = None,
        config: Optional[MicroPrimeConfig] = None,
    ) -> None:
        self._config = config or MicroPrimeConfig()
        self._strategies: list[Any] = strategies or [
            ClassDecomposeStrategy(config=self._config),
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
