"""Tests for SemanticDuplicateMainFixStep (REQ-SR-400)."""

from pathlib import Path

from startd8.repair.models import RepairContext, SemanticDiagnostic
from startd8.repair.steps.semantic_duplicate_main_fix import (
    SemanticDuplicateMainFixStep,
    _is_main_guard,
)

import ast


def _make_diag(line, file="main.py"):
    return SemanticDiagnostic(
        category="semantic", file=file,
        message="Multiple 'if __name__ == \"__main__\"' guards found",
        semantic_category="duplicate_main_guard",
        severity="warning", symbol="__main__", line=line,
    )


def _ctx(diagnostics):
    return RepairContext(diagnostics=diagnostics)


_STEP = SemanticDuplicateMainFixStep()
_FILE = Path("main.py")


class TestIsMainGuard:
    def test_standard(self):
        tree = ast.parse('if __name__ == "__main__": pass')
        node = tree.body[0]
        assert _is_main_guard(node)

    def test_reversed(self):
        tree = ast.parse('if "__main__" == __name__: pass')
        node = tree.body[0]
        assert _is_main_guard(node)

    def test_not_equal(self):
        tree = ast.parse('if __name__ != "__main__": pass')
        node = tree.body[0]
        assert not _is_main_guard(node)

    def test_wrong_value(self):
        tree = ast.parse('if __name__ == "__test__": pass')
        node = tree.body[0]
        assert not _is_main_guard(node)

    def test_not_if(self):
        tree = ast.parse('x = 1')
        node = tree.body[0]
        # Not an If node at all
        assert not isinstance(node, ast.If)


class TestTwoGuards:
    def test_second_removed(self):
        code = (
            'def main():\n'
            '    pass\n'
            '\n'
            'if __name__ == "__main__":\n'
            '    main()\n'
            '\n'
            'if __name__ == "__main__":\n'
            '    setup()\n'
        )
        diags = [_make_diag(7)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        # First guard preserved
        assert 'if __name__ == "__main__":\n    main()' in result.code
        # Second guard removed
        assert "setup()" not in result.code
        assert len(result.metrics["fixes"]) == 1


class TestThreeGuards:
    def test_second_and_third_removed(self):
        code = (
            'if __name__ == "__main__":\n'
            '    first()\n'
            '\n'
            'if __name__ == "__main__":\n'
            '    second()\n'
            '\n'
            'if __name__ == "__main__":\n'
            '    third()\n'
        )
        diags = [_make_diag(4)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert "first()" in result.code
        assert "second()" not in result.code
        assert "third()" not in result.code
        assert len(result.metrics["fixes"]) == 2


class TestNoModification:
    def test_single_guard(self):
        code = (
            'if __name__ == "__main__":\n'
            '    main()\n'
        )
        diags = [_make_diag(1)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert not result.modified

    def test_no_diagnostics(self):
        code = "import os\n"
        result = _STEP(code, _ctx([]), _FILE)
        assert not result.modified

    def test_syntax_error(self):
        code = "def foo(\n"
        diags = [_make_diag(1)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert not result.modified


class TestReversedComparison:
    def test_reversed_detected_and_removed(self):
        code = (
            'if __name__ == "__main__":\n'
            '    first()\n'
            '\n'
            'if "__main__" == __name__:\n'
            '    second()\n'
        )
        diags = [_make_diag(4)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert "first()" in result.code
        assert "second()" not in result.code


class TestNestedGuard:
    def test_nested_not_removed(self):
        """Guards inside functions are not top-level — not detected."""
        code = (
            'if __name__ == "__main__":\n'
            '    main()\n'
            '\n'
            'def setup():\n'
            '    if __name__ == "__main__":\n'
            '        pass\n'
        )
        diags = [_make_diag(5)]
        result = _STEP(code, _ctx(diags), _FILE)
        # Only 1 top-level guard found — no removal
        assert not result.modified


class TestDifferentContent:
    def test_different_bodies_second_still_removed(self):
        code = (
            'if __name__ == "__main__":\n'
            '    start_server()\n'
            '    logger.info("running")\n'
            '\n'
            'if __name__ == "__main__":\n'
            '    run_tests()\n'
        )
        diags = [_make_diag(5)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert "start_server()" in result.code
        assert "run_tests()" not in result.code


class TestStepMeta:
    def test_step_name(self):
        assert _STEP.name == "semantic_duplicate_main_fix"
