"""Tests for unused_variable_removal repair step (F841)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from startd8.repair.models import LintDiagnostic, RepairContext
from startd8.repair.steps.unused_variable_removal import (
    UnusedVariableRemovalStep,
    _find_unused_assignments,
)


def _make_context(*names: str) -> RepairContext:
    diagnostics = [
        LintDiagnostic(
            category="lint",
            message=f"Local variable `{n}` is assigned to but never used",
            rule="F841",
            line=1,
            fixable=False,
            file="test.py",
        )
        for n in names
    ]
    return RepairContext(diagnostics=diagnostics)


@pytest.fixture
def step():
    return UnusedVariableRemovalStep()


class TestUnusedVariableRemoval:
    def test_removes_simple_unused_var(self, step):
        code = textwrap.dedent("""\
            def foo():
                x = 42
                return 1
        """)
        result = step(code, _make_context("x"), Path("test.py"))
        assert result.modified is True
        assert "x = 42" not in result.code
        assert "return 1" in result.code

    def test_keeps_used_variable(self, step):
        code = textwrap.dedent("""\
            def foo():
                x = 42
                return x
        """)
        result = step(code, _make_context("x"), Path("test.py"))
        assert result.modified is False

    def test_skips_call_with_side_effects(self, step):
        code = textwrap.dedent("""\
            def foo():
                result = do_something()
                return 1
        """)
        result = step(code, _make_context("result"), Path("test.py"))
        assert result.modified is False

    def test_skips_underscore_convention(self, step):
        code = textwrap.dedent("""\
            def foo():
                _unused = 42
                return 1
        """)
        result = step(code, _make_context("_unused"), Path("test.py"))
        assert result.modified is False

    def test_no_f841_diagnostic_no_change(self, step):
        code = textwrap.dedent("""\
            def foo():
                x = 42
                return 1
        """)
        result = step(code, RepairContext(diagnostics=[]), Path("test.py"))
        assert result.modified is False

    def test_removes_multiple_unused_vars(self, step):
        code = textwrap.dedent("""\
            def foo():
                a = 1
                b = 2
                return 3
        """)
        result = step(code, _make_context("a", "b"), Path("test.py"))
        assert result.modified is True
        assert "a = 1" not in result.code
        assert "b = 2" not in result.code
        assert "return 3" in result.code

    def test_preserves_surrounding_code(self, step):
        code = textwrap.dedent("""\
            import os

            def foo():
                x = 42
                print("hello")
                return 1
        """)
        result = step(code, _make_context("x"), Path("test.py"))
        assert result.modified is True
        assert "import os" in result.code
        assert 'print("hello")' in result.code

    def test_handles_string_literal_assignment(self, step):
        code = textwrap.dedent("""\
            def foo():
                msg = "hello"
                return 1
        """)
        result = step(code, _make_context("msg"), Path("test.py"))
        assert result.modified is True
        assert 'msg = "hello"' not in result.code

    def test_handles_syntax_error_gracefully(self, step):
        code = "def foo(\n"
        result = step(code, _make_context("x"), Path("test.py"))
        assert result.modified is False

    def test_metrics_populated(self, step):
        code = textwrap.dedent("""\
            def foo():
                x = 42
                return 1
        """)
        result = step(code, _make_context("x"), Path("test.py"))
        assert result.modified is True
        assert len(result.metrics["removed_assignments"]) == 1


class TestFindUnusedAssignments:
    def test_finds_unused_in_function(self):
        code = textwrap.dedent("""\
            def foo():
                x = 42
                return 1
        """)
        removals = _find_unused_assignments(code, {"x"})
        assert len(removals) == 1

    def test_skips_used_variable(self):
        code = textwrap.dedent("""\
            def foo():
                x = 42
                return x
        """)
        removals = _find_unused_assignments(code, {"x"})
        assert len(removals) == 0

    def test_skips_side_effect_calls(self):
        code = textwrap.dedent("""\
            def foo():
                x = bar()
                return 1
        """)
        removals = _find_unused_assignments(code, {"x"})
        assert len(removals) == 0
