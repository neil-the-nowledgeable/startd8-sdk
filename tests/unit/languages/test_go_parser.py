"""Tests for Go regex-based source parser."""

import pytest

from startd8.languages.go_parser import GoElement, parse_go_source, parse_go_imports


# -- Representative Go source samples from online-boutique patterns --

GRPC_SERVER_SOURCE = '''\
package main

import (
	"context"
	"fmt"
	"net"
	"os"

	pb "github.com/GoogleCloudPlatform/microservices-demo/src/productcatalogservice/genproto/hipstershop"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	log "github.com/sirupsen/logrus"
)

const (
	defaultPort = "3550"
	maxRetries  = 5
)

var catalog []*pb.Product

// productCatalog implements the ProductCatalogService.
type productCatalog struct {
	pb.UnimplementedProductCatalogServiceServer
}

// ListProducts returns all products in the catalog.
func (p *productCatalog) ListProducts(ctx context.Context, req *pb.Empty) (*pb.ListProductsResponse, error) {
	return &pb.ListProductsResponse{Products: catalog}, nil
}

// GetProduct returns a product by ID.
func (p *productCatalog) GetProduct(ctx context.Context, req *pb.GetProductRequest) (*pb.Product, error) {
	for _, product := range catalog {
		if product.Id == req.Id {
			return product, nil
		}
	}
	return nil, fmt.Errorf("product not found: %s", req.Id)
}

// SearchProducts searches for products matching a query.
func (p *productCatalog) SearchProducts(ctx context.Context, req *pb.SearchProductsRequest) (*pb.SearchProductsResponse, error) {
	return &pb.SearchProductsResponse{}, nil
}

func main() {
	port := defaultPort
	if v := os.Getenv("PORT"); v != "" {
		port = v
	}
	log.Infof("starting server on port %s", port)

	lis, err := net.Listen("tcp", fmt.Sprintf(":%s", port))
	if err != nil {
		log.Fatal(err)
	}

	srv := grpc.NewServer()
	pb.RegisterProductCatalogServiceServer(srv, &productCatalog{})

	healthSrv := health.NewServer()
	healthpb.RegisterHealthServer(srv, healthSrv)

	log.Fatal(srv.Serve(lis))
}
'''

STRUCT_WITH_EMBEDDING = '''\
package server

// Server holds the gRPC server and its dependencies.
type Server struct {
	pb.UnimplementedFrontendServer
	Handler
	port    int
	catalog CatalogService
}

// Handler processes HTTP requests.
type Handler struct {
	templates map[string]*template.Template
}

// CatalogService defines the product catalog interface.
type CatalogService interface {
	ListProducts(ctx context.Context) ([]*Product, error)
	GetProduct(ctx context.Context, id string) (*Product, error)
}

type Money struct {
	CurrencyCode string
	Units        int64
	Nanos        int32
}
'''

TYPE_ALIASES = '''\
package types

type ProductID = string
type Money int64

type contextKey string
'''

CONST_VAR_BLOCKS = '''\
package config

const version = "1.0.0"

var debug bool = false

const (
	EnvPort    string = "PORT"
	EnvDebug          = "DEBUG"
	maxRetries int    = 3
)

var (
	catalog []*Product
	logger  *Logger
)
'''


