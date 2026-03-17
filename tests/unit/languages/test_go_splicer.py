"""Tests for Go body splicing (P6)."""

import pytest

from startd8.languages.go_splicer import (
    GoSpliceResult,
    splice_go_bodies,
    _find_func_declaration,
    _find_body_range,
    _extract_body_from_generated,
    _is_stub_body,
)


SKELETON = '''\
package main

import (
	"context"
	"fmt"
)

// Server holds gRPC server state.
type Server struct {
	port int
}

// ListProducts returns all products.
func (s *Server) ListProducts(ctx context.Context) ([]*Product, error) {
	panic("not implemented")
}

// GetProduct returns a single product by ID.
func (s *Server) GetProduct(ctx context.Context, id string) (*Product, error) {
	panic("not implemented")
}

// main starts the server.
func main() {
	panic("not implemented")
}
'''

GENERATED_LIST = '''\
func (s *Server) ListProducts(ctx context.Context) ([]*Product, error) {
	products := loadCatalog()
	return products, nil
}
'''

GENERATED_GET = '''\
func (s *Server) GetProduct(ctx context.Context, id string) (*Product, error) {
	for _, p := range catalog {
		if p.Id == id {
			return p, nil
		}
	}
	return nil, fmt.Errorf("product %s not found", id)
}
'''

GENERATED_MAIN = '''\
func main() {
	srv := grpc.NewServer()
	lis, err := net.Listen("tcp", ":8080")
	if err != nil {
		log.Fatal(err)
	}
	srv.Serve(lis)
}
'''


@pytest.mark.unit
class TestFindFuncDeclaration:

    def test_finds_function(self):
        lines = SKELETON.splitlines()
        idx = _find_func_declaration(lines, "main")
        assert idx is not None
        assert "func main()" in lines[idx]

    def test_finds_method_with_receiver(self):
        lines = SKELETON.splitlines()
        idx = _find_func_declaration(lines, "ListProducts", receiver_type="Server")
        assert idx is not None
        assert "ListProducts" in lines[idx]

    def test_returns_none_for_missing(self):
        lines = SKELETON.splitlines()
        assert _find_func_declaration(lines, "NonExistent") is None

    def test_method_without_receiver_not_found(self):
        """Method should not match when searching as plain function."""
        lines = SKELETON.splitlines()
        # ListProducts is a method, not a standalone function
        idx = _find_func_declaration(lines, "ListProducts")
        assert idx is None


@pytest.mark.unit
class TestFindBodyRange:

    def test_finds_single_line_body(self):
        lines = ["func main() {", '\tpanic("not implemented")', "}"]
        result = _find_body_range(lines, 0)
        assert result == (0, 2)

    def test_finds_multi_line_body(self):
        lines = SKELETON.splitlines()
        idx = _find_func_declaration(lines, "main")
        result = _find_body_range(lines, idx)
        assert result is not None
        open_line, close_line = result
        assert "{" in lines[open_line]
        assert lines[close_line].strip() == "}"

    def test_handles_nested_braces(self):
        lines = [
            "func handler() {",
            "\tif true {",
            "\t\tfmt.Println()",
            "\t}",
            "\tfor i := 0; i < 10; i++ {",
            "\t\tx := i",
            "\t}",
            "}",
        ]
        result = _find_body_range(lines, 0)
        assert result == (0, 7)


@pytest.mark.unit
class TestIsStubBody:

    def test_panic_not_implemented(self):
        assert _is_stub_body(['\tpanic("not implemented")'])

    def test_empty_body(self):
        assert _is_stub_body(["", "\t"])

    def test_real_body(self):
        assert not _is_stub_body(["\tfmt.Println('hello')"])

    def test_panic_todo(self):
        assert _is_stub_body(['\tpanic("TODO: implement this")'])


