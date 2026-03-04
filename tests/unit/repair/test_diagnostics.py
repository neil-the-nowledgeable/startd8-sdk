"""Tests for startd8.repair.diagnostics."""

from startd8.repair.diagnostics import (
    _sanitize,
    classify_checkpoint_category,
    parse_checkpoint_diagnostics,
)
from startd8.repair.models import ImportDiagnostic, LintDiagnostic, SyntaxDiagnostic


class _FakeResult:
    """Minimal CheckpointResult-like object for testing."""

    def __init__(self, name, status, errors=None, message=""):
        self.name = name
        self.status = status
        self.errors = errors or []
        self.message = message


class _FakeStatus:
    def __init__(self, value):
        self.value = value


class TestClassifyCheckpointCategory:
    def test_syntax_check(self):
        r = _FakeResult("Syntax Check", "failed")
        assert classify_checkpoint_category(r) == "syntax"

    def test_compile_check(self):
        r = _FakeResult("Compile Check", "failed")
        assert classify_checkpoint_category(r) == "syntax"

    def test_import_check(self):
        r = _FakeResult("Import Check", "failed")
        assert classify_checkpoint_category(r) == "import"

    def test_lint_check(self):
        r = _FakeResult("Lint Check", "failed")
        assert classify_checkpoint_category(r) == "lint"

    def test_ruff_check(self):
        r = _FakeResult("Ruff Lint", "failed")
        assert classify_checkpoint_category(r) == "lint"

    def test_test_check(self):
        r = _FakeResult("Test Runner", "failed")
        assert classify_checkpoint_category(r) == "test"

    def test_pytest_check(self):
        r = _FakeResult("Pytest", "failed")
        assert classify_checkpoint_category(r) == "test"

    def test_size_regression(self):
        r = _FakeResult("Size Regression", "failed")
        assert classify_checkpoint_category(r) == "size"

    def test_unknown(self):
        r = _FakeResult("Custom Gate", "failed")
        assert classify_checkpoint_category(r) == "unknown"


class TestParseCheckpointDiagnostics:
    def test_skips_passed_results(self):
        r = _FakeResult("Syntax Check", _FakeStatus("passed"))
        diags = parse_checkpoint_diagnostics([r])
        assert len(diags) == 0

    def test_syntax_error_parsed(self):
        r = _FakeResult(
            "Syntax Check",
            _FakeStatus("failed"),
            errors=['  File "foo.py", line 10\n    SyntaxError: invalid syntax'],
        )
        diags = parse_checkpoint_diagnostics([r])
        assert len(diags) >= 1
        assert isinstance(diags[0], SyntaxDiagnostic)
        assert diags[0].file == "foo.py"
        assert diags[0].line == 10

    def test_syntax_fallback_when_no_match(self):
        r = _FakeResult(
            "Syntax Check",
            _FakeStatus("failed"),
            errors=["some weird error"],
        )
        diags = parse_checkpoint_diagnostics([r])
        assert len(diags) == 1
        assert isinstance(diags[0], SyntaxDiagnostic)
        assert diags[0].file == ""

    def test_import_module_not_found(self):
        r = _FakeResult(
            "Import Check",
            _FakeStatus("failed"),
            errors=["ModuleNotFoundError: No module named 'grpc'"],
        )
        diags = parse_checkpoint_diagnostics([r])
        assert len(diags) == 1
        assert isinstance(diags[0], ImportDiagnostic)
        assert diags[0].module == "grpc"

    def test_import_cannot_import_name(self):
        r = _FakeResult(
            "Import Check",
            _FakeStatus("failed"),
            errors=["cannot import name 'Foo' from 'bar.baz'"],
        )
        diags = parse_checkpoint_diagnostics([r])
        assert len(diags) == 1
        assert isinstance(diags[0], ImportDiagnostic)
        assert diags[0].module == "bar.baz"
        assert diags[0].name == "Foo"

    def test_import_fallback(self):
        r = _FakeResult(
            "Import Check",
            _FakeStatus("failed"),
            errors=["some import error"],
        )
        diags = parse_checkpoint_diagnostics([r])
        assert len(diags) == 1
        assert isinstance(diags[0], ImportDiagnostic)

    def test_lint_error_parsed(self):
        r = _FakeResult(
            "Lint Check",
            _FakeStatus("failed"),
            errors=["foo.py:10:4: F401 'os' imported but unused"],
        )
        diags = parse_checkpoint_diagnostics([r])
        assert len(diags) == 1
        assert isinstance(diags[0], LintDiagnostic)
        assert diags[0].rule == "F401"
        assert diags[0].file == "foo.py"
        assert diags[0].line == 10
        assert diags[0].fixable is True

    def test_lint_non_fixable_rule(self):
        r = _FakeResult(
            "Lint Check",
            _FakeStatus("failed"),
            errors=["foo.py:5:1: C901 'func' is too complex"],
        )
        diags = parse_checkpoint_diagnostics([r])
        assert len(diags) == 1
        assert isinstance(diags[0], LintDiagnostic)
        assert diags[0].fixable is False

    def test_unknown_category_passthrough(self):
        r = _FakeResult(
            "Test Runner",
            _FakeStatus("failed"),
            errors=["FAILED test_foo.py::test_bar"],
        )
        diags = parse_checkpoint_diagnostics([r])
        assert len(diags) == 1
        assert diags[0].category == "test"

    def test_multiple_results(self):
        results = [
            _FakeResult(
                "Syntax Check", _FakeStatus("failed"),
                errors=['  File "a.py", line 5\n    SyntaxError: ...'],
            ),
            _FakeResult(
                "Import Check", _FakeStatus("failed"),
                errors=["ModuleNotFoundError: No module named 'foo'"],
            ),
            _FakeResult(
                "Lint Check", _FakeStatus("passed"),
            ),
        ]
        diags = parse_checkpoint_diagnostics(results)
        categories = {d.category for d in diags}
        assert "syntax" in categories
        assert "import" in categories
        assert "lint" not in categories  # passed, skipped


class TestSanitize:
    def test_strips_ansi(self):
        text = "\x1b[31mERROR\x1b[0m: bad"
        assert "\x1b[" not in _sanitize(text)
        assert "ERROR" in _sanitize(text)

    def test_truncates_long_lines(self):
        long_line = "x" * 600
        result = _sanitize(long_line)
        assert len(result) < 600
        assert result.endswith("...")

    def test_redacts_secrets(self):
        text = "MY_API_KEY=super_secret_123"
        result = _sanitize(text)
        assert "super_secret_123" not in result
        assert "***REDACTED***" in result

    def test_redacts_token(self):
        text = "AUTH_TOKEN=tok_abc123"
        result = _sanitize(text)
        assert "tok_abc123" not in result

    def test_normal_text_unchanged(self):
        text = "simple error message"
        assert _sanitize(text) == text
