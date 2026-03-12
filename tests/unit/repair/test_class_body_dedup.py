"""Tests for ClassBodyDeduplicationStep (REQ-RPL-105).

Verifies that bare method-body blocks at class level are stripped
while legitimate class variables and method definitions are preserved.
"""

import ast
import textwrap

import pytest

from startd8.repair.steps.class_body_dedup import (
    ClassBodyDeduplicationStep,
    _strip_bare_return_blocks,
)
from startd8.repair.models import RepairContext
from startd8.repair.config import RepairConfig
from pathlib import Path


@pytest.fixture
def step():
    return ClassBodyDeduplicationStep()


@pytest.fixture
def context():
    return RepairContext(config=RepairConfig())


# ── _strip_bare_return_blocks unit tests ──────────────────────────────


class TestStripBareReturnBlocks:
    """Low-level function tests."""

    def test_no_classes_no_change(self):
        code = "def foo():\n    return 42\n"
        fixed, count = _strip_bare_return_blocks(code)
        assert count == 0
        assert fixed == code

    def test_clean_class_no_change(self):
        code = textwrap.dedent("""\
            class Foo:
                x = 5

                def bar(self):
                    return self.x
        """)
        fixed, count = _strip_bare_return_blocks(code)
        assert count == 0
        assert fixed == code

    def test_strips_bare_return_before_def(self):
        """Core case: bare method body before the actual method definition."""
        code = textwrap.dedent("""\
            class JsonFormatter:
                import json
                log_entry = {"key": "value"}
                try:
                    return json.dumps(log_entry)
                except TypeError:
                    return json.dumps({})
                def format(self, record):
                    log_entry = {"key": "value"}
                    try:
                        return json.dumps(log_entry)
                    except TypeError:
                        return json.dumps({})
        """)
        fixed, count = _strip_bare_return_blocks(code)
        assert count == 1
        # Only the method should remain
        assert "def format(self, record):" in fixed
        assert fixed.count("return json.dumps") == 2  # only inside method
        # Should be valid Python
        ast.parse(fixed)

    def test_preserves_class_variables_without_return(self):
        """Class variables (no return) must be preserved."""
        code = textwrap.dedent("""\
            class Config:
                RESERVED = frozenset(("a", "b"))
                DEFAULT_LEVEL = 10

                def __init__(self):
                    self.level = self.DEFAULT_LEVEL
        """)
        fixed, count = _strip_bare_return_blocks(code)
        assert count == 0
        assert "RESERVED" in fixed
        assert "DEFAULT_LEVEL" in fixed

    def test_preserves_decorators(self):
        """Decorators before methods must not be stripped."""
        code = textwrap.dedent("""\
            class Foo:
                @staticmethod
                def bar():
                    return 1
        """)
        fixed, count = _strip_bare_return_blocks(code)
        assert count == 0
        assert "@staticmethod" in fixed

    def test_multiple_classes_only_fixes_bad_one(self):
        code = textwrap.dedent("""\
            class Good:
                def method(self):
                    return 1

            class Bad:
                return 1
                def method(self):
                    return 2

            class AlsoGood:
                x = 10
                def method(self):
                    return self.x
        """)
        fixed, count = _strip_bare_return_blocks(code)
        assert count == 1
        assert "class Good:" in fixed
        assert "class Bad:" in fixed
        assert "class AlsoGood:" in fixed
        assert "x = 10" in fixed
        ast.parse(fixed)

    def test_bare_block_at_end_of_class(self):
        """Bare return after last method."""
        code = textwrap.dedent("""\
            class Foo:
                def bar(self):
                    return 1
                return 99
        """)
        fixed, count = _strip_bare_return_blocks(code)
        assert count == 1
        assert "return 99" not in fixed
        assert "return 1" in fixed

    def test_run039_logger_pattern(self):
        """Reproduce the exact run-039 pattern from online-boutique."""
        code = textwrap.dedent("""\
            class CustomJsonFormatter:
                RESERVED_ATTRS = frozenset(('args', 'asctime'))
                def __init__(self, component='emailservice'):
                    self.component = component
                def format(self, record):
                    return "formatted"

            class JsonFormatter:
                import json
                from datetime import datetime
                log_entry = {
                    'timestamp': 'now',
                    'severity': 'INFO',
                }
                try:
                    return json.dumps(log_entry)
                except (TypeError, ValueError):
                    return json.dumps({'error': 'fail'})
                def format(self, record):
                    log_entry = {
                        'timestamp': 'now',
                        'severity': 'INFO',
                    }
                    try:
                        return json.dumps(log_entry)
                    except (TypeError, ValueError):
                        return json.dumps({'error': 'fail'})

            def getJSONLogger(name=None):
                return "logger"
        """)
        # Original has bare return at class level — compile() rejects it
        # even if ast.parse() doesn't (version-dependent).
        with pytest.raises(SyntaxError):
            compile(code, "<test>", "exec")

        fixed, count = _strip_bare_return_blocks(code)
        assert count == 1
        # Fixed IS valid Python
        ast.parse(fixed)
        # CustomJsonFormatter is intact
        assert "RESERVED_ATTRS" in fixed
        assert "class CustomJsonFormatter:" in fixed
        # JsonFormatter keeps only the method
        assert "class JsonFormatter:" in fixed
        assert fixed.count("def format") == 2  # one per class
        # getJSONLogger is intact
        assert "def getJSONLogger" in fixed

    def test_no_false_positive_on_nested_return(self):
        """Returns inside methods should never trigger removal."""
        code = textwrap.dedent("""\
            class Foo:
                def a(self):
                    if True:
                        return 1
                    return 0

                def b(self):
                    for x in range(10):
                        return x
        """)
        fixed, count = _strip_bare_return_blocks(code)
        assert count == 0
        assert fixed == code

    def test_async_def_treated_as_method(self):
        """async def at body indent counts as a method boundary."""
        code = textwrap.dedent("""\
            class Foo:
                return 1
                async def bar(self):
                    return 2
        """)
        fixed, count = _strip_bare_return_blocks(code)
        assert count == 1
        assert "return 1" not in fixed
        assert "return 2" in fixed
        ast.parse(fixed)


# ── Step integration tests ────────────────────────────────────────────


class TestClassBodyDeduplicationStep:
    """Test the step callable interface."""

    def test_step_name(self, step):
        assert step.name == "class_body_dedup"

    def test_no_change_returns_unmodified(self, step, context):
        code = "class Foo:\n    def bar(self):\n        return 1\n"
        result = step(code, context, Path("<test>"))
        assert not result.modified
        assert result.code == code

    def test_fixes_bare_return(self, step, context):
        code = textwrap.dedent("""\
            class Foo:
                return 1
                def bar(self):
                    return 2
        """)
        result = step(code, context, Path("<test>"))
        assert result.modified
        assert result.metrics["bare_blocks_removed"] == 1
        assert "return 1" not in result.code
        assert "return 2" in result.code
        ast.parse(result.code)