@pytest.mark.unit
class TestExtractBody:

    def test_extracts_simple_body(self):
        body = _extract_body_from_generated(GENERATED_MAIN, "main")
        assert body is not None
        assert "grpc.NewServer()" in body
        assert "srv.Serve(lis)" in body

    def test_extracts_method_body(self):
        body = _extract_body_from_generated(
            GENERATED_GET, "GetProduct", receiver_type="Server",
        )
        assert body is not None
        assert "p.Id == id" in body

    def test_returns_none_for_missing(self):
        body = _extract_body_from_generated(GENERATED_MAIN, "NonExistent")
        assert body is None


@pytest.mark.unit
class TestSpliceGoBodies:

    def test_splice_single_function(self):
        result = splice_go_bodies(
            SKELETON,
            {"main": GENERATED_MAIN},
        )
        assert result.code is not None
        assert result.functions_spliced == 1
        assert result.functions_skipped == 0
        assert "grpc.NewServer()" in result.code
        assert 'panic("not implemented")' not in result.code.split("func main")[1]

    def test_splice_method(self):
        result = splice_go_bodies(
            SKELETON,
            {"ListProducts": GENERATED_LIST},
            receiver_types={"ListProducts": "Server"},
        )
        assert result.code is not None
        assert result.functions_spliced == 1
        assert "loadCatalog()" in result.code

    def test_splice_multiple(self):
        result = splice_go_bodies(
            SKELETON,
            {
                "ListProducts": GENERATED_LIST,
                "GetProduct": GENERATED_GET,
                "main": GENERATED_MAIN,
            },
            receiver_types={
                "ListProducts": "Server",
                "GetProduct": "Server",
            },
        )
        assert result.code is not None
        assert result.functions_spliced == 3
        assert "loadCatalog()" in result.code
        assert "p.Id == id" in result.code
        assert "grpc.NewServer()" in result.code

    def test_warns_for_missing_function(self):
        result = splice_go_bodies(
            SKELETON,
            {"NonExistent": "func NonExistent() { x := 1 }"},
        )
        assert result.functions_skipped == 1
        assert any("not found" in w for w in result.warnings)

    def test_skips_non_stub_body(self):
        """Don't replace a real implementation."""
        real_skeleton = '''\
package main

func main() {
	fmt.Println("real code")
}
'''
        result = splice_go_bodies(
            real_skeleton,
            {"main": GENERATED_MAIN},
        )
        assert result.functions_skipped == 1
        assert any("not a stub" in w for w in result.warnings)
        # Original code preserved
        assert "real code" in result.code

    def test_preserves_struct_and_imports(self):
        """Non-function parts of skeleton are preserved."""
        result = splice_go_bodies(
            SKELETON,
            {"main": GENERATED_MAIN},
        )
        assert "type Server struct" in result.code
        assert 'import (' in result.code
        assert '"context"' in result.code

    def test_empty_bodies_dict(self):
        result = splice_go_bodies(SKELETON, {})
        assert result.code is not None
        assert result.functions_spliced == 0
        # Original skeleton preserved
        assert 'panic("not implemented")' in result.code

    def test_preserves_doc_comments(self):
        result = splice_go_bodies(
            SKELETON,
            {"main": GENERATED_MAIN},
        )
        assert "// main starts the server." in result.code


@pytest.mark.unit
class TestSpliceIndentation:

    def test_body_reindented_to_tab(self):
        """Go convention: tab indentation."""
        skeleton = '''\
package main

func process() {
	panic("not implemented")
}
'''
        generated = '''\
func process() {
	result := compute()
	if result > 0 {
		return result
	}
	return 0
}
'''
        result = splice_go_bodies(skeleton, {"process": generated})
        assert result.code is not None
        # All body lines should be tab-indented
        body_started = False
        for line in result.code.splitlines():
            if "func process()" in line:
                body_started = True
                continue
            if body_started and line.strip() == "}":
                break
            if body_started and line.strip():
                assert line.startswith("\t"), f"Line not tab-indented: {line!r}"
