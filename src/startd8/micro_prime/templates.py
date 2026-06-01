"""Template Registry for TRIVIAL element generation (REQ-MP-300–304).

Provides deterministic code templates for common patterns like ``__init__``,
``__repr__``, ``__eq__``, ``__hash__``, constants, app instances, type aliases,
simple properties, validation patterns, and dataclass boilerplate.
These bypass LLM generation entirely.

Phase 2 additions (REQ-MP-310–313):
- ``init_with_defaults``: ``__init__`` with optional params (defaults)
- ``init_varargs``: ``__init__`` with ``*args``/``**kwargs``
- ``simple_validation``: ``if not x: raise ValueError(...)``
- ``dataclass_boilerplate``: typed fields → class body for dataclass/Pydantic models

Safety guards (R4-S7, R5-S7, R2-S7, R5-S4):
- Name sanitization via ``_is_safe_identifier()``
- Safe literal serialization via ``repr()``
- No-regression guard: reject if output equals DFA stub
"""

from __future__ import annotations

import ast
import keyword
from dataclasses import dataclass
from typing import Callable, Optional

from startd8.forward_manifest import (
    ContractCategory,
    ForwardElementSpec,
    ForwardFileSpec,
    InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind, ParamKind

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Render contract (R4-S2)
# ═══════════════════════════════════════════════════════════════════════════
#
# All templates MUST emit **body-only** code (no ``def`` line, no ``class``
# line).  The splicer (``splicer.py``) handles:
#   1. Locating the ``raise NotImplementedError`` stub in the skeleton
#   2. Determining the stub's indentation
#   3. Re-indenting the template output to match
#
# Rules:
#   - Return the function/method body lines only, zero-indented
#   - For constants/variables: return the full assignment (``NAME = value``)
#   - For class boilerplate: return field declarations, zero-indented
#   - No trailing newline required (splicer adds newlines during splice)
#   - Multi-line bodies use ``\n`` to separate lines (not indent — splicer
#     applies indentation)
#
# The ``_validate_ast`` function verifies each output is valid Python by
# wrapping body-only code in ``def _check():`` before ``ast.parse()``.

# ═══════════════════════════════════════════════════════════════════════════
# Template entry + registry helpers (REQ-MP-300)
# ═══════════════════════════════════════════════════════════════════════════


def _safe_match(
    template: CodeTemplate,
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
) -> bool:
    """Call match_fn with guardrails; never raise."""
    try:
        return bool(template.match_fn(element, file_spec, contracts))
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Template match_fn failed for %s: %s", template.name, exc)
        return False


def _safe_render(
    template: CodeTemplate,
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
) -> Optional[str]:
    """Call render_fn with guardrails; never raise."""
    try:
        return template.render_fn(element, file_spec, contracts)
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("Template render_fn failed for %s: %s", template.name, exc)
        return None


_DFA_STUB_PATTERNS = frozenset({
    "raise NotImplementedError",
    "raise NotImplementedError()",
    "...",
})

# "pass" is a valid body for empty __init__ — handled separately
_DFA_STUB_PASS = "pass"


def _is_dfa_stub(code: str, *, element_name: str = "") -> bool:
    """Check whether *code* is equivalent to a DFA stub placeholder (R5-S4).

    Returns True if the output is no better than what DFA already provides.
    ``pass`` is exempted for dunder methods where it is semantically correct
    (e.g., empty ``__init__``).
    """
    stripped = code.strip()
    if stripped in _DFA_STUB_PATTERNS:
        return True
    if stripped == _DFA_STUB_PASS:
        # "pass" is valid for empty __init__, __del__, etc.
        return not element_name.startswith("__")
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2 template generators (REQ-MP-310–313)
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# Template implementations (REQ-MP-301–303)
# ═══════════════════════════════════════════════════════════════════════════


# Mapping from dunder method names to template generators


# ═══════════════════════════════════════════════════════════════════════════
# Go templates — deterministic code for common Go patterns
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# Java templates — deterministic code for common Java patterns
# ═══════════════════════════════════════════════════════════════════════════

# Canonical source: languages/java.py — import to avoid triplication.
from startd8.languages.java import _JAVA_RESERVED


# ═══════════════════════════════════════════════════════════════════════════
# C# templates — deterministic code for common C# patterns
# ═══════════════════════════════════════════════════════════════════════════

from startd8.languages.csharp import _CSHARP_RESERVED

# Models + per-language templates extracted to sibling modules (Tier-2);
# re-exported so `from ...micro_prime.templates import TemplateRegistry/GO_TEMPLATES/...` stays green.
from .templates_core import CodeTemplate, TemplateMatch  # noqa: F401
from .templates_python import (  # noqa: F401
    TEMPLATES,
    _APP_INSTANCE_NAMES,
    _DUNDER_TEMPLATES,
    _FRAMEWORK_IMPORTS,
    _coerce_constant_value,
    _detect_framework_constructor,
    _find_config_contract,
    _find_init_child,
    _is_dataclass_boilerplate_match,
    _is_property_setter,
    _is_safe_identifier,
    _is_simple_validation_match,
    _safe_default_repr,
    _template_app_instance,
    _template_config_constant,
    _template_constant,
    _template_context_enter,
    _template_context_exit,
    _template_dataclass_boilerplate,
    _template_eq,
    _template_hash,
    _template_init,
    _template_property_getter,
    _template_property_setter,
    _template_repr,
    _template_simple_validation,
    _template_str,
    _template_type_alias,
)
from .templates_go import (  # noqa: F401
    GO_TEMPLATES,
    _go_close_match,
    _go_close_render,
    _go_constructor_match,
    _go_constructor_render,
    _go_error_match,
    _go_error_render,
    _go_getter_match,
    _go_getter_render,
    _go_grpc_method_match,
    _go_grpc_method_render,
    _go_http_handler_match,
    _go_http_handler_render,
    _go_main_match,
    _go_main_render,
    _go_setter_match,
    _go_setter_render,
    _go_stringer_match,
    _go_stringer_render,
    _go_test_func_match,
    _go_test_func_render,
)
from .templates_java import (  # noqa: F401
    JAVA_TEMPLATES,
    _is_java_safe_identifier,
    _java_builder_match,
    _java_builder_render,
    _java_constructor_match,
    _java_constructor_render,
    _java_equals_match,
    _java_equals_render,
    _java_getter_match,
    _java_getter_render,
    _java_hashcode_match,
    _java_hashcode_render,
    _java_setter_match,
    _java_setter_render,
    _java_spring_main_match,
    _java_spring_main_render,
    _java_tostring_match,
    _java_tostring_render,
)
from .templates_csharp import (  # noqa: F401
    CSHARP_TEMPLATES,
    _csharp_async_method_match,
    _csharp_async_method_render,
    _csharp_constructor_match,
    _csharp_constructor_render,
    _csharp_di_constructor_match,
    _csharp_di_constructor_render,
    _csharp_dispose_match,
    _csharp_dispose_render,
    _csharp_equals_match,
    _csharp_equals_render,
    _csharp_gethashcode_match,
    _csharp_gethashcode_render,
    _csharp_property_match,
    _csharp_property_render,
    _csharp_tostring_match,
    _csharp_tostring_render,
    _is_csharp_safe_identifier,
)
from .templates_nodejs import (  # noqa: F401
    NODEJS_TEMPLATES,
    _JS_RESERVED,
    _is_js_safe_identifier,
    _js_async_method_match,
    _js_async_method_render,
    _js_constructor_match,
    _js_constructor_render,
    _js_express_handler_match,
    _js_express_handler_render,
    _js_getter_match,
    _js_getter_render,
    _js_setter_match,
    _js_setter_render,
    _js_tostring_match,
    _js_tostring_render,
)


# ═══════════════════════════════════════════════════════════════════════════
# Node.js templates — deterministic code for common JS/TS patterns
# ═══════════════════════════════════════════════════════════════════════════

# JavaScript reserved words (ES2023+)


def try_template_match(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
) -> Optional[str]:
    """Try to match and render a template; return code or None (REQ-MP-300)."""
    match = try_template_match_with_name(element, file_spec, contracts)
    return match.code if match else None


def try_template_match_with_name(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    contracts: list[InterfaceContract],
    extra_templates: Optional[list[CodeTemplate]] = None,
    language_id: str = "python",
) -> Optional[TemplateMatch]:
    """Try to match and render a template; return TemplateMatch or None."""
    # Name sanitization guard (R5-S7): reject elements with unsafe names
    if not _is_safe_identifier(element.name.lstrip("_")):
        logger.debug("Unsafe element name rejected: %r", element.name)
        return None

    templates_to_try = extra_templates if extra_templates is not None else TEMPLATES
    for template in templates_to_try:
        if not _safe_match(template, element, file_spec, contracts):
            continue
        body = _safe_render(template, element, file_spec, contracts)
        if not body:
            continue
        # No-regression guard (R5-S4): reject if output equals DFA stub
        if _is_dfa_stub(body, element_name=element.name):
            logger.debug(
                "Template %s output for %s is a DFA stub — skipping",
                template.name, element.name,
            )
            continue
        # REQ-MP-1200: AST validation is Python-only. Non-Python templates
        # are deterministic and pre-tested — skip ast.parse() which would
        # reject valid Go/Java/C#/JS output.
        if language_id == "python" and not _validate_ast(body, element):
            logger.warning(
                "Template output for %s failed AST validation, skipping",
                element.name,
            )
            continue
        return TemplateMatch(name=template.name, code=body)
    return None


# Templates that require explicit opt-in via the relaxed allowlist (R1-S7).
# These are not included in the default TEMPLATES list.
RELAXED_TEMPLATES: list[CodeTemplate] = []

# REQ-MP-1200: Polyglot template dispatch map — declarative tier registry
# pattern (Leg 10 #37). Maps language_id → template list. Unknown languages
# fall back to Python templates.
_LANGUAGE_TEMPLATES: dict[str, list[CodeTemplate]] = {
    "python": TEMPLATES,
    "java": JAVA_TEMPLATES,
    "go": GO_TEMPLATES,
    "csharp": CSHARP_TEMPLATES,
    "nodejs": NODEJS_TEMPLATES,
}


class TemplateRegistry:
    """Registry of deterministic code templates for trivial elements.

    Matches elements to templates based on element kind, name, and manifest
    metadata. Output is always validated via ``ast.parse()`` (REQ-MP-304).

    Args:
        enabled: Whether template matching is active (REQ-MP-303).
        relaxed_allowlist: Optional set of relaxed template names to enable.
            Only templates whose name appears in this set are active.
            Default ``None`` = no relaxed templates (R1-S7).
        language_id: Language identifier. When ``"java"``, Java-specific
            templates are included and AST validation uses Java rules.
    """

    def __init__(
        self,
        enabled: bool = True,
        relaxed_allowlist: Optional[frozenset[str]] = None,
        language_id: str = "python",
    ) -> None:
        self._enabled = enabled
        self._relaxed_allowlist = relaxed_allowlist or frozenset()
        self._language_id = language_id

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def relaxed_allowlist(self) -> frozenset[str]:
        """Currently enabled relaxed template names."""
        return self._relaxed_allowlist

    def _active_templates(self) -> list[CodeTemplate]:
        """Return the list of active templates (standard + language + allowlisted relaxed)."""
        base = _LANGUAGE_TEMPLATES.get(self._language_id, TEMPLATES)
        result = list(base)
        if self._relaxed_allowlist:
            result.extend(
                t for t in RELAXED_TEMPLATES
                if t.name in self._relaxed_allowlist
            )
        return result

    @staticmethod
    def has_templates_for(language_id: str) -> bool:
        """Return True if the given language has template definitions."""
        return language_id in _LANGUAGE_TEMPLATES

    def match(
        self,
        element: ForwardElementSpec,
        file_spec: Optional[ForwardFileSpec] = None,
        contracts: Optional[list[InterfaceContract]] = None,
    ) -> Optional[TemplateMatch]:
        """Attempt to match an element to a template.

        Returns the generated code body if a template matches and produces
        valid Python, or ``None`` if no template applies.

        Args:
            element: The manifest element to match.
            file_spec: Optional file spec for additional context.

        Returns:
            Generated code string or None.
        """
        if not self._enabled:
            return None
        if file_spec is None:
            from startd8.forward_manifest import ForwardFileSpec
            file_spec = ForwardFileSpec(file="", elements=[], imports=[])
        contracts = contracts or []
        return try_template_match_with_name(
            element, file_spec, contracts,
            extra_templates=self._active_templates(),
            language_id=self._language_id,
        )

    def is_trivial(
        self,
        element: ForwardElementSpec,
        file_spec: Optional[ForwardFileSpec] = None,
        contracts: Optional[list[InterfaceContract]] = None,
    ) -> bool:
        """Check if an element would match a template without rendering."""
        if not self._enabled:
            return False
        if file_spec is None:
            from startd8.forward_manifest import ForwardFileSpec
            file_spec = ForwardFileSpec(file="", elements=[], imports=[])
        contracts = contracts or []
        return try_template_match_with_name(
            element, file_spec, contracts,
            extra_templates=self._active_templates(),
            language_id=self._language_id,
        ) is not None


def _validate_ast(body: str, element: ForwardElementSpec) -> bool:
    """Validate that the template output is valid Python (REQ-MP-304)."""
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE, ElementKind.TYPE_ALIAS):
        return _try_parse(body)

    wrapper = "def _check():\n"
    indented_body = "\n".join(
        f"    {line}" for line in body.splitlines()
    )
    return _try_parse(wrapper + indented_body)


def _try_parse(code: str) -> bool:
    """Try ast.parse(), return True on success."""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False
