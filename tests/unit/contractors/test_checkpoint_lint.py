"""Tests for checkpoint lint severity classification.

Validates that style-only ruff codes (E741, E742, E743) are downgraded
to warnings instead of blocking errors, preventing false feature failures
from framework conventions (e.g. Locust's ``l`` parameter).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import subprocess

from startd8.contractors.checkpoint import (
    CheckpointStatus,
    IntegrationCheckpoint,
    _STYLE_ONLY_CODES,
)


class TestLintSeverityClassification:
    """Style-only ruff codes should be warnings, not errors."""

    def _make_checkpoint(self, tmp_path: Path) -> IntegrationCheckpoint:
        return IntegrationCheckpoint(project_root=tmp_path)

    def _mock_ruff(self, stdout: str, returncode: int = 1):
        """Create a mock subprocess result simulating ruff output."""
        result = MagicMock()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = ""
        return result

    def test_e741_downgraded_to_warning(self, tmp_path):
        """E741 (ambiguous variable name) should not fail the lint check."""
        py_file = tmp_path / "locustfile.py"
        py_file.write_text("def index(l): pass\n")

        ruff_output = (
            "locustfile.py:1:11: E741 Ambiguous variable name: `l`\n"
        )
        checkpoint = self._make_checkpoint(tmp_path)

        with patch("subprocess.run", return_value=self._mock_ruff(ruff_output)):
            result = checkpoint.check_lint([py_file])

        assert result.status == CheckpointStatus.PASSED
        assert len(result.warnings) == 0 or "E741" in result.warnings[0]
        assert len(result.errors) == 0

    def test_e741_multiple_occurrences(self, tmp_path):
        """Multiple E741 warnings should all be downgraded."""
        py_file = tmp_path / "locustfile.py"
        py_file.write_text("x = 1\n")

        ruff_output = (
            "locustfile.py:1:11: E741 Ambiguous variable name: `l`\n"
            "locustfile.py:5:14: E741 Ambiguous variable name: `l`\n"
            "locustfile.py:9:17: E741 Ambiguous variable name: `l`\n"
        )
        checkpoint = self._make_checkpoint(tmp_path)

        with patch("subprocess.run", return_value=self._mock_ruff(ruff_output)):
            result = checkpoint.check_lint([py_file])

        assert result.status == CheckpointStatus.PASSED
        assert len(result.errors) == 0

    def test_real_error_still_fails(self, tmp_path):
        """F821 (undefined name) should still fail the lint check."""
        py_file = tmp_path / "app.py"
        py_file.write_text("x = undefined_var\n")

        ruff_output = "app.py:1:5: F821 Undefined name `undefined_var`\n"
        checkpoint = self._make_checkpoint(tmp_path)

        with patch("subprocess.run", return_value=self._mock_ruff(ruff_output)):
            result = checkpoint.check_lint([py_file])

        assert result.status == CheckpointStatus.FAILED
        assert len(result.errors) == 1
        assert "F821" in result.errors[0]

    def test_mixed_errors_and_style_warnings(self, tmp_path):
        """E741 should be a warning while F821 is still an error."""
        py_file = tmp_path / "app.py"
        py_file.write_text("x = 1\n")

        ruff_output = (
            "app.py:1:11: E741 Ambiguous variable name: `l`\n"
            "app.py:3:5: F821 Undefined name `foo`\n"
        )
        checkpoint = self._make_checkpoint(tmp_path)

        with patch("subprocess.run", return_value=self._mock_ruff(ruff_output)):
            result = checkpoint.check_lint([py_file])

        assert result.status == CheckpointStatus.FAILED
        assert len(result.errors) == 1
        assert "F821" in result.errors[0]
        assert any("E741" in w for w in result.warnings)

    def test_style_only_codes_constant(self):
        """Verify the built-in style-only codes set."""
        assert "E741" in _STYLE_ONLY_CODES
        assert "E742" in _STYLE_ONLY_CODES
        assert "E743" in _STYLE_ONLY_CODES
        # Correctness codes should NOT be in the set
        assert "E711" not in _STYLE_ONLY_CODES
        assert "F821" not in _STYLE_ONLY_CODES

    def test_custom_style_ignore_codes(self, tmp_path):
        """Additional style_ignore_codes merge with built-in set."""
        py_file = tmp_path / "app.py"
        py_file.write_text("x = 1\n")

        ruff_output = "app.py:1:5: E711 Comparison to `None`\n"
        checkpoint = self._make_checkpoint(tmp_path)

        # Without custom codes, E711 is an error
        with patch("subprocess.run", return_value=self._mock_ruff(ruff_output)):
            result = checkpoint.check_lint([py_file])
        assert result.status == CheckpointStatus.FAILED

        # With custom codes, E711 becomes a warning
        with patch("subprocess.run", return_value=self._mock_ruff(ruff_output)):
            result = checkpoint.check_lint(
                [py_file], style_ignore_codes={"E711"}
            )
        assert result.status == CheckpointStatus.PASSED

    def test_e741_only_warnings_pass(self, tmp_path):
        """When only E741 warnings exist (no real errors), result is PASSED."""
        py_file = tmp_path / "locustfile.py"
        py_file.write_text("def f(l): pass\n")

        ruff_output = (
            "locustfile.py:1:11: E741 Ambiguous variable name: `l`\n"
            "locustfile.py:5:17: E741 Ambiguous variable name: `l`\n"
            "locustfile.py:9:19: E741 Ambiguous variable name: `l`\n"
            "locustfile.py:13:14: E741 Ambiguous variable name: `l`\n"
            "locustfile.py:17:15: E741 Ambiguous variable name: `l`\n"
        )
        checkpoint = self._make_checkpoint(tmp_path)

        with patch("subprocess.run", return_value=self._mock_ruff(ruff_output)):
            result = checkpoint.check_lint([py_file])

        # Should PASS — all diagnostics are style-only
        assert result.status == CheckpointStatus.PASSED
        assert len(result.errors) == 0
