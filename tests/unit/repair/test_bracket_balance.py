"""Tests for BracketBalanceStep (REQ-RPL-103)."""

from pathlib import Path

from startd8.repair.models import RepairContext
from startd8.repair.steps.bracket_balance import BracketBalanceStep


class TestBracketBalanceStep:
    """Tests for the bracket balance repair step."""

    def setup_method(self):
        self.step = BracketBalanceStep()
        self.ctx = RepairContext()
        self.path = Path("<test>")

    def test_balanced_code_unchanged(self):
        code = "x = (1 + 2)\ny = [3, 4]\nz = {'a': 1}\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is False
        assert result.code == code

    def test_unclosed_paren(self):
        code = "x = foo(\n    1, 2\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is True
        assert result.code.rstrip().endswith(")")
        assert result.metrics["unclosed_count"] == 1

    def test_unclosed_bracket(self):
        code = "x = [1, 2, 3\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is True
        assert result.code.rstrip().endswith("]")
        assert result.metrics["unclosed_count"] == 1

    def test_unclosed_brace(self):
        code = "x = {'a': 1, 'b': 2\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is True
        assert result.code.rstrip().endswith("}")
        assert result.metrics["unclosed_count"] == 1

    def test_multiple_unclosed(self):
        code = "x = foo([{'a': 1\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is True
        # Should close in reverse order: } ] )
        assert result.metrics["unclosed_count"] == 3
        assert result.metrics["appended"] == "}])"

    def test_delimiters_inside_single_string_ignored(self):
        code = "x = 'hello (world'\ny = 1\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is False

    def test_delimiters_inside_double_string_ignored(self):
        code = 'x = "hello [world"\ny = 1\n'
        result = self.step(code, self.ctx, self.path)
        assert result.modified is False

    def test_delimiters_inside_triple_string_ignored(self):
        code = 'x = """hello { world"""\ny = 1\n'
        result = self.step(code, self.ctx, self.path)
        assert result.modified is False

    def test_delimiters_inside_comment_ignored(self):
        code = "# this has ( and [ and {\nx = 1\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is False

    def test_nested_balanced(self):
        code = "x = foo(bar([1, 2], {'k': 'v'}))\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is False

    def test_protocol_name(self):
        assert self.step.name == "bracket_balance"

    def test_empty_code(self):
        result = self.step("", self.ctx, self.path)
        assert result.modified is False

    def test_mixed_string_and_real_delimiters(self):
        """String contains a bracket but real code has unclosed paren."""
        code = "x = foo('contains [bracket]',\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is True
        assert result.metrics["unclosed_count"] == 1
        assert result.metrics["appended"] == ")"
