"""Tests for Go signature string parser (REQ-EE-101)."""

from __future__ import annotations

import pytest

from startd8.forward_manifest import ForwardElementSpec, Visibility
from startd8.utils.code_manifest import ElementKind
from startd8.utils.go_signature_parser import parse_go_signatures


class TestBasicFunction:
    """func Name(...) patterns."""

    def test_function_with_params_and_return(self):
        sigs = ["func GetQuote(items []*pb.CartItem) *pb.Money"]
        result = parse_go_signatures(sigs, "service.go")
        assert len(result) == 1
        spec = result[0]
        assert spec.kind == ElementKind.FUNCTION
        assert spec.name == "GetQuote"
        assert spec.visibility == Visibility.PUBLIC
        assert spec.parent_class is None
        assert spec.decomposition_source == "parse-llm"
        assert spec.signature is not None

    def test_main_function(self):
        result = parse_go_signatures(["func main()"], "main.go")
        assert len(result) == 1
        spec = result[0]
        assert spec.kind == ElementKind.FUNCTION
        assert spec.name == "main"
        assert spec.visibility == Visibility.PRIVATE  # lowercase

    def test_constructor_function(self):
        result = parse_go_signatures(
            ["func NewShippingService() *ShippingService"], "service.go"
        )
        assert len(result) == 1
        spec = result[0]
        assert spec.kind == ElementKind.FUNCTION
        assert spec.name == "NewShippingService"
        assert spec.visibility == Visibility.PUBLIC

    def test_variadic_constructor(self):
        result = parse_go_signatures(
            ["func NewShippingService(opts ...Option) *ShippingService"], "service.go"
        )
        assert len(result) == 1
        assert result[0].kind == ElementKind.FUNCTION
        assert result[0].name == "NewShippingService"


class TestMethodWithReceiver:
    """func (recv) Name(...) patterns."""

    def test_pointer_receiver(self):
        sigs = [
            "func (s *ShippingService) ShipOrder(ctx context.Context, req *pb.ShipOrderReq) (string, error)"
        ]
        result = parse_go_signatures(sigs, "service.go")
        assert len(result) == 1
        spec = result[0]
        assert spec.kind == ElementKind.METHOD
        assert spec.name == "ShipOrder"
        assert spec.parent_class == "ShippingService"
        assert spec.visibility == Visibility.PUBLIC
        assert spec.signature is not None

    def test_value_receiver(self):
        result = parse_go_signatures(
            ["func (s ShippingService) GetName() string"], "service.go"
        )
        assert len(result) == 1
        spec = result[0]
        assert spec.kind == ElementKind.METHOD
        assert spec.name == "GetName"
        assert spec.parent_class == "ShippingService"

    def test_private_method(self):
        result = parse_go_signatures(
            ["func (s *Server) handleRequest(w http.ResponseWriter, r *http.Request)"],
            "server.go",
        )
        assert len(result) == 1
        spec = result[0]
        assert spec.kind == ElementKind.METHOD
        assert spec.name == "handleRequest"
        assert spec.visibility == Visibility.PRIVATE


class TestTypeDeclarations:
    """type Name struct/interface patterns."""

    def test_struct(self):
        result = parse_go_signatures(["type ShippingService struct"], "service.go")
        assert len(result) == 1
        spec = result[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "ShippingService"
        assert spec.visibility == Visibility.PUBLIC
        assert spec.is_abstract is False
        assert spec.signature is None

    def test_interface(self):
        result = parse_go_signatures(["type CartStore interface"], "store.go")
        assert len(result) == 1
        spec = result[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "CartStore"
        assert spec.is_abstract is True

    def test_struct_with_braces(self):
        result = parse_go_signatures(["type Money struct { ... }"], "money.go")
        assert len(result) == 1
        spec = result[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "Money"


class TestVisibility:
    """Go naming convention: uppercase = PUBLIC, lowercase = PRIVATE."""

    def test_uppercase_public(self):
        result = parse_go_signatures(["func HandleRequest()"], "handler.go")
        assert result[0].visibility == Visibility.PUBLIC

    def test_lowercase_private(self):
        result = parse_go_signatures(["func handleRequest()"], "handler.go")
        assert result[0].visibility == Visibility.PRIVATE

    def test_struct_uppercase_public(self):
        result = parse_go_signatures(["type Server struct"], "server.go")
        assert result[0].visibility == Visibility.PUBLIC

    def test_struct_lowercase_private(self):
        result = parse_go_signatures(["type server struct"], "server.go")
        assert result[0].visibility == Visibility.PRIVATE


class TestEdgeCases:
    """Empty input, garbage, and mixed lists."""

    def test_empty_input(self):
        assert parse_go_signatures([], "main.go") == []

    def test_unparseable_garbage(self):
        result = parse_go_signatures(["not a go signature"], "main.go")
        assert result == []

    def test_blank_string_skipped(self):
        result = parse_go_signatures(["", "  "], "main.go")
        assert result == []

    def test_multiple_mixed_signatures(self):
        sigs = [
            "type ShippingService struct",
            "func NewShippingService() *ShippingService",
            "func (s *ShippingService) ShipOrder(ctx context.Context) error",
            "type CartStore interface",
            "func main()",
        ]
        result = parse_go_signatures(sigs, "main.go")
        assert len(result) == 5

        assert result[0].kind == ElementKind.CLASS
        assert result[0].name == "ShippingService"

        assert result[1].kind == ElementKind.FUNCTION
        assert result[1].name == "NewShippingService"

        assert result[2].kind == ElementKind.METHOD
        assert result[2].name == "ShipOrder"
        assert result[2].parent_class == "ShippingService"

        assert result[3].kind == ElementKind.CLASS
        assert result[3].name == "CartStore"
        assert result[3].is_abstract is True

        assert result[4].kind == ElementKind.FUNCTION
        assert result[4].name == "main"

    def test_partial_garbage_mixed_with_valid(self):
        sigs = [
            "func GetQuote() int",
            "garbage line here",
            "type Money struct",
        ]
        result = parse_go_signatures(sigs, "main.go")
        assert len(result) == 2
        assert result[0].name == "GetQuote"
        assert result[1].name == "Money"


class TestGenericFunction:
    """Go 1.18+ generics: func Name[T constraint](...) ..."""

    def test_generic_function(self):
        result = parse_go_signatures(
            ["func Map[T any](items []T, fn func(T) T) []T"], "generics.go"
        )
        assert len(result) == 1
        spec = result[0]
        assert spec.kind == ElementKind.FUNCTION
        # The name captured is "Map" (regex stops at first `[` or `(`)
        assert spec.name == "Map"
        assert spec.visibility == Visibility.PUBLIC


class TestDecompositionSource:
    """All elements must have decomposition_source='parse-llm'."""

    def test_function_source(self):
        result = parse_go_signatures(["func Foo()"], "foo.go")
        assert result[0].decomposition_source == "parse-llm"

    def test_method_source(self):
        result = parse_go_signatures(["func (s *Svc) Bar()"], "svc.go")
        assert result[0].decomposition_source == "parse-llm"

    def test_type_source(self):
        result = parse_go_signatures(["type Baz struct"], "baz.go")
        assert result[0].decomposition_source == "parse-llm"
