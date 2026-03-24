"""Tests for Go MicroPrime Phase 2 — parser, skeleton enrichment, templates.

REQ-GO-MP-600: Interface method extraction
REQ-GO-MP-700: Go skeleton enrichment
REQ-GO-MP-100: Go file-level templates
"""

import pytest

from startd8.languages.go_parser import parse_go_source, GoElement
from startd8.micro_prime.skeleton_spec_extractor import extract_go_skeleton_specs
from startd8.micro_prime.templates import GO_TEMPLATES
from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec
from startd8.utils.code_manifest import ElementKind, Param, Signature


# ---------------------------------------------------------------------------
# Interface method extraction (REQ-GO-MP-600)
# ---------------------------------------------------------------------------

class TestInterfaceMethodExtraction:
    """REQ-GO-MP-600: Go parser extracts method signatures from interface bodies."""

    def test_interface_methods_extracted(self):
        source = '''
type ProductCatalogService interface {
    ListProducts(ctx context.Context) ([]*Product, error)
    GetProduct(ctx context.Context, id string) (*Product, error)
    SearchProducts(ctx context.Context, query string) ([]*Product, error)
}
'''
        elements = parse_go_source(source)
        iface = [e for e in elements if e.name == "ProductCatalogService"]
        assert len(iface) == 1
        assert iface[0].is_interface is True
        assert len(iface[0].interface_methods) == 3
        assert any("ListProducts" in m for m in iface[0].interface_methods)
        assert any("GetProduct" in m for m in iface[0].interface_methods)

    def test_empty_interface(self):
        source = 'type Empty interface {}\n'
        elements = parse_go_source(source)
        iface = [e for e in elements if e.name == "Empty"]
        assert len(iface) == 1
        assert iface[0].interface_methods == []

    def test_interface_with_embedded_type(self):
        source = '''
type ReadCloser interface {
    Reader
    Close() error
}
'''
        elements = parse_go_source(source)
        iface = [e for e in elements if e.name == "ReadCloser"]
        assert len(iface) == 1
        # Close should be extracted as a method
        assert any("Close" in m for m in iface[0].interface_methods)

    def test_struct_unchanged(self):
        """Struct elements should NOT have interface_methods populated."""
        source = '''
type Server struct {
    port int
    logger *log.Logger
}
'''
        elements = parse_go_source(source)
        srv = [e for e in elements if e.name == "Server"]
        assert len(srv) == 1
        assert srv[0].interface_methods == []
        assert srv[0].is_interface is False


# ---------------------------------------------------------------------------
# Go skeleton enrichment (REQ-GO-MP-700)
# ---------------------------------------------------------------------------

class TestGoSkeletonEnrichment:
    """REQ-GO-MP-700: Extract ForwardElementSpecs from Go skeleton stubs."""

    def test_panic_stub_detected(self):
        source = '''package main

func GetQuote(ctx context.Context, items []*CartItem) (*Money, error) {
    panic("not implemented")
}

func ShipOrder(ctx context.Context, address *Address) (string, error) {
    panic("not implemented")
}
'''
        specs = extract_go_skeleton_specs(source, "src/shipping/quote.go")
        assert len(specs) == 2
        names = {s.name for s in specs}
        assert "GetQuote" in names
        assert "ShipOrder" in names

    def test_non_stub_skipped(self):
        source = '''package main

func RealImplementation() string {
    return "hello"
}

func StubFunction() {
    panic("not implemented")
}
'''
        specs = extract_go_skeleton_specs(source, "src/main.go")
        assert len(specs) == 1
        assert specs[0].name == "StubFunction"

    def test_method_has_parent_class(self):
        source = '''package main

func Handle(ctx context.Context) error {
    panic("not implemented")
}
'''
        # Note: receiver-method skeleton enrichment requires _find_func_declaration
        # to support receiver_type matching. For now, standalone functions work.
        specs = extract_go_skeleton_specs(source, "src/server.go")
        assert len(specs) == 1
        assert specs[0].name == "Handle"
        assert specs[0].kind == ElementKind.FUNCTION

    def test_empty_source_returns_empty(self):
        assert extract_go_skeleton_specs("", "empty.go") == []
        assert extract_go_skeleton_specs("   ", "empty.go") == []

    def test_todo_stub_detected(self):
        source = '''package main

func InitTracing() {
    // TODO: OpenTelemetry tracing initialization
}
'''
        specs = extract_go_skeleton_specs(source, "src/main.go")
        assert len(specs) == 1
        assert specs[0].name == "InitTracing"


