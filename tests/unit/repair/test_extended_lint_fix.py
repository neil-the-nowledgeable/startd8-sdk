"""Tests for ExtendedLintFixStep (REQ-RPL-105)."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from startd8.repair.models import (
    LintDiagnostic,
    RepairContext,
    SyntaxDiagnostic,
)
from startd8.repair.steps.extended_lint_fix import ExtendedLintFixStep, _sanitized_env


class TestExtendedLintFixStep:
    """Tests for the extended lint fix repair step."""

    def setup_method(self):
        self.step = ExtendedLintFixStep()
        self.path = Path("<test>")

    def test_no_lint_diagnostics_noop(self):
        """No LintDiagnostics present -> no-op."""
        ctx = RepairContext(diagnostics=[])
        result = self.step("x = 1\n", ctx, self.path)
        assert result.modified is False

    def test_non_lint_diagnostics_ignored(self):
        """SyntaxDiagnostic is not a LintDiagnostic -> no-op."""
        diag = SyntaxDiagnostic(
            category="syntax", file="t.py", message="bad syntax",
        )
        ctx = RepairContext(diagnostics=[diag])
        result = self.step("x = 1\n", ctx, self.path)
        assert result.modified is False

    def test_non_fixable_lint_noop(self):
        """LintDiagnostic with fixable=False -> no-op."""
        diag = LintDiagnostic(
            category="lint", file="t.py", message="too complex",
            rule="C901", fixable=False,
        )
        ctx = RepairContext(diagnostics=[diag])
        result = self.step("x = 1\n", ctx, self.path)
        assert result.modified is False

    @patch("startd8.repair.steps.extended_lint_fix.subprocess.run")
    def test_command_construction(self, mock_run):
        """Verify ruff is called with shell=False and correct --select flags."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        diag = LintDiagnostic(
            category="lint", file="t.py", message="unused import",
            rule="F401", fixable=True,
        )
        ctx = RepairContext(diagnostics=[diag])

        # Patch tempfile + Path.read_text to simulate no change
        with patch("startd8.repair.steps.extended_lint_fix.tempfile.mkstemp") as mock_mkstemp, \
             patch("startd8.repair.steps.extended_lint_fix.os.close"), \
             patch("pathlib.Path.write_text"), \
             patch("pathlib.Path.read_text", return_value="x = 1\n"), \
             patch("pathlib.Path.unlink"):
            mock_mkstemp.return_value = (5, "/tmp/rpl_lint_test.py")
            self.step("x = 1\n", ctx, self.path)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ruff"
        assert cmd[1] == "check"
        assert "--fix" in cmd
        assert "--select" in cmd
        select_idx = cmd.index("--select")
        assert cmd[select_idx + 1] == "F401"
        # Verify shell=False (subprocess.run default, but check kwargs)
        assert mock_run.call_args[1].get("shell") is not True

    @patch("startd8.repair.steps.extended_lint_fix.subprocess.run")
    def test_multiple_rules_deduped(self, mock_run):
        """Multiple diagnostics with same rule are deduped in --select."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        diags = [
            LintDiagnostic(category="lint", file="t.py", message="unused", rule="F401", fixable=True, line=1),
            LintDiagnostic(category="lint", file="t.py", message="unused", rule="F401", fixable=True, line=5),
            LintDiagnostic(category="lint", file="t.py", message="undef", rule="F811", fixable=True, line=3),
        ]
        ctx = RepairContext(diagnostics=diags)

        with patch("startd8.repair.steps.extended_lint_fix.tempfile.mkstemp") as mock_mkstemp, \
             patch("startd8.repair.steps.extended_lint_fix.os.close"), \
             patch("pathlib.Path.write_text"), \
             patch("pathlib.Path.read_text", return_value="x = 1\n"), \
             patch("pathlib.Path.unlink"):
            mock_mkstemp.return_value = (5, "/tmp/rpl_lint_test.py")
            self.step("x = 1\n", ctx, self.path)

        cmd = mock_run.call_args[0][0]
        select_idx = cmd.index("--select")
        assert cmd[select_idx + 1] == "F401,F811"

    @patch("startd8.repair.steps.extended_lint_fix.subprocess.run")
    def test_modified_when_code_changes(self, mock_run):
        """If ruff changes the file, result.modified is True."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        diag = LintDiagnostic(
            category="lint", file="t.py", message="unused",
            rule="F401", fixable=True,
        )
        ctx = RepairContext(diagnostics=[diag])

        original = "import os\nx = 1\n"
        fixed = "x = 1\n"

        with patch("startd8.repair.steps.extended_lint_fix.tempfile.mkstemp") as mock_mkstemp, \
             patch("startd8.repair.steps.extended_lint_fix.os.close"), \
             patch("pathlib.Path.write_text"), \
             patch("pathlib.Path.read_text", return_value=fixed), \
             patch("pathlib.Path.unlink"):
            mock_mkstemp.return_value = (5, "/tmp/rpl_lint_test.py")
            result = self.step(original, ctx, self.path)

        assert result.modified is True
        assert result.code == fixed

    def test_protocol_name(self):
        assert self.step.name == "extended_lint_fix"


class TestSanitizedEnv:
    """Tests for environment sanitization."""

    @patch.dict("os.environ", {
        "PATH": "/usr/bin",
        "HOME": "/home/user",
        "OPENAI_API_KEY": "sk-secret",
        "MY_SECRET": "hidden",
        "AUTH_TOKEN": "tok123",
        "NORMAL_VAR": "visible",
    }, clear=True)
    def test_strips_secret_keys(self):
        env = _sanitized_env()
        assert "PATH" in env
        assert "HOME" in env
        assert "NORMAL_VAR" in env
        assert "OPENAI_API_KEY" not in env
        assert "MY_SECRET" not in env
        assert "AUTH_TOKEN" not in env
