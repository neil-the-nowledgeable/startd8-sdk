# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Java element templates (extracted from templates.py, Tier-2)."""

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


def _is_java_safe_identifier(name: str) -> bool:
    """Check that *name* is a valid Java identifier."""
    return (
        isinstance(name, str)
        and name.isidentifier()
        and name not in _JAVA_RESERVED
    )


def _java_getter_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match JavaBean getter: getName / isEnabled."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    name = elem.name
    return bool(
        (name.startswith("get") and len(name) > 3 and name[3].isupper())
        or (name.startswith("is") and len(name) > 2 and name[2].isupper())
    )


def _java_getter_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render JavaBean getter: return this.fieldName;"""
    name = elem.name
    if name.startswith("get"):
        field_name = name[3:4].lower() + name[4:]
    elif name.startswith("is"):
        field_name = name[2:3].lower() + name[3:]
    else:
        return None
    if not _is_java_safe_identifier(field_name):
        return None
    return f"return this.{field_name};"


def _java_setter_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match JavaBean setter: setName."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    name = elem.name
    return bool(name.startswith("set") and len(name) > 3 and name[3].isupper())


def _java_setter_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render JavaBean setter: this.fieldName = value;"""
    name = elem.name
    field_name = name[3:4].lower() + name[4:]
    if not _is_java_safe_identifier(field_name):
        return None
    # Derive param name from signature
    param_name = field_name
    if elem.signature:
        non_self = [p for p in elem.signature.params if p.name not in ("self", "cls")]
        if non_self:
            param_name = non_self[0].name
    return f"this.{field_name} = {param_name};"


def _java_constructor_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match Java constructor (name matches parent class)."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    return bool(elem.parent_class and elem.name == elem.parent_class)


def _java_constructor_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render constructor: field assignments from params."""
    if not elem.signature:
        return None
    params = [p for p in elem.signature.params if p.name not in ("self", "cls")]
    if not params:
        return "// no-op constructor"
    lines = []
    for p in params:
        if not _is_java_safe_identifier(p.name):
            return None
        lines.append(f"this.{p.name} = {p.name};")
    return "\n".join(lines)


def _java_equals_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    return elem.name == "equals" and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)


def _java_equals_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    cls = elem.parent_class or "this.getClass()"
    return (
        f"if (this == obj) return true;\n"
        f"if (obj == null || getClass() != obj.getClass()) return false;\n"
        f"{cls} other = ({cls}) obj;\n"
        f"return java.util.Objects.equals(this, other);"
    )


def _java_hashcode_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    return elem.name == "hashCode" and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)


def _java_hashcode_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    return "return java.util.Objects.hash();"


def _java_tostring_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    return elem.name == "toString" and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)


def _java_tostring_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    cls = elem.parent_class or "Object"
    return f'return "{cls}{{" + "}}";'


def _java_builder_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match a builder() factory method."""
    return (
        elem.name == "builder"
        and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)
        and bool(elem.parent_class)
    )


def _java_builder_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    cls = elem.parent_class
    return f"return new {cls}.Builder();"


def _java_spring_main_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match Spring Boot main method."""
    return (
        elem.name == "main"
        and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)
    )


def _java_spring_main_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    cls = elem.parent_class or "Application"
    return f"SpringApplication.run({cls}.class, args);"


JAVA_TEMPLATES: list[CodeTemplate] = [
    CodeTemplate(name="java_getter", match_fn=_java_getter_match, render_fn=_java_getter_render),
    CodeTemplate(name="java_setter", match_fn=_java_setter_match, render_fn=_java_setter_render),
    CodeTemplate(name="java_constructor", match_fn=_java_constructor_match, render_fn=_java_constructor_render),
    CodeTemplate(name="java_equals", match_fn=_java_equals_match, render_fn=_java_equals_render),
    CodeTemplate(name="java_hashcode", match_fn=_java_hashcode_match, render_fn=_java_hashcode_render),
    CodeTemplate(name="java_tostring", match_fn=_java_tostring_match, render_fn=_java_tostring_render),
    CodeTemplate(name="java_builder", match_fn=_java_builder_match, render_fn=_java_builder_render),
    CodeTemplate(name="java_spring_main", match_fn=_java_spring_main_match, render_fn=_java_spring_main_render),
]
