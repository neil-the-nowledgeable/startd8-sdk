"""Clause-to-template mapper for SIMPLE function-body decomposition (Phase 3).

Maps docstring responsibility clauses to existing templates for zero-LLM
assembly.  Unlike ``FunctionChainStrategy`` (MODERATE tier, LLM-generated
helpers), this produces deterministic code from template composition.

Integration point: ``MicroPrimeEngine._handle_simple()`` calls
``FunctionBodyDecomposer.try_decompose()`` after the template-first
short-circuit and before Ollama generation.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Optional

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.micro_prime.decomposer import _parse_responsibilities
from startd8.micro_prime.templates import (
    TemplateRegistry,
    _is_dfa_stub,
    _is_safe_identifier,
)
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature

logger = get_logger(__name__)

# Decorators that are safe for function-body decomposition (R2-S4).
_SAFE_DECORATORS: frozenset[str] = frozenset({
    "staticmethod",
    "classmethod",
    "property",
    "abstractmethod",
    "overload",
    "override",
})

# ── Clause signal patterns ───────────────────────────────────────────

# Each entry: (compiled regex, template_name)
_CLAUSE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:validate|check|verify|ensure)\b", re.IGNORECASE), "simple_validation"),
    (re.compile(r"\b(?:initialize|init|set\s*up|store|assign)\b", re.IGNORECASE), "dunder___init__"),
    (re.compile(r"\b(?:return\s+string|represent|display|format)\b", re.IGNORECASE), "dunder___repr__"),
    (re.compile(r"\b(?:compare|equal|match)\b", re.IGNORECASE), "dunder___eq__"),
    (re.compile(r"\b(?:hash)\b", re.IGNORECASE), "dunder___hash__"),
    (re.compile(r"\b(?:constant|default|config)\b", re.IGNORECASE), "constant"),
]


@dataclass(frozen=True)
class ClauseMapping:
    """Maps a responsibility clause to a template + synthetic element spec."""

    clause_text: str
    template_name: str
    synthetic_spec: ForwardElementSpec
    confidence: float


# ── Synthetic spec builders ──────────────────────────────────────────


def _build_validation_spec(
    clause: str,
    element: ForwardElementSpec,
) -> Optional[ForwardElementSpec]:
    """Build a synthetic spec for ``simple_validation`` template."""
    # Extract first word after validate/check/verify/ensure as param name
    match = re.search(
        r"\b(?:validate|check|verify|ensure)\s+(?:the\s+)?(\w+)",
        clause, re.IGNORECASE,
    )
    param_name = match.group(1) if match else "value"
    if not _is_safe_identifier(param_name):
        return None

    func_name = f"validate_{param_name}"
    kind = ElementKind.METHOD if element.parent_class else ElementKind.FUNCTION
    params: list[Param] = []
    if element.parent_class:
        params.append(Param(name="self", kind=ParamKind.POSITIONAL))
    params.append(Param(name=param_name, kind=ParamKind.POSITIONAL))

    return ForwardElementSpec(
        kind=kind,
        name=func_name,
        signature=Signature(params=params, return_annotation=None),
        parent_class=element.parent_class,
        docstring_hint=clause,
    )


def _build_dunder_spec(
    dunder_name: str,
    element: ForwardElementSpec,
) -> Optional[ForwardElementSpec]:
    """Build a synthetic spec for a dunder method template."""
    params: list[Param] = [
        Param(name="self", kind=ParamKind.POSITIONAL),
    ]
    # __init__ forwards the original element's non-self params
    if dunder_name == "__init__" and element.signature:
        for p in element.signature.params:
            if p.name in ("self", "cls"):
                continue
            params.append(p)
    # __eq__ needs an `other` param
    elif dunder_name == "__eq__":
        params.append(Param(name="other", kind=ParamKind.POSITIONAL))

    return ForwardElementSpec(
        kind=ElementKind.METHOD,
        name=dunder_name,
        signature=Signature(params=params, return_annotation=None),
        parent_class=element.parent_class or element.name,
        docstring_hint=f"{dunder_name} method",
    )


def _build_constant_spec(
    clause: str,
    element: ForwardElementSpec,
) -> Optional[ForwardElementSpec]:
    """Build a synthetic spec for a constant/default template."""
    # Try to extract NAME = ... pattern from clause
    match = re.search(r"\b([A-Z_][A-Z0-9_]*)\b", clause)
    name = match.group(1) if match else "DEFAULT"
    if not _is_safe_identifier(name):
        return None

    return ForwardElementSpec(
        kind=ElementKind.CONSTANT,
        name=name,
        signature=None,
        type_annotation="str",
        docstring_hint=clause,
    )


# ── Core mapping functions ───────────────────────────────────────────


def map_clause_to_template(
    clause: str,
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    template_registry: TemplateRegistry,
) -> Optional[ClauseMapping]:
    """Map a single responsibility clause to a template.

    Returns ``ClauseMapping`` if the clause matches a known pattern AND the
    synthetic spec is TRIVIAL (template-matched). Returns ``None`` otherwise.
    """
    for pattern, template_key in _CLAUSE_PATTERNS:
        if not pattern.search(clause):
            continue

        # Build synthetic spec based on template type
        if template_key == "simple_validation":
            spec = _build_validation_spec(clause, element)
        elif template_key.startswith("dunder_"):
            dunder_name = template_key.replace("dunder_", "")
            spec = _build_dunder_spec(dunder_name, element)
        elif template_key == "constant":
            spec = _build_constant_spec(clause, element)
        else:
            continue  # pragma: no cover

        if spec is None:
            logger.debug("Synthetic spec build failed for clause: %s", clause)
            continue

        # Verify the synthetic spec is TRIVIAL (matches a template)
        if not template_registry.is_trivial(spec):
            logger.debug(
                "Clause '%s' mapped to %s but spec is not TRIVIAL",
                clause[:60], template_key,
            )
            continue

        return ClauseMapping(
            clause_text=clause,
            template_name=template_key,
            synthetic_spec=spec,
            confidence=0.8,
        )

    logger.debug("No template match for clause: %.80s", clause)
    return None


def map_all_clauses(
    clauses: list[str],
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    template_registry: TemplateRegistry,
) -> Optional[list[ClauseMapping]]:
    """Map all clauses to templates. All-or-nothing (R4-S1).

    Returns the full mapping list only when every clause succeeds.
    Returns ``None`` if any clause fails to map.
    """
    mappings: list[ClauseMapping] = []
    for i, clause in enumerate(clauses):
        mapping = map_clause_to_template(clause, element, file_spec, template_registry)
        if mapping is None:
            logger.info(
                "Clause %d/%d unmappable — aborting function-body decomposition: %s",
                i + 1, len(clauses), clause[:60],
            )
            return None
        mappings.append(mapping)

    logger.info(
        "All %d clauses mapped to templates for %s",
        len(mappings), element.name,
    )
    return mappings


# ── Function Body Decomposer ────────────────────────────────────────


class FunctionBodyDecomposer:
    """Decomposes SIMPLE functions into template-renderable clauses (Phase 3).

    Sits between the template-first short-circuit and Ollama in
    ``_handle_simple``.  Unlike ``FunctionChainStrategy`` (MODERATE tier,
    LLM-generated helpers), this maps clauses to existing templates for
    zero-LLM assembly.
    """

    def __init__(
        self,
        template_registry: TemplateRegistry,
        confidence_threshold: float = 0.7,
    ) -> None:
        self._templates = template_registry
        self._confidence_threshold = confidence_threshold

    def try_decompose(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        contracts: list[InterfaceContract],
    ) -> Optional[str]:
        """Attempt to decompose a SIMPLE function into template-rendered clauses.

        Returns assembled code string on success, ``None`` on failure.
        Caller (``engine._handle_simple``) falls back to Ollama on ``None``.
        """
        # ── Applicability checks ─────────────────────────────────────
        if element.kind not in (
            ElementKind.FUNCTION, ElementKind.METHOD,
            ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD,
        ):
            return None

        if not element.docstring_hint:
            return None

        # Decorator guard (R2-S4)
        if element.decorators:
            for dec in element.decorators:
                # Extract base decorator name (strip parens, args)
                base = dec.lstrip("@").split("(")[0].split(".")[-1]
                if base not in _SAFE_DECORATORS:
                    logger.debug(
                        "Function-body decompose rejected for %s: unsafe decorator %s",
                        element.name, dec,
                    )
                    return None

        # Parse responsibility clauses
        clauses = _parse_responsibilities(element.docstring_hint)
        if len(clauses) < 2:
            return None

        # ── Map all clauses to templates ─────────────────────────────
        mappings = map_all_clauses(clauses, element, file_spec, self._templates)
        if mappings is None:
            return None

        # Check confidence threshold
        avg_confidence = sum(m.confidence for m in mappings) / len(mappings)
        if avg_confidence < self._confidence_threshold:
            logger.debug(
                "Function-body decompose rejected for %s: avg confidence %.2f < %.2f",
                element.name, avg_confidence, self._confidence_threshold,
            )
            return None

        # ── Render each clause via template ──────────────────────────
        rendered_parts: list[str] = []
        for mapping in mappings:
            match = self._templates.match(
                mapping.synthetic_spec, file_spec, contracts,
            )
            if match is None:
                logger.debug(
                    "Template render failed for clause: %s",
                    mapping.clause_text[:60],
                )
                return None

            # No-regression guard (R5-S4)
            if _is_dfa_stub(match.code, element_name=mapping.synthetic_spec.name):
                logger.debug(
                    "Template output is DFA stub for clause: %s",
                    mapping.clause_text[:60],
                )
                return None

            rendered_parts.append(match.code)

        # ── Assemble ─────────────────────────────────────────────────
        assembled = "\n".join(rendered_parts)

        # ast.parse syntax gate (R6-S1)
        try:
            # Body-only code: wrap in def to validate
            ast.parse(f"def _check():\n    {assembled.replace(chr(10), chr(10) + '    ')}")
        except SyntaxError:
            logger.debug(
                "Function-body decompose syntax validation failed for %s",
                element.name,
            )
            return None

        logger.info(
            "Function-body decomposition succeeded for %s: %d clauses, 0 LLM calls",
            element.name, len(mappings),
        )
        return assembled
