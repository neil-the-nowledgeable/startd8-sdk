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
        logger.info("Template render_fn failed for %s: %s", template.name, exc)
        return None


def _is_safe_identifier(name: str) -> bool:
    """Check that *name* is a valid Python identifier with no injection risk (R5-S7, R2-S7).

    Rejects names containing whitespace, non-identifier characters, or Python keywords.
    """
    return (
        isinstance(name, str)
        and name.isidentifier()
        and not keyword.iskeyword(name)
    )


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


def _safe_default_repr(default: str) -> str:
    """Safely serialize a default value for use in templates (R4-S7).

    Uses ``ast.literal_eval`` + ``repr`` round-trip to prevent injection
    from malicious manifest values.
    """
    try:
        parsed = ast.literal_eval(default)
        return repr(parsed)
    except (ValueError, SyntaxError):
        # Not a literal — return the raw string only if it's a safe identifier
        # (e.g. ``None``, ``True``, ``False``, or a constant name).
        if default in ("None", "True", "False") or _is_safe_identifier(default):
            return default
        return repr(default)


def _template_init(elem: ForwardElementSpec) -> Optional[str]:
    """Generate __init__ that stores all parameters as instance attributes.

    Handles plain params, params with defaults, *args, and **kwargs.
    Returns None if any parameter name fails ``_is_safe_identifier``.
    """
    if not elem.signature:
        return None
    params = [p for p in elem.signature.params if p.name not in ("self", "cls")]
    if not params:
        # Empty __init__ — no assignments needed
        return "pass"

    has_varargs = any(p.kind == ParamKind.VAR_POSITIONAL for p in params)
    has_kwargs = any(p.kind == ParamKind.VAR_KEYWORD for p in params)
    regular_params = [
        p for p in params
        if p.kind not in (ParamKind.VAR_POSITIONAL, ParamKind.VAR_KEYWORD)
    ]

    lines: list[str] = []
    for p in regular_params:
        if not _is_safe_identifier(p.name):
            return None
        lines.append(f"self.{p.name} = {p.name}")

    # Store *args / **kwargs (REQ-MP-311)
    if has_varargs:
        lines.append("self._args = args")
    if has_kwargs:
        lines.append("self._kwargs = kwargs")

    return "\n".join(lines) if lines else "pass"


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
        if ann.startswith("Optional[") or ann == "Optional":
            return f"{elem.name} = None"
    return None


def _template_property_getter(elem: ForwardElementSpec) -> Optional[str]:
    """Generate a simple property getter returning self._name."""
    attr_name = elem.name.lstrip("_")
    return f"return self._{attr_name}"


def _is_property_setter(
    elem: ForwardElementSpec,
    _file: ForwardFileSpec,
    _contracts: list[InterfaceContract],
) -> bool:
    """Match a @name.setter property method."""
    if elem.kind != ElementKind.METHOD:
        return False
    if not elem.decorators:
        return False
    return any(d == f"{elem.name}.setter" for d in elem.decorators)


def _template_property_setter(
    elem: ForwardElementSpec,
    _file: ForwardFileSpec,
    _contracts: list[InterfaceContract],
) -> Optional[str]:
    """Generate a simple property setter: self._name = value."""
    attr_name = elem.name.lstrip("_")
    # Derive the value param name (first non-self param, or "value")
    value_param = "value"
    if elem.signature:
        non_self = [p for p in elem.signature.params if p.name not in ("self", "cls")]
        if non_self:
            value_param = non_self[0].name
    if not _is_safe_identifier(value_param):
        return None
    return f"self._{attr_name} = {value_param}"


def _template_context_enter(elem: ForwardElementSpec) -> Optional[str]:
    """Generate __enter__: return self."""
    return "return self"