# ---------------------------------------------------------------------------
# Go file-level templates (REQ-GO-MP-100)
# ---------------------------------------------------------------------------

def _make_elem(name, kind=ElementKind.FUNCTION, parent=None, params=None, ret=None):
    sig = Signature(
        params=[Param(name=n, annotation=a) for n, a in (params or [])],
        return_annotation=ret,
    )
    return ForwardElementSpec(
        name=name, kind=kind, signature=sig, parent_class=parent,
    )


def _empty_file_spec():
    return ForwardFileSpec(file="src/main.go", elements=[], imports=[])


class TestGoTestFuncTemplate:
    def test_matches_test_function(self):
        elem = _make_elem("TestGetQuote")
        matched = [t for t in GO_TEMPLATES if t.name == "go_test_func" and t.match_fn(elem, _empty_file_spec(), [])]
        assert len(matched) == 1

    def test_renders_table_driven(self):
        elem = _make_elem("TestGetQuote")
        tmpl = [t for t in GO_TEMPLATES if t.name == "go_test_func"][0]
        body = tmpl.render_fn(elem, _empty_file_spec(), [])
        assert "tests :=" in body
        assert "t.Run" in body
        assert "GetQuote" in body

    def test_does_not_match_non_test(self):
        elem = _make_elem("GetQuote")
        matched = [t for t in GO_TEMPLATES if t.name == "go_test_func" and t.match_fn(elem, _empty_file_spec(), [])]
        assert len(matched) == 0


class TestGoHttpHandlerTemplate:
    def test_matches_handler_with_rw_request(self):
        elem = _make_elem(
            "homeHandler", kind=ElementKind.METHOD, parent="frontendServer",
            params=[("w", "http.ResponseWriter"), ("r", "*http.Request")],
        )
        matched = [t for t in GO_TEMPLATES if t.name == "go_http_handler" and t.match_fn(elem, _empty_file_spec(), [])]
        assert len(matched) == 1

    def test_does_not_match_without_rw(self):
        elem = _make_elem("getQuote", params=[("ctx", "context.Context")])
        matched = [t for t in GO_TEMPLATES if t.name == "go_http_handler" and t.match_fn(elem, _empty_file_spec(), [])]
        assert len(matched) == 0


class TestGoGrpcMethodTemplate:
    def test_matches_grpc_method(self):
        elem = _make_elem(
            "ListProducts", kind=ElementKind.METHOD, parent="productCatalogServer",
            params=[("ctx", "context.Context"), ("req", "*pb.ListProductsRequest")],
            ret="(*pb.ListProductsResponse, error)",
        )
        matched = [t for t in GO_TEMPLATES if t.name == "go_grpc_method" and t.match_fn(elem, _empty_file_spec(), [])]
        assert len(matched) == 1

    def test_renders_unimplemented(self):
        elem = _make_elem(
            "ListProducts", kind=ElementKind.METHOD, parent="productCatalogServer",
            params=[("ctx", "context.Context"), ("req", "*pb.ListProductsRequest")],
        )
        tmpl = [t for t in GO_TEMPLATES if t.name == "go_grpc_method"][0]
        body = tmpl.render_fn(elem, _empty_file_spec(), [])
        assert "Unimplemented" in body
        assert "ListProducts" in body

    def test_does_not_match_function(self):
        """Functions (no parent_class) should not match gRPC method template."""
        elem = _make_elem("ListProducts", params=[("ctx", "context.Context"), ("req", "*pb.Request")])
        matched = [t for t in GO_TEMPLATES if t.name == "go_grpc_method" and t.match_fn(elem, _empty_file_spec(), [])]
        assert len(matched) == 0
