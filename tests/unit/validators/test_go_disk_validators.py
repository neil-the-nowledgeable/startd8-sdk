"""Tests for Go disk validators in forward_manifest_validator.py (Phase G1)."""

import pytest
from startd8.forward_manifest_validator import (
    _validate_go_file,
    DiskComplianceResult,
)


VALID_GO = """\
package main

import "fmt"

func main() {
    fmt.Println("hello")
}
"""

INVALID_GO_PYTHON = """\
def hello():
    print("hello")
"""

NO_PACKAGE_GO = """\
import "fmt"

func main() {
    fmt.Println("hello")
}
"""

NO_DECL_GO = """\
package main

// just a comment, no declarations
"""

UNBALANCED_GO = """\
package main

func main() {
    fmt.Println("hello")
"""


class TestValidateGoFile:

    def _make_result(self):
        return DiskComplianceResult(file_path="main.go")

    def test_valid_go(self):
        result = _validate_go_file(VALID_GO, self._make_result())
        assert result.error is None or result.error == ""
        assert result.contract_compliance >= 0.7

    def test_python_fingerprint_rejected(self):
        result = _validate_go_file(INVALID_GO_PYTHON, self._make_result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0
        assert "fingerprint" in (result.error or "").lower()

    def test_missing_package_warning(self):
        result = _validate_go_file(NO_PACKAGE_GO, self._make_result())
        assert any(
            "missing package" in str(issue).lower()
            for issue in result.semantic_issues
        )

    def test_no_declaration_warning(self):
        result = _validate_go_file(NO_DECL_GO, self._make_result())
        assert any(
            "no func/type/var/const" in str(issue).lower()
            for issue in result.semantic_issues
        )

    def test_unbalanced_braces(self):
        result = _validate_go_file(UNBALANCED_GO, self._make_result())
        assert result.ast_valid is False
        assert "brace" in (result.error or "").lower()

    def test_semantic_issues_populated(self):
        """Go semantic checks (e.g., fmt.Println in service) populate semantic_issues."""
        source = (
            "package server\n\n"
            'import "fmt"\n\n'
            'func handle() { fmt.Println("debug") }\n'
        )
        result = _validate_go_file(source, self._make_result())
        cats = [i.get("category") for i in result.semantic_issues]
        assert "fmt_println_in_service" in cats