def _template_context_exit(elem: ForwardElementSpec) -> Optional[str]:
    """Generate __exit__: return None (don't suppress exceptions).

    Returning None/False means exceptions propagate normally.
    The (exc_type, exc_val, exc_tb) params are on the def line
    (handled by the splicer), not in the body.
    """
    return "return None"


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2 template generators (REQ-MP-310–313)
# ═══════════════════════════════════════════════════════════════════════════


def _template_simple_validation(
    elem: ForwardElementSpec,
    _file: ForwardFileSpec,
    _contracts: list[InterfaceContract],
) -> Optional[str]:
    """Generate simple validation pattern: ``if not x: raise ValueError(...)`` (REQ-MP-312).

    Matches functions/methods with exactly one non-self parameter and a name
    starting with ``validate_`` or ``check_``.
    """
    if not elem.signature:
        return None
    params = [p for p in elem.signature.params if p.name not in ("self", "cls")]
    if len(params) != 1:
        return None
    param = params[0]
    if not _is_safe_identifier(param.name):
        return None
    param_name = param.name
    return (
        f"if not {param_name}:\n"
        f"    raise ValueError({repr(f'{param_name} must not be empty')})"
    )


def _is_simple_validation_match(
    elem: ForwardElementSpec,
    _file: ForwardFileSpec,
    _contracts: list[InterfaceContract],
) -> bool:
    """Check if element is a simple validation function."""
    if elem.kind not in (
        ElementKind.FUNCTION, ElementKind.METHOD,
        ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD,
    ):
        return False
    if not elem.name.startswith(("validate_", "check_")):
        return False
    if not elem.signature:
        return False
    params = [p for p in elem.signature.params if p.name not in ("self", "cls")]
    return len(params) == 1


def _find_init_child(
    class_name: str, file_spec: ForwardFileSpec,
) -> Optional[ForwardElementSpec]:
    """Find the ``__init__`` child element of *class_name* in *file_spec*."""
    for e in file_spec.elements:
        if e.parent_class == class_name and e.name == "__init__":
            return e
    return None


def _template_dataclass_boilerplate(
    elem: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    _contracts: list[InterfaceContract],
) -> Optional[str]:
    """Generate typed field declarations for dataclass/Pydantic models (REQ-MP-313, R6-S3).

    Matches CLASS elements with ``dataclass`` or ``BaseModel`` indicators and
    renders typed field assignments from child method signatures or the class's
    own metadata.
    """
    init_elem = _find_init_child(elem.name, file_spec)
    if init_elem is None or not init_elem.signature:
        return None

    params = [
        p for p in init_elem.signature.params if p.name not in ("self", "cls")
    ]
    if not params:
        return None

    lines: list[str] = []
    for p in params:
        if not _is_safe_identifier(p.name):
            return None
        if p.annotation:
            if p.default is not None:
                lines.append(f"{p.name}: {p.annotation} = {_safe_default_repr(p.default)}")
            else:
                lines.append(f"{p.name}: {p.annotation}")
        else:
            if p.default is not None:
                lines.append(f"{p.name} = {_safe_default_repr(p.default)}")
            else:
                # Untyped, no default — skip (can't generate safe field)
                return None

    return "\n".join(lines) if lines else None


def _is_dataclass_boilerplate_match(
    elem: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    _contracts: list[InterfaceContract],
) -> bool:
    """Check if element is a dataclass/Pydantic model with typed fields."""
    if elem.kind != ElementKind.CLASS:
        return False
    # Must have dataclass decorator or BaseModel in bases
    is_dataclass = any(d == "dataclass" or d.startswith("dataclass(") for d in elem.decorators)
    is_pydantic = any(b == "BaseModel" or b.endswith(".BaseModel") for b in elem.bases)
    if not is_dataclass and not is_pydantic:
        return False
    # Must have an __init__ child with params in the file_spec
    init_child = _find_init_child(elem.name, file_spec)
    if init_child is None or not init_child.signature:
        return False
    params = [
        p for p in init_child.signature.params if p.name not in ("self", "cls")
    ]
    return len(params) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Template implementations (REQ-MP-301–303)
