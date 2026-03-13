"""Tests for dunder_all_fix repair step (F822)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.repair.models import LintDiagnostic, RepairContext
from startd8.repair.steps.dunder_all_fix import DunderAllFixStep


def _make_context(has_f822: bool = True) -> RepairContext:
    diagnostics = []
    if has_f822:
        diagnostics.append(
            LintDiagnostic(
                category="lint",
                message="Undefined name `inner` in `__all__`",
                rule="F822",
                line=6,
                fixable=False,
                file="test.py",
            )
        )
    return RepairContext(diagnostics=diagnostics)


class TestDunderAllFix:
    def test_strips_undefined_name(self):
        code = (
            "def create_app():\n"
            "    def inner():\n"
            "        pass\n"
            "    return None\n"
            "\n"
            '__all__ = ["create_app", "inner"]\n'
        )
        step = DunderAllFixStep()
        result = step(code, _make_context(), Path("test.py"))

        assert result.modified is True
        assert '"inner"' not in result.code
        assert '"create_app"' in result.code
        assert "__all__" in result.code

    def test_removes_all_when_all_undefined(self):
        code = (
            "x = 1\n"
            '__all__ = ["foo", "bar"]\n'
        )
        step = DunderAllFixStep()
        result = step(code, _make_context(), Path("test.py"))

        assert result.modified is True
        assert "__all__" not in result.code

    def test_no_change_when_all_valid(self):
        code = (
            "def foo():\n"
            "    pass\n"
            "\n"
            "def bar():\n"
            "    pass\n"
            "\n"
            '__all__ = ["foo", "bar"]\n'
        )
        step = DunderAllFixStep()
        result = step(code, _make_context(), Path("test.py"))

        assert result.modified is False

    def test_skips_without_f822_diagnostic(self):
        code = '__all__ = ["nonexistent"]\n'
        step = DunderAllFixStep()
        result = step(code, _make_context(has_f822=False), Path("test.py"))

        assert result.modified is False

    def test_handles_class_definitions(self):
        code = (
            "class MyClass:\n"
            "    pass\n"
            "\n"
            '__all__ = ["MyClass", "missing"]\n'
        )
        step = DunderAllFixStep()
        result = step(code, _make_context(), Path("test.py"))

        assert result.modified is True
        assert '"MyClass"' in result.code
        assert '"missing"' not in result.code

    def test_handles_imports_as_defined(self):
        code = (
            "from os import path\n"
            "import sys\n"
            "\n"
            '__all__ = ["path", "sys", "missing"]\n'
        )
        step = DunderAllFixStep()
        result = step(code, _make_context(), Path("test.py"))

        assert result.modified is True
        assert '"path"' in result.code
        assert '"sys"' in result.code
        assert '"missing"' not in result.code

    def test_flask_route_handler_pattern(self):
        """The exact pattern from PI-008: nested Flask route handler in __all__."""
        code = (
            "from flask import Flask, request\n"
            "\n"
            "def create_app():\n"
            "    app = Flask(__name__)\n"
            "\n"
            "    @app.route('/', methods=['POST'])\n"
            "    def talkToGemini():\n"
            "        return {'content': 'hello'}\n"
            "\n"
            "    return app\n"
            "\n"
            '__all__ = ["create_app", "talkToGemini"]\n'
        )
        step = DunderAllFixStep()
        result = step(code, _make_context(), Path("test.py"))

        assert result.modified is True
        assert '"talkToGemini"' not in result.code
        assert '"create_app"' in result.code

    def test_handles_syntax_error_gracefully(self):
        code = "def foo(\n"  # invalid syntax
        step = DunderAllFixStep()
        result = step(code, _make_context(), Path("test.py"))

        assert result.modified is False
        assert result.metrics.get("error") == "syntax_error"

    def test_multiline_all(self):
        code = (
            "def foo():\n"
            "    pass\n"
            "\n"
            "__all__ = [\n"
            '    "foo",\n'
            '    "bar",\n'
            "]\n"
        )
        step = DunderAllFixStep()
        result = step(code, _make_context(), Path("test.py"))

        assert result.modified is True
        assert '"foo"' in result.code
        assert '"bar"' not in result.code
