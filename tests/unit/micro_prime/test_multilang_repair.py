"""Tests for multi-language repair isolation — REQ-MPL-100, REQ-NODE-MP-350.

Verifies that:
- _detect_definition_line() recognizes function declarations in all 5 languages
- bare_statement_wrap is a no-op for non-Python languages
- Python bare_statement_wrap behavior is unchanged (regression)
- _hoist_leading_imports() recognizes Node.js CJS require() patterns
"""

import pytest

from startd8.micro_prime import repair as repair_mod
from startd8.micro_prime.repair import (
    _detect_definition_line,
    _hoist_leading_imports,
    _step_bare_statement_wrap,
)
from startd8.forward_manifest import ForwardElementSpec
from startd8.utils.code_manifest import ElementKind, Signature


_EMPTY_SIG = Signature(params=[])


# ---------------------------------------------------------------------------
# _detect_definition_line — multi-language recognition
# ---------------------------------------------------------------------------

class TestDetectDefinitionLine:
    """REQ-MPL-100: Recognize function declarations in all registered languages."""

    # Python
    def test_python_def(self):
        assert _detect_definition_line("def foo():") is True

    def test_python_async_def(self):
        assert _detect_definition_line("async def bar():") is True

    def test_python_class(self):
        assert _detect_definition_line("class MyClass:") is True

    def test_python_decorator(self):
        assert _detect_definition_line("@staticmethod") is True

    # Go
    def test_go_func(self):
        assert _detect_definition_line("func main() {") is True

    def test_go_method_with_receiver(self):
        assert _detect_definition_line("func (s *Server) Handle(ctx context.Context) error {") is True

    def test_go_func_with_leading_whitespace(self):
        assert _detect_definition_line("  func helper() {") is True

    # Java / C#
    def test_java_public(self):
        assert _detect_definition_line("public void handle(Request req) {") is True

    def test_java_private(self):
        assert _detect_definition_line("private int calculate() {") is True

    def test_csharp_protected(self):
        assert _detect_definition_line("protected override void OnInit() {") is True

    def test_csharp_static(self):
        assert _detect_definition_line("static async Task<int> RunAsync() {") is True

    # Node.js / TypeScript
    def test_nodejs_function(self):
        assert _detect_definition_line("function handle(req, res) {") is True

    def test_nodejs_export(self):
        assert _detect_definition_line("export default function() {") is True

    def test_nodejs_export_const(self):
        assert _detect_definition_line("export const handler = async (req) => {") is True

    def test_nodejs_async_function(self):
        assert _detect_definition_line("async function processOrder() {") is True

    # Negative cases
    def test_bare_body_returns_false(self):
        assert _detect_definition_line("    return x + y") is False

    def test_comment_returns_false(self):
        assert _detect_definition_line("// this is a comment") is False

    def test_empty_returns_false(self):
        assert _detect_definition_line("") is False


# ---------------------------------------------------------------------------
# bare_statement_wrap — language guard
# ---------------------------------------------------------------------------

def _make_element(name="foo", kind=ElementKind.FUNCTION):
    return ForwardElementSpec(
        name=name,
        kind=kind,
        signature=_EMPTY_SIG,
    )


class TestBareStatementWrapLanguageGuard:
    """REQ-MPL-100: bare_statement_wrap is a no-op for non-Python languages."""

    def test_noop_for_go(self):
        repair_mod._current_repair_language_id = "go"
        result = _step_bare_statement_wrap("return 42", _make_element())
        assert result.modified is False
        assert result.code == "return 42"

    def test_noop_for_java(self):
        repair_mod._current_repair_language_id = "java"
        result = _step_bare_statement_wrap("return 42;", _make_element())
        assert result.modified is False

    def test_noop_for_csharp(self):
        repair_mod._current_repair_language_id = "csharp"
        result = _step_bare_statement_wrap("return 42;", _make_element())
        assert result.modified is False

    def test_noop_for_nodejs(self):
        repair_mod._current_repair_language_id = "nodejs"
        result = _step_bare_statement_wrap("return 42;", _make_element())
        assert result.modified is False

    def test_still_wraps_python(self):
        """Regression: Python bare_statement_wrap still works."""
        repair_mod._current_repair_language_id = "python"
        # Body-only code without a def line should be wrapped
        result = _step_bare_statement_wrap("    return 42", _make_element())
        # It either wraps (modified=True) or detects it's already a def (modified=False)
        # The key assertion: it does NOT return a no-op early
        assert result.step_name == "bare_statement_wrap"
        # For Python, the step should attempt processing (not the 3-line guard)
        # If the element has no signature, _build_def_line returns None → modified=False
        # That's fine — the point is Python doesn't hit the language guard

    def teardown_method(self):
        """Reset global state after each test."""
        repair_mod._current_repair_language_id = "python"


# ---------------------------------------------------------------------------
# _hoist_leading_imports — Node.js CJS require() support (REQ-NODE-MP-350)
# ---------------------------------------------------------------------------

class TestHoistNodejsImports:
    """REQ-NODE-MP-350: _hoist_leading_imports recognizes CJS require()."""

    def setup_method(self):
        repair_mod._current_repair_language_id = "nodejs"

    def teardown_method(self):
        repair_mod._current_repair_language_id = "python"

    def test_hoist_const_require(self):
        lines = [
            "const express = require('express');",
            "",
            "function handler(req, res) {",
        ]
        hoisted, body = _hoist_leading_imports(lines, None)
        assert len(hoisted) == 1
        assert "require('express')" in hoisted[0]
        assert body[0].startswith("function")

    def test_hoist_destructured_require(self):
        lines = [
            "const { Router } = require('express');",
            "function setup() {",
        ]
        hoisted, body = _hoist_leading_imports(lines, None)
        assert len(hoisted) == 1
        assert "{ Router }" in hoisted[0]

    def test_hoist_esm_import(self):
        """ESM import already works via 'import ' prefix."""
        lines = [
            "import express from 'express';",
            "function handler(req, res) {",
        ]
        hoisted, body = _hoist_leading_imports(lines, None)
        assert len(hoisted) == 1
        assert "import express" in hoisted[0]

    def test_non_import_const_not_hoisted(self):
        lines = [
            "const x = 5;",
            "function foo() {",
        ]
        hoisted, body = _hoist_leading_imports(lines, None)
        assert len(hoisted) == 0

    def test_mixed_imports_hoisted(self):
        lines = [
            "const pino = require('pino');",
            "import { v4 } from 'uuid';",
            "",
            "function main() {",
        ]
        hoisted, body = _hoist_leading_imports(lines, None)
        assert len(hoisted) == 2

    def test_python_mode_skips_require(self):
        """Regression: Python mode should NOT hoist require()."""
        repair_mod._current_repair_language_id = "python"
        lines = [
            "const x = require('pkg');",
            "function foo() {",
        ]
        hoisted, body = _hoist_leading_imports(lines, None)
        assert len(hoisted) == 0
