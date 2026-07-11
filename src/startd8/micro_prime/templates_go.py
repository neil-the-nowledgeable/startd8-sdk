# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Go element templates (extracted from templates.py, Tier-2)."""

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
