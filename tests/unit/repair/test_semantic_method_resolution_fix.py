"""Tests for SemanticMethodResolutionFixStep (REQ-SR-100)."""

from pathlib import Path

from startd8.repair.models import RepairContext, SemanticDiagnostic
from startd8.repair.steps.semantic_method_resolution_fix import (
    SemanticMethodResolutionFixStep,
)


def _make_diag(symbol, line, file="locustfile.py"):
    return SemanticDiagnostic(
        category="semantic", file=file,
        message=f"'self.{symbol}()' called but '{symbol}' is a module-level function",
        semantic_category="method_resolution",
        severity="warning", symbol=symbol, line=line,
    )


def _ctx(diagnostics):
    return RepairContext(diagnostics=diagnostics)


_STEP = SemanticMethodResolutionFixStep()
_FILE = Path("locustfile.py")


class TestSelfDotModuleFunc:
    """Core rewrite: self.<func>() → <func>(self)."""

    def test_simple_rewrite(self):
        code = (
            "def index(l):\n"
            "    l.client.get('/')\n"
            "\n"
            "class UserBehavior(TaskSet):\n"
            "    def on_start(self):\n"
            "        self.index()\n"
        )
        diags = [_make_diag("index", 6)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert "index(self)" in result.code
        assert "self.index()" not in result.code

    def test_with_args(self):
        code = "        self.index(x, y)\n"
        diags = [_make_diag("index", 1)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert "index(self, x, y)" in result.code

    def test_preserves_surrounding_code(self):
        code = (
            "def index(l):\n"
            "    l.client.get('/')\n"
            "\n"
            "class UserBehavior(TaskSet):\n"
            "    def on_start(self):\n"
            "        self.index()\n"
            "\n"
            "    tasks = {index: 1}\n"
        )
        diags = [_make_diag("index", 6)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        # tasks dict untouched
        assert "tasks = {index: 1}" in result.code
        # Module-level function def untouched
        assert "def index(l):" in result.code

    def test_await_self_dot(self):
        code = "        await self.index()\n"
        diags = [_make_diag("index", 1)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert "await index(self)" in result.code
        assert "await self.index()" not in result.code

    def test_chained_call(self):
        code = "        x = self.index().result\n"
        diags = [_make_diag("index", 1)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert "index(self).result" in result.code


class TestNoModification:
    """Cases where the step should not modify anything."""

    def test_real_method_not_touched(self):
        """on_start is a class method — not flagged by validator, but verify step is safe."""
        code = "        self.on_start()\n"
        # No diagnostic for on_start — it's a real method
        result = _STEP(code, _ctx([]), _FILE)
        assert not result.modified

    def test_no_diagnostics(self):
        code = "import os\n"
        result = _STEP(code, _ctx([]), _FILE)
        assert not result.modified

    def test_symbol_not_in_code(self):
        """Diagnostic points to symbol that doesn't appear on that line."""
        code = "        self.other()\n"
        diags = [_make_diag("index", 1)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert not result.modified

    def test_line_out_of_range(self):
        code = "x = 1\n"
        diags = [_make_diag("index", 99)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert not result.modified


class TestMultipleFixes:
    def test_two_calls_different_lines(self):
        code = (
            "class Foo:\n"
            "    def setup(self):\n"
            "        self.a()\n"
            "        self.b()\n"
        )
        diags = [_make_diag("a", 3), _make_diag("b", 4)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert "a(self)" in result.code
        assert "b(self)" in result.code
        assert len(result.metrics["fixes"]) == 2


class TestMultipleClasses:
    def test_only_buggy_class_repaired(self):
        code = (
            "def index(l):\n"
            "    pass\n"
            "\n"
            "class Good:\n"
            "    def run(self):\n"
            "        pass\n"
            "\n"
            "class Bad:\n"
            "    def setup(self):\n"
            "        self.index()\n"
        )
        diags = [_make_diag("index", 10)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert "index(self)" in result.code
        # Good class untouched
        lines = result.code.splitlines()
        assert lines[4] == "    def run(self):"
        assert lines[5] == "        pass"


class TestStepMeta:
    def test_step_name(self):
        assert _STEP.name == "semantic_method_resolution_fix"
