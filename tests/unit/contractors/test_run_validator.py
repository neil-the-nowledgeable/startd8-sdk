"""Tests for run_validator() dispatcher and individual validator functions.

Verifies that:
1. ``run_validator`` is importable (fixes the ImportError from P3)
2. Each validator correctly detects its target pattern
3. Subprocess execution works end-to-end
4. All enrichment validator names have implementations
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Test 1: Import succeeds (the root cause of P3)
# ---------------------------------------------------------------------------

class TestRunValidatorImport:

    def test_run_validator_import_succeeds(self):
        """Verify ``run_validator`` is importable — the P3 fix."""
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            run_validator,
        )
        assert callable(run_validator)


# ---------------------------------------------------------------------------
# Test 2-6: Individual validator detection
# ---------------------------------------------------------------------------

class TestNoMarkdownFences:

    def test_clean_file_passes(self, tmp_path: Path):
        """A clean Python file produces no issues."""
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            run_validator,
        )
        f = tmp_path / "clean.py"
        f.write_text("x = 1\n", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            run_validator("no_markdown_fences", [str(f)])
        assert exc_info.value.code == 0

    def test_detects_fences(self, tmp_path: Path):
        """Detects leftover markdown fence markers."""
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            run_validator,
        )
        f = tmp_path / "fenced.py"
        f.write_text("```python\nx = 1\n```\n", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            run_validator("no_markdown_fences", [str(f)])
        assert exc_info.value.code == 1


class TestTestNaming:

    def test_detects_bad_test_name(self, tmp_path: Path):
        """Flags ``testBadName`` (missing underscore after 'test')."""
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            run_validator,
        )
        f = tmp_path / "test_bad.py"
        f.write_text(
            textwrap.dedent("""\
                def testBadName():
                    pass

                def test_good_name():
                    pass
            """),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as exc_info:
            run_validator("test_naming", [str(f)])
        assert exc_info.value.code == 1

    def test_detects_class_without_test_prefix(self, tmp_path: Path):
        """Flags class with test methods but no 'Test' prefix."""
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            run_validator,
        )
        f = tmp_path / "test_cls.py"
        f.write_text(
            textwrap.dedent("""\
                class MyChecks:
                    def test_something(self):
                        pass
            """),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as exc_info:
            run_validator("test_naming", [str(f)])
        assert exc_info.value.code == 1


class TestNoHardcodedSecrets:

    def test_detects_hardcoded_secret(self, tmp_path: Path):
        """Detects ``api_key = "sk-abc123"``."""
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            run_validator,
        )
        f = tmp_path / "secrets.py"
        f.write_text('api_key = "sk-abc123xyz"\n', encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            run_validator("no_hardcoded_secrets", [str(f)])
        assert exc_info.value.code == 1

    def test_ignores_placeholder(self, tmp_path: Path):
        """Does not flag ``api_key = "YOUR_KEY_HERE"``."""
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            run_validator,
        )
        f = tmp_path / "placeholder.py"
        f.write_text('api_key = "YOUR_KEY_HERE"\n', encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            run_validator("no_hardcoded_secrets", [str(f)])
        assert exc_info.value.code == 0


class TestNoSubstringTagMatching:

    def test_detects_substring_tag_match(self, tmp_path: Path):
        """Detects ``if "admin" in tags:`` pattern."""
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            run_validator,
        )
        f = tmp_path / "tags.py"
        f.write_text(
            textwrap.dedent("""\
                tags = ["admin", "user"]
                if "admin" in tags:
                    pass
            """),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as exc_info:
            run_validator("no_substring_tag_matching", [str(f)])
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Test 7: Unknown validator name
# ---------------------------------------------------------------------------

class TestRunValidatorUnknownName:

    def test_unknown_name_raises(self, tmp_path: Path):
        """Raises ValueError for unknown validator names."""
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            run_validator,
        )
        f = tmp_path / "dummy.py"
        f.write_text("x = 1\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Unknown validator"):
            run_validator("nonexistent_validator", [str(f)])


# ---------------------------------------------------------------------------
# Test 8: E2E subprocess execution
# ---------------------------------------------------------------------------

class TestSubprocessExecution:

    def test_subprocess_clean_file(self, tmp_path: Path):
        """Actually run the subprocess command and verify returncode 0."""
        f = tmp_path / "clean.py"
        f.write_text("x = 1\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable, "-c",
                f"from startd8.workflows.builtin.preflight_rules.rules_validators "
                f"import run_validator; run_validator('no_markdown_fences', [{str(f)!r}])",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Expected returncode 0, got {result.returncode}.\n"
            f"stderr: {result.stderr}"
        )

    def test_subprocess_detects_issue(self, tmp_path: Path):
        """Actually run the subprocess command and verify returncode 1 on issue."""
        f = tmp_path / "fenced.py"
        f.write_text("```python\nx = 1\n```\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable, "-c",
                f"from startd8.workflows.builtin.preflight_rules.rules_validators "
                f"import run_validator; run_validator('no_markdown_fences', [{str(f)!r}])",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1, (
            f"Expected returncode 1, got {result.returncode}.\n"
            f"stderr: {result.stderr}"
        )
        # Verify stdout is valid JSON
        issues = json.loads(result.stdout)
        assert len(issues) >= 1
        assert issues[0]["validator"] == "no_markdown_fences"


# ---------------------------------------------------------------------------
# Test 9: All enrichment validator names have implementations
# ---------------------------------------------------------------------------

class TestValidatorCoverage:

    def test_all_enrichment_validators_have_implementation(self):
        """Every name in the enrichment_validators set has a _VALIDATORS entry."""
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            _VALIDATORS,
        )

        # These are the names from context_seed_handlers.py enrichment_validators set
        enrichment_validators = {
            "relative_imports_valid",
            "deps_available",
            "no_circular_imports",
            "no_markdown_fences",
            "merge_damage",
            "no_relative_imports",
            "definition_ordering",
            "test_naming",
            "no_hardcoded_secrets",
            "no_substring_tag_matching",
        }

        missing = enrichment_validators - set(_VALIDATORS)
        assert not missing, (
            f"These enrichment validators have no _VALIDATORS entry: {sorted(missing)}"
        )
