"""Tests for non-Python file validators in forward_manifest_validator.

Covers REQ-MLT-400 (language mismatch detection), REQ-MLT-200 (go.mod
validation), and REQ-MLT-300 (HTML validation).
"""

import pytest

from startd8.forward_manifest_validator import (
    DiskComplianceResult,
    _detect_language_mismatch,
    _validate_go_mod,
    _validate_html_file,
)


# ---------------------------------------------------------------------------
# REQ-MLT-400: Language mismatch detection
# ---------------------------------------------------------------------------


class TestLanguageMismatchDetection:
    """Test _detect_language_mismatch universal first-pass."""

    def test_mismatch_python_future_in_html(self):
        content = "from __future__ import annotations\n"
        result = _detect_language_mismatch(content, "/tmp/index.html")
        assert result is not None
        assert "python_content_in_html" in result

    def test_mismatch_python_future_in_go_mod(self):
        content = "from __future__ import annotations\n"
        result = _detect_language_mismatch(content, "/tmp/go.mod")
        assert result is not None
        assert "python_content_in_" in result

    def test_mismatch_python_import_in_go(self):
        content = "import os\nimport sys\n"
        # .go extension is excluded from the Python import check
        result = _detect_language_mismatch(content, "/tmp/main.go")
        # .go files are excluded from the first-code-line import check
        # but `from __future__` would still trigger — `import os` alone won't
        assert result is None

    def test_mismatch_python_import_in_html(self):
        content = "import os\nimport sys\n"
        result = _detect_language_mismatch(content, "/tmp/index.html")
        assert result is not None
        assert "python_content_in_html" in result

    def test_mismatch_python_def_in_json(self):
        content = "def hello():\n    pass\n"
        result = _detect_language_mismatch(content, "/tmp/config.json")
        assert result is not None
        assert "python_content_in_json" in result

    def test_mismatch_python_class_in_yaml(self):
        content = "class MyClass:\n    pass\n"
        result = _detect_language_mismatch(content, "/tmp/config.yaml")
        assert result is not None
        assert "python_content_in_yaml" in result

    def test_mismatch_go_package_main_in_html(self):
        content = "package main\n\nfunc main() {}\n"
        result = _detect_language_mismatch(content, "/tmp/index.html")
        assert result is not None
        assert "go_content_in_html" in result

    def test_no_mismatch_valid_html(self):
        content = "<html><body>Hello</body></html>"
        result = _detect_language_mismatch(content, "/tmp/index.html")
        assert result is None

    def test_no_mismatch_valid_go_mod(self):
        content = "module example.com\ngo 1.22\n"
        result = _detect_language_mismatch(content, "/tmp/go.mod")
        assert result is None

    def test_no_mismatch_valid_dockerfile(self):
        content = "FROM golang:1.22\nRUN go build\n"
        result = _detect_language_mismatch(content, "/tmp/Dockerfile")
        assert result is None

    def test_no_mismatch_python_file(self):
        content = "from __future__ import annotations\nimport os\n"
        result = _detect_language_mismatch(content, "/tmp/app.py")
        assert result is None


# ---------------------------------------------------------------------------
# REQ-MLT-200: go.mod validator
# ---------------------------------------------------------------------------


class TestGoModValidator:
    """Test _validate_go_mod."""

    def _make_result(self) -> DiskComplianceResult:
        return DiskComplianceResult(file_path="go.mod")

    def test_go_mod_valid(self):
        content = "module example.com/foo\n\ngo 1.22\n"
        result = _validate_go_mod(content, self._make_result())
        assert result.ast_valid is True
        assert result.contract_compliance == 1.0
        assert result.error is None

    def test_go_mod_missing_module(self):
        content = "go 1.22\n"
        result = _validate_go_mod(content, self._make_result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0
        assert result.error == "missing module directive"

    def test_go_mod_missing_go_version(self):
        content = "module example.com/foo\n"
        result = _validate_go_mod(content, self._make_result())
        assert result.ast_valid is True
        assert result.contract_compliance == 0.5

    def test_go_mod_with_require_block(self):
        content = (
            "module example.com/foo\n\n"
            "go 1.22\n\n"
            "require (\n"
            "\tgithub.com/gin-gonic/gin v1.9.1\n"
            "\tgithub.com/stretchr/testify v1.8.4\n"
            ")\n"
        )
        result = _validate_go_mod(content, self._make_result())
        assert result.ast_valid is True
        assert result.contract_compliance == 1.0
        assert not result.semantic_issues

    def test_go_mod_with_comments(self):
        content = (
            "// This is the main module\n"
            "module example.com/foo\n\n"
            "go 1.22\n"
        )
        result = _validate_go_mod(content, self._make_result())
        assert result.ast_valid is True
        assert result.contract_compliance == 1.0

    def test_go_mod_invalid_require_entry(self):
        content = (
            "module example.com/foo\n\n"
            "go 1.22\n\n"
            "require (\n"
            "\tnot a valid entry\n"
            ")\n"
        )
        result = _validate_go_mod(content, self._make_result())
        assert result.ast_valid is True
        # Invalid require entries are warnings, not errors
        assert any(
            issue.get("category") == "go_mod_require"
            for issue in result.semantic_issues
            if isinstance(issue, dict)
        )

    def test_go_mod_invalid_module_path(self):
        content = "module some path with spaces\n\ngo 1.22\n"
        result = _validate_go_mod(content, self._make_result())
        assert any(
            issue.get("category") == "go_mod_module_path"
            for issue in result.semantic_issues
            if isinstance(issue, dict)
        )


# ---------------------------------------------------------------------------
# REQ-MLT-300: HTML validator
# ---------------------------------------------------------------------------


class TestHtmlValidator:
    """Test _validate_html_file."""

    def _make_result(self) -> DiskComplianceResult:
        return DiskComplianceResult(file_path="index.html")

    def test_html_valid_basic(self):
        content = "<html><body>Hello</body></html>"
        result = _validate_html_file(content, self._make_result())
        assert result.ast_valid is True
        assert result.contract_compliance == 1.0

    def test_html_valid_go_template(self):
        content = '{{define "home"}}<h1>Home</h1>{{end}}'
        result = _validate_html_file(content, self._make_result())
        assert result.ast_valid is True
        assert result.contract_compliance == 1.0

    def test_html_empty(self):
        content = ""
        result = _validate_html_file(content, self._make_result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0

    def test_html_whitespace_only(self):
        content = "   \n   \n"
        result = _validate_html_file(content, self._make_result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0

    def test_html_no_html_content(self):
        content = "just plain text\nnothing special here"
        result = _validate_html_file(content, self._make_result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0
        assert result.error == "no_html_content"

    def test_html_unbalanced_template(self):
        content = '{{define "x"}}content {{ .Name }'
        result = _validate_html_file(content, self._make_result())
        assert result.ast_valid is True
        assert result.contract_compliance == 0.8
        assert any(
            issue.get("category") == "html_template_balance"
            for issue in result.semantic_issues
            if isinstance(issue, dict)
        )

    def test_html_with_jinja(self):
        content = "{% block content %}<p>Hello</p>{% endblock %}"
        result = _validate_html_file(content, self._make_result())
        assert result.ast_valid is True
        assert result.contract_compliance == 1.0

    def test_html_with_doctype(self):
        content = "<!DOCTYPE html>\n<html><head></head><body></body></html>"
        result = _validate_html_file(content, self._make_result())
        assert result.ast_valid is True
        assert result.contract_compliance == 1.0