# ═══════════════════════════════════════════════════════════════════════════


def _coerce_constant_value(value: str) -> str:
    """Coerce a contract constant_value to a safe Python literal string."""
    try:
        parsed = ast.literal_eval(value)
        return repr(parsed)
    except (ValueError, SyntaxError):
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
    "__enter__": _template_context_enter,
    "__exit__": _template_context_exit,
}


# ═══════════════════════════════════════════════════════════════════════════
# Go templates — deterministic code for common Go patterns
# ═══════════════════════════════════════════════════════════════════════════


def _go_constructor_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match Go constructor: NewFoo / NewBar."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    return bool(elem.name.startswith("New") and len(elem.name) > 3 and elem.name[3].isupper())


def _go_constructor_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render Go constructor: return &StructName{field assignments}."""
    struct_name = elem.name[3:]  # NewCartStore -> CartStore
    if not elem.signature:
        return f"return &{struct_name}{{}}"
    params = [p for p in elem.signature.params if p.name not in ("self", "cls")]
    if not params:
        return f"return &{struct_name}{{}}"
    fields = ", ".join(f"{p.name}: {p.name}" for p in params)
    return f"return &{struct_name}{{{fields}}}"


def _go_stringer_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match Go String() method (fmt.Stringer interface)."""
    return elem.name == "String" and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)


def _go_stringer_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    cls = elem.parent_class or "Object"
    return f'return fmt.Sprintf("{cls}{{}}")'


def _go_error_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match Go Error() method (error interface)."""
    return elem.name == "Error" and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)


def _go_error_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    cls = elem.parent_class or "error"
    return f'return fmt.Sprintf("{cls}: %v", e)'


def _go_close_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match Go Close() method (io.Closer interface)."""
    return elem.name == "Close" and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)


def _go_close_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    return "return nil"


def _go_getter_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match Go getter: GetName / GetID (exported method, no params beyond receiver)."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    name = elem.name
    return bool(name.startswith("Get") and len(name) > 3 and name[3].isupper())


def _go_getter_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render Go getter: return s.fieldName."""
    name = elem.name
    field_name = name[3:4].lower() + name[4:]
    return f"return s.{field_name}"


def _go_setter_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match Go setter: SetName / SetID."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    name = elem.name
    return bool(name.startswith("Set") and len(name) > 3 and name[3].isupper())


def _go_setter_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render Go setter: s.fieldName = value."""
    name = elem.name
    field_name = name[3:4].lower() + name[4:]
    param_name = field_name
    if elem.signature:
        params = [p for p in elem.signature.params if p.name not in ("self", "cls")]
        if params:
            param_name = params[0].name
    return f"s.{field_name} = {param_name}"


def _go_main_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match Go main() function."""
    return elem.name == "main" and elem.kind in (ElementKind.METHOD, ElementKind.FUNCTION)


def _go_main_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    return 'log.Println("starting server")'


def _go_test_func_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match Go test function: TestXxx."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    return bool(elem.name.startswith("Test") and len(elem.name) > 4 and elem.name[4].isupper())


def _go_test_func_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render Go test: table-driven test skeleton."""
    test_target = elem.name[4:]  # TestGetQuote -> GetQuote
    return (
        f'tests := []struct {{\n'
        f'\tname string\n'
        f'\twant interface{{}}\n'
        f'}}{{{{\"basic\", nil}}}}\n'
        f'for _, tt := range tests {{\n'
        f'\tt.Run(tt.name, func(t *testing.T) {{\n'
        f'\t\t// TODO: call {test_target} and assert result\n'
        f'\t\tt.Errorf("{test_target}: not implemented")\n'
        f'\t}})\n'
        f'}}'
    )


