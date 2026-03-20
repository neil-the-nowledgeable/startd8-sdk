"""Tests for non-Python stub counting in disk compliance (Criterion 4).

Verifies that _validate_*_file() populates stubs_remaining using
language-specific stub patterns, so postmortem scoring doesn't
default to 1.0 for non-Python files with stubs.
"""

import pytest

from startd8.forward_manifest_validator import (
    DiskComplianceResult,
    _validate_go_file,
    _validate_java_file,
    _validate_js_file,
)


class TestJavaStubCounting:
    def _make_result(self):
        return DiskComplianceResult(file_path="Service.java")

    def test_no_stubs_zero(self):
        code = (
            "package com.example;\n\n"
            "public class Service {\n"
            "    public void process() {\n"
            "        System.out.println(\"working\");\n"
            "    }\n"
            "}\n"
        )
        result = _validate_java_file(code, self._make_result())
        assert result.stubs_remaining == 0

    def test_unsupported_operation_counted(self):
        code = (
            "package com.example;\n\n"
            "public class Service {\n"
            "    public void process() {\n"
            "        throw new UnsupportedOperationException(\"not implemented\");\n"
            "    }\n"
            "}\n"
        )
        result = _validate_java_file(code, self._make_result())
        assert result.stubs_remaining >= 1

    def test_todo_comment_counted(self):
        code = (
            "package com.example;\n\n"
            "public class Service {\n"
            "    public void process() {\n"
            "        // TODO implement this\n"
            "    }\n"
            "}\n"
        )
        result = _validate_java_file(code, self._make_result())
        assert result.stubs_remaining >= 1

    def test_multiple_stubs_counted(self):
        code = (
            "package com.example;\n\n"
            "public class Service {\n"
            "    public void a() {\n"
            "        throw new UnsupportedOperationException(\"nope\");\n"
            "    }\n"
            "    public void b() {\n"
            "        throw new RuntimeException(\"TODO later\");\n"
            "    }\n"
            "}\n"
        )
        result = _validate_java_file(code, self._make_result())
        assert result.stubs_remaining >= 2


class TestGoStubCounting:
    def _make_result(self):
        return DiskComplianceResult(file_path="server.go")

    def test_no_stubs_zero(self):
        code = (
            "package main\n\n"
            "func main() {\n"
            "    fmt.Println(\"hello\")\n"
            "}\n"
        )
        result = _validate_go_file(code, self._make_result())
        assert result.stubs_remaining == 0

    def test_panic_not_implemented_counted(self):
        code = (
            "package server\n\n"
            "func Handle() {\n"
            '    panic("not implemented")\n'
            "}\n"
        )
        result = _validate_go_file(code, self._make_result())
        assert result.stubs_remaining >= 1

    def test_todo_comment_counted(self):
        code = (
            "package server\n\n"
            "func Handle() {\n"
            "    // TODO implement handler\n"
            "}\n"
        )
        result = _validate_go_file(code, self._make_result())
        assert result.stubs_remaining >= 1


class TestJsStubCounting:
    def _make_result(self):
        return DiskComplianceResult(file_path="service.js")

    def test_no_stubs_zero(self):
        code = (
            "const express = require('express');\n"
            "const app = express();\n"
            "module.exports = app;\n"
        )
        result = _validate_js_file(code, self._make_result())
        assert result.stubs_remaining == 0

    def test_throw_not_implemented_counted(self):
        code = (
            "function process() {\n"
            "    throw new Error('not implemented');\n"
            "}\n"
            "module.exports = { process };\n"
        )
        result = _validate_js_file(code, self._make_result())
        assert result.stubs_remaining >= 1

    def test_todo_comment_counted(self):
        code = (
            "function process() {\n"
            "    // TODO implement this\n"
            "}\n"
            "module.exports = { process };\n"
        )
        result = _validate_js_file(code, self._make_result())
        assert result.stubs_remaining >= 1


class TestPostmortemScoringImpact:
    """Verify that stubs_remaining > 0 actually lowers the quality score."""

    def test_stubs_lower_score(self):
        from startd8.contractors.prime_postmortem import compute_disk_quality_score

        clean = DiskComplianceResult(file_path="Clean.java")
        clean.stubs_remaining = 0

        stubby = DiskComplianceResult(file_path="Stubby.java")
        stubby.stubs_remaining = 5

        clean_score = compute_disk_quality_score(clean)
        stubby_score = compute_disk_quality_score(stubby)
        assert stubby_score < clean_score, (
            f"stubs_remaining=5 should lower score: {stubby_score} vs {clean_score}"
        )
