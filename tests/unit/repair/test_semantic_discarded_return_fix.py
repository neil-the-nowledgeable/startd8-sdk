"""Tests for SemanticDiscardedReturnFixStep (REQ-SR-300)."""

from pathlib import Path

from startd8.repair.models import RepairContext, SemanticDiagnostic
from startd8.repair.steps.semantic_discarded_return_fix import (
    SemanticDiscardedReturnFixStep,
    _infer_variable_name,
)


def _make_diag(symbol, line, file="server.py"):
    return SemanticDiagnostic(
        category="semantic", file=file,
        message=f"Return value of '{symbol}' is discarded",
        semantic_category="discarded_return",
        severity="warning", symbol=symbol, line=line,
    )


def _ctx(diagnostics):
    return RepairContext(diagnostics=diagnostics)


_STEP = SemanticDiscardedReturnFixStep()
_FILE = Path("server.py")


class TestInferVariableName:
    def test_env_var(self):
        assert _infer_variable_name("GCP_PROJECT_ID", set()) == "gcp_project_id"

    def test_port(self):
        assert _infer_variable_name("PORT", set()) == "port"

    def test_alloydb(self):
        assert _infer_variable_name("ALLOYDB_TABLE_NAME", set()) == "alloydb_table_name"

    def test_none_arg(self):
        assert _infer_variable_name(None, set()) == "_result"

    def test_keyword_collision(self):
        assert _infer_variable_name("CLASS", set()) == "_result"

    def test_existing_name_collision(self):
        assert _infer_variable_name("PORT", {"port"}) == "port_value"

    def test_empty_string(self):
        assert _infer_variable_name("", set()) == "_result"

    def test_special_chars(self):
        assert _infer_variable_name("MY-VAR.NAME", set()) == "my_var_name"

    def test_digit_leading_name(self):
        assert _infer_variable_name("1PASSWORD_KEY", set()) == "_1password_key"

    def test_consecutive_underscores(self):
        assert _infer_variable_name("A___B___C", set()) == "a_b_c"

    def test_debug(self):
        assert _infer_variable_name("DEBUG", set()) == "debug"


class TestSimpleRewrite:
    def test_env_get(self):
        code = "os.environ.get('GCP_PROJECT_ID')\n"
        diags = [_make_diag("os.environ.get", 1)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert result.code == "gcp_project_id = os.environ.get('GCP_PROJECT_ID')\n"

    def test_env_get_with_default(self):
        code = "os.environ.get('PORT', '8080')\n"
        diags = [_make_diag("os.environ.get", 1)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert result.code == "port = os.environ.get('PORT', '8080')\n"

    def test_getenv(self):
        code = "os.getenv('DEBUG')\n"
        diags = [_make_diag("os.getenv", 1)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert result.code == "debug = os.getenv('DEBUG')\n"

    def test_preserves_indentation(self):
        code = (
            "def setup():\n"
            "    os.environ.get('KEY')\n"
        )
        diags = [_make_diag("os.environ.get", 2)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert "    key = os.environ.get('KEY')\n" in result.code


class TestNoModification:
    def test_already_assigned(self):
        """ast.Assign, not ast.Expr — validator doesn't flag this."""
        code = "x = os.environ.get('KEY')\n"
        result = _STEP(code, _ctx([]), _FILE)
        assert not result.modified

    def test_no_diagnostics(self):
        code = "import os\n"
        result = _STEP(code, _ctx([]), _FILE)
        assert not result.modified

    def test_syntax_error(self):
        code = "def foo(\n"  # broken syntax
        diags = [_make_diag("os.environ.get", 1)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert not result.modified


class TestNameCollision:
    def test_existing_var_gets_suffix(self):
        code = "port = 8080\nos.environ.get('PORT')\n"
        diags = [_make_diag("os.environ.get", 2)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert "port_value = os.environ.get('PORT')" in result.code


class TestNonStringArg:
    def test_variable_arg_uses_result(self):
        code = "os.environ.get(key_var)\n"
        diags = [_make_diag("os.environ.get", 1)]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert "_result = os.environ.get(key_var)" in result.code


class TestMultipleConsecutive:
    def test_three_bare_calls(self):
        code = (
            "os.environ.get('A')\n"
            "os.environ.get('B')\n"
            "os.environ.get('C')\n"
        )
        diags = [
            _make_diag("os.environ.get", 1),
            _make_diag("os.environ.get", 2),
            _make_diag("os.environ.get", 3),
        ]
        result = _STEP(code, _ctx(diags), _FILE)
        assert result.modified
        assert "a = os.environ.get('A')" in result.code
        assert "b = os.environ.get('B')" in result.code
        assert "c = os.environ.get('C')" in result.code
        assert len(result.metrics["fixes"]) == 3


class TestStepMeta:
    def test_step_name(self):
        assert _STEP.name == "semantic_discarded_return_fix"
