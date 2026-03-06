"""Tests for the startd8 repair CLI command (REQ-RPL-205)."""

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from startd8.cli import app

runner = CliRunner()


@pytest.fixture
def tmp_py_file(tmp_path):
    """Create a temporary Python file."""
    def _make(content: str, name: str = "example.py") -> Path:
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p
    return _make


class TestRepairCommandSyntaxError:
    """Test repair command with files containing syntax errors."""

    def test_repairs_markdown_fences(self, tmp_py_file):
        """File with markdown fences should be repaired."""
        fpath = tmp_py_file("```python\nx = 1\n```")
        result = runner.invoke(app, ["repair", str(fpath)])
        assert result.exit_code == 0
        # File should now be valid Python
        repaired = fpath.read_text(encoding="utf-8")
        ast.parse(repaired)  # Should not raise

    def test_repairs_syntax_error_shown_in_table(self, tmp_py_file):
        """Repair results table should be displayed."""
        fpath = tmp_py_file("```python\nx = 1\n```")
        result = runner.invoke(app, ["repair", str(fpath)])
        assert result.exit_code == 0
        assert "Repair Results" in result.output


class TestRepairCommandDryRun:
    """Test that dry-run mode doesn't modify files."""

    def test_dry_run_no_modification(self, tmp_py_file):
        """Dry-run should not modify the file."""
        original = "```python\nx = 1\n```"
        fpath = tmp_py_file(original)
        result = runner.invoke(app, ["repair", "--dry-run", str(fpath)])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        # File should be unchanged
        assert fpath.read_text(encoding="utf-8") == original

    def test_dry_run_shows_would_modify(self, tmp_py_file):
        """Dry-run should list files that would be modified."""
        fpath = tmp_py_file("```python\nx = 1\n```")
        result = runner.invoke(app, ["repair", "--dry-run", str(fpath)])
        assert result.exit_code == 0
        assert "Would modify" in result.output


class TestRepairCommandCleanFile:
    """Test with a valid file that needs no repair."""

    def test_clean_file_no_changes(self, tmp_py_file):
        """Valid Python file should produce no repairs."""
        fpath = tmp_py_file("x = 1\ny = 2\n")
        result = runner.invoke(app, ["repair", str(fpath)])
        assert result.exit_code == 0
        assert "clean" in result.output.lower() or "no repairs" in result.output.lower()

    def test_clean_file_unchanged(self, tmp_py_file):
        """Valid file content should not change."""
        original = "x = 1\ny = 2\n"
        fpath = tmp_py_file(original)
        runner.invoke(app, ["repair", str(fpath)])
        assert fpath.read_text(encoding="utf-8") == original


class TestRepairCommandEdgeCases:
    """Edge case tests for the repair command."""

    def test_nonexistent_file(self, tmp_path):
        """Non-existent file should produce a warning."""
        result = runner.invoke(app, ["repair", str(tmp_path / "ghost.py")])
        assert result.exit_code == 1

    def test_non_python_file(self, tmp_path):
        """Non-Python file should be skipped."""
        txt = tmp_path / "data.txt"
        txt.write_text("hello")
        result = runner.invoke(app, ["repair", str(txt)])
        assert result.exit_code == 1
        assert "non-Python" in result.output or "No valid" in result.output

    def test_multiple_files(self, tmp_py_file, tmp_path):
        """Multiple files should all be processed."""
        f1 = tmp_py_file("```python\nx = 1\n```", "a.py")
        f2 = tmp_py_file("y = 2\n", "b.py")
        result = runner.invoke(app, ["repair", str(f1), str(f2)])
        assert result.exit_code == 0
        # f1 should be repaired, f2 should be clean
        ast.parse(f1.read_text())
