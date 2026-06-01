# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Node.js/JavaScript element templates (extracted from templates.py, Tier-2)."""

from __future__ import annotations

import ast  # noqa: F401
import keyword  # noqa: F401
from dataclasses import dataclass  # noqa: F401
from typing import Callable, Optional  # noqa: F401

from startd8.forward_manifest import (  # noqa: F401
    ContractCategory, ForwardElementSpec, ForwardFileSpec, InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind, ParamKind  # noqa: F401
from startd8.languages.java import _JAVA_RESERVED  # noqa: F401
from startd8.languages.csharp import _CSHARP_RESERVED  # noqa: F401

from .templates_core import CodeTemplate, TemplateMatch  # noqa: F401

logger = get_logger(__name__)


_JS_RESERVED: frozenset[str] = frozenset({
    "abstract", "arguments", "await", "boolean", "break", "byte", "case",
    "catch", "char", "class", "const", "continue", "debugger", "default",
    "delete", "do", "double", "else", "enum", "eval", "export", "extends",
    "false", "final", "finally", "float", "for", "function", "goto", "if",
    "implements", "import", "in", "instanceof", "int", "interface", "let",
    "long", "native", "new", "null", "package", "private", "protected",
    "public", "return", "short", "static", "super", "switch", "synchronized",
    "this", "throw", "throws", "transient", "true", "try", "typeof", "var",
    "void", "volatile", "while", "with", "yield",
})


def _is_js_safe_identifier(name: str) -> bool:
    """Check that *name* is a valid JavaScript identifier."""
    return (
        isinstance(name, str)
        and name.isidentifier()
        and name not in _JS_RESERVED
    )


def _js_constructor_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match JS class constructor."""
    return (
        elem.name == "constructor"
        and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)
        and bool(elem.parent_class)
    )


def _js_constructor_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render JS constructor: this.field = param assignments."""
    if not elem.signature:
        return None
    params = [p for p in elem.signature.params if p.name not in ("self", "cls")]
    if not params:
        return "// no-op constructor"
    lines = []
    for p in params:
        if not _is_js_safe_identifier(p.name):
            return None
        lines.append(f"this.{p.name} = {p.name};")
    return "\n".join(lines)


def _js_tostring_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    return elem.name == "toString" and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)


def _js_tostring_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    cls = elem.parent_class or "Object"
    return f"return `{cls}{{}}`;"


def _js_getter_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match JS getter: getName / getItems."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    name = elem.name
    return bool(name.startswith("get") and len(name) > 3 and name[3].isupper())


def _js_getter_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    name = elem.name
    field = name[3:4].lower() + name[4:]
    if not _is_js_safe_identifier(field):
        return None
    return f"return this.{field};"


def _js_setter_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match JS setter: setName / setItems."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    name = elem.name
    return bool(name.startswith("set") and len(name) > 3 and name[3].isupper())


def _js_setter_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    name = elem.name
    field = name[3:4].lower() + name[4:]
    if not _is_js_safe_identifier(field):
        return None
    param = field
    if elem.signature:
        params = [p for p in elem.signature.params if p.name not in ("self", "cls")]
        if params:
            param = params[0].name
    return f"this.{field} = {param};"


def _js_async_method_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match async methods (name ends with Async or has async decorator)."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION, ElementKind.ASYNC_METHOD, ElementKind.ASYNC_FUNCTION):
        return False
    return bool(
        elem.kind in (ElementKind.ASYNC_METHOD, ElementKind.ASYNC_FUNCTION)
        or elem.name.endswith("Async")
    )


def _js_async_method_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    return "throw new Error('not implemented');"


def _js_express_handler_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match Express route handler (common names)."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    return elem.name in ("get", "post", "put", "delete", "patch", "handle", "handler")


def _js_express_handler_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    return "res.status(200).json({ status: 'ok' });"


NODEJS_TEMPLATES: list[CodeTemplate] = [
    CodeTemplate(name="js_constructor", match_fn=_js_constructor_match, render_fn=_js_constructor_render),
    CodeTemplate(name="js_tostring", match_fn=_js_tostring_match, render_fn=_js_tostring_render),
    CodeTemplate(name="js_getter", match_fn=_js_getter_match, render_fn=_js_getter_render),
    CodeTemplate(name="js_setter", match_fn=_js_setter_match, render_fn=_js_setter_render),
    CodeTemplate(name="js_async_method", match_fn=_js_async_method_match, render_fn=_js_async_method_render),
    CodeTemplate(name="js_express_handler", match_fn=_js_express_handler_match, render_fn=_js_express_handler_render),
]
