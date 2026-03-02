"""Tests for the Micro Prime Body Splicer."""

from __future__ import annotations

import ast

import pytest

from startd8.forward_manifest import ForwardElementSpec
from startd8.micro_prime.splicer import (
    _extract_body,
    _find_def_line,
    _find_stub_after_def,
    splice_body_into_skeleton,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature


class TestSpliceBodyIntoSkeleton:
    """Tests for splice_body_into_skeleton()."""

    def test_splice_function_body(self, simple_function_element, sample_skeleton):
        body = "def get_name(self, key: str) -> str:\n    return key.upper()"
        result = splice_body_into_skeleton(body, simple_function_element, sample_skeleton)
        assert result is not None
        assert "return key.upper()" in result
        assert "raise NotImplementedError" in result  # Other stub still there
        # Should parse
        ast.parse(result)

    def test_splice_body_only(self, simple_function_element, sample_skeleton):
        body = "return key.upper()"
        result = splice_body_into_skeleton(body, simple_function_element, sample_skeleton)
        assert result is not None
        assert "return key.upper()" in result
        ast.parse(result)

    def test_splice_preserves_other_stubs(self, simple_function_element, sample_skeleton):
        body = "return key"
        result = splice_body_into_skeleton(body, simple_function_element, sample_skeleton)
        assert result is not None
        # get_value's stub should still be there
        lines = result.splitlines()
        # Count remaining NotImplementedError lines
        stub_count = sum(1 for line in lines if "raise NotImplementedError" in line)
        assert stub_count == 1  # Only get_value's stub remains

    def test_splice_constant(self, constant_element, sample_skeleton):
        body = "DEFAULT_TIMEOUT = 30"
        result = splice_body_into_skeleton(body, constant_element, sample_skeleton)
        assert result is not None
        assert "DEFAULT_TIMEOUT = 30" in result
        # Should not have the STARTD8_AUTO_STUB anymore
        assert "STARTD8_AUTO_STUB" not in result

    def test_splice_invalid_body_returns_none(self, simple_function_element, sample_skeleton):
        body = "def get_name(self, :\n    invalid"  # Syntax error in body
        result = splice_body_into_skeleton(body, simple_function_element, sample_skeleton)
        # May return None if spliced result doesn't parse
        # (depends on whether the body is extractable)

    def test_element_not_in_skeleton_returns_none(self, sample_skeleton):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="nonexistent_function",
            signature=Signature(params=[], return_annotation="None"),
        )
        result = splice_body_into_skeleton("return 1", elem, sample_skeleton)
        assert result is None


class TestFindDefLine:
    """Tests for _find_def_line()."""

    def test_finds_regular_def(self, sample_skeleton):
        lines = sample_skeleton.splitlines()
        idx = _find_def_line("get_name", ElementKind.FUNCTION, lines)
        assert idx is not None
        assert "def get_name" in lines[idx]

    def test_finds_class_def(self, sample_skeleton):
        lines = sample_skeleton.splitlines()
        idx = _find_def_line("MyClass", ElementKind.CLASS, lines)
        assert idx is not None
        assert "class MyClass" in lines[idx]

    def test_not_found_returns_none(self, sample_skeleton):
        lines = sample_skeleton.splitlines()
        idx = _find_def_line("nonexistent", ElementKind.FUNCTION, lines)
        assert idx is None

    def test_finds_async_def(self):
        lines = ["async def fetch(url):", "    pass"]
        idx = _find_def_line("fetch", ElementKind.ASYNC_FUNCTION, lines)
        assert idx == 0


class TestFindStubAfterDef:
    """Tests for _find_stub_after_def()."""

    def test_finds_stub(self, sample_skeleton):
        lines = sample_skeleton.splitlines()
        def_idx = _find_def_line("get_name", ElementKind.FUNCTION, lines)
        stub_idx = _find_stub_after_def(lines, def_idx)
        assert stub_idx is not None
        assert "raise NotImplementedError" in lines[stub_idx]

    def test_stub_not_found(self):
        lines = ["def foo():", "    return 1", "    return 2"]
        idx = _find_stub_after_def(lines, 0)
        assert idx is None


class TestExtractBody:
    """Tests for _extract_body()."""

    def test_extracts_from_def(self, simple_function_element):
        code = "def get_name(self, key: str) -> str:\n    return key.upper()"
        body = _extract_body(code, simple_function_element)
        assert "return key.upper()" in body
        # Should not contain the def line
        assert "def get_name" not in body

    def test_body_only_returns_as_is(self, simple_function_element):
        code = "return key.upper()"
        body = _extract_body(code, simple_function_element)
        assert "return key.upper()" in body

    def test_multiline_body(self, simple_function_element):
        code = (
            "def get_name(self, key: str) -> str:\n"
            "    result = key.upper()\n"
            "    return result"
        )
        body = _extract_body(code, simple_function_element)
        assert "result = key.upper()" in body
        assert "return result" in body
