"""Tests for Go file-level decomposition — REQ-GO-MP-300.

Verifies that _enrich_non_python_file_spec_from_skeleton() breaks
multi-function Go files into individual function elements.
"""

import pytest

from startd8.micro_prime.engine import _enrich_non_python_file_spec_from_skeleton
from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec
from startd8.utils.code_manifest import ElementKind, Signature


_EMPTY_SIG = Signature(params=[])


def _file_spec(file, elements=None):
    return ForwardFileSpec(
        file=file,
        elements=elements or [ForwardElementSpec(
            name=file.rsplit("/", 1)[-1].rsplit(".", 1)[0],
            kind=ElementKind.FUNCTION,
            signature=_EMPTY_SIG,
        )],
        imports=[],
    )


GO_SKELETON_2_STUBS = '''package shippingservice

import "context"

func GetQuote(ctx context.Context, items []*CartItem) (*Money, error) {
\tpanic("not implemented")
}

func ShipOrder(ctx context.Context, address *Address) (string, error) {
\tpanic("not implemented")
}
'''

GO_SKELETON_4_STUBS = '''package main

func initStats() {
\t// TODO: Stats/Metrics initialization
}

func initTracing() {
\t// TODO: OpenTelemetry tracing initialization
}

func GetQuote(ctx context.Context) (*Money, error) {
\tpanic("not implemented")
}

func main() {
\tlog.Println("starting")
}
'''


class TestGoDecomposition:
    """REQ-GO-MP-300: Break Go files into per-function elements."""

    def test_decomposes_multi_stub_file(self):
        fs = _file_spec("src/shippingservice/quote.go")
        result = _enrich_non_python_file_spec_from_skeleton(
            fs, GO_SKELETON_2_STUBS, "go",
        )
        # Original file-level element ("quote") kept + 2 decomposed stubs
        names = {e.name for e in result.elements}
        assert "GetQuote" in names
        assert "ShipOrder" in names
        # More elements than the original 1
        assert len(result.elements) > 1

    def test_elements_have_correct_kind(self):
        fs = _file_spec("src/shippingservice/quote.go")
        result = _enrich_non_python_file_spec_from_skeleton(
            fs, GO_SKELETON_2_STUBS, "go",
        )
        decomposed = [e for e in result.elements if e.decomposition_source]
        for elem in decomposed:
            assert elem.kind == ElementKind.FUNCTION

    def test_preserves_file_path(self):
        fs = _file_spec("src/shippingservice/quote.go")
        result = _enrich_non_python_file_spec_from_skeleton(
            fs, GO_SKELETON_2_STUBS, "go",
        )
        assert result.file == "src/shippingservice/quote.go"

    def test_skips_non_stub_functions(self):
        """Only stub functions should be decomposed, not real implementations."""
        skeleton = '''package main

func RealFunction() string {
\treturn "hello"
}

func StubFunction() {
\tpanic("not implemented")
}
'''
        fs = _file_spec("src/main.go")
        result = _enrich_non_python_file_spec_from_skeleton(
            fs, skeleton, "go",
        )
        # Only 1 stub → not more than 1 element → no decomposition
        assert len(result.elements) == 1

    def test_skips_python_language(self):
        """Python should not use Go decomposition."""
        fs = _file_spec("src/main.py")
        result = _enrich_non_python_file_spec_from_skeleton(
            fs, GO_SKELETON_2_STUBS, "python",
        )
        assert len(result.elements) == 1  # unchanged

    def test_skips_when_already_decomposed(self):
        """Don't decompose when file_spec already has >3 elements."""
        elements = [
            ForwardElementSpec(name=f"func{i}", kind=ElementKind.FUNCTION, signature=_EMPTY_SIG)
            for i in range(5)
        ]
        fs = ForwardFileSpec(file="src/main.go", elements=elements, imports=[])
        result = _enrich_non_python_file_spec_from_skeleton(
            fs, GO_SKELETON_2_STUBS, "go",
        )
        assert len(result.elements) == 5  # unchanged

    def test_empty_skeleton_returns_unchanged(self):
        fs = _file_spec("src/main.go")
        result = _enrich_non_python_file_spec_from_skeleton(fs, "", "go")
        assert len(result.elements) == 1

    def test_handles_todo_stubs(self):
        fs = _file_spec("src/main.go")
        result = _enrich_non_python_file_spec_from_skeleton(
            fs, GO_SKELETON_4_STUBS, "go",
        )
        # 3 stubs decomposed (initStats, initTracing, GetQuote)
        # + original file-level element kept ("main" from file_spec)
        names = {e.name for e in result.elements}
        assert "initStats" in names
        assert "initTracing" in names
        assert "GetQuote" in names
        # More elements than original 1
        assert len(result.elements) > 1
        # The decomposed stubs have decomposition_source set
        decomposed = [e for e in result.elements if e.decomposition_source]
        assert len(decomposed) == 3
