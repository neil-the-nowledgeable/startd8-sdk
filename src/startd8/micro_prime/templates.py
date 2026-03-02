"""Template Registry for TRIVIAL element generation (REQ-MP-300–304).

Provides deterministic code templates for common patterns like ``__init__``,
``__repr__``, ``__eq__``, ``__hash__``, constants, and simple properties.
These bypass LLM generation entirely.
"""

from __future__ import annotations

import ast
from typing import Callable, Optional

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Built-in template functions (REQ-MP-301)
# ═══════════════════════════════════════════════════════════════════════════


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
# Template Registry (REQ-MP-300, 302, 303, 304)
# ═══════════════════════════════════════════════════════════════════════════

# Mapping from dunder method names to template generators
_DUNDER_TEMPLATES: dict[str, Callable[[ForwardElementSpec], Optional[str]]] = {
    "__init__": _template_init,
    "__repr__": _template_repr,
    "__str__": _template_str,
    "__eq__": _template_eq,
    "__hash__": _template_hash,
}


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
    ) -> Optional[str]:
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

        body = self._try_match(element, file_spec)
        if body is None:
            return None

        # REQ-MP-304: Validate output passes ast.parse()
        if not self._validate_ast(body, element):
            logger.warning(
                "Template output for %s failed AST validation, skipping",
                element.name,
            )
            return None

        return body

    def _try_match(
        self,
        element: ForwardElementSpec,
        file_spec: Optional[ForwardFileSpec],
    ) -> Optional[str]:
        """Internal matching logic — returns raw body or None."""
        # Constants and variables (REQ-MP-301)
        if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
            return _template_constant(element)

        # Properties (REQ-MP-301)
        if element.kind == ElementKind.PROPERTY:
            return _template_property_getter(element)

        # Dunder methods (REQ-MP-301)
        if element.name in _DUNDER_TEMPLATES:
            template_fn = _DUNDER_TEMPLATES[element.name]
            return template_fn(element)

        return None

    def _validate_ast(self, body: str, element: ForwardElementSpec) -> bool:
        """Validate that the template output is valid Python (REQ-MP-304).

        For function/method bodies, wraps in a function definition before parsing.
        For constants, parses directly.
        """
        if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
            # Constants are full assignment statements
            return _try_parse(body)

        # Function/method bodies need a wrapper to parse
        wrapper = "def _check():\n"
        indented_body = "\n".join(
            f"    {line}" for line in body.splitlines()
        )
        return _try_parse(wrapper + indented_body)

    def is_trivial(self, element: ForwardElementSpec) -> bool:
        """Check if an element would match a template without generating code.

        Useful for classification without the cost of generation + validation.
        """
        if not self._enabled:
            return False
        if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
            return True
        if element.kind == ElementKind.PROPERTY:
            return True
        if element.name in _DUNDER_TEMPLATES:
            return True
        return False


def _try_parse(code: str) -> bool:
    """Try ast.parse(), return True on success."""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False