def _go_http_handler_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match Go HTTP handler: method with Handler/Handle in name or parent."""
    if elem.kind not in (ElementKind.METHOD, ElementKind.FUNCTION):
        return False
    name = elem.name
    if elem.signature and elem.signature.params:
        param_types = [p.annotation or "" for p in elem.signature.params]
        has_response_writer = any("ResponseWriter" in t for t in param_types)
        has_request = any("Request" in t for t in param_types)
        if has_response_writer and has_request:
            return True
    return "Handler" in name or "Handle" in name


def _go_http_handler_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render Go HTTP handler: write response with status."""
    return (
        'w.Header().Set("Content-Type", "application/json")\n'
        'w.WriteHeader(http.StatusOK)\n'
        'fmt.Fprintf(w, `{"status":"ok"}`)'
    )


def _go_grpc_method_match(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> bool:
    """Match Go gRPC method: method on a *Server type with context + proto request params."""
    if elem.kind != ElementKind.METHOD:
        return False
    if not elem.parent_class:
        return False
    # gRPC methods typically have (ctx context.Context, req *pb.XxxRequest) → (*pb.XxxResponse, error)
    if elem.signature and elem.signature.params:
        param_types = [p.annotation or "" for p in elem.signature.params]
        has_context = any("Context" in t for t in param_types)
        has_proto_req = any("Request" in t or "pb." in t for t in param_types)
        if has_context and has_proto_req:
            return True
    return False


def _go_grpc_method_render(
    elem: ForwardElementSpec, _f: ForwardFileSpec, _c: list[InterfaceContract],
) -> Optional[str]:
    """Render Go gRPC method: unimplemented status."""
    return f'return nil, status.Errorf(codes.Unimplemented, "method {elem.name} not implemented")'


GO_TEMPLATES: list[CodeTemplate] = [
    CodeTemplate(name="go_constructor", match_fn=_go_constructor_match, render_fn=_go_constructor_render),
    CodeTemplate(name="go_stringer", match_fn=_go_stringer_match, render_fn=_go_stringer_render),
    CodeTemplate(name="go_error", match_fn=_go_error_match, render_fn=_go_error_render),
    CodeTemplate(name="go_close", match_fn=_go_close_match, render_fn=_go_close_render),
    CodeTemplate(name="go_getter", match_fn=_go_getter_match, render_fn=_go_getter_render),
    CodeTemplate(name="go_setter", match_fn=_go_setter_match, render_fn=_go_setter_render),
    CodeTemplate(name="go_main", match_fn=_go_main_match, render_fn=_go_main_render),
    CodeTemplate(name="go_test_func", match_fn=_go_test_func_match, render_fn=_go_test_func_render),
    CodeTemplate(name="go_http_handler", match_fn=_go_http_handler_match, render_fn=_go_http_handler_render),
    CodeTemplate(name="go_grpc_method", match_fn=_go_grpc_method_match, render_fn=_go_grpc_method_render),
]


# ═══════════════════════════════════════════════════════════════════════════
# Java templates — deterministic code for common Java patterns
# ═══════════════════════════════════════════════════════════════════════════

# Canonical source: languages/java.py — import to avoid triplication.
from startd8.languages.java import _JAVA_RESERVED


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


# ═══════════════════════════════════════════════════════════════════════════
# C# templates — deterministic code for common C# patterns
# ═══════════════════════════════════════════════════════════════════════════

from startd8.languages.csharp import _CSHARP_RESERVED


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


# ═══════════════════════════════════════════════════════════════════════════
# Node.js templates — deterministic code for common JS/TS patterns
# ═══════════════════════════════════════════════════════════════════════════

# JavaScript reserved words (ES2023+)
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
        name="property_setter",
        match_fn=_is_property_setter,
        render_fn=_template_property_setter,
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
    # Phase 2 templates (REQ-MP-310–313)
    CodeTemplate(
        name="simple_validation",
        match_fn=_is_simple_validation_match,
        render_fn=_template_simple_validation,
    ),
    CodeTemplate(
        name="dataclass_boilerplate",
        match_fn=_is_dataclass_boilerplate_match,
        render_fn=_template_dataclass_boilerplate,
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
