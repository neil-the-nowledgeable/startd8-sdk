"""Tests for Java body splicer (Phase 3)."""

import pytest
from startd8.languages.java_splicer import (
    JavaSpliceResult,
    splice_java_bodies,
    _find_method_declaration,
    _find_body_range,
    _is_stub_body,
    JAVA_SKELETON_SENTINEL,
)


SKELETON = """\
// [STARTD8-SKELETON]
package com.example;

public class UserService {

    public String getName() {
        throw new UnsupportedOperationException("TODO");
    }

    public void setName(String name) {
        throw new UnsupportedOperationException("TODO");
    }

    public int getAge() {
        throw new UnsupportedOperationException("TODO");
    }
}
"""

GENERATED_GET_NAME = """\
    public String getName() {
        return this.name;
    }
"""

GENERATED_SET_NAME = """\
    public void setName(String name) {
        this.name = name;
    }
"""


class TestSpliceJavaBodies:

    def test_splice_single_method(self):
        result = splice_java_bodies(SKELETON, {"getName": GENERATED_GET_NAME})
        assert result.code is not None
        assert result.methods_spliced == 1
        assert "return this.name;" in result.code
        # Stub should be gone for getName
        assert result.code.count('throw new UnsupportedOperationException("TODO")') == 2

    def test_splice_multiple_methods(self):
        result = splice_java_bodies(SKELETON, {
            "getName": GENERATED_GET_NAME,
            "setName": GENERATED_SET_NAME,
        })
        assert result.methods_spliced == 2
        assert "return this.name;" in result.code
        assert "this.name = name;" in result.code

    def test_method_not_found(self):
        result = splice_java_bodies(SKELETON, {"nonExistent": "public void nonExistent() { }"})
        assert result.methods_skipped == 1
        assert any("not found" in w for w in result.warnings)

    def test_preserves_indentation(self):
        result = splice_java_bodies(SKELETON, {"getName": GENERATED_GET_NAME})
        assert result.code is not None
        # The spliced body should be indented
        for line in result.code.splitlines():
            if "return this.name" in line:
                assert line.startswith("    ") or line.startswith("\t")

    def test_non_stub_body_skipped(self):
        non_stub_skeleton = SKELETON.replace(
            'throw new UnsupportedOperationException("TODO");',
            'return "already implemented";',
            1,  # Only replace the first one
        )
        result = splice_java_bodies(non_stub_skeleton, {"getName": GENERATED_GET_NAME})
        assert result.methods_skipped >= 1


class TestFindMethodDeclaration:
    def test_find_method(self):
        lines = SKELETON.splitlines()
        idx = _find_method_declaration(lines, "getName")
        assert idx is not None
        assert "getName" in lines[idx]

    def test_find_missing(self):
        lines = SKELETON.splitlines()
        assert _find_method_declaration(lines, "nonExistent") is None


class TestFindBodyRange:
    def test_find_range(self):
        lines = SKELETON.splitlines()
        idx = _find_method_declaration(lines, "getName")
        assert idx is not None
        body_range = _find_body_range(lines, idx)
        assert body_range is not None
        open_line, close_line = body_range
        assert close_line > open_line


class TestIsStubBody:
    def test_stub_detected(self):
        assert _is_stub_body(['        throw new UnsupportedOperationException("TODO");'])

    def test_real_body_not_stub(self):
        assert not _is_stub_body(["        return this.name;"])

    def test_empty_is_stub(self):
        assert _is_stub_body([""])


class TestAnnotations:
    def test_annotated_method_found(self):
        code = """\
package com.example;

public class MyClass {

    @Override
    public String toString() {
        throw new UnsupportedOperationException("TODO");
    }
}
"""
        generated = """\
    @Override
    public String toString() {
        return "MyClass{}";
    }
"""
        result = splice_java_bodies(code, {"toString": generated})
        assert result.methods_spliced == 1
        assert 'return "MyClass{}"' in result.code