@pytest.mark.unit
class TestFunctionParsing:

    def test_standalone_function(self):
        elements = parse_go_source('package main\n\nfunc main() {\n}\n')
        funcs = [e for e in elements if e.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "main"
        assert funcs[0].signature == ""

    def test_function_with_params_and_return(self):
        source = 'package main\n\nfunc Add(a int, b int) int {\n\treturn a + b\n}\n'
        elements = parse_go_source(source)
        funcs = [e for e in elements if e.kind == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "Add"
        assert funcs[0].signature == "a int, b int"
        assert funcs[0].return_type == "int"
        assert funcs[0].is_exported is True

    def test_unexported_function(self):
        source = 'package main\n\nfunc helper() {}\n'
        elements = parse_go_source(source)
        funcs = [e for e in elements if e.kind == "function"]
        assert funcs[0].is_exported is False

    def test_multiple_return_values(self):
        source = 'package main\n\nfunc Divide(a, b float64) (float64, error) {\n}\n'
        elements = parse_go_source(source)
        funcs = [e for e in elements if e.kind == "function"]
        assert funcs[0].return_type == "(float64, error)"

    def test_grpc_server_main(self):
        elements = parse_go_source(GRPC_SERVER_SOURCE)
        funcs = [e for e in elements if e.kind == "function"]
        func_names = {f.name for f in funcs}
        assert "main" in func_names


@pytest.mark.unit
class TestMethodParsing:

    def test_pointer_receiver_method(self):
        source = 'package svc\n\nfunc (s *Server) Start() error {\n}\n'
        elements = parse_go_source(source)
        methods = [e for e in elements if e.kind == "method"]
        assert len(methods) == 1
        assert methods[0].name == "Start"
        assert methods[0].parent_type == "Server"
        assert methods[0].is_pointer_receiver is True
        assert methods[0].receiver_name == "s"

    def test_value_receiver_method(self):
        source = 'package svc\n\nfunc (m Money) String() string {\n}\n'
        elements = parse_go_source(source)
        methods = [e for e in elements if e.kind == "method"]
        assert methods[0].parent_type == "Money"
        assert methods[0].is_pointer_receiver is False

    def test_grpc_service_methods(self):
        elements = parse_go_source(GRPC_SERVER_SOURCE)
        methods = [e for e in elements if e.kind == "method"]
        method_names = {m.name for m in methods}
        assert "ListProducts" in method_names
        assert "GetProduct" in method_names
        assert "SearchProducts" in method_names
        # All methods should have productCatalog as parent
        for m in methods:
            assert m.parent_type == "productCatalog"

    def test_method_not_double_counted_as_function(self):
        """Methods should not also appear as functions."""
        elements = parse_go_source(GRPC_SERVER_SOURCE)
        funcs = [e for e in elements if e.kind == "function"]
        func_names = {f.name for f in funcs}
        assert "ListProducts" not in func_names
        assert "GetProduct" not in func_names

    def test_method_doc_comment(self):
        elements = parse_go_source(GRPC_SERVER_SOURCE)
        methods = [e for e in elements if e.kind == "method"]
        list_prod = [m for m in methods if m.name == "ListProducts"][0]
        assert list_prod.doc_comment is not None
        assert "returns all products" in list_prod.doc_comment.lower()


@pytest.mark.unit
class TestTypeParsing:

    def test_struct_type(self):
        source = 'package main\n\ntype Server struct {\n\tport int\n}\n'
        elements = parse_go_source(source)
        types = [e for e in elements if e.kind == "class"]
        assert len(types) == 1
        assert types[0].name == "Server"
        assert types[0].is_interface is False

    def test_interface_type(self):
        elements = parse_go_source(STRUCT_WITH_EMBEDDING)
        types = [e for e in elements if e.kind == "class"]
        ifaces = [t for t in types if t.is_interface]
        assert len(ifaces) == 1
        assert ifaces[0].name == "CatalogService"

    def test_struct_embedded_types(self):
        elements = parse_go_source(STRUCT_WITH_EMBEDDING)
        types = [e for e in elements if e.kind == "class"]
        server = [t for t in types if t.name == "Server"][0]
        # Should detect Handler as embedded type
        assert "Handler" in server.bases

    def test_grpc_struct(self):
        elements = parse_go_source(GRPC_SERVER_SOURCE)
        types = [e for e in elements if e.kind == "class"]
        assert len(types) == 1
        assert types[0].name == "productCatalog"

    def test_exported_type(self):
        elements = parse_go_source(STRUCT_WITH_EMBEDDING)
        types = [e for e in elements if e.kind == "class"]
        server = [t for t in types if t.name == "Server"][0]
        assert server.is_exported is True

    def test_unexported_type(self):
        elements = parse_go_source(GRPC_SERVER_SOURCE)
        types = [e for e in elements if e.kind == "class"]
        pc = [t for t in types if t.name == "productCatalog"][0]
        assert pc.is_exported is False


@pytest.mark.unit
class TestTypeAliasParsing:

    def test_type_alias(self):
        elements = parse_go_source(TYPE_ALIASES)
        aliases = [e for e in elements if e.kind == "type_alias"]
        names = {a.name for a in aliases}
        assert "ProductID" in names
        assert "Money" in names
        assert "contextKey" in names

    def test_alias_target(self):
        elements = parse_go_source(TYPE_ALIASES)
        aliases = [e for e in elements if e.kind == "type_alias"]
        pid = [a for a in aliases if a.name == "ProductID"][0]
        assert pid.type_annotation == "string"


@pytest.mark.unit
class TestConstVarParsing:

    def test_single_const(self):
        elements = parse_go_source(CONST_VAR_BLOCKS)
        consts = [e for e in elements if e.kind == "constant"]
        names = {c.name for c in consts}
        assert "version" in names

    def test_single_var(self):
        elements = parse_go_source(CONST_VAR_BLOCKS)
        vars_ = [e for e in elements if e.kind == "variable"]
        names = {v.name for v in vars_}
        assert "debug" in names

    def test_const_block(self):
        elements = parse_go_source(CONST_VAR_BLOCKS)
        consts = [e for e in elements if e.kind == "constant"]
        names = {c.name for c in consts}
        assert "EnvPort" in names
        assert "EnvDebug" in names
        assert "maxRetries" in names

    def test_var_block(self):
        elements = parse_go_source(CONST_VAR_BLOCKS)
        vars_ = [e for e in elements if e.kind == "variable"]
        names = {v.name for v in vars_}
        assert "catalog" in names
        assert "logger" in names

    def test_exported_const(self):
        elements = parse_go_source(CONST_VAR_BLOCKS)
        consts = [e for e in elements if e.kind == "constant"]
        env_port = [c for c in consts if c.name == "EnvPort"][0]
        assert env_port.is_exported is True
        max_r = [c for c in consts if c.name == "maxRetries"][0]
        assert max_r.is_exported is False

    def test_grpc_server_consts_and_vars(self):
        elements = parse_go_source(GRPC_SERVER_SOURCE)
        consts = [e for e in elements if e.kind == "constant"]
        vars_ = [e for e in elements if e.kind == "variable"]
        const_names = {c.name for c in consts}
        var_names = {v.name for v in vars_}
        assert "defaultPort" in const_names
        assert "maxRetries" in const_names
        assert "catalog" in var_names


@pytest.mark.unit
class TestImportParsing:

    def test_block_imports(self):
        imports = parse_go_imports(GRPC_SERVER_SOURCE)
        assert "context" in imports
        assert "fmt" in imports
        assert "net" in imports
        assert "os" in imports
        assert "google.golang.org/grpc" in imports

    def test_single_import(self):
        source = 'package main\n\nimport "fmt"\n'
        imports = parse_go_imports(source)
        assert imports == ["fmt"]

    def test_aliased_imports(self):
        imports = parse_go_imports(GRPC_SERVER_SOURCE)
        # Aliased imports should still capture the path
        paths = set(imports)
        assert "github.com/sirupsen/logrus" in paths
        assert "google.golang.org/grpc/health/grpc_health_v1" in paths


@pytest.mark.unit
class TestElementOrdering:

    def test_elements_sorted_by_line(self):
        elements = parse_go_source(GRPC_SERVER_SOURCE)
        lines = [e.line_number for e in elements]
        assert lines == sorted(lines)


@pytest.mark.unit
class TestFullServiceParsing:
    """Integration test: parse the full gRPC server source."""

    def test_all_element_kinds_found(self):
        elements = parse_go_source(GRPC_SERVER_SOURCE)
        kinds = {e.kind for e in elements}
        assert "function" in kinds
        assert "method" in kinds
        assert "class" in kinds
        assert "constant" in kinds
        assert "variable" in kinds

    def test_element_count(self):
        elements = parse_go_source(GRPC_SERVER_SOURCE)
        assert len(elements) >= 7  # 1 struct + 3 methods + 1 func + 2 consts + 1 var
