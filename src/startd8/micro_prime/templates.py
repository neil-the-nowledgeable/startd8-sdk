"""Template Registry for TRIVIAL element generation (REQ-MP-300–304).

Provides deterministic code templates for common patterns like ``__init__``,
``__repr__``, ``__eq__``, ``__hash__``, constants, app instances, type aliases,
and simple properties. These bypass LLM generation entirely.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Callable, Optional

from startd8.forward_manifest import (
    ContractCategory,
    ForwardElementSpec,
    ForwardFileSpec,
    InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Template entry + registry helpers (REQ-MP-300)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CodeTemplate:
    """Deterministic code template entry."""

    name: str
    match_fn: Callable[
        [ForwardElementSpec, ForwardFileSpec, list[InterfaceContract]],
        bool,
    ]
    render_fn: Callable[
        [ForwardElementSpec, ForwardFileSpec, list[InterfaceContract]],
        str,
    ]


@dataclass(frozen=True)
class TemplateMatch:
    """Template match result."""

    name: str
    code: str


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
        logger.debug("Template render_fn failed for %s: %s", template.name, exc)
        return None


def _template_init(elem: ForwardElementSpec) -> Optional[str]:
    """Generate __init__ that stores all parameters as instance attributes."""
    if not elem.signature:
        return None
    params = [p for p in elem.signature.params if p.name not in ("self", "cls")]
    if not params:
        # Empty __init__ — no assignments needed
        return "pass"
    lines = []
    for p in params:
        lines.append(f"self.{p.name} = {p.name}")
    return "\n".join(lines)


def _template_repr(elem: ForwardElementSpec) -> Optional[str]:
    """Generate __repr__ using class name and init params."""
    if not elem.parent_class:
        return None
    # Try to infer fields from signature (if __repr__ has no params, use class name)
    return f'return f"{elem.parent_class}({{self.__dict__}})"'


def _template_str(elem: ForwardElementSpec) -> Optional[str]:
    """Generate __str__ with a simple string conversion."""
    if not elem.parent_class:
        return None
    return 'return str(self.__dict__)'


def _template_eq(elem: ForwardElementSpec) -> Optional[str]:
    """Generate __eq__ comparing __dict__ attributes."""
    return (
        "if not isinstance(other, self.__class__):\n"
        "    return NotImplemented\n"
        "return self.__dict__ == other.__dict__"
    )


def _template_hash(elem: ForwardElementSpec) -> Optional[str]:
    """Generate __hash__ based on hashable attributes."""
    return "return hash(tuple(sorted(self.__dict__.items())))"


def _template_constant(elem: ForwardElementSpec) -> Optional[str]:
    """Generate a constant placeholder based on type annotation."""
    if elem.signature and elem.signature.return_annotation:
        ann = elem.signature.return_annotation
        defaults = {
            "str": '""',
            "int": "0",
            "float": "0.0",
            "bool": "False",
            "list": "[]",
            "dict": "{}",
            "set": "set()",
            "tuple": "()",
            "None": "None",
        }
        for type_str, default in defaults.items():
            if ann == type_str:
                return f"{elem.name} = {default}"
        # Fallback for Optional, List, Dict etc.
        if ann.startswith("Optional"):
            return f"{elem.name} = None"
    return None


def _template_property_getter(elem: ForwardElementSpec) -> Optional[str]:
    """Generate a simple property getter returning self._name."""
    attr_name = elem.name.lstrip("_")
    return f"return self._{attr_name}"


# ═══════════════════════════════════════════════════════════════════════════
# Template implementations (REQ-MP-301–303)
# ═══════════════════════════════════════════════════════════════════════════


def _coerce_constant_value(value: str) -> str:
    """Coerce a contract constant_value to a safe Python literal string."""
    try:
        parsed = ast.literal_eval(value)
        return repr(parsed)
    except Exception:
        return repr(value)


def _find_config_contract(
    elem: ForwardElementSpec,
    contracts: list[InterfaceContract],
) -> Optional[InterfaceContract]:
    """Find a CONFIG_KEY contract that applies to this element."""
    for c in contracts:
        if c.category != ContractCategory.CONFIG_KEY:
            continue
        if c.constant_value is None:
            continue
        if elem.source_contract_id and c.contract_id == elem.source_contract_id:
            return c
        if c.env_var and c.env_var == elem.name:
            return c
        binding = c.binding_text or ""
        desc = c.description or ""
        if elem.name in binding or elem.name in desc:
            return c
    return None


def _template_config_constant(
    elem: ForwardElementSpec,
    _file: ForwardFileSpec,
    contracts: list[InterfaceContract],
) -> Optional[str]:
    """Generate constant from CONFIG_KEY contract (REQ-MP-301)."""
    contract = _find_config_contract(elem, contracts)
    if contract is None:
        return None
    rendered = _coerce_constant_value(contract.constant_value or "")
    annotation = (
        elem.signature.return_annotation
        if elem.signature and elem.signature.return_annotation
        else None
    )
    if annotation:
        return f"{elem.name}: {annotation} = {rendered}"
    return f"{elem.name} = {rendered}"


_APP_INSTANCE_NAMES = {"app", "application", "server", "api"}
_FRAMEWORK_IMPORTS = {
    ("flask", "Flask"): "Flask(__name__)",
    ("fastapi", "FastAPI"): "FastAPI()",
    ("starlette.applications", "Starlette"): "Starlette()",
    ("django.core.wsgi", "get_wsgi_application"): "get_wsgi_application()",
}


def _detect_framework_constructor(file_spec: ForwardFileSpec) -> Optional[str]:
    """Detect framework constructor from imports (REQ-MP-302)."""
    for imp in file_spec.imports:
        if imp.kind != "from":
            continue
        for name in imp.names:
            key = (imp.module, name)
            ctor = _FRAMEWORK_IMPORTS.get(key)
            if ctor:
                return ctor
    return None


def _template_app_instance(
    elem: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    _contracts: list[InterfaceContract],
) -> Optional[str]:
    """Generate app/server instance based on framework imports (REQ-MP-302)."""
    if elem.name.lower() not in _APP_INSTANCE_NAMES:
        return None
    ctor = _detect_framework_constructor(file_spec)
    if ctor is None:
        return None
    return f"{elem.name} = {ctor}"


def _template_type_alias(
    elem: ForwardElementSpec,
    _file: ForwardFileSpec,
    _contracts: list[InterfaceContract],
) -> Optional[str]:
    """Generate a type alias deterministically (REQ-MP-303)."""
    type_ann = getattr(elem, "type_annotation", None)
    value_repr = getattr(elem, "value_repr", None)
    alias = type_ann or value_repr
    if not alias:
        return None
    return f"{elem.name} = {alias}"

# Mapping from dunder method names to template generators
_DUNDER_TEMPLATES: dict[str, Callable[[ForwardElementSpec], Optional[str]]] = {
    "__init__": _template_init,
    "__repr__": _template_repr,
    "__str__": _template_str,
    "__eq__": _template_eq,
    "__hash__": _template_hash,
}


TEMPLATES: list[CodeTemplate] = [
    CodeTemplate(
        name="config_constant",
        match_fn=lambda e, _f, c: (
            e.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE)
            and _find_config_contract(e, c) is not None
        ),
        render_fn=lambda e, f, c: _template_config_constant(e, f, c) or "",
    ),
    CodeTemplate(
        name="app_instance",
        match_fn=lambda e, f, _c: (
            e.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE)
            and e.name.lower() in _APP_INSTANCE_NAMES
            and _detect_framework_constructor(f) is not None
        ),
        render_fn=lambda e, f, c: _template_app_instance(e, f, c) or "",
    ),
    CodeTemplate(
        name="type_alias",
        match_fn=lambda e, _f, _c: (
            e.kind == ElementKind.TYPE_ALIAS
            and (getattr(e, "type_annotation", None) or getattr(e, "value_repr", None))
        ),
        render_fn=lambda e, f, c: _template_type_alias(e, f, c) or "",
    ),
    CodeTemplate(
        name="property_getter",
        match_fn=lambda e, _f, _c: e.kind == ElementKind.PROPERTY,
        render_fn=lambda e, f, c: _template_property_getter(e) or "",
    ),
    CodeTemplate(
        name="dunder_method",
        match_fn=lambda e, _f, _c: e.name in _DUNDER_TEMPLATES,
        render_fn=lambda e, f, c: _DUNDER_TEMPLATES[e.name](e) or "",
    ),
    CodeTemplate(
        name="typed_constant_default",
        match_fn=lambda e, _f, _c: (
            e.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE)
            and _template_constant(e) is not None
        ),
        render_fn=lambda e, f, c: _template_constant(e) or "",
    ),
]


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
) -> Optional[TemplateMatch]:
    """Try to match and render a template; return TemplateMatch or None."""
    for template in TEMPLATES:
        if not _safe_match(template, element, file_spec, contracts):
            continue
        body = _safe_render(template, element, file_spec, contracts)
        if not body:
            continue
        if not _validate_ast(body, element):
            logger.warning(
                "Template output for %s failed AST validation, skipping",
                element.name,
            )
            continue
        return TemplateMatch(name=template.name, code=body)
    return None


class TemplateRegistry:
    """Registry of deterministic code templates for trivial elements.

    Matches elements to templates based on element kind, name, and manifest
    metadata. Output is always validated via ``ast.parse()`` (REQ-MP-304).

    Args:
        enabled: Whether template matching is active (REQ-MP-303).
    """

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

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
            return None
        contracts = contracts or []
        return try_template_match_with_name(element, file_spec, contracts)

    def _try_match(
        self,
        element: ForwardElementSpec,
        file_spec: Optional[ForwardFileSpec],
        contracts: list[InterfaceContract],
    ) -> Optional[CodeTemplate]:
        """Internal matching logic — returns template or None."""
        if file_spec is None:
            return None
        for template in TEMPLATES:
            if _safe_match(template, element, file_spec, contracts):
                return template
        return None

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
            return False
        contracts = contracts or []
        return self._try_match(element, file_spec, contracts) is not None


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
