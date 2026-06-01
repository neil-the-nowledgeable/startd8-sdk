# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""C# element templates (extracted from templates.py, Tier-2)."""

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


def _is_csharp_safe_identifier(name: str) -> bool:
    """Check that *name* is a valid C# identifier."""
    return (
        isinstance(name, str)
        and name.isidentifier()
        and name not in _CSHARP_RESERVED
    )


def _csharp_property_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match C# auto-property (PascalCase, PROPERTY kind)."""
    return elem.kind == ElementKind.PROPERTY


def _csharp_property_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render C# auto-property: get; set;"""
    return "get; set;"


def _csharp_constructor_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match C# constructor (name matches parent class or is .ctor)."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    return bool(
        elem.parent_class
        and (elem.name == elem.parent_class or elem.name == ".ctor")
    )


def _csharp_constructor_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render C# constructor: field assignments with _prefix convention."""
    if not elem.signature:
        return None
    params = [p for p in elem.signature.params if p.name not in ("self", "cls")]
    if not params:
        return "// no-op constructor"
    lines = []
    for p in params:
        if not _is_csharp_safe_identifier(p.name):
            return None
        field = f"_{p.name[0].lower()}{p.name[1:]}" if p.name[0].isupper() else f"_{p.name}"
        lines.append(f"{field} = {p.name};")
    return "\n".join(lines)


def _csharp_equals_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    return elem.name == "Equals" and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)


def _csharp_equals_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    cls = elem.parent_class or "this.GetType()"
    return (
        f"if (ReferenceEquals(this, obj)) return true;\n"
        f"if (obj is not {cls} other) return false;\n"
        f"return Equals(this, other);"
    )


def _csharp_gethashcode_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    return elem.name == "GetHashCode" and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)


def _csharp_gethashcode_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    return "return HashCode.Combine();"


def _csharp_tostring_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    return elem.name == "ToString" and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)


def _csharp_tostring_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    cls = elem.parent_class or "Object"
    return f'return $"{cls}{{}}";'


def _csharp_dispose_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match IDisposable.Dispose()."""
    return elem.name == "Dispose" and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)


def _csharp_dispose_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    return "// TODO: Dispose managed resources\nGC.SuppressFinalize(this);"


def _csharp_async_method_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match async methods (name ends with Async or return type is Task)."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    return bool(elem.name.endswith("Async"))


def _csharp_async_method_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render async stub: await Task.CompletedTask."""
    return "await Task.CompletedTask;\nthrow new NotImplementedException();"


def _csharp_di_constructor_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match DI constructor — constructor with interface parameters."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    if not elem.parent_class or elem.name != elem.parent_class:
        return False
    if not elem.signature:
        return False
    params = [p for p in elem.signature.params if p.name not in ("self", "cls")]
    return any(
        (p.annotation or "").startswith("I") and len(p.annotation or "") > 1
        for p in params
    )


def _csharp_di_constructor_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render DI constructor: private readonly fields + assignments."""
    if not elem.signature:
        return None
    params = [p for p in elem.signature.params if p.name not in ("self", "cls")]
    if not params:
        return None
    lines = []
    for p in params:
        if not _is_csharp_safe_identifier(p.name):
            return None
        field = f"_{p.name[0].lower()}{p.name[1:]}" if p.name[0].isupper() else f"_{p.name}"
        lines.append(f"{field} = {p.name} ?? throw new ArgumentNullException(nameof({p.name}));")
    return "\n".join(lines)


CSHARP_TEMPLATES: list[CodeTemplate] = [
    CodeTemplate(name="csharp_di_constructor", match_fn=_csharp_di_constructor_match, render_fn=_csharp_di_constructor_render),
    CodeTemplate(name="csharp_constructor", match_fn=_csharp_constructor_match, render_fn=_csharp_constructor_render),
    CodeTemplate(name="csharp_property", match_fn=_csharp_property_match, render_fn=_csharp_property_render),
    CodeTemplate(name="csharp_equals", match_fn=_csharp_equals_match, render_fn=_csharp_equals_render),
    CodeTemplate(name="csharp_gethashcode", match_fn=_csharp_gethashcode_match, render_fn=_csharp_gethashcode_render),
    CodeTemplate(name="csharp_tostring", match_fn=_csharp_tostring_match, render_fn=_csharp_tostring_render),
    CodeTemplate(name="csharp_dispose", match_fn=_csharp_dispose_match, render_fn=_csharp_dispose_render),
    CodeTemplate(name="csharp_async_method", match_fn=_csharp_async_method_match, render_fn=_csharp_async_method_render),
]
