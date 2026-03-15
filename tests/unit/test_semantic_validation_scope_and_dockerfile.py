"""Tests for L2 cross-scope duplicate detection and L3 Dockerfile digest validation.

Verifies REQ-SV-301/302 (cross-scope duplicates) and REQ-SV-401/402
(Dockerfile SHA256 digest) from SEMANTIC_VALIDATION_REQUIREMENTS.md.
"""

import pytest

from startd8.forward_manifest_validator import (
    validate_disk_compliance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_py(tmp_path, rel_path, content):
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return rel_path


def _write_file(tmp_path, rel_path, content):
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return rel_path


def _scope_issues(result):
    return [
        i for i in result.semantic_issues
        if isinstance(i, dict) and i.get("category") == "cross_scope_duplicate"
    ]


def _digest_issues(result):
    return [
        i for i in result.semantic_issues
        if isinstance(i, dict) and i.get("category") == "dockerfile_digest"
    ]


# ---------------------------------------------------------------------------
# L2: Cross-scope duplicate detection (REQ-SV-301)
# ---------------------------------------------------------------------------


class TestCrossScopeDuplicates:
    def test_nested_function_same_as_module_level(self, tmp_path):
        """Run-050 bug: talkToGemini at module level AND inside a class."""
        rel = _write_py(
            tmp_path, "app.py",
            (
                "def talkToGemini(prompt):\n"
                "    return prompt\n\n"
                "class ShoppingAssistant:\n"
                "    def handle(self):\n"
                "        def talkToGemini(prompt):\n"
                "            return prompt\n"
                "        return talkToGemini('hi')\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _scope_issues(result)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "talkToGemini" in issues[0]["symbol"]
        assert "ShoppingAssistant" in issues[0]["message"]

    def test_function_inside_class_same_as_module(self, tmp_path):
        """Method with same name as module-level function."""
        rel = _write_py(
            tmp_path, "app.py",
            (
                "def process():\n"
                "    return 1\n\n"
                "class Handler:\n"
                "    def process(self):\n"
                "        return 2\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _scope_issues(result)
        assert len(issues) == 1
        assert "process" in issues[0]["symbol"]

    def test_different_names_no_issue(self, tmp_path):
        rel = _write_py(
            tmp_path, "app.py",
            (
                "def foo():\n"
                "    return 1\n\n"
                "class Bar:\n"
                "    def baz(self):\n"
                "        return 2\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _scope_issues(result) == []

    def test_only_nested_no_module_level(self, tmp_path):
        """Function defined only inside a class — not a cross-scope dup."""
        rel = _write_py(
            tmp_path, "app.py",
            (
                "class Outer:\n"
                "    def helper(self):\n"
                "        return 1\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _scope_issues(result) == []

    def test_module_level_duplicate_is_separate_field(self, tmp_path):
        """Module-level duplicates go to duplicate_definitions, not semantic_issues."""
        rel = _write_py(
            tmp_path, "app.py",
            "def foo():\n    pass\n\ndef foo():\n    pass\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.duplicate_definitions == 1
        # No cross-scope issue — both are at module level
        assert _scope_issues(result) == []

    def test_multiple_cross_scope_duplicates(self, tmp_path):
        rel = _write_py(
            tmp_path, "app.py",
            (
                "def alpha():\n    return 1\n\n"
                "def beta():\n    return 2\n\n"
                "class Container:\n"
                "    def alpha(self):\n        return 3\n"
                "    def beta(self):\n        return 4\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _scope_issues(result)
        assert len(issues) == 2
        symbols = {i["symbol"] for i in issues}
        assert symbols == {"alpha", "beta"}

    def test_deeply_nested_function(self, tmp_path):
        """Function nested two levels deep that shadows a module-level name."""
        rel = _write_py(
            tmp_path, "app.py",
            (
                "def render():\n"
                "    return 'html'\n\n"
                "class View:\n"
                "    def dispatch(self):\n"
                "        def render():\n"
                "            return 'inner'\n"
                "        return render()\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _scope_issues(result)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "render"

    def test_class_inside_class_same_name(self, tmp_path):
        """Nested class with same name as module-level class."""
        rel = _write_py(
            tmp_path, "app.py",
            (
                "class Config:\n"
                "    x = 1\n\n"
                "class App:\n"
                "    class Config:\n"
                "        y = 2\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _scope_issues(result)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "Config"


# ---------------------------------------------------------------------------
# L3: Dockerfile SHA256 digest validation (REQ-SV-401)
# ---------------------------------------------------------------------------


class TestDockerfileDigest:
    def test_valid_64char_digest_passes(self, tmp_path):
        digest = "a" * 64
        rel = _write_file(
            tmp_path, "Dockerfile",
            f"FROM python:3.11@sha256:{digest}\nCMD [\"python\"]\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _digest_issues(result) == []
        assert result.contract_compliance == pytest.approx(1.0)

    def test_truncated_8char_digest_flagged(self, tmp_path):
        """Run-050 bug: 8-char truncated digest."""
        rel = _write_file(
            tmp_path, "Dockerfile",
            "FROM python:3.11@sha256:abcd1234\nCMD [\"python\"]\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _digest_issues(result)
        assert len(issues) == 1
        assert issues[0]["severity"] == "error"
        assert "8 chars" in issues[0]["message"]

    def test_empty_digest_flagged(self, tmp_path):
        rel = _write_file(
            tmp_path, "Dockerfile",
            "FROM python:3.11@sha256:\nCMD [\"python\"]\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _digest_issues(result)
        assert len(issues) == 1
        assert "0 chars" in issues[0]["message"]
        assert "sha256:<empty>" in str(issues[0]["symbol"])

    def test_no_digest_passes(self, tmp_path):
        """FROM without @sha256 should not trigger digest check."""
        rel = _write_file(
            tmp_path, "Dockerfile",
            "FROM python:3.11-slim\nCMD [\"python\"]\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _digest_issues(result) == []

    def test_multiple_from_lines_both_flagged(self, tmp_path):
        """Multi-stage build with two truncated digests."""
        rel = _write_file(
            tmp_path, "Dockerfile",
            (
                "FROM python:3.11@sha256:aabb1122 AS builder\n"
                "WORKDIR /build\n"
                "FROM python:3.11-slim@sha256:ccdd3344\n"
                "CMD [\"python\"]\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _digest_issues(result)
        assert len(issues) == 2

    def test_valid_digest_multistage(self, tmp_path):
        d1 = "a" * 64
        d2 = "b" * 64
        rel = _write_file(
            tmp_path, "Dockerfile",
            (
                f"FROM python:3.11@sha256:{d1} AS builder\n"
                "WORKDIR /build\n"
                f"FROM python:3.11-slim@sha256:{d2}\n"
                "ENTRYPOINT [\"python\"]\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert _digest_issues(result) == []
        assert result.contract_compliance == pytest.approx(1.0)

    def test_digest_issue_coexists_with_no_entrypoint_warning(self, tmp_path):
        """Both a truncated digest and missing entrypoint should be reported."""
        rel = _write_file(
            tmp_path, "Dockerfile",
            "FROM python:3.11@sha256:abcd\nWORKDIR /app\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        digest = _digest_issues(result)
        assert len(digest) == 1
        # Also has the "no CMD or ENTRYPOINT" warning
        non_dict_issues = [i for i in result.semantic_issues if isinstance(i, str)]
        assert any("CMD" in i for i in non_dict_issues)

    def test_line_number_reported(self, tmp_path):
        rel = _write_file(
            tmp_path, "Dockerfile",
            "# Comment\nFROM python:3.11@sha256:deadbeef\nCMD [\"python\"]\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        issues = _digest_issues(result)
        assert len(issues) == 1
        assert issues[0]["line"] == 2


# ---------------------------------------------------------------------------
# Existing Dockerfile tests still pass (backward compat)
# ---------------------------------------------------------------------------


class TestDockerfileBackwardCompat:
    def test_missing_from_still_fails(self, tmp_path):
        rel = _write_file(
            tmp_path, "Dockerfile",
            "WORKDIR /app\nCMD [\"python\"]\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is False
        assert "FROM" in result.error

    def test_no_entrypoint_warning_still_works(self, tmp_path):
        rel = _write_file(
            tmp_path, "Dockerfile",
            "FROM python:3.11\nWORKDIR /app\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.contract_compliance == pytest.approx(0.8)
        assert any(
            (isinstance(i, str) and "CMD" in i)
            for i in result.semantic_issues
        )
